"""E2E: secure-mode approval journey over the HTTP surface.

Slice 4 (blueprint §5.1, §7.3; plan §2.4). Drives a full secure-mode run through
the public API exactly as the VS Code extension would: start the run, then repeat
"inspect state -> approve the pending gate" until the run completes. Asserts the
four mandatory secure gates were each encountered and the 12-phase pipeline
finished.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app
from anvil_runtime.core.phase_contracts import PHASE_IDS

MANDATORY_GATES = ["post-proposal", "post-architecture", "post-blueprint", "pre-deployment"]


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(tmp_path)))


def test_secure_run_requires_each_mandatory_gate_then_completes(
    client: TestClient,
) -> None:
    run_id = client.post(
        "/v1/runs", json={"mode": "secure", "security_profile": "restricted"}
    ).json()["run_id"]

    encountered_gates: list[str] = []
    # Bounded loop: at most one approval per phase plus slack.
    for _ in range(len(PHASE_IDS) + 4):
        state = client.get(f"/v1/runs/{run_id}").json()
        if state["status"] == "completed":
            break
        assert state["status"] == "awaiting_approval", state
        gate = state["pending_approval_gate"]
        encountered_gates.append(gate)
        resp = client.post(
            f"/v1/runs/{run_id}/approve",
            json={
                "gateId": gate,
                "gateName": gate.replace("-", " ").title(),
                "approved": True,
                "requesterId": "e2e-user",
            },
        )
        assert resp.status_code == 204
    else:  # pragma: no cover - loop should always break on completion
        pytest.fail("secure run did not complete within the expected gate budget")

    final = client.get(f"/v1/runs/{run_id}").json()
    assert final["status"] == "completed"
    assert len(final["completed_phases"]) == len(PHASE_IDS)
    # Each immutable secure gate was presented for approval, in order.
    assert encountered_gates == MANDATORY_GATES


def test_secure_journey_emits_approval_events(client: TestClient) -> None:
    run_id = client.post(
        "/v1/runs", json={"mode": "secure", "security_profile": "restricted"}
    ).json()["run_id"]

    # Approve the first gate so at least one ApprovalGranted is on the stream.
    state = client.get(f"/v1/runs/{run_id}").json()
    client.post(
        f"/v1/runs/{run_id}/approve",
        json={
            "gateId": state["pending_approval_gate"],
            "gateName": "Post Proposal",
            "approved": True,
            "requesterId": "e2e-user",
        },
    )

    body = client.get(f"/v1/runs/{run_id}/events").text
    assert "ApprovalRequired" in body
    assert "ApprovalGranted" in body
