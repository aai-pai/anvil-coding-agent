"""API request/response models and JSON-schema constants.

Slice 1 deliverable (blueprint §4.1, §4.2, §5.1). These Pydantic models are the
typed contract for the ``/v1`` REST surface implemented in Slice 4. The
``*_SCHEMA`` constants (blueprint §4.2) are derived deterministically from the
models so the schema and the runtime validation can never disagree.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from anvil_runtime.core.phase_contracts import EventEnvelope, PhaseCompleteEvent

# ---------------------------------------------------------------------------
# Run control models (blueprint §4.1)
# ---------------------------------------------------------------------------


class RunStartRequest(BaseModel):
    """Body for ``POST /v1/runs``."""

    mode: Literal["yolo", "gated", "secure"]
    security_profile: Literal["open", "restricted", "strict"]
    phase_gates: list[str] = Field(default_factory=list)
    run_overrides: dict[str, object] = Field(default_factory=dict)
    # Optional free-form task. When set, the runtime writes it to the workspace's
    # domain-knowledge file so the proposal phase builds *this* instead of needing
    # the file to be edited by hand (conversational "@anvil build ..." flow).
    task: str | None = None


class RunStarted(BaseModel):
    """Response for ``POST /v1/runs``."""

    run_id: str
    started_at: datetime
    mode: str


class ApprovalRequest(BaseModel):
    """Body for ``POST /v1/runs/{run_id}/approve`` (secure/gated approvals)."""

    gateId: str
    gateName: str
    approved: bool
    comments: str | None = None
    requesterId: str


class OverrideRequest(BaseModel):
    """Body for ``POST /v1/runs/{run_id}/override`` (force/rollback/stop)."""

    action: Literal["force-advance", "rollback", "stop"]
    targetPhase: str | None = None
    reason: str
    comments: str | None = None
    requesterId: str


# ---------------------------------------------------------------------------
# Response models for the remaining `/v1` endpoints (blueprint §5.1)
# ---------------------------------------------------------------------------


class RunStateResponse(BaseModel):
    """Response for ``GET /v1/runs/{run_id}``."""

    run_id: str
    status: str
    current_phase: str | None = None
    completed_phases: list[str] = Field(default_factory=list)
    pending_approval_gate: str | None = None


class OverrideResult(BaseModel):
    """Response for ``POST /v1/runs/{run_id}/override``."""

    status: str
    action: str
    targetPhase: str | None = None


class ArtifactResponse(BaseModel):
    """Response for ``GET /v1/artifacts/{phase}``."""

    phase: str
    path: str
    checksum: str
    generatedAt: datetime


class HealthResponse(BaseModel):
    """Response for ``GET /v1/health``."""

    status: str
    runtime: str
    checks: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# JSON Schemas stored as constants (blueprint §4.2)
# ---------------------------------------------------------------------------
# Generated from the canonical models above so there is a single source of
# truth. EVENT_ENVELOPE_SCHEMA and PHASE_COMPLETE_SCHEMA describe core
# contracts that live in anvil_runtime.core.phase_contracts.

APPROVAL_REQUEST_SCHEMA: dict[str, object] = ApprovalRequest.model_json_schema()
OVERRIDE_REQUEST_SCHEMA: dict[str, object] = OverrideRequest.model_json_schema()
EVENT_ENVELOPE_SCHEMA: dict[str, object] = EventEnvelope.model_json_schema()
PHASE_COMPLETE_SCHEMA: dict[str, object] = PhaseCompleteEvent.model_json_schema()


__all__ = [
    "RunStartRequest",
    "RunStarted",
    "ApprovalRequest",
    "OverrideRequest",
    "RunStateResponse",
    "OverrideResult",
    "ArtifactResponse",
    "HealthResponse",
    "APPROVAL_REQUEST_SCHEMA",
    "OVERRIDE_REQUEST_SCHEMA",
    "EVENT_ENVELOPE_SCHEMA",
    "PHASE_COMPLETE_SCHEMA",
]
