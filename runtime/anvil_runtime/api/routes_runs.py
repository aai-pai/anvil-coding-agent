"""Run-control routes: start, inspect, approve, override.

Slice 4 deliverable (blueprint §5.1 endpoints 1-4). These routes are a thin
HTTP surface over :class:`DevelopmentManager`; all orchestration, gating, and
state ownership stay in the supervisor (architecture: single-writer runtime).

After a state-changing call (start, approval-granted, force-advance, rollback)
the route drives ``run_until_pause`` so the supervisor advances serially to the
next gate, escalation, stop, or completion before responding.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from anvil_runtime.api.deps import get_manager
from anvil_runtime.api.models import (
    ApprovalRequest,
    OverrideRequest,
    OverrideResult,
    RunStarted,
    RunStartRequest,
    RunStateResponse,
)
from anvil_runtime.core.development_manager import DevelopmentManager, RunProgress

router = APIRouter(prefix="/v1/runs", tags=["runs"])


def _to_state_response(progress: RunProgress) -> RunStateResponse:
    """Map the supervisor's internal progress to the public response model."""
    return RunStateResponse(
        run_id=progress.run_id,
        status=progress.status,
        current_phase=progress.current_phase,
        completed_phases=list(progress.completed_phases),
        pending_approval_gate=progress.pending_approval_gate,
    )


@router.post("", response_model=RunStarted, status_code=status.HTTP_201_CREATED)
def start_run(
    request: RunStartRequest,
    manager: DevelopmentManager = Depends(get_manager),
) -> RunStarted:
    """``POST /v1/runs`` — start a run and advance to the first pause point."""
    started = manager.start_run(request)
    manager.run_until_pause(started.run_id)
    return started


@router.get("/{run_id}", response_model=RunStateResponse)
def get_run(
    run_id: str,
    manager: DevelopmentManager = Depends(get_manager),
) -> RunStateResponse:
    """``GET /v1/runs/{run_id}`` — current status, phase, and pending gate."""
    try:
        progress = manager.get_progress(run_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run '{run_id}'"
        )
    return _to_state_response(progress)


@router.post("/{run_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve(
    run_id: str,
    body: ApprovalRequest,
    manager: DevelopmentManager = Depends(get_manager),
) -> Response:
    """``POST /v1/runs/{run_id}/approve`` — record a gate decision (204)."""
    try:
        decision = manager.submit_approval(run_id, body)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run '{run_id}'"
        )
    # Only a granted approval clears the pause and lets the run proceed.
    if decision.approved:
        manager.run_until_pause(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{run_id}/override", response_model=OverrideResult)
def override(
    run_id: str,
    body: OverrideRequest,
    manager: DevelopmentManager = Depends(get_manager),
) -> OverrideResult:
    """``POST /v1/runs/{run_id}/override`` — force-advance, rollback, or stop."""
    try:
        result = manager.apply_override(run_id, body)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run '{run_id}'"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # force-advance and rollback resume execution; stop leaves the run halted.
    if body.action != "stop":
        manager.run_until_pause(run_id)
    return result


__all__ = ["router"]
