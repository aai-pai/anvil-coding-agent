"""E2E: per-run workspace isolation (#9, FR-RUN-001..004) — regression for FR-001.

A fresh `build` prompt, submitted while the base workspace already holds unrelated
canonical artifacts, must build the requested project in its own isolated run
workspace and leave the pre-existing artifacts untouched.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


def test_fresh_build_is_isolated_from_existing_artifacts(tmp_path: pathlib.Path) -> None:
    base = tmp_path
    # Pre-existing UNRELATED canonical artifacts at the base (the FR-001 trap).
    (base / "docs").mkdir()
    (base / "docs" / "proposal.md").write_text("ORIGINAL UNRELATED PROPOSAL", encoding="utf-8")
    (base / "domain-knowledge").mkdir()
    (base / "domain-knowledge" / "background-information.md").write_text(
        "Build the Anvil factory itself.", encoding="utf-8"
    )

    client = TestClient(create_app(workspace_root=str(base), execution_mode="offline-llm"))
    resp = client.post(
        "/v1/runs",
        json={
            "mode": "yolo",
            "security_profile": "open",
            "task": "build a cli that converts usd to cents",
        },
    )
    assert resp.status_code == 201

    # The run executed in its own isolated runs/<date>-<slug>/ workspace.
    runs = sorted((base / "runs").glob("*"))
    assert len(runs) == 1
    run_ws = runs[0]

    # The prompt and generated artifacts live in the run workspace.
    bg = (run_ws / "domain-knowledge" / "background-information.md").read_text(encoding="utf-8")
    assert "usd to cents" in bg
    assert (run_ws / "docs" / "proposal.md").is_file()

    # The pre-existing unrelated artifacts at the base are untouched (isolation).
    assert (base / "docs" / "proposal.md").read_text(encoding="utf-8") == "ORIGINAL UNRELATED PROPOSAL"
    assert (base / "domain-knowledge" / "background-information.md").read_text(
        encoding="utf-8"
    ) == "Build the Anvil factory itself."
