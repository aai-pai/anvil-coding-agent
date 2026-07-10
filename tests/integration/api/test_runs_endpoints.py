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


def test_resume_route_recovers_secure_run_after_server_restart(
    tmp_path: pathlib.Path,
) -> None:
    # First server: secure run pauses at post-proposal, then the server "dies".
    client1 = TestClient(create_app(workspace_root=str(tmp_path)))
    run_id = _start(client1, mode="secure")
    assert client1.get(f"/v1/runs/{run_id}").json()["status"] == "awaiting_approval"

    # Second server over the same workspace: the run is gone from memory...
    client2 = TestClient(create_app(workspace_root=str(tmp_path)))
    assert client2.get(f"/v1/runs/{run_id}").status_code == 404
    # ...until /resume rebuilds it from the checkpoint, pause included.
    resp = client2.post(f"/v1/runs/{run_id}/resume")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "awaiting_approval"
    assert body["pending_approval_gate"] == "post-proposal"
    assert "proposal" in body["completed_phases"]
    # The run is addressable again through the normal routes.
    assert client2.get(f"/v1/runs/{run_id}").status_code == 200


def test_resume_route_finds_isolated_task_run_by_scanning(
    tmp_path: pathlib.Path,
) -> None:
    # A task run lives in runs/<date>-<slug>/ under the server root.
    client1 = TestClient(create_app(workspace_root=str(tmp_path)))
    resp = client1.post(
        "/v1/runs",
        json={"mode": "yolo", "security_profile": "open", "task": "tiny tool"},
    )
    run_id = resp.json()["run_id"]

    client2 = TestClient(create_app(workspace_root=str(tmp_path)))
    resumed = client2.post(f"/v1/runs/{run_id}/resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "completed"  # yolo run had finished


def test_resume_route_unknown_run_returns_404(tmp_path: pathlib.Path) -> None:
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    assert client.post("/v1/runs/ghost/resume").status_code == 404


def test_task_in_request_is_written_to_isolated_run_workspace(
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
    # #9: the task is written into an isolated runs/<date>-<slug>/ workspace, not the
    # server root.
    matches = list(tmp_path.glob("runs/*/domain-knowledge/background-information.md"))
    assert len(matches) == 1
    assert "build a CLI calculator" in matches[0].read_text(encoding="utf-8")
    assert not (tmp_path / "domain-knowledge").exists()


def test_instructions_resolved_event_records_path(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    # #14 (FR-INS-004): the audit trail records which instructions governed the run.
    (tmp_path / "anvil-instructions.md").write_text(
        "Default to Python.", encoding="utf-8"
    )
    resp = client.post(
        "/v1/runs",
        json={"mode": "yolo", "security_profile": "open", "task": "build a tool"},
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]
    events_files = list(tmp_path.glob("runs/*/logs/events.jsonl"))
    assert len(events_files) == 1
    lines = events_files[0].read_text(encoding="utf-8").splitlines()
    resolved = [l for l in lines if '"InstructionsResolved"' in l]
    assert len(resolved) == 1
    assert "anvil-instructions.md" in resolved[0]
    assert run_id in resolved[0]


def test_instructions_absent_event_records_null(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    client.post(
        "/v1/runs",
        json={"mode": "yolo", "security_profile": "open", "task": "build a tool"},
    )
    events_files = list(tmp_path.glob("runs/*/logs/events.jsonl"))
    resolved = [
        l
        for l in events_files[0].read_text(encoding="utf-8").splitlines()
        if '"InstructionsResolved"' in l
    ]
    assert len(resolved) == 1
    assert '"path": null' in resolved[0] or '"path":null' in resolved[0]


def test_source_path_build_copies_into_isolated_workspace(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    # #17 (FR-SRC-001/002): the file is copied into a fresh runs/<date>-<slug>/
    # workspace whose slug derives from the first heading.
    project = tmp_path / "my-project" / "domain-knowledge"
    project.mkdir(parents=True)
    source = project / "background-information.md"
    source.write_text(
        "# Modern To-Do List\n\nA to-do list app in plain HTML.\n", encoding="utf-8"
    )
    (project / "anvil-instructions.md").write_text(
        "Default to a single-file HTML app.", encoding="utf-8"
    )

    resp = client.post(
        "/v1/runs",
        json={"mode": "yolo", "security_profile": "open", "source_path": str(source)},
    )
    assert resp.status_code == 201, resp.text
    matches = list(tmp_path.glob("runs/*/domain-knowledge/background-information.md"))
    assert len(matches) == 1
    run_dk = matches[0].parent
    assert "modern-to-do-list" in run_dk.parent.name
    assert "A to-do list app in plain HTML." in matches[0].read_text(encoding="utf-8")
    # FR-INS-005: the sibling instructions file travels with the request.
    assert (run_dk / "anvil-instructions.md").read_text(encoding="utf-8") == (
        "Default to a single-file HTML app."
    )
    # The source project itself is untouched (isolation preserved).
    assert not (tmp_path / "my-project" / "runs").exists()


def test_source_path_missing_returns_400(client: TestClient, tmp_path: pathlib.Path) -> None:
    resp = client.post(
        "/v1/runs",
        json={
            "mode": "yolo",
            "security_profile": "open",
            "source_path": str(tmp_path / "nope.md"),
        },
    )
    assert resp.status_code == 400
    assert "source_path" in resp.json()["detail"]
    assert not (tmp_path / "runs").exists()  # FR-SRC-003: nothing is created


def test_task_and_source_path_are_mutually_exclusive(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "intent.md"
    source.write_text("# X\n", encoding="utf-8")
    resp = client.post(
        "/v1/runs",
        json={
            "mode": "yolo",
            "security_profile": "open",
            "task": "build a thing",
            "source_path": str(source),
        },
    )
    assert resp.status_code == 400  # FR-SRC-004


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
    assert first["completed_phases"] == ["intake"]
    second = client.post(f"/v1/runs/{run_id}/advance").json()
    assert second["completed_phases"] == ["intake", "proposal"]

    # Drive to completion.
    state = second
    for _ in range(20):
        if state["status"] == "completed":
            break
        state = client.post(f"/v1/runs/{run_id}/advance").json()
    assert state["status"] == "completed"
    assert len(state["completed_phases"]) == 13


def test_advance_unknown_run_returns_404(client: TestClient) -> None:
    assert client.post("/v1/runs/ghost/advance").status_code == 404


def test_per_run_workspace_writes_under_chosen_folder(tmp_path: pathlib.Path) -> None:
    # The chosen `workspace` is the base; the run isolates under <base>/runs/<slug>/.
    server_root = tmp_path / "server"
    project = tmp_path / "my-project"
    client = TestClient(create_app(workspace_root=str(server_root)))

    resp = client.post(
        "/v1/runs",
        json={
            "mode": "yolo",
            "security_profile": "open",
            "task": "build a converter",
            "workspace": str(project),
        },
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # #9: isolated under <chosen workspace>/runs/<date>-<slug>/, not at the chosen
    # folder root nor the server root.
    matches = list(project.glob("runs/*/domain-knowledge/background-information.md"))
    assert len(matches) == 1
    assert not (project / "domain-knowledge").exists()
    assert not (server_root / "domain-knowledge").exists()

    # Run-scoped routes resolve to the per-run manager.
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "completed"
    assert len(state["completed_phases"]) == 13


def test_yolo_run_completes_through_all_phases(client: TestClient) -> None:
    run_id = _start(client, mode="yolo")
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "completed"
    assert state["pending_approval_gate"] is None
    assert state["completed_phases"][0] == "intake"
    assert state["completed_phases"][-1] == "cleanup"
    assert len(state["completed_phases"]) == 13


def test_secure_run_pauses_at_first_mandatory_gate(client: TestClient) -> None:
    run_id = _start(client, mode="secure")
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "awaiting_approval"
    assert state["pending_approval_gate"] == "post-proposal"
    # The gated phase has completed but the run is held before the next.
    assert state["completed_phases"] == ["intake", "proposal"]


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


def test_approving_wrong_gate_returns_409(client: TestClient) -> None:
    # Pre-approving a future mandatory gate must be rejected, not recorded.
    run_id = _start(client, mode="secure")  # paused at post-proposal
    resp = client.post(
        f"/v1/runs/{run_id}/approve",
        json={
            "gateId": "pre-deployment",
            "gateName": "Pre-Deployment",
            "approved": True,
            "requesterId": "user-1",
        },
    )
    assert resp.status_code == 409
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "awaiting_approval"
    assert state["pending_approval_gate"] == "post-proposal"


def test_approval_without_pending_gate_returns_409(client: TestClient) -> None:
    # An empty-gate approval must not resume a run that is not awaiting one
    # (a stray chat `yes` used to revive stopped runs this way).
    run_id = _start(client, mode="secure")
    client.post(
        f"/v1/runs/{run_id}/override",
        json={"action": "stop", "reason": "halt", "requesterId": "user-1"},
    )
    resp = client.post(
        f"/v1/runs/{run_id}/approve",
        json={"gateId": "", "gateName": "", "approved": True, "requesterId": "user-1"},
    )
    assert resp.status_code == 409
    assert client.get(f"/v1/runs/{run_id}").json()["status"] == "stopped"


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
