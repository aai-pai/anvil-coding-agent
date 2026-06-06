"""E2E: a fresh manager instance resumes a run from the last completed phase.

Slice 2 (spec FR-SV-022/023). Simulates a runtime restart: a new
DevelopmentManager reads the persisted run state and continues to completion.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PHASE_IDS


def test_resume_after_simulated_restart(tmp_path: pathlib.Path) -> None:
    # --- first process: run the first three phases, then "crash" ---
    mgr1 = DevelopmentManager(workspace_root=str(tmp_path))
    started = mgr1.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    run_id = started.run_id
    for phase in ("proposal", "factory-init", "specification"):
        result = mgr1.dispatch_phase(run_id, phase)
        assert result.status == "success"

    # --- second process: brand-new manager over the same workspace ---
    mgr2 = DevelopmentManager(workspace_root=str(tmp_path))
    plan = mgr2.resume_run(run_id)
    assert plan.resume_from == "architecture"
    assert set(plan.skipped_phases) == {"proposal", "factory-init", "specification"}
    assert plan.invalidated_phases == []

    # Emitted a ResumeFromCheckpoint event (FR-SV-023).
    events = mgr2._events.read_all()  # noqa: SLF001 (test introspection)
    assert any(e.eventType == "ResumeFromCheckpoint" for e in events)

    # Continue to completion from the checkpoint.
    progress = mgr2.run_until_pause(run_id)
    assert progress.status == "completed"
    assert progress.completed_phases == list(PHASE_IDS)
