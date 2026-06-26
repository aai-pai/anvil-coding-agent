"""Integration test: a phase failure writes a failure record (#FR, FR-REC-001/005).

Uses the stub executor + artifact validator so the proposal phase reports an output
it never writes -> validation fails -> the supervisor writes an FR per failure.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.state.event_bus import EventBus


def test_failure_writes_failure_record(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    manager = DevelopmentManager(
        workspace_root=str(tmp_path),
        event_bus=bus,
        artifact_validator=ArtifactValidator(workspace_root=str(tmp_path), event_bus=bus),
    )
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)

    # The proposal never validates (stub writes nothing) -> run escalates.
    assert progress.status == "escalated"

    records = sorted((tmp_path / "docs" / "failure_records").glob("FR-*.md"))
    assert records  # at least one FR written
    assert records[0].name.startswith("FR-001-")
    text = records[0].read_text(encoding="utf-8")
    assert started.run_id in text          # FR-REC-004
    assert "proposal" in text
    assert "**Status:** Open" in text

    # Every failure event (incl. the retry) produces its own record -> sequenced.
    if len(records) > 1:
        assert records[1].name.startswith("FR-002-")
