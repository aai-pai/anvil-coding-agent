"""E2E: major drift triggers rollback and re-execution.

Slice 6 (spec §2.5, FR-DR-006; blueprint §7.3; plan §2.6). A completed run is
checked for drift; a major finding routes to rollback + re-execute, the
supervisor rolls back the offending phase and its downstream, and the run
re-completes.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import OverrideRequest, RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.drift.checker import DriftChecker, DriftContext
from anvil_runtime.drift.remediation import DriftRemediator
from anvil_runtime.state.event_bus import EventBus


def test_major_drift_rolls_back_and_reexecutes(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    manager = DevelopmentManager(workspace_root=str(tmp_path), event_bus=bus)

    # 1. Run to completion (YOLO: no gates).
    started = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")
    )
    progress = manager.run_until_pause(started.run_id)
    assert progress.status == "completed"
    assert len(progress.completed_phases) == 12

    # 2. Drift check finds a missing blueprint module (major).
    report = DriftChecker(event_bus=bus, run_id=started.run_id).check(
        "implementation",
        DriftContext(blueprint_modules=["mod_a", "mod_b"], code_modules=["mod_a"]),
    )
    assert report.highest_severity == "major"

    # 3. Remediation routes major drift to rollback + re-execute (FR-DR-006).
    plan = DriftRemediator().plan(report, attempt=1)
    assert plan.action == "rollback-reexecute"

    # 4. User signals rollback (FR-SV-020); the supervisor rolls back the
    #    implementation phase and its downstream and resumes the run.
    override = manager.apply_override(
        started.run_id,
        OverrideRequest(
            action="rollback", targetPhase="implementation",
            reason=plan.detail, requesterId="e2e",
        ),
    )
    assert override.action == "rollback"
    after_rollback = manager.get_progress(started.run_id)
    assert "implementation" not in after_rollback.completed_phases
    assert "qa" not in after_rollback.completed_phases

    # 5. Re-execution re-completes the run.
    final = manager.run_until_pause(started.run_id)
    assert final.status == "completed"
    assert len(final.completed_phases) == 12

    types = {e.eventType for e in bus.read_all()}
    assert "DriftCheckResult" in types
    assert "Rollback" in types
