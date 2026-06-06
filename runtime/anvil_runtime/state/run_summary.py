"""Human-readable run summary writer.

Slice 2 deliverable (spec FR-SV-025). Appends a human-readable line to
``logs/run-summary.log`` at the end of each phase: phase name, status, artifacts
produced, duration, and token usage when available. This complements the
machine-readable JSONL audit trail in :mod:`anvil_runtime.state.event_bus`.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.config.schema import RUN_SUMMARY_LOG_PATH
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent


class RunSummaryWriter:
    """Appends per-phase summary lines to ``logs/run-summary.log``."""

    def __init__(self, workspace_root: str | pathlib.Path = ".") -> None:
        self._path = pathlib.Path(workspace_root) / RUN_SUMMARY_LOG_PATH

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def write_phase_summary(self, run_id: str, event: PhaseCompleteEvent) -> None:
        artifacts = ", ".join(event.artifact_paths) if event.artifact_paths else "-"
        if event.token_usage:
            tokens = ", ".join(f"{k}={v}" for k, v in sorted(event.token_usage.items()))
        else:
            tokens = "n/a"
        line = (
            f"[run {run_id}] phase={event.phase_name} status={event.status} "
            f"duration_ms={event.duration_ms} artifacts=[{artifacts}] tokens=[{tokens}]"
        )
        if event.failure_reason:
            line += f" failure_reason={event.failure_reason!r}"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


__all__ = ["RunSummaryWriter"]
