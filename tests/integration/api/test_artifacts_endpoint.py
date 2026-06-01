"""Integration tests: artifact lookup endpoint.

Slice 4 (blueprint §5.1 endpoint 6; plan §2.4). Confirms ``GET
/v1/artifacts/{phase}`` reports an existing artifact's path, checksum, and
generated-at time, and returns ``404`` for directory-only phases, unknown
phases, and not-yet-generated artifacts.
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture()
def client(workspace: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(workspace)))


def test_returns_artifact_metadata_for_generated_phase(
    client: TestClient, workspace: pathlib.Path
) -> None:
    content = b"# Architecture\n"
    (workspace / "docs" / "architecture.md").write_bytes(content)

    resp = client.get("/v1/artifacts/architecture")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "architecture"
    assert body["path"] == "docs/architecture.md"
    assert body["checksum"] == hashlib.sha256(content).hexdigest()
    assert body["generatedAt"]  # ISO timestamp from file mtime


def test_directory_only_phase_has_no_document_artifact(client: TestClient) -> None:
    # `implementation` owns only `src/`; there is no single document artifact.
    assert client.get("/v1/artifacts/implementation").status_code == 404


def test_not_yet_generated_artifact_returns_404(client: TestClient) -> None:
    # `blueprint` is a known phase, but no file was written to the workspace.
    assert client.get("/v1/artifacts/blueprint").status_code == 404


def test_unknown_phase_returns_404(client: TestClient) -> None:
    assert client.get("/v1/artifacts/not-a-phase").status_code == 404
