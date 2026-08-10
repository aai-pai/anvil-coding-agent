"""Integration: secure-mode mandatory gates pause and resume on approval.

Slice 2 (spec FR-SV-012, FR-OM-009/012).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import ApprovalRequest, RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager


def _approve(mgr: DevelopmentManager, run_id: str, gate: str) -> None:
    mgr.submit_approval(
        run_id,
        ApprovalRequest(gateId=gate, gateName=gate, approved=True, requesterId="user-1"),
    )


def test_secure_run_pauses_at_each_mandatory_gate(tmp_path: pathlib.Path) -> None:
    mgr = DevelopmentManager(workspace_root=str(tmp_path))
    started = mgr.start_run(RunStartRequest(mode="secure", security_profile="restricted"))
    run_id = started.run_id

    # Pause 1: post-proposal.
    p = mgr.run_until_pause(run_id)
    assert p.status == "awaiting_approval"
    assert p.pending_approval_gate == "post-proposal"
    assert p.completed_phases == ["intake", "proposal"]

    # Pause 2: post-architecture.
    _approve(mgr, run_id, "post-proposal")
    p = mgr.run_until_pause(run_id)
    assert p.pending_approval_gate == "post-architecture"
    assert "architecture" in p.completed_phases
    assert "blueprint" not in p.completed_phases

    # Pause 3: post-blueprint.
    _approve(mgr, run_id, "post-architecture")
    p = mgr.run_until_pause(run_id)
    assert p.pending_approval_gate == "post-blueprint"

    # Pause 4: pre-deployment (a *pre*-phase gate before deployment).
    _approve(mgr, run_id, "post-blueprint")
    p = mgr.run_until_pause(run_id)
    assert p.pending_approval_gate == "pre-deployment"
    assert p.current_phase == "deployment"
    assert "deployment" not in p.completed_phases
    assert "documentation" in p.completed_phases

    # Final: approve pre-deployment -> run completes.
    _approve(mgr, run_id, "pre-deployment")
    p = mgr.run_until_pause(run_id)
    assert p.status == "completed"
    assert "deployment" in p.completed_phases
    assert "cleanup" in p.completed_phases


def test_denied_approval_keeps_run_paused(tmp_path: pathlib.Path) -> None:
    mgr = DevelopmentManager(workspace_root=str(tmp_path))
    started = mgr.start_run(RunStartRequest(mode="secure", security_profile="restricted"))
    mgr.run_until_pause(started.run_id)
    decision = mgr.submit_approval(
        started.run_id,
        ApprovalRequest(
            gateId="post-proposal", gateName="Post-Proposal",
            approved=False, requesterId="user-1",
        ),
    )
    assert decision.approved is False
    # Still gated: re-running does not advance past the unapproved gate.
    p = mgr.run_until_pause(started.run_id)
    assert p.pending_approval_gate == "post-proposal"
    assert p.completed_phases == ["intake", "proposal"]
