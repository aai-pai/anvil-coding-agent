"""Unit tests: intake completeness assessment (#15, FR-INT-004..006/009/010).

Covers the marker-protocol parser, the question/assumption execution modes of
the LLM backend's intake path, the supervisor's clarification-mode selection,
and the stub agent's deterministic pass-through.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.agents.phases import IntakeAgent
from anvil_runtime.core.development_manager import (
    CLARIFICATION_MAX_ROUNDS,
    DevelopmentManager,
)
from anvil_runtime.core.phase_contracts import PhaseInvocationPayload
from anvil_runtime.llm.openrouter_provider import CompletionResponse
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)


class _FakeProvider:
    """Returns a canned completion and records the prompt it was given."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.prompts: list[str] = []

    def complete(self, request) -> CompletionResponse:  # noqa: ANN001
        self.prompts.append(request.prompt)
        return CompletionResponse(
            model=request.model, content=self._content,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


def _run_intake(tmp_path: pathlib.Path, content: str, mode: str):
    provider = _FakeProvider(content)
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    dk = tmp_path / "domain-knowledge"
    dk.mkdir(parents=True, exist_ok=True)
    (dk / "background-information.md").write_text("# App\n\nbuild an app\n", encoding="utf-8")
    session = backend.start(AgentRuntimeConfig(model="m"))
    step = PhaseStep(
        phase="intake", instruction="",
        input_files=["domain-knowledge/background-information.md"],
        output_paths=["domain-knowledge/background-information.md"],
        context={"run_id": "r1", "clarification_mode": mode},
    )
    return backend.run(session, step), provider, tmp_path


def test_parse_intake_extracts_capped_questions(tmp_path: pathlib.Path) -> None:
    backend = LLMBackend(provider=object(), workspace_root=str(tmp_path))
    content = "\n".join(f"QUESTION: q{i}?" for i in range(8)) + "\nASSUMPTION: a1"
    questions, assumptions = backend._parse_intake(content)
    assert questions == [f"q{i}?" for i in range(5)]  # FR-INT-005: cap of 5
    assert assumptions == ["a1"]


def test_complete_marker_yields_no_questions(tmp_path: pathlib.Path) -> None:
    result, _, _ = _run_intake(tmp_path, "INTAKE: complete", mode="questions")
    assert result.status == "success"
    assert result.questions == []
    assert result.assumptions == []
    assert result.artifacts == []


def test_questions_mode_reports_questions_and_writes_nothing(
    tmp_path: pathlib.Path,
) -> None:
    result, _, root = _run_intake(
        tmp_path, "QUESTION: Persist data?\nQUESTION: Which stack?", mode="questions"
    )
    assert result.questions == ["Persist data?", "Which stack?"]
    assert result.artifacts == []
    text = (root / "domain-knowledge" / "background-information.md").read_text(encoding="utf-8")
    assert "Assumptions" not in text


def test_assumptions_mode_appends_to_domain_knowledge(tmp_path: pathlib.Path) -> None:
    # FR-INT-010: gaps become recorded assumptions in the file; never questions.
    result, _, root = _run_intake(
        tmp_path,
        "QUESTION: should be ignored?\nASSUMPTION: No persistence.\nASSUMPTION: Plain HTML.",
        mode="assumptions",
    )
    assert result.questions == []  # assumption mode never pauses a run
    assert result.assumptions == ["No persistence.", "Plain HTML."]
    text = (root / "domain-knowledge" / "background-information.md").read_text(encoding="utf-8")
    assert "## Assumptions" in text
    assert "- No persistence." in text
    assert result.artifacts == ["domain-knowledge/background-information.md"]


def test_intake_prompt_carries_instructions_and_mode(tmp_path: pathlib.Path) -> None:
    provider = _FakeProvider("INTAKE: complete")
    backend = LLMBackend(
        provider=provider, workspace_root=str(tmp_path),
        instructions="Default stack: plain HTML.",
    )
    session = backend.start(AgentRuntimeConfig(model="m"))
    backend.run(session, PhaseStep(
        phase="intake", instruction="", context={"clarification_mode": "questions"},
    ))
    prompt = provider.prompts[0]
    assert "Standing instructions" in prompt  # FR-INT-006
    assert "QUESTION:" in prompt
    assert "ASSUMPTION:" not in prompt


def test_clarification_mode_selection(tmp_path: pathlib.Path) -> None:
    # FR-INT-009/010: yolo or an exhausted round budget forces assumption mode.
    mgr = DevelopmentManager(workspace_root=str(tmp_path))

    class _Ctx:
        mode = "gated"
        clarification_round = 0

    assert mgr._clarification_mode(_Ctx()) == "questions"
    _Ctx.mode = "yolo"
    assert mgr._clarification_mode(_Ctx()) == "assumptions"
    _Ctx.mode = "secure"
    _Ctx.clarification_round = CLARIFICATION_MAX_ROUNDS
    assert mgr._clarification_mode(_Ctx()) == "assumptions"


def test_stub_intake_agent_is_deterministic_pass_through(tmp_path: pathlib.Path) -> None:
    # FR-INT-004: stub mode reports success, no questions, no writes.
    event = IntakeAgent().run(PhaseInvocationPayload(phase_name="intake"))
    assert event.status == "success"
    assert event.questions == []
    assert event.artifact_paths == []
