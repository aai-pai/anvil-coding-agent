"""Integration tests: specialist invocation boundaries and auditing.

Slice 6 (spec §2.10, FR-SA-005/006/007/011/012; plan §2.6). Confirms a specialist
runs only within declared phases and output boundaries, and that allow/block
decisions are audited.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from anvil_runtime.agents.specialist_registry import (
    ROLE_SCHEMA_VERSION,
    SpecialistInvocationContext,
    SpecialistRegistry,
)
from anvil_runtime.state.event_bus import EventBus


@pytest.fixture()
def registry_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "specialist-roles.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "roles": [
                    {
                        "roleId": "security-reviewer",
                        "rolePurpose": "review security",
                        "allowedPhases": ["qa", "implementation"],
                        "declaredOutputs": ["docs/reviews/security.md"],
                        "allowedTools": ["file.read"],
                        "roleSchemaVersion": ROLE_SCHEMA_VERSION,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_invocation_within_phase_is_audited(tmp_path: pathlib.Path, registry_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    registry = SpecialistRegistry(
        sources=[("workspace", registry_path)], event_bus=bus, run_id="r1"
    )
    result = registry.invoke(
        "security-reviewer", SpecialistInvocationContext(phase="qa")
    )
    assert result.status == "success"
    assert any(e.eventType == "SpecialistCompleted" for e in bus.read_all())


def test_out_of_scope_phase_is_blocked_and_logged(
    tmp_path: pathlib.Path, registry_path: pathlib.Path
) -> None:
    bus = EventBus(str(tmp_path))
    registry = SpecialistRegistry(
        sources=[("workspace", registry_path)], event_bus=bus, run_id="r1"
    )
    result = registry.invoke(
        "security-reviewer", SpecialistInvocationContext(phase="proposal")
    )
    assert result.status == "blocked"
    blocked = [e for e in bus.read_all() if e.eventType == "SpecialistInvocationBlocked"]
    assert blocked and blocked[0].data["phase"] == "proposal"


def test_protected_output_role_is_rejected_on_load(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "roles": [
                    {
                        "roleId": "bad-writer",
                        "rolePurpose": "writes source",
                        "allowedPhases": ["implementation"],
                        "declaredOutputs": ["src/payload.py"],
                        "roleSchemaVersion": ROLE_SCHEMA_VERSION,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bus = EventBus(str(tmp_path))
    registry = SpecialistRegistry(sources=[("workspace", path)], event_bus=bus, run_id="r1")
    assert registry.load().roles == []
    assert any(e.eventType == "SpecialistRoleRejected" for e in bus.read_all())
