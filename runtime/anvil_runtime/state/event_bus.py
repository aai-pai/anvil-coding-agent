"""Structured event bus: JSONL audit trail + in-process subscribers.

Slice 2 deliverable (blueprint §3.1; spec FR-SV-024/026). Every lifecycle
boundary emits an :class:`EventEnvelope`. The bus appends one JSON object per
line to ``logs/events.jsonl`` (queryable audit trail) and fans the event out to
subscribed callbacks (the SSE stream in Slice 4 subscribes here). A final
completeness/redaction pass is Slice 6.
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Iterator

from anvil_runtime.config.schema import EVENTS_LOG_PATH
from anvil_runtime.core.phase_contracts import EventEnvelope

EventCallback = Callable[[EventEnvelope], None]


class Subscription:
    """Handle returned by :meth:`EventBus.subscribe`; call ``dispose`` to remove."""

    def __init__(self, unsubscribe: Callable[[], None]) -> None:
        self._unsubscribe = unsubscribe
        self._active = True

    def dispose(self) -> None:
        if self._active:
            self._unsubscribe()
            self._active = False


class EventBus:
    """Writes events to a JSONL log and notifies in-process subscribers."""

    def __init__(self, workspace_root: str | pathlib.Path = ".") -> None:
        self._events_path = pathlib.Path(workspace_root) / EVENTS_LOG_PATH
        self._subscribers: list[EventCallback] = []

    @property
    def events_path(self) -> pathlib.Path:
        return self._events_path

    def subscribe(self, callback: EventCallback) -> Subscription:
        self._subscribers.append(callback)

        def _remove() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return Subscription(_remove)

    def emit(self, event: EventEnvelope) -> None:
        """Append the event to the JSONL log, then notify subscribers."""
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        line = event.model_dump_json()
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        # Notify subscribers; a failing subscriber must not break emission.
        for callback in list(self._subscribers):
            callback(event)

    def read_all(self) -> list[EventEnvelope]:
        """Load every persisted event (used by tests and resume diagnostics)."""
        if not self._events_path.exists():
            return []
        events: list[EventEnvelope] = []
        with self._events_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if raw:
                    events.append(EventEnvelope.model_validate_json(raw))
        return events

    def stream(self, run_id: str) -> Iterator[EventEnvelope]:
        """Yield already-persisted events for a run (point-in-time snapshot).

        Live streaming to the extension is layered on top of :meth:`subscribe`
        in Slice 4; this snapshot iterator supports tests and replay.
        """
        for event in self.read_all():
            if event.runId == run_id:
                yield event


__all__ = ["EventBus", "Subscription", "EventCallback"]
