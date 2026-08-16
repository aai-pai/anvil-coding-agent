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
    monkeypatch.setenv("ANVIL_TEST_EXECUTOR", "docker")
    monkeypatch.setenv("ANVIL_TEST_IMAGE", "python:3.12-slim")
    monkeypatch.setenv("ANVIL_TEST_SETUP_COMMAND", "pip install -e . pytest")
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
    assert backend._test_executor == "docker"
    assert backend._test_image == "python:3.12-slim"
    assert backend._test_setup_command == "pip install -e . pytest"


# -- docker executor at the adapter level (v0.1.4 #25) ----------------------


class _FakeDockerCli:
    """docker CLI seam: probe OK, container lifecycle OK, scripted test runs."""

    def __init__(self, test_results: list[tuple[int | None, str]],
                 probe_ok: bool = True, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self._test_results = list(test_results)
        self._probe_ok = probe_ok
        self._fail_on = fail_on

    def __call__(self, args: list[str], timeout_s: float | None = None):
        self.calls.append(list(args))
        sub = args[1]
        if sub == "info":
            return (0, "27.0\n") if self._probe_ok else (1, "daemon down")
        if self._fail_on == sub:
            return 1, f"simulated {sub} failure"
        if sub == "run":
            return 0, "cid-1\n"
        if sub == "exec" and args[-2] == "-c":
            return self._test_results.pop(0) if self._test_results else (0, "ok")
        return 0, ""

    def subcommands(self) -> list[str]:
        return [c[1] for c in self.calls]


def test_docker_executor_unlocks_restricted_profile_at_intake(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    cli = _FakeDockerCli([])
    backend, provider, _bus = _backend(
        tmp_path, ["INTAKE: complete"], command,
        test_executor="docker", docker_exec_fn=cli)
    session = backend.start(AgentRuntimeConfig(model="m",
                                               security_profile="restricted"))
    result = backend.run(session, PhaseStep(
        phase="intake", instruction="assess",
        output_paths=[DOMAIN_REL], input_files=[DOMAIN_REL],
    ))
    assert result.status == "success"
    assert ["docker", "info", "--format", "{{.ServerVersion}}"] in cli.calls


def test_docker_unavailable_refused_at_intake(tmp_path: pathlib.Path) -> None:
    command = _stage(tmp_path)
    cli = _FakeDockerCli([], probe_ok=False)
    backend, provider, _bus = _backend(
        tmp_path, [], command, test_executor="docker", docker_exec_fn=cli)
    session = backend.start(AgentRuntimeConfig(model="m", security_profile="open"))
    result = backend.run(session, PhaseStep(
        phase="intake", instruction="assess",
        output_paths=[DOMAIN_REL], input_files=[DOMAIN_REL],
    ))
    assert result.status == "failure"
    assert "docker is not usable" in result.failure_reason
    assert "daemon down" in result.failure_reason
    assert provider.requests == []  # refused before any completion


def test_local_refusal_message_names_the_docker_alternative(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    backend, _provider, _bus = _backend(tmp_path, [], command)
    session = backend.start(AgentRuntimeConfig(model="m",
                                               security_profile="restricted"))
    result = backend.run(session, PhaseStep(
        phase="intake", instruction="assess",
        output_paths=[DOMAIN_REL], input_files=[DOMAIN_REL],
    ))
    assert result.status == "failure"
    assert "testExecutor 'docker'" in result.failure_reason


def test_docker_loop_red_then_green_repairs_and_cleans_up(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    cli = _FakeDockerCli([
        (1, "failure in alpha.py: marker missing"),  # round 1: red
        (0, "ok"),                                   # after repair: green
    ])
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command,
        test_executor="docker", docker_exec_fn=cli)
    result = _run_impl(backend)
    assert result.status == "success"
    assert len(provider.requests) == 3  # 2 generations + 1 repair
    assert "DockerExecutorSelected" in bus.types()
    assert bus.types().count("ExternalTestsFailed") == 1
    assert bus.types().count("ExternalTestsPassed") == 1
    subs = cli.subcommands()
    assert subs.count("run") == 1  # one container for the whole pass
    assert subs.count("cp") == 2   # fresh copy-in per round
    assert subs.count("rm") == 1   # always cleaned up


# -- structured localization + interface context (v0.1.4 #26/#27) ----------

# Writes a JUnit report; stdout deliberately never names alpha.py, so any
# implication MUST come from the report's traceback frames (#26), not the
# basename grep.
JUNIT_CHECK_SCRIPT = textwrap.dedent("""\
    import pathlib, sys
    report = pathlib.Path(sys.argv[1])
    report.parent.mkdir(parents=True, exist_ok=True)
    text = pathlib.Path("src/alpha.py").read_text(encoding="utf-8")
    if "FIXED" in text:
        report.write_text("<testsuites><testsuite>"
                          "<testcase classname='t' name='ok'/>"
                          "</testsuite></testsuites>", encoding="utf-8")
        sys.exit(0)
    report.write_text('''<testsuites><testsuite>
    <testcase classname="tests.t" name="test_a">
    <failure message="AssertionError: marker missing">
    frame: alpha.py line 2</failure></testcase>
    <testcase classname="tests.t" name="test_b">
    <failure message="AssertionError: marker missing">
    frame: alpha.py line 2</failure></testcase>
    </testsuite></testsuites>''', encoding="utf-8")
    print("2 tests failed")
    sys.exit(1)
    """)


def _stage_junit(tmp_path: pathlib.Path) -> str:
    _stage(tmp_path)
    (tmp_path / "check_junit.py").write_text(JUNIT_CHECK_SCRIPT,
                                             encoding="utf-8")
    return sys.executable + " check_junit.py {junit_xml}"


def test_clusters_drive_implication_and_prompts(tmp_path: pathlib.Path) -> None:
    command = _stage_junit(tmp_path)
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    # stdout never named alpha.py -> implication came from the report.
    started = [e for e in bus.events if e.eventType == "RepairRoundStarted"]
    assert started[0].data["implicated"] == ["src/alpha.py"]
    assert started[0].data["clusters"] == [
        {"error_type": "failure", "file": "src/alpha.py", "count": 2}]
    prompt = provider.requests[2].prompt
    assert "2 test failure(s) share one root cause" in prompt  # FR-JL-004
    assert "tests.t.test_a" in prompt
    # FR-IC-001/003: sibling interfaces present, bodies absent.
    assert "Interfaces of the OTHER generated files" in prompt
    assert "def beta()" in prompt
    assert "return 2" not in prompt


def test_minimal_context_gates_interfaces_only(tmp_path: pathlib.Path) -> None:
    command = _stage_junit(tmp_path)
    backend, provider, _bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command,
        repair_context="minimal")
    result = _run_impl(backend)
    assert result.status == "success"
    prompt = provider.requests[2].prompt
    assert "Interfaces of the OTHER generated files" not in prompt  # FR-IC-004
    assert "share one root cause" in prompt  # #26 is gated by the token, not this


def test_missing_report_degrades_to_basename_with_warning(
    tmp_path: pathlib.Path,
) -> None:
    # Token present but the command never writes the report; stdout names
    # alpha.py so the basename fallback still localizes.
    _stage(tmp_path)
    (tmp_path / "noreport.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    command = sys.executable + " noreport.py {junit_xml}"
    backend, provider, bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    assert "JunitReportMissing" in bus.types()
    started = [e for e in bus.events if e.eventType == "RepairRoundStarted"]
    assert started[0].data["implicated"] == ["src/alpha.py"]
    assert "clusters" not in started[0].data


def test_repair_prompts_are_persisted_verbatim(tmp_path: pathlib.Path) -> None:
    command = _stage_junit(tmp_path)
    backend, provider, _bus = _backend(
        tmp_path, [BAD_ALPHA, GOOD_BETA, GOOD_ALPHA], command)
    result = _run_impl(backend)
    assert result.status == "success"
    prompt_files = sorted((tmp_path / "logs" / "repair-prompts").glob("*.md"))
    assert [p.name for p in prompt_files] == ["001-src-alpha.py.md"]
    # Byte-for-byte the prompt that was actually sent (requests[2] = repair).
    assert prompt_files[0].read_text(encoding="utf-8") \
        == provider.requests[2].prompt


def test_docker_copies_report_out(tmp_path: pathlib.Path) -> None:
    _stage(tmp_path)
    command = "pytest tests -q --junitxml {junit_xml}"
    cli = _FakeDockerCli([(0, "ok")])
    backend, _provider, _bus = _backend(
        tmp_path, [GOOD_ALPHA, GOOD_BETA], command,
        test_executor="docker", docker_exec_fn=cli)
    result = _run_impl(backend)
    assert result.status == "success"
    copy_outs = [c for c in cli.calls if c[1] == "cp"
                 and "junit-report.xml" in c[2]]
    assert copy_outs and copy_outs[0][2].startswith("cid-1:/workspace/")


def test_docker_infra_failure_fails_step_with_reason_and_cleans_up(
    tmp_path: pathlib.Path,
) -> None:
    command = _stage(tmp_path)
    cli = _FakeDockerCli([], fail_on="cp")
    backend, _provider, _bus = _backend(
        tmp_path, [GOOD_ALPHA, GOOD_BETA], command,
        test_executor="docker", docker_exec_fn=cli)
    result = _run_impl(backend)
    assert result.status == "failure"
    assert "docker test executor failed" in result.failure_reason
    assert "simulated cp failure" in result.failure_reason
    assert cli.subcommands().count("rm") == 1  # finally-cleanup ran


# -- fault-aware localization (v0.1.5 #28/#29) ------------------------------

# The failure names a SYMBOL (`alpha_marker`) and never a source basename —
# the assertion-shaped failure v0.1.4 silently discarded. Test file is
# `test_x.py` on purpose: `test_alpha.py` would contain "alpha.py" and be
# picked up by the basename matcher, hiding what is being tested.
SYMBOL_JUNIT_SCRIPT = textwrap.dedent("""\
    import pathlib, sys
    report = pathlib.Path(sys.argv[1])
    report.parent.mkdir(parents=True, exist_ok=True)
    text = pathlib.Path("src/alpha.py").read_text(encoding="utf-8")
    if "FIXED" in text:
        report.write_text("<testsuites><testsuite>"
                          "<testcase classname='t' name='ok'/>"
                          "</testsuite></testsuites>", encoding="utf-8")
        sys.exit(0)
    report.write_text('''<testsuites><testsuite>
    <testcase classname="tests.test_x" name="test_a">
    <failure message="AssertionError: alpha_marker returned the wrong value">
    tests/test_x.py:9: in test_a</failure></testcase>
    </testsuite></testsuites>''', encoding="utf-8")
    print("1 test failed")
    sys.exit(1)
    """)

ALPHA_SYMBOL = "def alpha_marker():\n    return 'not yet'\n"
ALPHA_FIXED = "def alpha_marker():\n    return 'FIXED'\n"
BETA_USES_ALPHA = "from alpha import alpha_marker\n\ndef beta_entry():\n    return alpha_marker()\n"


def _stage_symbol_junit(tmp_path: pathlib.Path) -> str:
    _stage(tmp_path)
    (tmp_path / "check_symbol.py").write_text(SYMBOL_JUNIT_SCRIPT,
                                              encoding="utf-8")
    return sys.executable + " check_symbol.py {junit_xml}"


def test_symbol_only_failure_is_repaired_not_dropped(
    tmp_path: pathlib.Path,
) -> None:
    """The v0.1.4 loop dropped this cluster silently — 43 of 67 failures in
    the healthiest measured run. It must now reach repair."""
    command = _stage_symbol_junit(tmp_path)
    backend, _provider, bus = _backend(
        tmp_path, [ALPHA_SYMBOL, BETA_USES_ALPHA, ALPHA_FIXED], command,
    )

    result = _run_impl(backend)

    assert result.status == "success"
    assert "RepairRoundStarted" in bus.types()
    assert "UnlocalizedCluster" not in bus.types()
    assert "FIXED" in (tmp_path / "src/alpha.py").read_text(encoding="utf-8")


def test_basename_gate_restores_v014_blindness(tmp_path: pathlib.Path) -> None:
    """FR-FL-007 ablation: with `basename`, the same cluster is unlocalized
    and the loop falls back to regenerating everything, as v0.1.4 did."""
    command = _stage_symbol_junit(tmp_path)
    backend, provider, _bus = _backend(
        tmp_path, [ALPHA_SYMBOL, BETA_USES_ALPHA, ALPHA_FIXED, ALPHA_FIXED],
        command, repair_localization="basename",
    )

    _run_impl(backend)

    # No selection completion is ever issued on the basename path.
    prompts = [r.prompt for r in provider.requests]
    assert not any("Name the ONE most likely" in p for p in prompts)


def test_unlocalized_cluster_is_reported_not_silently_dropped(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-006: a cluster naming nothing indexable still leaves a trace."""
    command = _stage_symbol_junit(tmp_path)
    # Generated code defines no symbol the failure text names.
    backend, _provider, bus = _backend(
        tmp_path,
        ["def unrelated():\n    return 1\n", GOOD_BETA, ALPHA_FIXED],
        command,
    )

    _run_impl(backend)

    assert "UnlocalizedCluster" in bus.types()


def test_selection_is_skipped_when_only_one_candidate(
    tmp_path: pathlib.Path,
) -> None:
    """Architecture §#28 step 4: the unambiguous case must not pay for a
    completion."""
    command = _stage_symbol_junit(tmp_path)
    backend, provider, _bus = _backend(
        tmp_path, [ALPHA_SYMBOL, GOOD_BETA, ALPHA_FIXED], command,
    )

    _run_impl(backend)

    prompts = [r.prompt for r in provider.requests]
    assert not any("Name the ONE most likely" in p for p in prompts)


def test_slices_gate_adds_upstream_bodies_and_interfaces_does_not(
    tmp_path: pathlib.Path,
) -> None:
    """FR-DS-004: the ablation contract is at the prompt level.

    ``alpha.py`` is made to depend on ``beta.py`` so the repaired file has
    an upstream to slice — a leaf file correctly produces no slice block.
    """
    command = _stage_symbol_junit(tmp_path)
    alpha_dep = ("from beta import beta_helper\n\n"
                 "def alpha_marker():\n    return beta_helper()\n")
    beta_helper = "def beta_helper():\n    return 'not yet'\n"
    alpha_dep_fixed = ("from beta import beta_helper\n\n"
                       "def alpha_marker():\n    return 'FIXED'\n")

    backend, provider, _bus = _backend(
        tmp_path, [alpha_dep, beta_helper, alpha_dep_fixed], command,
    )
    _run_impl(backend)
    with_slices = [r.prompt for r in provider.requests
                   if "REPAIR mode" in r.prompt]

    backend2, provider2, _bus2 = _backend(
        tmp_path, [alpha_dep, beta_helper, alpha_dep_fixed], command,
        repair_context="interfaces",
    )
    _run_impl(backend2)
    with_interfaces = [r.prompt for r in provider2.requests
                       if "REPAIR mode" in r.prompt]

    assert with_slices and with_interfaces
    assert any("depends on (read-only" in p for p in with_slices)
    assert not any("depends on (read-only" in p for p in with_interfaces)


# Names symbols from BOTH generated files, so the cluster is ambiguous and
# fault selection (FR-FL-004) has to run.
MULTI_JUNIT_SCRIPT = textwrap.dedent("""\
    import pathlib, sys
    report = pathlib.Path(sys.argv[1])
    report.parent.mkdir(parents=True, exist_ok=True)
    text = pathlib.Path("src/alpha.py").read_text(encoding="utf-8")
    if "FIXED" in text:
        report.write_text("<testsuites><testsuite>"
                          "<testcase classname='t' name='ok'/>"
                          "</testsuite></testsuites>", encoding="utf-8")
        sys.exit(0)
    report.write_text('''<testsuites><testsuite>
    <testcase classname="tests.test_x" name="test_a">
    <failure message="AssertionError: alpha_marker got a bad value from beta_helper">
    tests/test_x.py:9: in test_a</failure></testcase>
    </testsuite></testsuites>''', encoding="utf-8")
    print("1 test failed")
    sys.exit(1)
    """)

ALPHA_DEP = ("from beta import beta_helper\n\n"
             "def alpha_marker():\n    return beta_helper()\n")
BETA_HELPER = "def beta_helper():\n    return 'not yet'\n"
ALPHA_DEP_FIXED = ("from beta import beta_helper\n\n"
                   "def alpha_marker():\n    return 'FIXED'\n")


def _stage_multi_junit(tmp_path: pathlib.Path) -> str:
    _stage(tmp_path)
    (tmp_path / "check_multi.py").write_text(MULTI_JUNIT_SCRIPT,
                                             encoding="utf-8")
    return sys.executable + " check_multi.py {junit_xml}"


def test_ambiguous_cluster_issues_one_selection_completion(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-004: one completion per ambiguous cluster, not per candidate."""
    command = _stage_multi_junit(tmp_path)
    backend, provider, _bus = _backend(
        tmp_path, [ALPHA_DEP, BETA_HELPER, "src/alpha.py", ALPHA_DEP_FIXED],
        command,
    )

    _run_impl(backend)

    selections = [r for r in provider.requests
                  if "Name the ONE most likely" in r.prompt]
    assert len(selections) == 1
    assert selections[0].max_tokens == backend.FAULT_SELECTION_MAX_TOKENS
    # The candidate listing carries the producer-first ordering.
    assert "src/beta.py" in selections[0].prompt


def test_out_of_set_selection_degrades_to_ranked_first_candidate(
    tmp_path: pathlib.Path,
) -> None:
    """FR-FL-004: selection is never a crash path, and FR-FL-003's ranking is
    the defined fallback — which is why it is normative, not advisory."""
    command = _stage_multi_junit(tmp_path)
    backend, _provider, bus = _backend(
        tmp_path,
        [ALPHA_DEP, BETA_HELPER, "I have no idea", ALPHA_DEP_FIXED],
        command,
    )

    result = _run_impl(backend)

    assert "FaultSelectionDegraded" in bus.types()
    assert result.status in ("success", "failure")  # degraded, not crashed


def test_selection_completion_usage_is_accounted(
    tmp_path: pathlib.Path,
) -> None:
    """The extra completion must show up in the step's usage, or the release
    would under-report its own token cost."""
    command = _stage_multi_junit(tmp_path)
    backend, _provider, _bus = _backend(
        tmp_path, [ALPHA_DEP, BETA_HELPER, "src/alpha.py", ALPHA_DEP_FIXED],
        command,
    )

    result = _run_impl(backend)

    # 2 generation + 1 selection + 1 repair completions, 7 tokens each.
    assert result.usage["total_tokens"] == 4 * 7
