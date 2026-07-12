"""Unit tests: configurable completion token budgets (v0.1.3 #19).

The v0.1.2 hardcoded ``max_tokens`` (400 intake / 1500 doc / 4000 code) made
large tasks unbuildable: a spec that cannot fit the budget fails with
``finish_reason=length`` on every retry and escalates (observed on the
Commit0 tinydb run). The budgets are now config fields with env overrides,
mirroring #18's input-side limit.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)


class _CapturingProvider:
    """Records each CompletionRequest and returns a minimal valid response."""

    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)

        class _Response:
            content = "## Problem Statement\n\ngenerated body"
            finish_reason = "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        return _Response()


def _run_phase(backend: LLMBackend, phase: str, outputs: list[str]) -> None:
    session = backend.start(AgentRuntimeConfig(model="test-model"))
    backend.run(session, PhaseStep(phase=phase, instruction="do it",
                                   output_paths=outputs))


def test_default_budgets_match_v012_values(tmp_path: pathlib.Path) -> None:
    provider = _CapturingProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    _run_phase(backend, "specification", ["docs/spec.md"])
    _run_phase(backend, "implementation", ["src/"])
    _run_phase(backend, "intake", ["domain-knowledge/background-information.md"])
    by_phase = {r.phase: r.max_tokens for r in provider.requests}
    assert by_phase["specification"] == 1500
    assert by_phase["implementation"] == 4000
    assert by_phase["intake"] == 400


def test_constructor_overrides_reach_requests(tmp_path: pathlib.Path) -> None:
    provider = _CapturingProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path),
                         intake_max_tokens=900, doc_max_tokens=6000,
                         code_max_tokens=16000)
    _run_phase(backend, "specification", ["docs/spec.md"])
    _run_phase(backend, "implementation", ["src/"])
    _run_phase(backend, "intake", ["domain-knowledge/background-information.md"])
    by_phase = {r.phase: r.max_tokens for r in provider.requests}
    assert by_phase["specification"] == 6000
    assert by_phase["implementation"] == 16000
    assert by_phase["intake"] == 900


def test_env_overrides_flow_through_app_wiring(tmp_path: pathlib.Path,
                                               monkeypatch) -> None:
    # env override > config field > default (#18 precedence, output side).
    monkeypatch.setenv("ANVIL_DOC_MAX_TOKENS", "7000")
    monkeypatch.setenv("ANVIL_CODE_MAX_TOKENS", "20000")
    monkeypatch.setenv("ANVIL_INTAKE_MAX_TOKENS", "800")
    from anvil_runtime.app import _build_real_manager
    from anvil_runtime.security.secret_adapter import SecretAdapter
    from anvil_runtime.state.event_bus import EventBus

    manager = _build_real_manager(
        str(tmp_path), None, EventBus(str(tmp_path)),
        SecretAdapter(provided_key="offline"), execution_mode="offline-llm",
    )
    backend = manager._executor._bridge._adapter._backend
    assert backend._doc_max_tokens == 7000
    assert backend._code_max_tokens == 20000
    assert backend._intake_max_tokens == 800
