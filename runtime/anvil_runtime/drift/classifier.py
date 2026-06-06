"""Drift severity classification.

Slice 6 deliverable (spec §2.5.1, FR-DR-004/005/006/007). Maps a drift *kind*
(the scenario detected) to a severity — ``minor``, ``major``, or ``critical`` —
following the spec's worked examples. Severity drives remediation routing in
:mod:`anvil_runtime.drift.remediation`.
"""

from __future__ import annotations

from typing import Literal

DriftSeverity = Literal["minor", "major", "critical"]

# Drift kind -> severity (spec §2.5.1 scenarios + §2.5.3 examples).
_SEVERITY: dict[str, DriftSeverity] = {
    # Minor: cosmetic / non-structural (FR-DR-005).
    "missing_docstring": "minor",
    "naming_mismatch": "minor",
    # Major: missing module / incomplete feature (FR-DR-006).
    "missing_module": "major",
    "incomplete_feature": "major",
    "extra_module": "major",  # code not in blueprint/architecture/spec
    "low_coverage": "major",
    "unverified_nfr": "major",
    # Critical: architectural violation / missing core feature (FR-DR-007).
    "architectural_violation": "critical",
    "missing_core_feature": "critical",
    "boundary_violation": "critical",
}

_RANK: dict[DriftSeverity, int] = {"minor": 1, "major": 2, "critical": 3}


def classify(kind: str) -> DriftSeverity:
    """Severity for a drift kind; unknown kinds default to ``major`` (fail safe)."""
    return _SEVERITY.get(kind, "major")


def highest(severities: list[DriftSeverity]) -> DriftSeverity | None:
    """Return the most severe of a list, or ``None`` when empty."""
    if not severities:
        return None
    return max(severities, key=lambda s: _RANK[s])


def rank(severity: DriftSeverity) -> int:
    return _RANK[severity]


__all__ = ["classify", "highest", "rank", "DriftSeverity"]
