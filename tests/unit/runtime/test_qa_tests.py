"""Unit tests: the qa phase emits executable tests (v0.1.5 #30)."""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)

QA_OUTPUTS = ["docs/qa-test-plan.md", "tests/unit/", "tests/integration/",
              "tests/e2e/"]

DOMAIN = textwrap.dedent("""\
    # Task

    <!-- anvil:contract -->
    Implement a calculator.
    <!-- anvil:context -->
    prose
    """)


class _Provider:
    def __init__(self, script: list[str] | None = None) -> None:
        self.requests = []
        self._script = list(script or [])

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)
        content = self._script.pop(0) if self._script else "def test_x():\n    assert True\n"

        class _Response:
            finish_reason = "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        _Response.content = content
        return _Response()


def _stage(tmp_path: pathlib.Path) -> None:
    (tmp_path / "domain-knowledge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "domain-knowledge/background-information.md").write_text(
        DOMAIN, encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src/calculator.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8")


def _qa_step() -> PhaseStep:
    return PhaseStep(
        phase="qa", instruction="write tests", output_paths=QA_OUTPUTS,
        input_files=["docs/plan.md"], context={"run_id": "run-1"},
    )


def _run(tmp_path: pathlib.Path, **kwargs):
    provider = _Provider(kwargs.pop("script", None))
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path),
                         **kwargs)
    session = backend.start(AgentRuntimeConfig(model="m",
                                               security_profile="open"))
    return backend.run(session, _qa_step()), provider


def test_qa_writes_python_tests_and_no_markdown_under_tests(
    tmp_path: pathlib.Path,
) -> None:
    """The v0.1.4 defect: an identical GENERATED.md in each test directory
    and never a test."""
    _stage(tmp_path)

    result, _provider = _run(tmp_path)

    assert result.status == "success"
    assert (tmp_path / "tests/unit/test_calculator.py").is_file()
    assert not list((tmp_path / "tests").rglob("GENERATED.md"))


def test_qa_still_writes_its_plan_document(tmp_path: pathlib.Path) -> None:
    """Routing qa to the code path must not drop the plan — it is still
    worth producing, and the artifact schema requires it."""
    _stage(tmp_path)

    _run(tmp_path)

    assert (tmp_path / "docs/qa-test-plan.md").is_file()


def test_qa_prompt_is_its_own_mode_not_the_implementation_prompt(
    tmp_path: pathlib.Path,
) -> None:
    """FR-QT-001: the implementation source is the subject under test."""
    _stage(tmp_path)

    _result, provider = _run(tmp_path)

    test_prompts = [r.prompt for r in provider.requests
                    if "QA phase agent" in r.prompt]
    assert test_prompts
    prompt = test_prompts[0]
    assert "Implementation under test:" in prompt
    assert "def add(a, b):" in prompt  # the real source travels
    assert "implementation phase agent" not in prompt.lower()


def test_plan_only_gate_restores_v014_behavior(tmp_path: pathlib.Path) -> None:
    """FR-QT-006: Commit0 runs pin this so their surface is unchanged."""
    _stage(tmp_path)

    result, _provider = _run(tmp_path, qa_tests="plan-only")

    assert result.status == "success"
    assert (tmp_path / "docs/qa-test-plan.md").is_file()
    assert not list((tmp_path / "tests").rglob("*.py"))
    assert (tmp_path / "tests/unit/GENERATED.md").is_file()  # v0.1.4 shape


def test_targets_come_from_the_plan_when_it_names_them(
    tmp_path: pathlib.Path,
) -> None:
    """FR-QT-001: the contract manifest pins src/, so it must not be the
    source of test targets."""
    _stage(tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs/plan.md").write_text(
        "Write tests/unit/test_alpha.py and tests/e2e/test_journey.py.",
        encoding="utf-8")

    _run(tmp_path)

    assert (tmp_path / "tests/unit/test_alpha.py").is_file()
    assert (tmp_path / "tests/e2e/test_journey.py").is_file()


def test_collect_gate_fails_a_phase_whose_tests_do_not_collect(
    tmp_path: pathlib.Path,
) -> None:
    """FR-QT-004: existence and a .py extension are satisfied by three files
    containing `assert True` — collection is the minimum bar."""
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/qa-test-plan.md").write_text(
        "---\nartifactId: a\nphase: qa\ngeneratedAt: t\ntype: QA Test Plan\n"
        "title: t\nderivedFrom: [docs/plan.md]\n---\n\n## Test\n\nbody\n",
        encoding="utf-8")

    validator = ArtifactValidator(workspace_root=str(tmp_path),
                                  qa_collect=lambda root: 0)
    result = validator.validate("qa", ["docs/qa-test-plan.md"])

    assert not result.valid
    assert any(i.kind == "empty" for i in result.issues)


def test_collect_gate_treats_unknown_as_unknown_not_zero(
    tmp_path: pathlib.Path,
) -> None:
    """A missing pytest is a tooling problem, not a failed qa phase."""
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/qa-test-plan.md").write_text(
        "---\nartifactId: a\nphase: qa\ngeneratedAt: t\ntype: QA Test Plan\n"
        "title: t\nderivedFrom: [docs/plan.md]\n---\n\n## Test\n\nbody\n",
        encoding="utf-8")

    validator = ArtifactValidator(workspace_root=str(tmp_path),
                                  qa_collect=lambda root: None)
    result = validator.validate("qa", ["docs/qa-test-plan.md"])

    assert result.valid
