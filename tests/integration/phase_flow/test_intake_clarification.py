"""Integration tests: bounded intake clarification (#15, FR-INT-007..011).

Drives the supervisor with an executor whose intake step emits questions in
question mode and assumptions in assumption mode, asserting: the interactive
pause, the answer write-back, the single-round bound, and that yolo runs never
pause.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent
from anvil_runtime.state.event_bus import EventBus


class _QuestioningExecutor:
    """Intake emits questions (question mode) / assumptions (assumption mode)."""

    def __init__(self) -> None:
        self.intake_modes: list[str] = []

    def run(self, agent, payload):  # noqa: ANN001 - matches executor protocol
        questions: list[str] = []
        assumptions: list[str] = []
        if agent.phase_id == "intake":
            mode = str(payload.phase_context.get("clarification_mode"))
            self.intake_modes.append(mode)
            if mode == "questions":
                questions = ["Persist data?", "Which UI stack?"]
            else:
                assumptions = ["No persistence."]
        return PhaseCompleteEvent(
            phase_name=agent.phase_id,
            status="success",
            artifact_paths=[],
            checksums={},
            duration_ms=0,
            questions=questions,
            assumptions=assumptions,
        )


def _manager(tmp_path: pathlib.Path):
    bus = EventBus(str(tmp_path))
    executor = _QuestioningExecutor()
    manager = DevelopmentManager(
        workspace_root=str(tmp_path), event_bus=bus, executor=executor
    )
    return manager, bus, executor


def test_gated_run_pauses_then_resumes_after_answers(tmp_path: pathlib.Path) -> None:
    manager, bus, executor = _manager(tmp_path)
    started = manager.start_run(RunStartRequest(mode="gated", security_profile="restricted"))
    progress = manager.run_until_pause(started.run_id)

    # FR-INT-007: paused with the intake questions exposed.
    assert progress.status == "awaiting_clarification"
    assert progress.pending_questions == ["Persist data?", "Which UI stack?"]
    assert any(e.eventType == "ClarificationRequired" for e in bus.read_all())

    # FR-INT-008: answers land in the domain-knowledge file; the run resumes.
    manager.submit_clarification(started.run_id, ["Yes, localStorage", "Plain HTML"])
    text = (tmp_path / "domain-knowledge" / "background-information.md").read_text(
        encoding="utf-8"
    )
    assert "## Clarifications" in text
    assert "**Q:** Persist data?" in text
    assert "**A:** Yes, localStorage" in text

    progress = manager.run_until_pause(started.run_id)
    # FR-INT-009: the re-run used assumption mode and can never pause again.
    assert executor.intake_modes == ["questions", "assumptions"]
    assert progress.status == "completed"
    assert any(e.eventType == "ClarificationReceived" for e in bus.read_all())
    assert any(e.eventType == "IntakeAssessed" for e in bus.read_all())


def test_yolo_run_never_pauses_for_clarification(tmp_path: pathlib.Path) -> None:
    manager, _, executor = _manager(tmp_path)
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)
    # FR-INT-010: straight to assumption mode; the run completes unattended.
    assert executor.intake_modes == ["assumptions"]
    assert progress.status == "completed"


def test_clarify_outside_pause_is_rejected(tmp_path: pathlib.Path) -> None:
    manager, _, _ = _manager(tmp_path)
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    manager.run_until_pause(started.run_id)
    with pytest.raises(ValueError):
        manager.submit_clarification(started.run_id, ["answer"])
