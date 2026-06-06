"""Event stream route: Server-Sent Events over the run's audit trail.

Slice 4 deliverable (blueprint §5.1 endpoint 5). ``GET /v1/runs/{run_id}/events``
returns ``text/event-stream`` with one :class:`EventEnvelope` JSON object per SSE
message. v0.1.0 streams the persisted snapshot of the run's events
(``logs/events.jsonl`` via :meth:`EventBus.stream`) and then closes — deterministic
and replayable. Continuous live tailing layers on :meth:`EventBus.subscribe` in a
later iteration without changing this contract.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from anvil_runtime.api.deps import get_run_event_bus, get_run_manager
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.state.event_bus import EventBus

router = APIRouter(prefix="/v1/runs", tags=["events"])

SSE_MEDIA_TYPE = "text/event-stream"


@router.get("/{run_id}/events")
def stream_events(
    run_id: str,
    manager: DevelopmentManager = Depends(get_run_manager),
    event_bus: EventBus = Depends(get_run_event_bus),
) -> StreamingResponse:
    """Stream the run's audit events as SSE (``EventEnvelope`` JSON per message)."""
    try:
        manager.get_progress(run_id)  # 404 for an unknown run before streaming
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run '{run_id}'"
        )

    def event_generator() -> Iterator[str]:
        for event in event_bus.stream(run_id):
            yield f"event: {event.eventType}\n"
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type=SSE_MEDIA_TYPE)


__all__ = ["router", "SSE_MEDIA_TYPE"]
