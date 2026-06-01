"""Unit tests for the development manager. Slice 2 (spec §2.1)."""

from __future__ import annotations

import pathlib

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.agents.factory import PhaseAgentFactory
from anvil_runtime.api.models import OverrideRequest, RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import (
    PHASE_IDS,
    PhaseCompleteEvent,
    PhaseInvocationPayload,
)
from anvil_runtime.core.retry_controller import RetryController


def _manager(tmp_path: pathlib.Path) -> DevelopmentManager:
    return DevelopmentManager(workspace_root=str(tmp_path))


class _FailingProposalAgent(BasePhaseAgent):
    phase_id = "proposal"

    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        return PhaseCompleteEvent(
            phase_name="proposal", status="failure", duration_ms=0,
            failure_reason="boom",
        )


def test_yolo_run_completes_all_phases(tmp_path: pathlib.Path) -> None:
    mgr = _manager(tmp_path)
    started = mgr.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = mgr.run_until_pause(started.run_id)
    assert progress.status == "completed"
    assert progress.completed_phases == list(PHASE_IDS)
    assert progress.pending_approval_gate is None


def test_run_persists_checkpoints_and_events(tmp_path: pathlib.Path) -> None:
    mgr = _manager(tmp_path)
    started = mgr.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    mgr.run_until_pause(started.run_id)
    assert (tmp_path / ".anvil" / "run-state.json").exists()
    assert (tmp_path / "logs" / "events.jsonl").exists()
    assert (tmp_path / "logs" / "run-summary.log").exists()


def test_dispatch_phase_blocks_when_prerequisites_incomplete(tmp_path: pathlib.Path) -> None:
    mgr = _manager(tmp_path)
    started = mgr.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    # architecture cannot run before its predecessors.
    result = mgr.dispatch_phase(started.run_id, "architecture")
    assert result.status == "blocked"


def test_rollback_invalidates_phase_and_downstream(tmp_path: pathlib.Path) -> None:
    mgr = _manager(tmp_path)
    started = mgr.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    mgr.run_until_pause(started.run_id)
    plan = mgr.rollback(started.run_id, "architecture", reason="major drift")
    assert plan.target_phase == "architecture"
    assert "blueprint" in plan.invalidated_phases
    progress = mgr.get_progress(started.run_id)
    assert "architecture" not in progress.completed_phases
    assert "proposal" in progress.completed_phases


def test_override_stop_marks_run_stopped(tmp_path: pathlib.Path) -> None:
    mgr = _manager(tmp_path)
    started = mgr.start_run(RunStartRequest(mode="secure", security_profile="restricted"))
    mgr.run_until_pause(started.run_id)  # pauses at post-proposal
    result = mgr.apply_override(
        started.run_id, OverrideRequest(action="stop", reason="halt", requesterId="u")
    )
    assert result.action == "stop"
    assert mgr.get_progress(started.run_id).status == "stopped"


def test_failing_phase_escalates_after_retry_budget(tmp_path: pathlib.Path) -> None:
    # Override only the proposal agent with one that always fails.
    factory = PhaseAgentFactory()
    factory._classes["proposal"] = _FailingProposalAgent  # noqa: SLF001
    mgr = DevelopmentManager(
        workspace_root=str(tmp_path),
        factory=factory,
        retry_controller=RetryController(max_retries_per_phase=2),
    )
    started = mgr.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = mgr.run_until_pause(started.run_id)
    assert progress.status == "escalated"
    assert progress.current_phase == "proposal"
    assert progress.completed_phases == []
    # A critical PhaseEscalation event was emitted.
    events = mgr._events.read_all()  # noqa: SLF001
    escalations = [e for e in events if e.eventType == "PhaseEscalation"]
    assert len(escalations) == 1
    assert escalations[0].severity == "critical"
    assert escalations[0].data["attempts"] == 3  # initial + 2 retries
