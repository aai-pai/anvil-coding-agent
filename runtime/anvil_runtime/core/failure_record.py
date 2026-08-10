"""Automatic failure-record (FR) generation (feature; spec FR-REC-001..005).

On every phase failure the supervisor renders its escalation packet into an
FR-001/002-style Markdown record under ``<run>/docs/failure_records/``,
deterministically (no LLM call). These are supervisor-owned diagnostic artifacts —
not phase artifacts — so they bypass complexity gating and the canonical artifact
policy.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime

from anvil_runtime.core.escalation_service import EscalationPacket

_RECORDS_DIR = "docs/failure_records"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:40].rstrip("-") or "failure"


def _next_seq(records_dir: pathlib.Path) -> int:
    if not records_dir.exists():
        return 1
    return len(list(records_dir.glob("FR-*.md"))) + 1


def render_fr(
    seq: int, packet: EscalationPacket, mode: str, exec_mode: str, now: datetime
) -> str:
    """Render an FR-001/002-style failure record (deterministic; no LLM)."""
    fr_id = f"FR-{seq:03d}"
    rows = "\n".join(
        f"| {e.get('timestamp', '')} | {e.get('eventType', '')} | "
        f"{e.get('phase', '')} | {e.get('severity', '')} |"
        for e in packet.recent_events[-10:]
    ) or "| (none) | | | |"
    actions = ", ".join(packet.available_actions) or "retry, rollback, stop"
    return f"""# {fr_id}: {packet.phase} phase failure

**Date:** {now.date().isoformat()}
**Run ID:** `{packet.run_id}`
**Operating Mode:** `{mode}`
**Execution Mode:** `{exec_mode}`
**Status:** Open

---

## Summary

Phase `{packet.phase}` failed on attempt {packet.attempts} with: {packet.reason}

## Observed Evidence

| timestamp | eventType | phase | severity |
|---|---|---|---|
{rows}

## Root Cause

_To be investigated._

## Impact

Phase `{packet.phase}` did not complete on this attempt.

## Recommendations

Available supervisor actions: {actions}.

## Verification Plan

_To be completed after a fix is applied._
"""


def write_fr(
    workspace_root: str,
    packet: EscalationPacket,
    mode: str,
    exec_mode: str,
    now: datetime,
) -> str:
    """Render and write a failure record; return its workspace-relative path."""
    records_dir = pathlib.Path(workspace_root) / _RECORDS_DIR
    records_dir.mkdir(parents=True, exist_ok=True)
    seq = _next_seq(records_dir)
    name = f"FR-{seq:03d}-{_slug(packet.reason)}.md"
    (records_dir / name).write_text(
        render_fr(seq, packet, mode, exec_mode, now), encoding="utf-8"
    )
    return f"{_RECORDS_DIR}/{name}"


__all__ = ["render_fr", "write_fr"]
