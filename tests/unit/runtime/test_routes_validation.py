"""Unit tests: request-body validation on the `/v1` routes.

Slice 4 (blueprint §5.1; plan §2.4). Exercises the FastAPI request-model
boundary — malformed bodies are rejected with ``422`` before any supervisor
logic runs — plus 404 mapping for unknown resources. Uses an app over a
temporary workspace so no repo state is touched.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(tmp_path)))


def test_start_run_rejects_unknown_mode(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs",
        json={"mode": "turbo", "security_profile": "restricted"},
    )
    assert resp.status_code == 422


def test_start_run_rejects_missing_security_profile(client: TestClient) -> None:
    resp = client.post("/v1/runs", json={"mode": "gated"})
    assert resp.status_code == 422


def test_start_run_rejects_unknown_security_profile(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs",
        json={"mode": "gated", "security_profile": "paranoid"},
    )
    assert resp.status_code == 422


def test_approve_rejects_incomplete_body(client: TestClient) -> None:
    # Missing required fields (gateName, approved, requesterId).
    resp = client.post("/v1/runs/anything/approve", json={"gateId": "post-proposal"})
    assert resp.status_code == 422


def test_override_rejects_unknown_action(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs/anything/override",
        json={"action": "nuke", "reason": "x", "requesterId": "u1"},
    )
    assert resp.status_code == 422


def test_get_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.get("/v1/runs/does-not-exist")
    assert resp.status_code == 404


def test_unknown_artifact_phase_returns_404(client: TestClient) -> None:
    resp = client.get("/v1/artifacts/not-a-phase")
    assert resp.status_code == 404
