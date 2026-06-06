"""Unit tests for the checkpoint store. Slice 2 (FR-SV-021/022/022A)."""

from __future__ import annotations

import pathlib

from anvil_runtime.state.checkpoint_store import (
    CheckpointStore,
    PhaseCheckpoint,
    compute_checksum,
)


def test_initialize_and_load_run_state(tmp_path: pathlib.Path) -> None:
    store = CheckpointStore(tmp_path)
    store.initialize_run("run-1", "secure")
    state = store.load_run_state("run-1")
    assert state is not None
    assert state.run_id == "run-1"
    assert state.mode == "secure"
    assert store.load_run_state("missing") is None


def test_save_phase_completion_orders_canonically(tmp_path: pathlib.Path) -> None:
    store = CheckpointStore(tmp_path)
    store.initialize_run("run-1", "yolo")
    store.save_phase_completion("run-1", PhaseCheckpoint(phase="specification", completed_at="t2"))
    store.save_phase_completion("run-1", PhaseCheckpoint(phase="proposal", completed_at="t1"))
    state = store.load_run_state("run-1")
    assert [c["phase"] for c in state.completed_phases] == ["proposal", "specification"]
    assert store.completed_phase_ids("run-1") == {"proposal", "specification"}


def test_earliest_invalid_phase_none_when_no_checksums(tmp_path: pathlib.Path) -> None:
    store = CheckpointStore(tmp_path)
    store.initialize_run("run-1", "yolo")
    store.save_phase_completion("run-1", PhaseCheckpoint(phase="proposal", completed_at="t"))
    assert store.earliest_invalid_phase("run-1") is None


def test_earliest_invalid_phase_detects_modified_and_missing(tmp_path: pathlib.Path) -> None:
    store = CheckpointStore(tmp_path)
    store.initialize_run("run-1", "yolo")
    artifact = tmp_path / "docs" / "proposal.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("original", encoding="utf-8")
    checksum = compute_checksum(artifact)
    store.save_phase_completion(
        "run-1",
        PhaseCheckpoint(phase="proposal", completed_at="t", checksums={"docs/proposal.md": checksum}),
    )
    # Valid initially.
    assert store.earliest_invalid_phase("run-1") is None
    # Modified -> invalid.
    artifact.write_text("tampered", encoding="utf-8")
    assert store.earliest_invalid_phase("run-1") == "proposal"
    # Missing -> invalid.
    artifact.unlink()
    assert store.earliest_invalid_phase("run-1") == "proposal"


def test_invalidate_phases_marks_stale(tmp_path: pathlib.Path) -> None:
    store = CheckpointStore(tmp_path)
    store.initialize_run("run-1", "yolo")
    store.save_phase_completion("run-1", PhaseCheckpoint(phase="proposal", completed_at="t"))
    store.save_phase_completion("run-1", PhaseCheckpoint(phase="factory-init", completed_at="t"))
    store.invalidate_phases("run-1", ["factory-init"])
    state = store.load_run_state("run-1")
    assert store.completed_phase_ids("run-1") == {"proposal"}
    assert "factory-init" in state.stale_phases
