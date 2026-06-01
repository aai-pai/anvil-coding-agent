"""Specialist role registry: loading, validation, and bounded dispatch.

Slice 6 deliverable (blueprint §3.1, §4.2; spec §2.10, FR-SA-001..012). Loads
optional specialist-role definitions from user-root and workspace registries
(workspace overrides user-root by ``roleId``, FR-SA-001), validates them against
the role schema (FR-SA-002/003/004), and dispatches them only within their
declared invocation phases and output boundaries (FR-SA-005/007). When no
registry is present the system is unaffected (backward-compatible).
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, Field

from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS, PHASE_IDS, EventEnvelope
from anvil_runtime.state.event_bus import EventBus

ROLE_SCHEMA_VERSION = "0.1.0"

# Supervisor-/phase-owned paths a specialist must never write (FR-SA-007), except
# for explicitly supplemental prefixes.
_DIR_PROTECTED_PREFIXES: tuple[str, ...] = ("src/", "tests/", ".anvil/", "logs/")
SUPPLEMENTAL_ALLOWED_PREFIXES: tuple[str, ...] = ("docs/reviews/",)
# Canonical phase document outputs are protected too.
_CANONICAL_OUTPUTS: frozenset[str] = frozenset(
    out
    for contract in PHASE_CONTRACTS.values()
    for out in contract.allowed_outputs
    if not out.endswith("/")
)


class SpecialistRole(BaseModel):
    """A bounded, contract-driven specialist role (FR-SA-002)."""

    roleId: str
    rolePurpose: str
    allowedPhases: list[str] = Field(default_factory=list)
    requiredInputs: list[str] = Field(default_factory=list)
    declaredOutputs: list[str] = Field(default_factory=list)
    allowedTools: list[str] = Field(default_factory=list)
    modelConstraints: list[str] = Field(default_factory=list)
    completionCriteria: str = ""
    roleSchemaVersion: str = ROLE_SCHEMA_VERSION


class SpecialistRegistryModel(BaseModel):
    """The merged, validated set of specialist roles."""

    roleSchemaVersion: str = ROLE_SCHEMA_VERSION
    roles: list[SpecialistRole] = Field(default_factory=list)


class SpecialistInvocationContext(BaseModel):
    """Context for a single specialist invocation."""

    phase: str
    inputs: list[str] = Field(default_factory=list)
    approval_context: str | None = None


class SpecialistResult(BaseModel):
    """Structured result of a specialist invocation (FR-SA-012)."""

    role_id: str
    status: Literal["success", "blocked"]
    output_paths: list[str] = Field(default_factory=list)
    reason: str | None = None


SPECIALIST_ROLE_SCHEMA: dict[str, object] = SpecialistRole.model_json_schema()

SpecialistSource = tuple[str, pathlib.Path]  # ("workspace"|"user", yaml path)


class SpecialistRegistry:
    """Loads, validates, and dispatches specialist roles."""

    def __init__(
        self,
        sources: list[SpecialistSource] | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # ``sources`` ordered highest-precedence first (workspace before user).
        self._sources = sources or []
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # -- loading ----------------------------------------------------------

    def load(self) -> SpecialistRegistryModel:
        """Merge registries by precedence and keep only valid roles (FR-SA-001/003)."""
        merged: dict[str, SpecialistRole] = {}
        for source, path in self._sources:
            for role in self._read_roles(path):
                # First writer wins (sources are highest-precedence first).
                if role.roleId in merged:
                    continue
                errors = self.validate_role(role)
                if errors:
                    self._emit("SpecialistRoleRejected", severity="error", data={
                        "roleId": role.roleId, "source": source, "errors": errors,
                    })
                    continue
                merged[role.roleId] = role
        return SpecialistRegistryModel(roles=list(merged.values()))

    @staticmethod
    def _read_roles(path: pathlib.Path) -> list[SpecialistRole]:
        if not path.is_file():
            return []
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = payload.get("roles", []) if isinstance(payload, dict) else []
        roles: list[SpecialistRole] = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    roles.append(SpecialistRole.model_validate(item))
                except Exception:  # noqa: BLE001 - malformed role; skip with no crash
                    continue
        return roles

    # -- validation -------------------------------------------------------

    def validate_role(self, role: SpecialistRole) -> list[str]:
        """Return validation errors (empty == valid) for a role (FR-SA-002/003/004)."""
        errors: list[str] = []
        if not role.roleId:
            errors.append("missing roleId")
        if not role.rolePurpose:
            errors.append("missing rolePurpose")
        if not role.allowedPhases:
            errors.append("allowedPhases must be non-empty")
        for phase in role.allowedPhases:
            if phase not in PHASE_IDS:
                errors.append(f"invalid phase reference '{phase}'")
        if role.roleSchemaVersion != ROLE_SCHEMA_VERSION:
            errors.append(
                f"incompatible roleSchemaVersion '{role.roleSchemaVersion}' "
                f"(expected '{ROLE_SCHEMA_VERSION}')"
            )
        for out in role.declaredOutputs:
            if self._is_protected_output(out):
                errors.append(f"declaredOutput '{out}' writes a protected path")
        return errors

    @staticmethod
    def _is_protected_output(path: str) -> bool:
        if any(path.startswith(prefix) for prefix in SUPPLEMENTAL_ALLOWED_PREFIXES):
            return False
        if path in _CANONICAL_OUTPUTS:
            return True
        return any(path.startswith(prefix) for prefix in _DIR_PROTECTED_PREFIXES)

    # -- dispatch ---------------------------------------------------------

    def invoke(
        self, role_id: str, context: SpecialistInvocationContext
    ) -> SpecialistResult:
        """Invoke a role within its declared boundaries (FR-SA-005/006/007)."""
        role = self._find(role_id)
        if role is None:
            return self._blocked(role_id, "unknown specialist role")

        if context.phase not in role.allowedPhases:
            self._emit("SpecialistInvocationBlocked", severity="warning", data={
                "roleId": role_id, "phase": context.phase, "reason": "phase not allowed",
            })
            return self._blocked(
                role_id, f"role '{role_id}' may not be invoked in phase '{context.phase}'"
            )

        protected = [o for o in role.declaredOutputs if self._is_protected_output(o)]
        if protected:
            self._emit("SpecialistInvocationBlocked", severity="error", data={
                "roleId": role_id, "protected_outputs": protected,
            })
            return self._blocked(
                role_id, f"declared outputs write protected paths: {protected}"
            )

        self._emit("SpecialistCompleted", data={
            "roleId": role_id, "phase": context.phase,
            "output_paths": role.declaredOutputs,
        })
        return SpecialistResult(
            role_id=role_id, status="success", output_paths=list(role.declaredOutputs)
        )

    def _find(self, role_id: str) -> SpecialistRole | None:
        for role in self.load().roles:
            if role.roleId == role_id:
                return role
        return None

    @staticmethod
    def _blocked(role_id: str, reason: str) -> SpecialistResult:
        return SpecialistResult(role_id=role_id, status="blocked", reason=reason)

    def _emit(self, event_type: str, severity: str = "info", data: dict | None = None) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=self._run_id,
            phase="", severity=severity, data=data or {},
        ))


__all__ = [
    "SpecialistRegistry",
    "SpecialistRole",
    "SpecialistRegistryModel",
    "SpecialistInvocationContext",
    "SpecialistResult",
    "SPECIALIST_ROLE_SCHEMA",
    "ROLE_SCHEMA_VERSION",
]
