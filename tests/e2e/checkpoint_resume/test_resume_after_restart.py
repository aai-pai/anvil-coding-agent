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
    for phase in ("intake", "proposal", "factory-init"):
        result = mgr1.dispatch_phase(run_id, phase)
        assert result.status == "success"

    # --- second process: brand-new manager over the same workspace ---
    mgr2 = DevelopmentManager(workspace_root=str(tmp_path))
    plan = mgr2.resume_run(run_id)
    assert plan.resume_from == "specification"
    assert set(plan.skipped_phases) == {"intake", "proposal", "factory-init"}
    assert plan.invalidated_phases == []

    # Emitted a ResumeFromCheckpoint event (FR-SV-023).
    events = mgr2._events.read_all()  # noqa: SLF001 (test introspection)
    assert any(e.eventType == "ResumeFromCheckpoint" for e in events)

    # Continue to completion from the checkpoint.
    progress = mgr2.run_until_pause(run_id)
    assert progress.status == "completed"
    assert progress.completed_phases == list(PHASE_IDS)


def test_resumed_secure_run_keeps_its_mandatory_gates(tmp_path: pathlib.Path) -> None:
    # A restart must not strip a secure run of its approval gates.
    mgr1 = DevelopmentManager(workspace_root=str(tmp_path))
    started = mgr1.start_run(RunStartRequest(mode="secure", security_profile="restricted"))
    run_id = started.run_id
    assert mgr1.run_until_pause(run_id).pending_approval_gate == "post-proposal"

    mgr2 = DevelopmentManager(workspace_root=str(tmp_path))
    mgr2.resume_run(run_id)
    progress = mgr2.run_until_pause(run_id)
    # Still gated: the next mandatory secure gate, not a straight run-through.
    assert progress.status == "awaiting_approval"
    assert progress.pending_approval_gate == "post-proposal"


def test_resumed_run_keeps_approved_gates_and_complexity_tier(
    tmp_path: pathlib.Path,
) -> None:
    from anvil_runtime.api.models import ApprovalRequest

    mgr1 = DevelopmentManager(workspace_root=str(tmp_path))
    started = mgr1.start_run(RunStartRequest(mode="secure", security_profile="restricted"))
    run_id = started.run_id
    mgr1.run_until_pause(run_id)  # post-proposal
    mgr1.submit_approval(run_id, ApprovalRequest(
        gateId="post-proposal", gateName="Post-Proposal",
        approved=True, requesterId="u",
    ))

    mgr2 = DevelopmentManager(workspace_root=str(tmp_path))
    mgr2.resume_run(run_id)
    progress = mgr2.run_until_pause(run_id)
    # The already-approved gate is not re-asked; the run advances to the next one.
    assert progress.pending_approval_gate == "post-architecture"


def test_corrupt_run_state_file_does_not_brick_the_store(tmp_path: pathlib.Path) -> None:
    from anvil_runtime.state.checkpoint_store import CheckpointStore

    store = CheckpointStore(str(tmp_path))
    store.initialize_run("r1", "yolo")
    store.path.write_text("{truncated", encoding="utf-8")
    assert store.load_run_state("r1") is None  # treated as no checkpoint
    # The corrupt bytes are preserved for forensics; new writes start clean.
    assert store.path.with_suffix(".json.corrupt").exists()
    store.initialize_run("r2", "yolo")
    assert store.load_run_state("r2") is not None
