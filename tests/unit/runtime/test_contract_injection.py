"""Unit tests: verbatim contract injection into phase prompts (v0.1.3 #20).

The contract block must reach EVERY phase prompt verbatim (with the fixed
binding preamble), the context part must stay a normal intake/proposal-only
input, an unmarkered file must behave exactly as v0.1.2, and an over-cap
contract must fail at intake — never be clipped.
"""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.contract import CONTRACT_PREAMBLE
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)

DOMAIN_REL = "domain-knowledge/background-information.md"

MARKERED = textwrap.dedent("""\
    # Build the widget tool

    <!-- anvil:contract -->

    - PINNED_FACT: the function is `count_issues(text) -> dict`
    <!-- anvil:context -->

    CTX_ONLY_FACT: widgets were invented in 1953.
    """)


class _CapturingProvider:
    def __init__(self, content: str = "## Problem Statement\n\nbody") -> None:
        self.requests = []
        self._content = content

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)
        content = self._content

        class _Response:
            finish_reason = "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        _Response.content = content
        return _Response()


def _backend(tmp_path: pathlib.Path, **kwargs) -> tuple[LLMBackend, _CapturingProvider]:
    provider = kwargs.pop("provider", None) or _CapturingProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path), **kwargs)
    return backend, provider


def _write_domain(tmp_path: pathlib.Path, text: str) -> None:
    target = tmp_path / DOMAIN_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _run(backend: LLMBackend, phase: str, outputs: list[str],
         inputs: list[str] | None = None, context: dict | None = None):
    session = backend.start(AgentRuntimeConfig(model="test-model"))
    return backend.run(session, PhaseStep(
        phase=phase, instruction="do it", output_paths=outputs,
        input_files=list(inputs or []), context=dict(context or {}),
    ))


def test_contract_verbatim_in_every_phase_prompt(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "proposal.md").write_text("proposal body", encoding="utf-8")
    backend, provider = _backend(tmp_path)

    _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL])
    _run(backend, "proposal", ["docs/proposal.md"], inputs=[DOMAIN_REL])
    _run(backend, "specification", ["docs/spec.md"], inputs=["docs/proposal.md"])
    _run(backend, "implementation", ["src/"], inputs=["docs/plan.md"])
    _run(backend, "cleanup", ["docs/phase-summary-log.md"], inputs=[])

    assert len(provider.requests) == 5
    for request in provider.requests:
        assert "PINNED_FACT: the function is `count_issues(text) -> dict`" \
            in request.prompt
        assert CONTRACT_PREAMBLE in request.prompt


def test_context_travels_only_to_intake_and_proposal(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "proposal.md").write_text("proposal body", encoding="utf-8")
    backend, provider = _backend(tmp_path)

    _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL])
    _run(backend, "proposal", ["docs/proposal.md"], inputs=[DOMAIN_REL])
    _run(backend, "specification", ["docs/spec.md"], inputs=["docs/proposal.md"])

    intake, proposal, spec = provider.requests
    assert "CTX_ONLY_FACT" in intake.prompt
    assert "CTX_ONLY_FACT" in proposal.prompt
    assert "CTX_ONLY_FACT" not in spec.prompt
    # The contract is injected once, never duplicated through the input read.
    assert intake.prompt.count("PINNED_FACT") == 1
    assert proposal.prompt.count("PINNED_FACT") == 1


def test_unmarkered_file_keeps_v012_prompts(tmp_path: pathlib.Path) -> None:
    text = "# Task\n\nplain prose task, PLAIN_FACT included\n"
    _write_domain(tmp_path, text)
    backend, provider = _backend(tmp_path)
    _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL])
    _run(backend, "proposal", ["docs/proposal.md"], inputs=[DOMAIN_REL])
    for request in provider.requests:
        assert CONTRACT_PREAMBLE not in request.prompt
        assert "PLAIN_FACT" in request.prompt


def test_over_cap_contract_fails_at_intake(tmp_path: pathlib.Path) -> None:
    big = ("<!-- anvil:contract -->\n" + ("PIN " * 200) + "\n<!-- anvil:context -->\n")
    _write_domain(tmp_path, big)
    backend, provider = _backend(tmp_path, contract_max_chars=100)
    result = _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL])
    assert result.status == "failure"
    assert "ANVIL_CONTRACT_MAX_CHARS" in result.failure_reason
    assert provider.requests == []  # failed before any completion was spent


def test_contract_is_exempt_from_input_char_limit(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    backend, provider = _backend(tmp_path, input_char_limit=10)
    _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL])
    # Context got truncated to 10 chars, but the pinned fact still arrives whole.
    assert "PINNED_FACT: the function is `count_issues(text) -> dict`" \
        in provider.requests[0].prompt


def test_assumptions_append_into_contract_block(tmp_path: pathlib.Path) -> None:
    from anvil_runtime.contract import split_contract

    _write_domain(tmp_path, MARKERED)
    provider = _CapturingProvider(content="ASSUMPTION: no persistence needed")
    backend, _ = _backend(tmp_path, provider=provider)
    result = _run(backend, "intake", [DOMAIN_REL], inputs=[DOMAIN_REL],
                  context={"clarification_mode": "assumptions"})
    assert result.status == "success"
    updated = (tmp_path / DOMAIN_REL).read_text(encoding="utf-8")
    split = split_contract(updated)
    assert "no persistence needed" in split.contract
    assert "no persistence needed" not in split.context
    # Re-resolution (next phase prompt) reflects the appended binding fact.
    _run(backend, "specification", ["docs/spec.md"], inputs=[])
    assert "no persistence needed" in provider.requests[-1].prompt


def test_env_override_reaches_backend(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setenv("ANVIL_CONTRACT_MAX_CHARS", "12345")
    from anvil_runtime.app import _build_real_manager
    from anvil_runtime.security.secret_adapter import SecretAdapter
    from anvil_runtime.state.event_bus import EventBus

    manager = _build_real_manager(
        str(tmp_path), None, EventBus(str(tmp_path)),
        SecretAdapter(provided_key="offline"), execution_mode="offline-llm",
    )
    backend = manager._executor._bridge._adapter._backend
    assert backend._contract_max_chars == 12345
