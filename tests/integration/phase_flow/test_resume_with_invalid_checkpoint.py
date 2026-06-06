"""Integration: resume re-validates checkpoints and rewinds to earliest invalid.

Slice 2 (spec FR-SV-022A).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.state.checkpoint_store import (
    CheckpointStore,
    PhaseCheckpoint,
    compute_checksum,
)


def test_resume_rewinds_to_earliest_invalid_phase(tmp_path: pathlib.Path) -> None:
    # Seed a run with two completed phases; the second references an artifact
    # whose checksum we then break.
    store = CheckpointStore(tmp_path)
    store.initialize_run("seed-run", "yolo")
    store.save_phase_completion("seed-run", PhaseCheckpoint(phase="proposal", completed_at="t1"))

    artifact = tmp_path / "artifact.txt"
    artifact.write_text("good", encoding="utf-8")
    store.save_phase_completion(
        "seed-run",
        PhaseCheckpoint(
            phase="factory-init",
            completed_at="t2",
            checksums={"artifact.txt": compute_checksum(artifact)},
        ),
    )

    # Corrupt the artifact so the factory-init checkpoint no longer validates.
    artifact.write_text("tampered", encoding="utf-8")

    mgr = DevelopmentManager(workspace_root=str(tmp_path))
    plan = mgr.resume_run("seed-run")

    assert plan.resume_from == "factory-init"
    assert "factory-init" in plan.invalidated_phases
    # proposal validated cleanly and is retained as skipped.
    assert "proposal" in plan.skipped_phases
    assert "factory-init" not in plan.skipped_phases
