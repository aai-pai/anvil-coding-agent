"""Unit tests: pinned sampling temperature (v0.1.3 follow-up).

Motivated by the Commit0 tinydb variance measurement (24/201 vs 78/201 across
two identical one-shot runs): the runtime never sent a temperature, so every
completion sampled at the provider default. `ANVIL_TEMPERATURE` /
`temperature` pins it for reproducible measurement runs; unset keeps the
historical no-temperature request byte-for-byte.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.llm.openrouter_provider import CompletionRequest, HttpxTransport
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)


class _CapturingProvider:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)

        class _Response:
            content = "## Problem Statement\n\nbody"
            finish_reason = "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        return _Response()


class _CapturingClient:
    def __init__(self) -> None:
        self.payloads = []

    def post(self, url, json, headers):  # noqa: A002,ANN001
        self.payloads.append(json)

        class _Resp:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None: ...

            @staticmethod
            def json() -> dict:
                return {"choices": [{"message": {"content": "ok"},
                                     "finish_reason": "stop"}],
                        "usage": {}}

        return _Resp()


def _run_phases(backend: LLMBackend) -> None:
    session = backend.start(AgentRuntimeConfig(model="test-model"))
    backend.run(session, PhaseStep(phase="specification", instruction="x",
                                   output_paths=["docs/spec.md"]))
    backend.run(session, PhaseStep(phase="implementation", instruction="x",
                                   output_paths=["src/"]))
    backend.run(session, PhaseStep(phase="intake", instruction="x",
                                   output_paths=["domain-knowledge/background-information.md"]))


def test_default_requests_carry_no_temperature(tmp_path: pathlib.Path) -> None:
    provider = _CapturingProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    _run_phases(backend)
    assert all(r.temperature is None for r in provider.requests)


def test_pinned_temperature_reaches_every_request(tmp_path: pathlib.Path) -> None:
    provider = _CapturingProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path),
                         temperature=0.0)
    _run_phases(backend)
    assert provider.requests, "phases must have issued completions"
    assert all(r.temperature == 0.0 for r in provider.requests)


def test_transport_payload_includes_temperature_only_when_set() -> None:
    client = _CapturingClient()
    transport = HttpxTransport(client=client)
    transport.complete(CompletionRequest(model="m", prompt="p"), api_key="k")
    transport.complete(CompletionRequest(model="m", prompt="p", temperature=0.0),
                       api_key="k")
    assert "temperature" not in client.payloads[0]  # historical request shape
    assert client.payloads[1]["temperature"] == 0.0  # 0 is a meaningful value


def test_env_override_reaches_backend(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setenv("ANVIL_TEMPERATURE", "0")
    from anvil_runtime.app import _build_real_manager
    from anvil_runtime.security.secret_adapter import SecretAdapter
    from anvil_runtime.state.event_bus import EventBus

    manager = _build_real_manager(
        str(tmp_path), None, EventBus(str(tmp_path)),
        SecretAdapter(provided_key="offline"), execution_mode="offline-llm",
    )
    backend = manager._executor._bridge._adapter._backend
    assert backend._temperature == 0.0


def test_unset_env_keeps_provider_default(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.delenv("ANVIL_TEMPERATURE", raising=False)
    from anvil_runtime.app import _build_real_manager
    from anvil_runtime.security.secret_adapter import SecretAdapter
    from anvil_runtime.state.event_bus import EventBus

    manager = _build_real_manager(
        str(tmp_path), None, EventBus(str(tmp_path)),
        SecretAdapter(provided_key="offline"), execution_mode="offline-llm",
    )
    backend = manager._executor._bridge._adapter._backend
    assert backend._temperature is None
