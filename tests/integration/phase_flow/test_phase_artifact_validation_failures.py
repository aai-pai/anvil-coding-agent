"""Integration tests: artifact validation failures across phase outputs.

Slice 6 (spec FR-SV-009, FR-AR-001/002; plan §2.6). Exercises the validator over
several phase contracts with controlled defects, confirming deterministic
failures and audit emission.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS
from anvil_runtime.state.event_bus import EventBus

GOOD_ARCH = """---
type: Architecture
title: Architecture — test
artifactId: architecture-v1
phase: architecture
generatedAt: 2026-05-31T00:00:00Z
derivedFrom: [docs/spec.md]
---
# Architecture

## Components
The components.
"""


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


def test_valid_then_invalid_are_deterministic(workspace: pathlib.Path) -> None:
    validator = ArtifactValidator(workspace_root=str(workspace))
    arch = workspace / "docs" / "architecture.md"
    arch.write_text(GOOD_ARCH, encoding="utf-8")

    contract = PHASE_CONTRACTS["architecture"]
    first = validator.validate("architecture", contract.allowed_outputs)
    second = validator.validate("architecture", contract.allowed_outputs)
    assert first.valid is True
    assert first.model_dump() == second.model_dump()  # deterministic

    # Corrupt the section heading -> deterministic failure.
    arch.write_text(GOOD_ARCH.replace("## Components", "## Parts"), encoding="utf-8")
    failed = validator.validate("architecture", contract.allowed_outputs)
    assert failed.valid is False
    assert any(i.kind == "section" for i in failed.issues)


def test_validation_failure_is_audited(workspace: pathlib.Path) -> None:
    bus = EventBus(str(workspace))
    validator = ArtifactValidator(workspace_root=str(workspace), event_bus=bus, run_id="r1")
    # No file written -> missing artifact.
    result = validator.validate("blueprint", ["docs/blueprint.md"])
    assert result.valid is False
    failures = [e for e in bus.read_all() if e.eventType == "ArtifactValidationFailed"]
    assert failures and failures[0].phase == "blueprint"


def test_multiple_phase_documents(workspace: pathlib.Path) -> None:
    validator = ArtifactValidator(workspace_root=str(workspace))
    # packaging/documentation/deployment require metadata but no sections.
    for phase, path in [
        ("packaging", "docs/packaging-plan.md"),
        ("deployment", "docs/deployment-plan.md"),
    ]:
        (workspace / path).write_text(
            f"---\ntype: Plan\ntitle: {phase} plan\n"
            f"artifactId: {phase}-v1\nphase: {phase}\ngeneratedAt: t\n"
            f"derivedFrom: [docs/architecture.md]\n---\n# {phase}\nbody\n",
            encoding="utf-8",
        )
        assert validator.validate(phase, [path]).valid is True
