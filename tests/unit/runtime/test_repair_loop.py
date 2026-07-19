"""Unit tests: bounded external-test repair loop (v0.1.4 #23).

Verification by execution is strictly opt-in: no configured command means
v0.1.3 behavior byte-for-byte. With a command: compile smoke first, then run
→ map failures to implicated files → per-file repair → re-validate against
the contract → re-run, bounded by repairMaxRounds; exhausted rounds fail the
step with the last output tail. Executing workspace code is an
`open`-profile capability, refused at intake otherwise.
"""

from __future__ import annotations

import pathlib
import sys
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

# The verification command: green iff src/alpha.py contains FIXED; red output
# names alpha.py (exercising the failure->file mapping).
CHECK_SCRIPT = textwrap.dedent("""\
    import pathlib, sys
    text = pathlib.Path("src/alpha.py").read_text(encoding="utf-8")
    if "FIXED" in text:
        sys.exit(0)
    print("failure in alpha.py: marker missing")
    sys.exit(1)
    """)

GOOD_ALPHA = "def alpha():\n    return 'FIXED'\n"
BAD_ALPHA = "def alpha():\n    return 'not yet'\n"
GOOD_BETA = "def beta():\n    return 2\n"


class _ScriptedProvider:
    def __init__(self, script: list[str]) -> None:
        self.requests = []
        self._script = list(script)

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)
        content = self._script.pop(0) if self._script else GOOD_ALPHA

        class _Response:
            finish_reason = "stop"
            usage = {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}

        _Response.content = content
        return _Response()


class _Bus:
    def __init__(self) -> None:
        self.events = []

    def emit(self, envelope) -> None:  # noqa: ANN001
        self.events.append(envelope)

    def types(self) -> list[str]:
        return [e.eventType for e in self.events]


def _stage(tmp_path: pathlib.Path) -> str:
    target = tmp_path / DOMAIN_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(MANIFEST_DOMAIN, encoding="utf-8")
    (tmp_path / "check.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    return f"{sys.executable} check.py"


def _backend(tmp_path: pathlib.Path, script: list[str], command: str | None,
             **kwargs):
    bus = _Bus()
    provider = _ScriptedProvider(script)
    backend = LLMBackend(
        provider=provider, workspace_root=str(tmp_path), event_bus=bus,
        external_test_command=command, **kwargs,
    )
    return backend, provider, bus


def _run_impl(backend: LLMBackend, profile: str = "open"):
    session = backend.start(AgentRuntimeConfig(model="m", security_profile=profile))
    return backend.run(session, PhaseStep(
        phase="implementation", instruction="implement",
        output_paths=["src/"], input_files=["docs/plan.md"],
        context={"run_id": "run-1"},
    ))


def test_no_command_means_no_execution(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path)
    backend, provider, bus = _backend(tmp_path, [BAD_ALPHA, GOOD_BETA], None)
    result = _run_impl(backend)
    assert result.status == "success"
    assert len(provider.requests) == 2  # generation only, no repair
    assert not any(t.startswith(("ExternalTests", "RepairRound"))
                   for t in bus.types())


def test_green_first_try_passes_without_repair(tmp_path: pathlib.Path) -> None:
    command = _stage(tmp_path)
    backend, provider, bus = _backend(tmp_path, [GOOD_ALPHA, GOOD_BETA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    assert len(provider.requests) == 2
    assert "ExternalTestsPassed" in bus.types()
    assert "RepairRoundStarted" not in bus.types()


def test_red_then_green_repairs_only_implicated_file(tmp_path: pathlib.Path) -> None:
    command = _stage(tmp_path)
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    assert len(provider.requests) == 3  # 2 generations + 1 repair
    assert "`src/alpha.py`" in provider.requests[2].prompt
    assert "REPAIR mode" in provider.requests[2].prompt
    assert "failure in alpha.py" in provider.requests[2].prompt  # tail included
    started = [e for e in bus.events if e.eventType == "RepairRoundStarted"]
    assert started[0].data["implicated"] == ["src/alpha.py"]
    # beta was never regenerated (content is exactly what generation wrote;
    # _strip_fences trims the trailing newline at write time).
    assert (tmp_path / "src" / "beta.py").read_text(encoding="utf-8") \
        == GOOD_BETA.rstrip("\n")
    assert bus.types().count("ExternalTestsFailed") == 1
    assert bus.types().count("ExternalTestsPassed") == 1


def test_rounds_are_bounded_and_failure_carries_tail(tmp_path: pathlib.Path) -> None:
    command = _stage(tmp_path)
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, BAD_ALPHA, BAD_ALPHA], command,
        repair_max_rounds=2)
    result = _run_impl(backend)
    assert result.status == "failure"
    assert "still failing after 2 repair round(s)" in result.failure_reason
    assert "failure in alpha.py" in result.failure_reason
    assert len(provider.requests) == 4  # 2 gen + 2 repair rounds x 1 file


def test_compile_smoke_repairs_syntax_before_any_test_run(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    broken = "def alpha(:\n    FIXED\n"  # syntax error
    backend, provider, bus = _backend(
        tmp_path, [broken, GOOD_BETA, GOOD_ALPHA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    round_zero = [e for e in bus.events if e.eventType == "RepairRoundStarted"
                  and e.data.get("round") == 0]
    assert round_zero and round_zero[0].data["stage"] == "compile"
    assert "SyntaxError" in provider.requests[2].prompt
    # After the round-zero fix the first command run is already green.
    assert bus.types().count("ExternalTestsFailed") == 0


def test_restricted_profile_refuses_command_at_intake(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    backend, provider, _bus = _backend(tmp_path, [], command)
    session = backend.start(AgentRuntimeConfig(model="m",
                                               security_profile="restricted"))
    result = backend.run(session, PhaseStep(
        phase="intake", instruction="assess",
        output_paths=[DOMAIN_REL], input_files=[DOMAIN_REL],
    ))
    assert result.status == "failure"
    assert "restricted" in result.failure_reason
    assert "externalTestCommand" in result.failure_reason
    assert provider.requests == []  # refused before any completion


def test_open_profile_intake_proceeds(tmp_path: pathlib.Path) -> None:
    command = _stage(tmp_path)
    backend, provider, _bus = _backend(tmp_path, ["INTAKE: complete"], command)
    session = backend.start(AgentRuntimeConfig(model="m", security_profile="open"))
    result = backend.run(session, PhaseStep(
        phase="intake", instruction="assess",
        output_paths=[DOMAIN_REL], input_files=[DOMAIN_REL],
    ))
    assert result.status == "success"


def test_repair_that_unpins_contract_fails_the_round(
    tmp_path: pathlib.Path,
) -> None:
    # Manifest pins alpha() in alpha.py; the repair drops it -> the round is
    # red on contract grounds even though the check command would pass.
    pinned = MANIFEST_DOMAIN.replace(
        '"symbols": []',
        '"symbols": [{"qualname": "alpha", "signature": "def alpha()",'
        ' "file": "alpha.py"}]',
    )
    (tmp_path / DOMAIN_REL).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / DOMAIN_REL).write_text(pinned, encoding="utf-8")
    (tmp_path / "check.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    command = f"{sys.executable} check.py"
    renamed = "def renamed():\n    return 'FIXED'\n"  # green cmd, broken contract
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, renamed], command, repair_max_rounds=1)
    result = _run_impl(backend)
    assert result.status == "failure"
    assert "contract violations introduced by repair" in result.failure_reason
    assert "missing symbol: alpha" in result.failure_reason


def test_phase_progress_events_cover_generate_and_repair(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    backend, _provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command)
    _run_impl(backend)
    progress = [e.data for e in bus.events if e.eventType == "PhaseProgress"]
    stages = [(p["stage"], p["artifact"]) for p in progress]
    assert ("generate", "src/alpha.py") in stages
    assert ("generate", "src/beta.py") in stages
    assert ("repair", "src/alpha.py") in stages


def test_env_wiring_reaches_backend(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.setenv("ANVIL_TEST_COMMAND", "pytest -q tests")
    monkeypatch.setenv("ANVIL_REPAIR_MAX_ROUNDS", "3")
    monkeypatch.setenv("ANVIL_TEST_TIMEOUT_S", "120")
    from anvil_runtime.app import _build_real_manager
    from anvil_runtime.security.secret_adapter import SecretAdapter
    from anvil_runtime.state.event_bus import EventBus

    manager = _build_real_manager(
        str(tmp_path), None, EventBus(str(tmp_path)),
        SecretAdapter(provided_key="offline"), execution_mode="offline-llm",
    )
    backend = manager._executor._bridge._adapter._backend
    assert backend._test_command == "pytest -q tests"
    assert backend._repair_max_rounds == 3
    assert backend._test_timeout_s == 120
