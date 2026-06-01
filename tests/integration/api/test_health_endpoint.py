"""Integration tests: health endpoint.

Slice 4 (blueprint §5.1 endpoint 7; plan §2.4). Confirms ``GET /v1/health``
reports liveness, the runtime name, and a per-subsystem check map.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(tmp_path)))


def test_health_reports_ok_and_runtime_name(client: TestClient) -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["runtime"] == "anvil-runtime"


def test_health_exposes_subsystem_checks(client: TestClient) -> None:
    checks = client.get("/v1/health").json()["checks"]
    assert checks["config"] == "ok"
    # MCP discovery and OpenHands are wired in Slice 5; honestly pending now.
    assert checks["mcp_discovery"] == "pending"
    assert checks["openhands"] == "pending"
