"""Unit tests: mechanical contract validation in the artifact validator (#21).

Post-implementation, generated ``src/`` is AST-checked against the contract's
``contract-manifest``: every pinned file must exist and every pinned symbol
must exist with an unchanged signature. Violations name the offender, emit
``ArtifactValidationFailed``, and fail the phase into the normal retry path
— never a silent warning. A prose-only contract (or none) validates as today.
"""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent
from anvil_runtime.state.event_bus import EventBus

CONTRACT_WITH_MANIFEST = textwrap.dedent("""\
    # Task

    <!-- anvil:contract -->
    Pinned interface below.

    ```contract-manifest
    {"files": ["counter.py"],
     "symbols": [{"qualname": "count_issues",
                  "signature": "def count_issues(text) -> dict",
                  "file": "counter.py"}]}
    ```
    <!-- anvil:context -->
    prose
    """)

CONFORMING_SRC = "def count_issues(text) -> dict:\n    return {}\n"


def _stage(tmp_path: pathlib.Path, domain: str, src: dict[str, str]) -> None:
    target = tmp_path / "domain-knowledge" / "background-information.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(domain, encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    for rel, content in src.items():
        (tmp_path / "src" / rel).write_text(content, encoding="utf-8")


def test_conforming_src_passes(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path, CONTRACT_WITH_MANIFEST, {"counter.py": CONFORMING_SRC})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is True


def test_missing_file_fails_with_offender_named(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path, CONTRACT_WITH_MANIFEST, {})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is False
    details = [i.detail for i in result.issues if i.kind == "contract"]
    assert any("missing file: counter.py" in d for d in details)


def test_missing_symbol_fails_with_offender_named(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path, CONTRACT_WITH_MANIFEST, {"counter.py": "OTHER = 1\n"})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is False
    details = [i.detail for i in result.issues if i.kind == "contract"]
    assert any("missing symbol: count_issues" in d for d in details)


def test_changed_signature_fails_with_offender_named(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path, CONTRACT_WITH_MANIFEST,
           {"counter.py": "def count_issues(text) -> bool:\n    return True\n"})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is False
    details = [i.detail for i in result.issues if i.kind == "contract"]
    assert any("changed signature: count_issues" in d for d in details)


def test_absent_manifest_validates_as_today(tmp_path: pathlib.Path) -> None:
    prose_only = CONTRACT_WITH_MANIFEST.split("```contract-manifest")[0] \
        + "<!-- anvil:context -->\nprose\n"
    _stage(tmp_path, prose_only, {})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is True


def test_malformed_manifest_fails_loudly(tmp_path: pathlib.Path) -> None:
    broken = CONTRACT_WITH_MANIFEST.replace('{"files"', '{oops "files"')
    _stage(tmp_path, broken, {"counter.py": CONFORMING_SRC})
    result = ArtifactValidator(tmp_path).validate("implementation", ["src/"])
    assert result.valid is False
    assert any("JSON" in i.detail for i in result.issues)


def test_only_the_implementation_phase_is_checked(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path, CONTRACT_WITH_MANIFEST, {})  # violations exist in src/
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "phase-summary-log.md").write_text("log\n", encoding="utf-8")
    result = ArtifactValidator(tmp_path).validate(
        "cleanup", ["docs/phase-summary-log.md"])
    assert result.valid is True


class _SucceedingExecutor:
    """Fake executor: the phase agent 'succeeds' without writing anything."""

    def run(self, agent, payload) -> PhaseCompleteEvent:  # noqa: ANN001
        return PhaseCompleteEvent(
            phase_name=payload.phase_name, status="success",
            artifact_paths=["src/"], duration_ms=0,
        )


def test_violation_enters_the_retry_path(tmp_path: pathlib.Path) -> None:
    """FR posture: a manifest violation is a phase FAILURE (retried, recorded),
    not a silent warning."""
    _stage(tmp_path, CONTRACT_WITH_MANIFEST, {"counter.py": "OTHER = 1\n"})
    bus = EventBus(str(tmp_path))
    manager = DevelopmentManager(
        workspace_root=str(tmp_path), event_bus=bus,
        executor=_SucceedingExecutor(),
        artifact_validator=ArtifactValidator(tmp_path, event_bus=bus),
    )
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    # Make the implementation phase the next ready one.
    ctx = manager._runs[run_id]
    ctx.completed = {"intake", "proposal", "factory-init", "specification",
                     "architecture", "blueprint", "dev-plan"}

    result = manager.dispatch_phase(run_id, "implementation")
    assert result.status == "failure"  # first attempt -> retry scheduled
    assert "artifact validation failed" in (result.complete_event.failure_reason or "")
    assert "missing symbol: count_issues" in result.complete_event.failure_reason
    # The validator emits under its own (manager-scoped) bus handle; assert on
    # the persisted audit trail rather than the per-run stream filter.
    log = (tmp_path / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "ArtifactValidationFailed" in log, \
        "ArtifactValidationFailed must reach the audit trail"
