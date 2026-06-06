"""Escalation packet construction and emission.

Slice 2 deliverable (blueprint §3.1; spec FR-SV-019/020). When self-heal retries
are exhausted (or an unremediable condition occurs), the supervisor builds an
:class:`EscalationPacket` with full phase context and emits a ``PhaseEscalation``
event, then pauses the run awaiting a user decision (retry / rollback / stop).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from anvil_runtime.core.phase_contracts import EventEnvelope

if TYPE_CHECKING:  # avoid a hard import cycle; EventBus only needs `.emit`.
    from anvil_runtime.state.event_bus import EventBus

# User decisions available in response to an escalation (spec FR-SV-020).
ESCALATION_ACTIONS = ("retry", "rollback", "stop")


class EscalationPacket(BaseModel):
    """Context bundle attached to a ``PhaseEscalation`` event."""

    run_id: str
    phase: str
    reason: str
    attempts: int = 0
    recent_events: list[dict[str, object]] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=lambda: list(ESCALATION_ACTIONS))
    created_at: datetime | None = None


class EscalationService:
    """Builds escalation packets and emits them to the audit trail."""

    def __init__(self, event_bus: "EventBus | None" = None) -> None:
        self._event_bus = event_bus

    def build_packet(
        self,
        run_id: str,
        phase: str,
        reason: str,
        attempts: int = 0,
        recent_events: list[dict[str, object]] | None = None,
        created_at: datetime | None = None,
    ) -> EscalationPacket:
        return EscalationPacket(
            run_id=run_id,
            phase=phase,
            reason=reason,
            attempts=attempts,
            recent_events=list(recent_events or []),
            created_at=created_at or datetime.now(timezone.utc),
        )

    def escalate(self, packet: EscalationPacket) -> EventEnvelope:
        """Emit a critical ``PhaseEscalation`` event and return it."""
        event = EventEnvelope(
            timestamp=packet.created_at or datetime.now(timezone.utc),
            eventType="PhaseEscalation",
            runId=packet.run_id,
            phase=packet.phase,
            severity="critical",
            data={
                "reason": packet.reason,
                "attempts": packet.attempts,
                "available_actions": packet.available_actions,
                "recent_events": packet.recent_events,
            },
        )
        if self._event_bus is not None:
            self._event_bus.emit(event)
        return event


__all__ = ["EscalationPacket", "EscalationService", "ESCALATION_ACTIONS"]
