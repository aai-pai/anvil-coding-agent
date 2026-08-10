"""E2E: full run over the REST API with the real execution pipeline (offline).

Post-v0.1.0 integration. Drives ``create_app(execution_mode="offline-llm")`` —
the same wiring as ``ANVIL_EXECUTION_MODE=real`` but with the offline LLM
transport (no API key, no network) — through the HTTP surface the VS Code
extension uses, and confirms real artifacts are produced and served.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(
        create_app(workspace_root=str(tmp_path), execution_mode="offline-llm")
    )


def test_yolo_run_produces_real_artifacts(client: TestClient, tmp_path: pathlib.Path) -> None:
    started = client.post(
        "/v1/runs", json={"mode": "yolo", "security_profile": "open"}
    )
    assert started.status_code == 201
    run_id = started.json()["run_id"]

    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "completed"
    assert len(state["completed_phases"]) == 13

    # Real artifacts were written to the workspace through the pipeline.
    assert (tmp_path / "docs" / "proposal.md").is_file()
    assert (tmp_path / "docs" / "spec.md").is_file()

    # And are served by the artifacts endpoint with a real checksum.
    artifact = client.get("/v1/artifacts/architecture")
    assert artifact.status_code == 200
    assert artifact.json()["path"] == "docs/architecture.md"
    assert len(artifact.json()["checksum"]) == 64  # sha-256 hex


def test_execution_mode_is_exposed(client: TestClient) -> None:
    # The app records its execution mode for diagnostics.
    app = create_app(execution_mode="offline-llm")
    assert app.state.execution_mode == "offline-llm"
