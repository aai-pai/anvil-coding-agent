"""Unit tests for the retry controller. Slice 2 (FR-SV-018, NFR-RB-001/002)."""

from __future__ import annotations

from anvil_runtime.core.retry_controller import RetryController


def test_default_budget_allows_two_retries() -> None:
    rc = RetryController(max_retries_per_phase=2)
    assert rc.attempts("r", "proposal") == 0
    assert rc.should_retry("r", "proposal") is True
    assert rc.record_failure("r", "proposal") == 1
    assert rc.should_retry("r", "proposal") is True  # 1 <= 2
    assert rc.record_failure("r", "proposal") == 2
    assert rc.should_retry("r", "proposal") is True  # 2 <= 2
    assert rc.record_failure("r", "proposal") == 3
    assert rc.should_retry("r", "proposal") is False  # 3 > 2
    assert rc.retries_exhausted("r", "proposal") is True


def test_exponential_backoff_2s_base() -> None:
    rc = RetryController()
    assert rc.backoff_seconds(1) == 2
    assert rc.backoff_seconds(2) == 4
    assert rc.backoff_seconds(3) == 8
    assert rc.backoff_seconds(0) == 0


def test_reset_clears_counter() -> None:
    rc = RetryController()
    rc.record_failure("r", "qa")
    rc.reset("r", "qa")
    assert rc.attempts("r", "qa") == 0


def test_counters_are_isolated_per_run_and_phase() -> None:
    rc = RetryController()
    rc.record_failure("r1", "qa")
    rc.record_failure("r1", "qa")
    rc.record_failure("r2", "qa")
    assert rc.attempts("r1", "qa") == 2
    assert rc.attempts("r2", "qa") == 1
    assert rc.snapshot("r1") == {"qa": 2}
