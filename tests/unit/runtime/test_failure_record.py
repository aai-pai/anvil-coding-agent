"""Unit tests: failure-record rendering and writing (#FR, FR-REC-001..004)."""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from anvil_runtime.core.escalation_service import EscalationPacket
from anvil_runtime.core.failure_record import render_fr, write_fr

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _packet() -> EscalationPacket:
    return EscalationPacket(
        run_id="run-abc",
        phase="proposal",
        reason="artifact validation failed: missing required section 'Scope'",
        attempts=2,
        recent_events=[
            {"timestamp": "t1", "eventType": "PhaseFailed", "phase": "proposal", "severity": "error"},
        ],
    )


def test_render_has_layout_and_fields() -> None:
    md = render_fr(1, _packet(), mode="yolo", exec_mode="real", now=_NOW)
    assert md.startswith("# FR-001: proposal phase failure")
    assert "`run-abc`" in md  # FR-REC-004: run id present
    assert "**Status:** Open" in md
    for section in ("## Summary", "## Observed Evidence", "## Root Cause",
                    "## Impact", "## Recommendations", "## Verification Plan"):
        assert section in md  # FR-REC-002 layout
    assert "attempt 2" in md
    assert "missing required section" in md


def test_write_fr_creates_sequenced_files(tmp_path: pathlib.Path) -> None:
    p1 = write_fr(str(tmp_path), _packet(), "yolo", "real", _NOW)
    p2 = write_fr(str(tmp_path), _packet(), "yolo", "real", _NOW)
    assert p1.startswith("docs/failure_records/FR-001-")
    assert p2.startswith("docs/failure_records/FR-002-")
    assert (tmp_path / p1).is_file()
    assert (tmp_path / p2).is_file()
