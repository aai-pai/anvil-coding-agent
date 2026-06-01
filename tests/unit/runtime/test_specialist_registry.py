"""Unit tests: specialist role registry loading, validation, and dispatch.

Slice 6 (spec §2.10, FR-SA-001..007; plan §2.6). Verifies precedence merge,
schema validation, protected-path enforcement, and bounded invocation.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from anvil_runtime.agents.specialist_registry import (
    ROLE_SCHEMA_VERSION,
    SpecialistInvocationContext,
    SpecialistRegistry,
    SpecialistRole,
)


def _write_registry(path: pathlib.Path, roles: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"roles": roles}), encoding="utf-8")


def _role(**overrides) -> dict:
    base = {
        "roleId": "reviewer",
        "rolePurpose": "review code",
        "allowedPhases": ["qa"],
        "declaredOutputs": ["docs/reviews/review.md"],
        "roleSchemaVersion": ROLE_SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


def test_no_registry_is_backward_compatible() -> None:
    registry = SpecialistRegistry(sources=[])
    assert registry.load().roles == []


def test_workspace_overrides_user_by_role_id(tmp_path: pathlib.Path) -> None:
    ws = tmp_path / "workspace.yaml"
    user = tmp_path / "user.yaml"
    _write_registry(ws, [_role(rolePurpose="workspace review")])
    _write_registry(user, [_role(rolePurpose="user review")])
    registry = SpecialistRegistry(sources=[("workspace", ws), ("user", user)])
    roles = registry.load().roles
    assert len(roles) == 1
    assert roles[0].rolePurpose == "workspace review"


def test_validate_role_catches_errors() -> None:
    registry = SpecialistRegistry()
    bad = SpecialistRole(
        roleId="x", rolePurpose="", allowedPhases=["nope"],
        declaredOutputs=["src/thing.py"], roleSchemaVersion="9.9.9",
    )
    errors = registry.validate_role(bad)
    joined = " ".join(errors)
    assert "rolePurpose" in joined
    assert "invalid phase reference 'nope'" in joined
    assert "protected path" in joined
    assert "incompatible roleSchemaVersion" in joined


def test_invalid_roles_are_dropped_on_load(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "roles.yaml"
    _write_registry(path, [_role(), _role(roleId="bad", allowedPhases=["nope"])])
    registry = SpecialistRegistry(sources=[("workspace", path)])
    ids = {r.roleId for r in registry.load().roles}
    assert ids == {"reviewer"}


def test_invoke_blocked_outside_allowed_phase(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "roles.yaml"
    _write_registry(path, [_role(allowedPhases=["qa"])])
    registry = SpecialistRegistry(sources=[("workspace", path)])
    result = registry.invoke("reviewer", SpecialistInvocationContext(phase="implementation"))
    assert result.status == "blocked"
    assert "may not be invoked" in (result.reason or "")


def test_invoke_succeeds_within_boundaries(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "roles.yaml"
    _write_registry(path, [_role(allowedPhases=["qa"])])
    registry = SpecialistRegistry(sources=[("workspace", path)])
    result = registry.invoke("reviewer", SpecialistInvocationContext(phase="qa"))
    assert result.status == "success"
    assert result.output_paths == ["docs/reviews/review.md"]


def test_invoke_unknown_role_blocked() -> None:
    assert SpecialistRegistry().invoke(
        "ghost", SpecialistInvocationContext(phase="qa")
    ).status == "blocked"
