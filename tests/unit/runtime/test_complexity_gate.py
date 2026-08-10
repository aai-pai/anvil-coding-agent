"""Unit tests: complexity gating helpers (#11, FR-CX-001/002).

Covers the tier -> excluded-phase mapping and the proposal tier marker parser.
"""

from __future__ import annotations

from anvil_runtime.core.development_manager import excluded_for_tier
from anvil_runtime.sdk.openhands_adapter import LLMBackend


def test_excluded_for_tier_mapping() -> None:
    assert excluded_for_tier("simple") == {
        "qa", "packaging", "documentation", "deployment", "cleanup"
    }
    assert excluded_for_tier("standard") == {
        "packaging", "documentation", "deployment", "cleanup"
    }
    assert excluded_for_tier("complex") == set()


def test_excluded_for_tier_unknown_or_none_gates_nothing() -> None:
    # No assessment -> run everything (backward compatible with stub/offline runs).
    assert excluded_for_tier(None) == set()
    assert excluded_for_tier("") == set()
    assert excluded_for_tier("bogus") == set()


def test_extract_tier_parses_and_strips_marker() -> None:
    cleaned, tier = LLMBackend._extract_tier("# Proposal\n\nbody\n\nCOMPLEXITY: simple")
    assert tier == "simple"
    assert "COMPLEXITY" not in cleaned
    assert "body" in cleaned


def test_extract_tier_none_when_absent() -> None:
    cleaned, tier = LLMBackend._extract_tier("# Proposal\n\njust the body")
    assert tier is None
    assert "just the body" in cleaned
