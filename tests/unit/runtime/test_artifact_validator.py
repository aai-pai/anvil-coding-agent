"""Unit tests: deterministic artifact validation.

Slice 6 (spec FR-SV-009, FR-AR-001/002/005; plan §2.6). Uses synthetic artifacts
with controlled errors (blueprint §7.4) to verify pass/fail determinism.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.state.event_bus import EventBus

VALID_PROPOSAL = """---
artifactId: proposal-v1
phase: proposal
generatedAt: 2026-05-31T00:00:00Z
derivedFrom: [domain-knowledge/background-information.md]
---
# Proposal

## Problem Statement
Something.

## Scope
In and out.
"""


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


def _validator(workspace: pathlib.Path) -> ArtifactValidator:
    return ArtifactValidator(workspace_root=str(workspace))


def test_valid_artifact_passes(workspace: pathlib.Path) -> None:
    (workspace / "docs" / "proposal.md").write_text(VALID_PROPOSAL, encoding="utf-8")
    result = _validator(workspace).validate("proposal", ["docs/proposal.md"])
    assert result.valid is True
    assert result.issues == []


def test_missing_artifact_fails(workspace: pathlib.Path) -> None:
    result = _validator(workspace).validate("proposal", ["docs/proposal.md"])
    assert result.valid is False
    assert result.issues[0].kind == "missing"


def test_empty_artifact_fails(workspace: pathlib.Path) -> None:
    (workspace / "docs" / "proposal.md").write_text("   \n", encoding="utf-8")
    result = _validator(workspace).validate("proposal", ["docs/proposal.md"])
    assert any(i.kind == "empty" for i in result.issues)


def test_missing_metadata_fails(workspace: pathlib.Path) -> None:
    (workspace / "docs" / "proposal.md").write_text(
        "# Proposal\n\n## Problem Statement\nx\n\n## Scope\ny\n", encoding="utf-8"
    )
    result = _validator(workspace).validate("proposal", ["docs/proposal.md"])
    assert any(i.kind == "metadata" for i in result.issues)


def test_missing_required_section_fails(workspace: pathlib.Path) -> None:
    no_scope = VALID_PROPOSAL.replace("## Scope\nIn and out.", "")
    (workspace / "docs" / "proposal.md").write_text(no_scope, encoding="utf-8")
    result = _validator(workspace).validate("proposal", ["docs/proposal.md"])
    assert any(i.kind == "section" and "Scope" in i.detail for i in result.issues)


def test_directory_only_phase_checks_existence(workspace: pathlib.Path) -> None:
    validator = _validator(workspace)
    # implementation owns src/ — no document schema; missing dir fails.
    missing = validator.validate("implementation", ["src/"])
    assert missing.valid is False
    (workspace / "src").mkdir()
    present = validator.validate("implementation", ["src/"])
    assert present.valid is True


def test_failure_emits_event(workspace: pathlib.Path) -> None:
    bus = EventBus(str(workspace))
    ArtifactValidator(workspace_root=str(workspace), event_bus=bus, run_id="r1").validate(
        "proposal", ["docs/proposal.md"]
    )
    assert any(e.eventType == "ArtifactValidationFailed" for e in bus.read_all())
