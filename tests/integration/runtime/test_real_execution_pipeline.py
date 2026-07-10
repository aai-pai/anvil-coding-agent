"""Integration tests: real (LLM-backed) execution pipeline.

Post-v0.1.0 integration. Verifies the HttpxTransport request shaping, the
LLMBackend artifact writing, and the BridgeExecutor + ArtifactValidator wiring in
the supervisor — all without network access (offline transport / fake httpx).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.agents.phase_invocation import BridgeExecutor, build_invocation_payload
from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS, PHASE_IDS
from anvil_runtime.llm.openrouter_provider import (
    CompletionRequest,
    HttpxTransport,
    OfflineTransport,
    OpenRouterProvider,
)
from anvil_runtime.llm.model_router import ModelRouter
from anvil_runtime.llm.usage_tracker import UsageTracker
from anvil_runtime.sdk.openhands_adapter import LLMBackend, OpenHandsAdapter
from anvil_runtime.sdk.session_bridge import SessionBridge
from anvil_runtime.security.secret_adapter import SecretAdapter
from anvil_runtime.state.event_bus import EventBus


# -- HttpxTransport (real call shape, fake client) --------------------------


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse({
            "choices": [{"message": {"content": "# Generated\n\nreal content"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        })


def test_httpx_transport_shapes_request_and_parses_response() -> None:
    client = _FakeHttpClient()
    transport = HttpxTransport(client=client)
    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="k-123"), transport=transport
    )
    resp = provider.complete(CompletionRequest(model="gemma-4", prompt="hi", max_tokens=64))

    assert resp.content == "# Generated\n\nreal content"
    assert resp.usage["total_tokens"] == 20
    call = client.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["json"]["model"] == "gemma-4"
    assert call["json"]["messages"][0]["content"] == "hi"
    assert call["headers"]["Authorization"] == "Bearer k-123"  # key forwarded


# -- LLMBackend writes validated artifacts ----------------------------------


def test_llm_backend_writes_validated_document(tmp_path: pathlib.Path) -> None:
    provider = OpenRouterProvider(secret_adapter=SecretAdapter(provided_key="k"))
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=LLMBackend(provider, str(tmp_path))),
        workspace_root=str(tmp_path),
    )
    payload = build_invocation_payload(PHASE_CONTRACTS["proposal"])
    event = bridge.execute_phase(payload, subtask="planning")

    assert event.status == "success"
    assert event.artifact_paths == ["docs/proposal.md"]
    written = tmp_path / "docs" / "proposal.md"
    assert written.is_file()
    # The written document passes artifact validation (metadata + sections).
    result = ArtifactValidator(workspace_root=str(tmp_path)).validate(
        "proposal", ["docs/proposal.md"]
    )
    assert result.valid is True


# -- Unusable completions fail the step (never placeholder "success") -------


class _CannedProvider:
    """Provider stand-in returning a fixed completion."""

    def __init__(self, content: str, finish_reason: str | None = None) -> None:
        from anvil_runtime.llm.openrouter_provider import CompletionResponse

        self._response = CompletionResponse(
            model="m", content=content, usage={"total_tokens": 1},
            finish_reason=finish_reason,
        )

    def complete(self, req: CompletionRequest):
        return self._response


def test_empty_llm_response_fails_doc_phase(tmp_path: pathlib.Path) -> None:
    backend = LLMBackend(_CannedProvider(""), str(tmp_path))
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=backend), workspace_root=str(tmp_path)
    )
    event = bridge.execute_phase(build_invocation_payload(PHASE_CONTRACTS["proposal"]))
    assert event.status == "failure"
    assert "empty" in (event.failure_reason or "")
    assert not (tmp_path / "docs" / "proposal.md").exists()  # nothing written


def test_truncated_llm_response_fails_code_phase(tmp_path: pathlib.Path) -> None:
    backend = LLMBackend(
        _CannedProvider("=== FILE: src/main.py ===\nprint(", finish_reason="length"),
        str(tmp_path),
    )
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=backend), workspace_root=str(tmp_path)
    )
    event = bridge.execute_phase(
        build_invocation_payload(PHASE_CONTRACTS["implementation"])
    )
    assert event.status == "failure"
    assert "truncated" in (event.failure_reason or "")
    assert not (tmp_path / "src" / "main.py").exists()  # partial file not written


# -- Full supervisor run with real pipeline (offline transport) -------------


def test_supervisor_real_pipeline_writes_and_validates_all_phases(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="k"), transport=OfflineTransport()
    )
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=LLMBackend(provider, str(tmp_path))),
        workspace_root=str(tmp_path),
    )
    manager = DevelopmentManager(
        workspace_root=str(tmp_path),
        event_bus=bus,
        executor=BridgeExecutor(bridge),
        artifact_validator=ArtifactValidator(workspace_root=str(tmp_path), event_bus=bus),
    )

    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)

    assert progress.status == "completed"
    assert len(progress.completed_phases) == len(PHASE_IDS)
    # Real artifacts exist on disk and were checksummed.
    assert (tmp_path / "docs" / "proposal.md").is_file()
    assert (tmp_path / "docs" / "architecture.md").is_file()
    # No validation failures were raised during the run.
    assert not any(e.eventType == "ArtifactValidationFailed" for e in bus.read_all())


def test_routing_and_usage_events_carry_run_id(tmp_path: pathlib.Path) -> None:
    # FR-EVT-001/002: across a real (offline) run, ModelRouteSelected and
    # TokenUsageReported carry the active, non-empty run id.
    bus = EventBus(str(tmp_path))
    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="k"), transport=OfflineTransport()
    )
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=LLMBackend(provider, str(tmp_path))),
        model_router=ModelRouter(event_bus=bus),
        usage_tracker=UsageTracker(event_bus=bus),
        workspace_root=str(tmp_path),
    )
    manager = DevelopmentManager(
        workspace_root=str(tmp_path),
        event_bus=bus,
        executor=BridgeExecutor(bridge),
        artifact_validator=ArtifactValidator(workspace_root=str(tmp_path), event_bus=bus),
    )
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    manager.run_until_pause(started.run_id)

    telemetry = [
        e for e in bus.read_all()
        if e.eventType in ("ModelRouteSelected", "TokenUsageReported")
    ]
    assert telemetry  # routing/usage events were emitted
    assert any(e.eventType == "ModelRouteSelected" for e in telemetry)
    assert all(e.runId == started.run_id for e in telemetry)
    assert started.run_id  # non-empty


def test_invalid_artifact_fails_phase(tmp_path: pathlib.Path) -> None:
    # A stub executor reports artifact_paths but writes nothing -> validation
    # fails -> the phase fails (retries then escalates).
    bus = EventBus(str(tmp_path))
    manager = DevelopmentManager(
        workspace_root=str(tmp_path),
        event_bus=bus,
        artifact_validator=ArtifactValidator(workspace_root=str(tmp_path), event_bus=bus),
    )
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)

    # The first phase never validates (no file written by the stub) -> escalated.
    assert progress.status == "escalated"
    assert any(e.eventType == "ArtifactValidationFailed" for e in bus.read_all())
