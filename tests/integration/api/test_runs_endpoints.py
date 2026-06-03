"""Integration tests: run-control endpoint lifecycle.

Slice 4 (blueprint §5.1 endpoints 1-4; plan §2.4). Drives the HTTP surface over
a real :class:`DevelopmentManager` (stub phase agents) on a temporary workspace:
start -> inspect -> approve/override. Confirms secure-mode gating pauses the run
and that approvals/overrides advance it.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(tmp_path)))


def _start(client: TestClient, mode: str = "gated", profile: str = "restricted") -> str:
    resp = client.post(
        "/v1/runs", json={"mode": mode, "security_profile": profile}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == mode
    assert body["run_id"]
    return body["run_id"]


def test_task_in_request_is_written_to_domain_knowledge(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    resp = client.post(
        "/v1/runs",
        json={
            "mode": "yolo",
            "security_profile": "open",
            "task": "build a CLI calculator",
        },
    )
    assert resp.status_code == 201
    dk = tmp_path / "domain-knowledge" / "background-information.md"
    assert dk.is_file()
    assert "build a CLI calculator" in dk.read_text(encoding="utf-8")


def test_deferred_run_advances_one_phase_at_a_time(client: TestClient) -> None:
    # defer=true starts the run without advancing it (for live progress streaming).
    run_id = client.post(
        "/v1/runs?defer=true", json={"mode": "yolo", "security_profile": "open"}
    ).json()["run_id"]
    initial = client.get(f"/v1/runs/{run_id}").json()
    assert initial["status"] == "running"
    assert initial["completed_phases"] == []

    # Each advance completes exactly one more phase.
    first = client.post(f"/v1/runs/{run_id}/advance").json()
    assert first["completed_phases"] == ["proposal"]
    second = client.post(f"/v1/runs/{run_id}/advance").json()
    assert second["completed_phases"] == ["proposal", "factory-init"]

    # Drive to completion.
    state = second
    for _ in range(20):
        if state["status"] == "completed":
            break
        state = client.post(f"/v1/runs/{run_id}/advance").json()
    assert state["status"] == "completed"
    assert len(state["completed_phases"]) == 12


def test_advance_unknown_run_returns_404(client: TestClient) -> None:
    assert client.post("/v1/runs/ghost/advance").status_code == 404


def test_yolo_run_completes_through_all_phases(client: TestClient) -> None:
    run_id = _start(client, mode="yolo")
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "completed"
    assert state["pending_approval_gate"] is None
    assert state["completed_phases"][0] == "proposal"
    assert state["completed_phases"][-1] == "cleanup"
    assert len(state["completed_phases"]) == 12


def test_secure_run_pauses_at_first_mandatory_gate(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "awaiting_approval"
    assert state["pending_approval_gate"] == "post-proposal"
    # The gated phase has completed but the run is held before the next.
    assert state["completed_phases"] == ["proposal"]


def test_approval_advances_to_next_gate(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    resp = client.post(
        f"/v1/runs/{run_id}/approve",
        json={
            "gateId": "post-proposal",
            "gateName": "Post-Proposal",
            "approved": True,
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 204
    state = client.get(f"/v1/runs/{run_id}").json()
    # Next mandatory secure gate is post-architecture.
    assert state["status"] == "awaiting_approval"
    assert state["pending_approval_gate"] == "post-architecture"


def test_denied_approval_keeps_run_paused(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    resp = client.post(
        f"/v1/runs/{run_id}/approve",
        json={
            "gateId": "post-proposal",
            "gateName": "Post-Proposal",
            "approved": False,
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 204
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["pending_approval_gate"] == "post-proposal"


def test_override_force_advance_bypasses_gate(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    resp = client.post(
        f"/v1/runs/{run_id}/override",
        json={
            "action": "force-advance",
            "reason": "manual go-ahead",
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "accepted",
        "action": "force-advance",
        "targetPhase": None,
    }
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["pending_approval_gate"] == "post-architecture"


def test_override_stop_halts_run(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    resp = client.post(
        f"/v1/runs/{run_id}/override",
        json={"action": "stop", "reason": "abort", "requesterId": "user-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "stop"
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "stopped"


def test_override_rollback_accepts_target_phase(client: TestClient) -> None:
    run_id = _start(client, mode="secure")  # paused at post-proposal
    resp = client.post(
        f"/v1/runs/{run_id}/override",
        json={
            "action": "rollback",
            "targetPhase": "proposal",
            "reason": "redo proposal",
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "rollback"
    assert body["targetPhase"] == "proposal"
    # Re-running re-completes proposal and pauses again at its mandatory gate.
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["pending_approval_gate"] == "post-proposal"


def test_override_rollback_requires_target_phase(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    resp = client.post(
        f"/v1/runs/{run_id}/override",
        json={"action": "rollback", "reason": "redo", "requesterId": "user-1"},
    )
    assert resp.status_code == 400


def test_approve_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs/ghost/approve",
        json={
            "gateId": "post-proposal",
            "gateName": "Post-Proposal",
            "approved": True,
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 404
