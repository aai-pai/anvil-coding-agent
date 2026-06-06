"""Per-phase token usage tracking and budget enforcement.

Slice 5 deliverable (blueprint §3.1; spec NFR-TK-003, FR-ML-006). Accumulates
token usage per phase, emits ``TokenUsageReported`` to the audit trail, and
checks usage against the configured ``tokenBudgetPerPhase`` so the supervisor can
escalate a phase that exceeds its budget (NFR-TK-003). Budgets are advisory here;
the Policy Engine performs the authoritative ``TokenBudgetPerPhase`` check.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.state.event_bus import EventBus


class PhaseUsage(BaseModel):
    """Accumulated token usage for one phase."""

    phase: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class UsageTracker:
    """Accumulates and reports per-phase token usage (NFR-TK-003)."""

    def __init__(
        self,
        budgets: dict[str, int] | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._budgets = budgets or {}
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._usage: dict[str, PhaseUsage] = {}

    def record(self, phase: str, usage: dict[str, int]) -> PhaseUsage:
        """Add a usage delta for a phase and emit ``TokenUsageReported``."""
        acc = self._usage.setdefault(phase, PhaseUsage(phase=phase))
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        total = int(usage.get("total_tokens", prompt + completion))
        acc.prompt_tokens += prompt
        acc.completion_tokens += completion
        acc.total_tokens += total
        over, limit = self.check_budget(phase)
        self._emit("TokenUsageReported", phase, severity="warning" if over else "info", data={
            "total_tokens": acc.total_tokens,
            "budget": limit,
            "over_budget": over,
        })
        return acc

    def total_for(self, phase: str) -> int:
        usage = self._usage.get(phase)
        return usage.total_tokens if usage else 0

    def check_budget(self, phase: str) -> tuple[bool, int | None]:
        """Return ``(over_budget, limit)``; limit is ``None`` when unbudgeted."""
        limit = self._budgets.get(phase)
        if limit is None:
            return False, None
        return self.total_for(phase) > limit, limit

    def over_budget(self, phase: str) -> bool:
        return self.check_budget(phase)[0]

    def all_usage(self) -> dict[str, PhaseUsage]:
        return dict(self._usage)

    def _emit(self, event_type: str, phase: str, severity: str, data: dict) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=self._run_id,
            phase=phase, severity=severity, data=data,
        ))


__all__ = ["UsageTracker", "PhaseUsage"]
