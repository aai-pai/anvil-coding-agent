"""Integration tests: SSE event stream.

Slice 4 (blueprint §5.1 endpoint 5; plan §2.4). Confirms ``GET
/v1/runs/{run_id}/events`` serves ``text/event-stream`` and replays the run's
audit envelopes (one JSON ``EventEnvelope`` per SSE message).
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(workspace_root=str(tmp_path)))


def _parse_sse_data(body: str) -> list[dict]:
    """Extract JSON payloads from ``data:`` lines of an SSE body."""
    events: list[dict] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_event_stream_content_type_and_payloads(client: TestClient) -> None:
    run_id = client.post(
        "/v1/runs", json={"mode": "yolo", "security_profile": "open"}
    ).json()["run_id"]

    resp = client.get(f"/v1/runs/{run_id}/events")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_data(resp.text)
    assert events, "expected at least one streamed event"
    # Every envelope belongs to this run and carries the audit fields.
    assert all(ev["runId"] == run_id for ev in events)
    types = {ev["eventType"] for ev in events}
    assert "SupervisorStarted" in types
    assert "RunCompleted" in types


def test_event_stream_only_contains_requested_run(client: TestClient) -> None:
    run_a = client.post(
        "/v1/runs", json={"mode": "yolo", "security_profile": "open"}
    ).json()["run_id"]
    run_b = client.post(
        "/v1/runs", json={"mode": "yolo", "security_profile": "open"}
    ).json()["run_id"]

    events_b = _parse_sse_data(client.get(f"/v1/runs/{run_b}/events").text)
    assert events_b
    assert all(ev["runId"] == run_b for ev in events_b)
    assert run_a != run_b


def test_event_stream_unknown_run_returns_404(client: TestClient) -> None:
    assert client.get("/v1/runs/missing/events").status_code == 404
