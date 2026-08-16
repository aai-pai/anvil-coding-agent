"""Bounded self-heal retry control with exponential backoff.

Slice 2 deliverable (spec FR-SV-017/018/019, NFR-RB-001/002). Tracks per-phase
attempt counters for a run and decides whether another self-heal retry is
allowed before escalation. Default budget is 2 retries per phase (configurable
via the precedence hierarchy in later slices); backoff is exponential with a
2-second base (1st retry after 2s, 2nd after 4s).
"""

from __future__ import annotations

from anvil_runtime.config.schema import DEFAULT_MAX_RETRIES_PER_PHASE

RETRY_BACKOFF_BASE_SECONDS = 2


class RetryController:
    """Per-(run, phase) retry budget tracker."""

    def __init__(
        self,
        max_retries_per_phase: int = DEFAULT_MAX_RETRIES_PER_PHASE,
        backoff_base_seconds: int = RETRY_BACKOFF_BASE_SECONDS,
    ) -> None:
        self._max_retries = max_retries_per_phase
        self._backoff_base = backoff_base_seconds
        # key -> number of failures recorded so far.
        self._attempts: dict[tuple[str, str], int] = {}

    @staticmethod
    def _key(run_id: str, phase_id: str) -> tuple[str, str]:
        return (run_id, phase_id)

    def attempts(self, run_id: str, phase_id: str) -> int:
        """Number of failures recorded for this phase so far."""
        return self._attempts.get(self._key(run_id, phase_id), 0)

    def record_failure(self, run_id: str, phase_id: str) -> int:
        """Record a failed attempt and return the new failure count."""
        key = self._key(run_id, phase_id)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        return self._attempts[key]

    def should_retry(self, run_id: str, phase_id: str) -> bool:
        """True while recorded failures are within the retry budget."""
        return self.attempts(run_id, phase_id) <= self._max_retries

    def retries_exhausted(self, run_id: str, phase_id: str) -> bool:
        return not self.should_retry(run_id, phase_id)

    def backoff_seconds(self, attempt: int) -> int:
        """Exponential backoff for the Nth retry (attempt is 1-based).

        attempt=1 -> 2s, attempt=2 -> 4s (NFR-RB-002).
        """
        if attempt < 1:
            return 0
        return self._backoff_base * (2 ** (attempt - 1))

    def reset(self, run_id: str, phase_id: str) -> None:
        """Clear the counter for a phase (e.g., after success or rollback)."""
        self._attempts.pop(self._key(run_id, phase_id), None)

    def snapshot(self, run_id: str) -> dict[str, int]:
        """Per-phase failure counts for a run (for RunState.retry_counters)."""
        return {
            phase: count
            for (rid, phase), count in self._attempts.items()
            if rid == run_id
        }

    def restore(self, run_id: str, counters: dict[str, int]) -> None:
        """Rehydrate counters from a checkpoint (FR-FX-002).

        The read side of :meth:`snapshot`, which had no callers at all until
        v0.1.5 — so a server restart silently reset every phase's retry
        budget to zero, and resume is a documented, load-bearing feature.
        """
        for phase, count in (counters or {}).items():
            self._attempts[self._key(run_id, phase)] = int(count)


__all__ = ["RetryController", "RETRY_BACKOFF_BASE_SECONDS"]
