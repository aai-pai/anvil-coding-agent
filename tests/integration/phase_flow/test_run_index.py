"""Integration test: OKF run index generation (#16, FR-OKF-003)."""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent


class _DocWritingExecutor:
    """Writes a minimal OKF document for each doc-owning phase."""

    def __init__(self, root: pathlib.Path) -> None:
        self._root = root

    def run(self, agent, payload):  # noqa: ANN001 - matches executor protocol
        artifacts: list[str] = []
        for rel in payload.output_paths:
            if rel.endswith(".md"):
                target = self._root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    f"---\ntype: Test Doc\ntitle: {agent.phase_id}\n"
                    f"description: doc for {agent.phase_id}\n---\n# {agent.phase_id}\n",
                    encoding="utf-8",
                )
                artifacts.append(rel)
        return PhaseCompleteEvent(
            phase_name=agent.phase_id, status="success",
            artifact_paths=artifacts, checksums={}, duration_ms=0,
        )


def test_completed_run_writes_okf_index(tmp_path: pathlib.Path) -> None:
    manager = DevelopmentManager(
        workspace_root=str(tmp_path), executor=_DocWritingExecutor(tmp_path)
    )
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)
    assert progress.status == "completed"

    index = tmp_path / "docs" / "index.md"
    assert index.is_file()
    text = index.read_text(encoding="utf-8")
    # Every doc artifact is listed with its OKF type and description; the index
    # itself is not self-listed.
    assert "[proposal.md](/docs/proposal.md)" in text
    assert "**Test Doc**" in text
    assert "doc for proposal" in text
    assert "[index.md]" not in text
