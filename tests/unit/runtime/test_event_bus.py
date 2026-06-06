"""Unit tests for the event bus. Slice 2 (FR-SV-024/026)."""

from __future__ import annotations

import pathlib

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.state.event_bus import EventBus


def _event(run_id: str, event_type: str) -> EventEnvelope:
    return EventEnvelope(
        timestamp="2026-05-31T00:00:00Z",
        eventType=event_type,
        runId=run_id,
        phase="proposal",
    )


def test_emit_appends_jsonl_and_reads_back(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    bus.emit(_event("r1", "PhaseStarted"))
    bus.emit(_event("r1", "PhaseCompleted"))
    assert bus.events_path.exists()
    events = bus.read_all()
    assert [e.eventType for e in events] == ["PhaseStarted", "PhaseCompleted"]


def test_subscribers_receive_events_until_disposed(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    received: list[str] = []
    sub = bus.subscribe(lambda e: received.append(e.eventType))
    bus.emit(_event("r1", "A"))
    sub.dispose()
    bus.emit(_event("r1", "B"))
    assert received == ["A"]


def test_stream_filters_by_run(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    bus.emit(_event("r1", "A"))
    bus.emit(_event("r2", "B"))
    bus.emit(_event("r1", "C"))
    streamed = [e.eventType for e in bus.stream("r1")]
    assert streamed == ["A", "C"]
