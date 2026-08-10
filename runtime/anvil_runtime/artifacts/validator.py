"""Deterministic artifact validation.

Slice 6 deliverable (blueprint §3.1; spec FR-SV-009, FR-AR-001/002/005).
Validates that a phase's required outputs exist and conform to their schema:
the canonical document exists and is non-empty, carries a valid metadata header
(FR-AR-005) when required, and contains the schema's required section headings.
Validation is deterministic pass/fail — no warnings or soft errors (FR-AR-002) —
and emits ``ArtifactValidationFailed`` on any issue.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from anvil_runtime.artifacts.metadata import (
    split_front_matter,
    validate_metadata,
)
from anvil_runtime.artifacts.schemas import ARTIFACT_SCHEMAS, ArtifactSchema
from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.state.event_bus import EventBus


class ArtifactIssue(BaseModel):
    """A single deterministic validation failure."""

    path: str
    kind: str  # "missing" | "empty" | "metadata" | "section" | "contract"
    detail: str


class ArtifactValidationResult(BaseModel):
    """Pass/fail outcome of validating a phase's artifacts."""

    phase: str
    valid: bool
    issues: list[ArtifactIssue] = Field(default_factory=list)


class ArtifactValidator:
    """Validates phase artifacts against schema and structure requirements."""

    def __init__(
        self,
        workspace_root: str | pathlib.Path = ".",
        schemas: dict[str, ArtifactSchema] | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = pathlib.Path(workspace_root)
        self._schemas = schemas if schemas is not None else ARTIFACT_SCHEMAS
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def validate(self, phase_id: str, artifact_paths: list[str]) -> ArtifactValidationResult:
        """Validate the phase's required outputs (FR-SV-009)."""
        issues: list[ArtifactIssue] = []
        schema = self._schemas.get(phase_id)

        if schema is None:
            # Directory-only phase: require each declared output path to exist.
            for rel in artifact_paths:
                if not (self._root / rel).exists():
                    issues.append(ArtifactIssue(
                        path=rel, kind="missing", detail="declared output does not exist"
                    ))
        else:
            issues.extend(self._validate_document(schema))

        # v0.1.3 #21: the generated code is checked mechanically against the
        # task contract's manifest (when one is pinned). Deterministic AST
        # checks, no LLM — violations fail the phase into the retry path.
        if phase_id == "implementation":
            issues.extend(self._validate_contract_manifest())

        result = ArtifactValidationResult(
            phase=phase_id, valid=not issues, issues=issues
        )
        if not result.valid:
            self._emit_failure(result)
        return result

    def _validate_document(self, schema: ArtifactSchema) -> list[ArtifactIssue]:
        issues: list[ArtifactIssue] = []
        target = self._root / schema.path
        if not target.is_file():
            return [ArtifactIssue(
                path=schema.path, kind="missing", detail="required artifact is missing"
            )]
        text = target.read_text(encoding="utf-8")
        if not text.strip():
            return [ArtifactIssue(path=schema.path, kind="empty", detail="artifact is empty")]

        meta, body = split_front_matter(text)
        if schema.require_metadata:
            for problem in validate_metadata(meta):
                issues.append(ArtifactIssue(
                    path=schema.path, kind="metadata", detail=problem
                ))
        # Required sections are checked against heading lines only (not body
        # prose), so a passing mention in paragraph text cannot mask a missing
        # section heading.
        headings = "\n".join(
            line for line in body.splitlines() if line.lstrip().startswith("#")
        ).lower()
        for heading in schema.required_sections:
            if heading.lower() not in headings:
                issues.append(ArtifactIssue(
                    path=schema.path, kind="section",
                    detail=f"missing required section '{heading}'",
                ))
        return issues

    def _validate_contract_manifest(self) -> list[ArtifactIssue]:
        """Check ``src/`` against the contract's manifest (#21), if any.

        A prose-only contract (or no contract at all) validates as today; a
        malformed manifest fence fails loudly rather than silently skipping
        the mechanical check.
        """
        from anvil_runtime.contract import (
            DOMAIN_KNOWLEDGE_REL,
            parse_contract_manifest,
            resolve_contract,
            validate_manifest,
        )

        resolved = resolve_contract(self._root)
        if not resolved.present:
            return []
        manifest, error = parse_contract_manifest(resolved.text)
        if error is not None:
            return [ArtifactIssue(
                path=DOMAIN_KNOWLEDGE_REL, kind="contract", detail=error
            )]
        if manifest is None:
            return []
        return [
            ArtifactIssue(path="src/", kind="contract", detail=violation)
            for violation in validate_manifest(manifest, self._root / "src")
        ]

    def _emit_failure(self, result: ArtifactValidationResult) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType="ArtifactValidationFailed",
            runId=self._run_id, phase=result.phase, severity="error",
            data={"issues": [i.model_dump() for i in result.issues]},
        ))


__all__ = ["ArtifactValidator", "ArtifactValidationResult", "ArtifactIssue"]
