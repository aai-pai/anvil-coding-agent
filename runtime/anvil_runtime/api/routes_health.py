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
    """Per-subsystem readiness. Slice 5 flips the pending entries to live probes."""
    return {
        "config": "ok",
        "mcp_discovery": "pending",  # Slice 5 (tools/mcp_manager)
        "openhands": "pending",  # Slice 5 (sdk/openhands_adapter)
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """``GET /v1/health`` — runtime liveness and subsystem checks."""
    checks = build_checks()
    overall = "ok" if all(state != "error" for state in checks.values()) else "degraded"
    return HealthResponse(status=overall, runtime=RUNTIME_NAME, checks=checks)


__all__ = ["router", "build_checks", "RUNTIME_NAME"]
