"""Unit tests: skeleton-aware, per-artifact implementation (v0.1.3 #22).

When the contract manifest or the plan names the output files, the
implementation phase generates ONE completion per file (each under
``codeMaxTokens``), includes an existing target's current source in that
file's prompt, reports per-file usage, and retries a failed file without
regenerating the others. With no derivable file list the v0.1.2
single-completion behavior is preserved exactly.
"""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    LLMBackend,
    PhaseStep,
)

DOMAIN_REL = "domain-knowledge/background-information.md"

MANIFEST_DOMAIN = textwrap.dedent("""\
    # Task

    <!-- anvil:contract -->
    Implement the two modules.

    ```contract-manifest
    {"files": ["alpha.py", "beta.py"], "symbols": []}
    ```
    <!-- anvil:context -->
    prose
    """)


class _ScriptedProvider:
    """Returns scripted (content, finish_reason) tuples in call order."""

    def __init__(self, script: list[tuple[str, str]] | None = None) -> None:
        self.requests = []
        self._script = list(script or [])

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)
        content, finish = (self._script.pop(0) if self._script
                           else ("def generated():\n    return 1\n", "stop"))

        class _Response:
            usage = {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}

        _Response.content = content
        _Response.finish_reason = finish
        return _Response()


class _Bus:
    def __init__(self) -> None:
        self.events = []

    def emit(self, envelope) -> None:  # noqa: ANN001
        self.events.append(envelope)


def _write(tmp_path: pathlib.Path, rel: str, text: str) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _run_impl(backend: LLMBackend, inputs: list[str] = ("docs/plan.md",)):
    session = backend.start(AgentRuntimeConfig(model="test-model"))
    return backend.run(session, PhaseStep(
        phase="implementation", instruction="implement",
        output_paths=["src/"], input_files=list(inputs),
        context={"run_id": "run-1"},
    ))


def test_manifest_files_get_one_completion_each(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    provider = _ScriptedProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    result = _run_impl(backend)
    assert result.status == "success"
    assert result.artifacts == ["src/alpha.py", "src/beta.py"]
    assert len(provider.requests) == 2
    for request in provider.requests:
        assert "exactly ONE file" in request.prompt
        assert request.max_tokens == 4000  # per-file, each under codeMaxTokens
    assert (tmp_path / "src" / "alpha.py").read_text(encoding="utf-8").startswith(
        "def generated()")


def test_existing_target_source_is_in_its_prompt_only(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    _write(tmp_path, "src/alpha.py", "def stub():\n    STUB_SENTINEL = 0\n")
    provider = _ScriptedProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    _run_impl(backend)
    alpha_prompt, beta_prompt = (r.prompt for r in provider.requests)
    assert "STUB_SENTINEL" in alpha_prompt
    assert "complete it IN PLACE" in alpha_prompt
    assert "STUB_SENTINEL" not in beta_prompt
    assert "Current content" not in beta_prompt  # greenfield file: unchanged


def test_plan_named_files_drive_per_artifact_mode(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, "# Task\n\nno markers\n")
    _write(tmp_path, "docs/plan.md",
           "Slice 1 builds `src/x.py`; slice 2 builds `src/y.py`.\n")
    provider = _ScriptedProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    result = _run_impl(backend)
    assert result.artifacts == ["src/x.py", "src/y.py"]
    assert len(provider.requests) == 2


def test_no_file_list_keeps_v012_single_completion(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, "# Task\n\nno markers\n")
    _write(tmp_path, "docs/plan.md", "A plan that names no source files.\n")
    provider = _ScriptedProvider(
        [("=== FILE: src/app.py ===\nprint('hi')\n", "stop")])
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    result = _run_impl(backend)
    assert len(provider.requests) == 1
    assert "=== FILE:" in provider.requests[0].prompt  # old multi-file format
    assert result.artifacts == ["src/app.py"]


def test_failed_file_retries_that_file_only(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    provider = _ScriptedProvider([
        ("alpha ok", "stop"),
        ("beta truncated", "length"),  # first beta attempt fails...
        ("beta ok", "stop"),           # ...and only beta is retried
    ])
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    result = _run_impl(backend)
    assert result.status == "success"
    assert len(provider.requests) == 3
    alpha_calls = [r for r in provider.requests if "`src/alpha.py`" in r.prompt]
    beta_calls = [r for r in provider.requests if "`src/beta.py`" in r.prompt]
    assert len(alpha_calls) == 1  # never regenerated
    assert len(beta_calls) == 2
    assert (tmp_path / "src" / "beta.py").read_text(encoding="utf-8") == "beta ok"


def test_permanently_failing_file_fails_the_step_named(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    provider = _ScriptedProvider([
        ("alpha ok", "stop"),
        ("beta truncated", "length"),
        ("beta truncated again", "length"),
    ])
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    result = _run_impl(backend)
    assert result.status == "failure"
    assert "src/beta.py" in result.failure_reason
    assert "finish_reason=length" in result.failure_reason


def test_code_fences_are_stripped_from_single_file_output(
    tmp_path: pathlib.Path,
) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    provider = _ScriptedProvider([
        ("```python\ndef a():\n    return 1\n```", "stop"),
        ("def b():\n    return 2\n", "stop"),
    ])
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path))
    _run_impl(backend)
    alpha = (tmp_path / "src" / "alpha.py").read_text(encoding="utf-8")
    assert "```" not in alpha
    assert alpha.startswith("def a():")


def test_per_file_usage_reported_on_token_usage_event(
    tmp_path: pathlib.Path,
) -> None:
    _write(tmp_path, DOMAIN_REL, MANIFEST_DOMAIN)
    bus = _Bus()
    provider = _ScriptedProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path),
                         event_bus=bus)
    result = _run_impl(backend)
    usage_events = [e for e in bus.events if e.eventType == "TokenUsageReported"]
    assert [e.data["artifact"] for e in usage_events] == \
        ["src/alpha.py", "src/beta.py"]
    assert all(e.data["total_tokens"] == 12 for e in usage_events)
    assert all(e.runId == "run-1" for e in usage_events)
    # The step aggregate still carries the sum for the phase-level report.
    assert result.usage["total_tokens"] == 24
