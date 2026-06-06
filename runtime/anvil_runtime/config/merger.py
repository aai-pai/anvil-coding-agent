"""Configuration merge with precedence semantics.

Slice 3 deliverable (spec §2.7.2; FR-CF-001/002/003). Merges the four
:class:`ConfigSources` levels (lowest to highest) into an
:class:`EffectiveConfig`:

* scalars  — higher precedence overrides lower (FR-CF-001)
* lists    — appended/unioned lowest-first, deduped (FR-CF-002)
* maps     — deep-merged, higher keys override (FR-CF-003)
"""

from __future__ import annotations

from anvil_runtime.config.loader import ConfigSources
from anvil_runtime.config.schema import EffectiveConfig


def _union_lists(low: list, high: list) -> list:
    """Append ``high`` onto ``low`` preserving order, skipping duplicates."""
    out = list(low)
    for item in high:
        if item not in out:
            out.append(item)
    return out


def _merge_pair(low: object, high: object) -> object:
    """Merge a lower-precedence value with a higher-precedence one."""
    if isinstance(low, dict) and isinstance(high, dict):
        result: dict[object, object] = dict(low)
        for key, hi_value in high.items():
            if key in result:
                result[key] = _merge_pair(result[key], hi_value)
            else:
                result[key] = hi_value
        return result
    if isinstance(low, list) and isinstance(high, list):
        return _union_lists(low, high)
    # Scalars (or mismatched types): higher precedence wins.
    return high


def deep_merge(levels_low_to_high: list[dict[str, object]]) -> dict[str, object]:
    """Fold the precedence levels with :func:`_merge_pair`, lowest first."""
    merged: dict[str, object] = {}
    for level in levels_low_to_high:
        merged_obj = _merge_pair(merged, level)
        assert isinstance(merged_obj, dict)  # top level is always a mapping
        merged = merged_obj
    return merged


class ConfigMerger:
    """Merges config sources into an :class:`EffectiveConfig`."""

    def merge_to_dict(self, sources: ConfigSources) -> dict[str, object]:
        return deep_merge(sources.ordered_low_to_high())

    def merge(self, sources: ConfigSources) -> EffectiveConfig:
        """Produce the typed effective config (pydantic validates field types)."""
        return EffectiveConfig.model_validate(self.merge_to_dict(sources))


__all__ = ["ConfigMerger", "deep_merge"]
