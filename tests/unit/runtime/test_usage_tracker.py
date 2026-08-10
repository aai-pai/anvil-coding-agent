"""Unit tests: per-phase token usage tracking and budget checks.

Slice 5 (spec NFR-TK-003; plan §2.5). Verifies accumulation, budget detection,
and ``TokenUsageReported`` emission.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.llm.usage_tracker import UsageTracker
from anvil_runtime.state.event_bus import EventBus


def test_accumulates_usage_across_calls() -> None:
    tracker = UsageTracker()
    tracker.record("implementation", {"prompt_tokens": 100, "completion_tokens": 20})
    tracker.record("implementation", {"prompt_tokens": 30, "completion_tokens": 10})
    assert tracker.total_for("implementation") == 160


def test_derives_total_when_absent() -> None:
    tracker = UsageTracker()
    usage = tracker.record("qa", {"prompt_tokens": 5, "completion_tokens": 7})
    assert usage.total_tokens == 12


def test_budget_detection() -> None:
    tracker = UsageTracker(budgets={"implementation": 100})
    tracker.record("implementation", {"total_tokens": 80})
    assert tracker.over_budget("implementation") is False
    tracker.record("implementation", {"total_tokens": 40})
    over, limit = tracker.check_budget("implementation")
    assert over is True
    assert limit == 100


def test_unbudgeted_phase_never_over_budget() -> None:
    tracker = UsageTracker()
    tracker.record("proposal", {"total_tokens": 10_000})
    assert tracker.over_budget("proposal") is False


def test_emits_token_usage_reported(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    tracker = UsageTracker(budgets={"implementation": 50}, event_bus=bus, run_id="r1")
    tracker.record("implementation", {"total_tokens": 60})
    events = [e for e in bus.read_all() if e.eventType == "TokenUsageReported"]
    assert events
    assert events[-1].data["over_budget"] is True
    assert events[-1].severity == "warning"


def test_record_event_carries_passed_run_id(tmp_path: pathlib.Path) -> None:
    # FR-EVT-001/002: a run_id passed to record() labels the event, overriding
    # the constructor's run_id.
    bus = EventBus(str(tmp_path))
    tracker = UsageTracker(event_bus=bus, run_id="ctor")
    tracker.record("implementation", {"total_tokens": 10}, run_id="run-xyz")
    events = [e for e in bus.read_all() if e.eventType == "TokenUsageReported"]
    assert events and events[-1].runId == "run-xyz"
