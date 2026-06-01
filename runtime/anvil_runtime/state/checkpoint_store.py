"""Run-state checkpoint persistence and resume validation.

Slice 2 deliverable (blueprint §3.1; spec FR-SV-021/022/022A). Persists
per-phase completion (name, timestamp, artifact checksums) to
``.anvil/run-state.json`` and, on resume, re-validates that each completed
phase's artifacts still exist and their checksums still match — resuming from
the earliest invalid phase rather than blindly skipping it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from pydantic import BaseModel, Field

from anvil_runtime.config.schema import CHECKPOINT_PATH
from anvil_runtime.core.phase_contracts import PHASE_IDS, RunState

RUN_STATE_VERSION = "0.1.0"


class PhaseCheckpoint(BaseModel):
    """A single completed-phase record persisted in the run state."""

    phase: str
    completed_at: str
    checksums: dict[str, str] = Field(default_factory=dict)


def compute_checksum(path: str | pathlib.Path) -> str:
    """SHA-256 of a file's bytes (hex)."""
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CheckpointStore:
    """Loads/saves run-state checkpoints and computes resume points."""

    def __init__(self, workspace_root: str | pathlib.Path = ".") -> None:
        self._root = pathlib.Path(workspace_root)
        self._path = self._root / CHECKPOINT_PATH

    @property
    def path(self) -> pathlib.Path:
        return self._path

    # -- persistence ------------------------------------------------------

    def _read_container(self) -> dict[str, object]:
        if not self._path.exists():
            return {"runStateVersion": RUN_STATE_VERSION, "runs": {}}
        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_container(self, container: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(container, handle, indent=2, sort_keys=True)

    def initialize_run(self, run_id: str, mode: str) -> RunState:
        """Create (or return existing) run state for a run."""
        existing = self.load_run_state(run_id)
        if existing is not None:
            return existing
        state = RunState(runStateVersion=RUN_STATE_VERSION, run_id=run_id, mode=mode)
        self._persist_state(state)
        return state

    def load_run_state(self, run_id: str) -> RunState | None:
        container = self._read_container()
        runs = container.get("runs", {})
        raw = runs.get(run_id) if isinstance(runs, dict) else None
        if raw is None:
            return None
        return RunState.model_validate(raw)

    def _persist_state(self, state: RunState) -> None:
        container = self._read_container()
        runs = container.setdefault("runs", {})
        if isinstance(runs, dict):
            runs[state.run_id] = state.model_dump()
        container["runStateVersion"] = RUN_STATE_VERSION
        self._write_container(container)

    def save_phase_completion(self, run_id: str, phase: PhaseCheckpoint) -> None:
        """Append/replace a completed-phase entry and persist (FR-SV-021)."""
        state = self.load_run_state(run_id)
        if state is None:
            state = RunState(runStateVersion=RUN_STATE_VERSION, run_id=run_id, mode="")
        # Replace any prior entry for the same phase; keep canonical order.
        completed = [c for c in state.completed_phases if c.get("phase") != phase.phase]
        completed.append(phase.model_dump())
        completed.sort(key=lambda c: _phase_index(str(c.get("phase", ""))))
        state.completed_phases = completed
        # A freshly (re)completed phase is no longer stale.
        state.stale_phases = [p for p in state.stale_phases if p != phase.phase]
        self._persist_state(state)

    def completed_phase_ids(self, run_id: str) -> set[str]:
        state = self.load_run_state(run_id)
        if state is None:
            return set()
        return {str(c.get("phase")) for c in state.completed_phases}

    # -- rollback ---------------------------------------------------------

    def invalidate_phases(self, run_id: str, phases: list[str]) -> None:
        """Mark phases incomplete + stale and drop their checkpoints (FR-SV-020A/B)."""
        state = self.load_run_state(run_id)
        if state is None:
            return
        drop = set(phases)
        state.completed_phases = [
            c for c in state.completed_phases if str(c.get("phase")) not in drop
        ]
        stale = set(state.stale_phases) | drop
        state.stale_phases = [p for p in PHASE_IDS if p in stale]
        self._persist_state(state)

    # -- resume validation (FR-SV-022A) -----------------------------------

    def earliest_invalid_phase(self, run_id: str) -> str | None:
        """First completed phase whose stored artifacts/checksums no longer hold.

        Returns ``None`` when every completed checkpoint re-validates.
        """
        state = self.load_run_state(run_id)
        if state is None:
            return None
        by_phase = {str(c.get("phase")): c for c in state.completed_phases}
        for phase in PHASE_IDS:
            entry = by_phase.get(phase)
            if entry is None:
                continue
            if not self._checkpoint_valid(entry):
                return phase
        return None

    def _checkpoint_valid(self, entry: dict[str, object]) -> bool:
        checksums = entry.get("checksums") or {}
        if not isinstance(checksums, dict):
            return False
        for rel_path, expected in checksums.items():
            target = self._root / str(rel_path)
            if not target.exists():
                return False
            if compute_checksum(target) != expected:
                return False
        return True


def _phase_index(phase_id: str) -> int:
    try:
        return PHASE_IDS.index(phase_id)
    except ValueError:
        return len(PHASE_IDS)


__all__ = [
    "CheckpointStore",
    "PhaseCheckpoint",
    "compute_checksum",
    "RUN_STATE_VERSION",
]
