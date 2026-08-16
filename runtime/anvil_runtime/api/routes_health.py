"""Health route.

Slice 4 deliverable (blueprint §5.1 endpoint 7). ``GET /v1/health`` reports
liveness plus a per-subsystem check map. ``config`` is verified in Slice 3 and
reports ``ok``; ``mcp_discovery`` and ``openhands`` are wired in Slice 5 and
honestly report ``pending`` until then. Overall ``status`` is ``ok`` unless a
subsystem is in ``error``.
"""

from __future__ import annotations

from fastapi import APIRouter

from anvil_runtime.api.models import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])

RUNTIME_NAME = "anvil-runtime"


def build_checks() -> dict[str, str]:
    """Per-subsystem readiness (FR-FX-004).

    These read "pending" for releases after the work shipped, which made the
    endpoint say less than nothing. Report what is true: the execution
    adapter is wired and serving runs; MCP discovery is built and
    unit-tested but never constructed by the application factory, so it is
    ``not-wired`` rather than pending — a distinction a reader can act on.
    """
    return {
        "config": "ok",
        "mcp_discovery": "not-wired",  # tools/ is unwired; v0.1.6 activates it
        "openhands": "ok",  # sdk/openhands_adapter backs every real run
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """``GET /v1/health`` — runtime liveness and subsystem checks."""
    checks = build_checks()
    overall = "ok" if all(state != "error" for state in checks.values()) else "degraded"
    return HealthResponse(status=overall, runtime=RUNTIME_NAME, checks=checks)


__all__ = ["router", "build_checks", "RUNTIME_NAME"]
