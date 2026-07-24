"""Unit tests: docker-isolated test execution (v0.1.4 #25).

The docker CLI seam (``exec_fn``) is faked; assertions are on the exact
command sequence — hardening flags, copy-in/copy-out (no bind mount),
network only during setup, host-side timeout removing the container —
because that sequence IS the security posture.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.verify import DockerError, DockerExecutor, docker_probe

CID = "cid-123"


class _FakeDocker:
    """Records every CLI call; scripted results for the test-command execs."""

    def __init__(self, test_results: list[tuple[int | None, str]] | None = None,
                 fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self._test_results = list(test_results or [(0, "ok")])
        self._fail_on = fail_on  # docker subcommand ("run", "cp", ...) to break

    def __call__(self, args: list[str], timeout_s: float | None = None):
        self.calls.append(list(args))
        sub = args[1]
        if self._fail_on == sub:
            return 1, f"simulated {sub} failure"
        if sub == "run":
            return 0, CID + "\n"
        if sub == "exec" and args[-2] == "-c":  # sh -c <command or setup>
            if self._test_results:
                return self._test_results.pop(0)
            return 0, "ok"
        return 0, ""  # mkdir / cp / rm / network / info

    def subcommands(self) -> list[str]:
        return [c[1] for c in self.calls]


def _executor(tmp_path: pathlib.Path, fake: _FakeDocker, **kwargs) -> DockerExecutor:
    return DockerExecutor(
        image="python:3.11-slim", workspace=tmp_path, run_id="run-1",
        exec_fn=fake, **kwargs,
    )


def test_container_hardening_flags_and_no_network_without_setup(
    tmp_path: pathlib.Path,
) -> None:
    fake = _FakeDocker()
    ex = _executor(tmp_path, fake)
    result = ex.run("pytest -q", timeout_s=60)
    assert result.passed
    run_call = next(c for c in fake.calls if c[1] == "run")
    joined = " ".join(run_call)
    assert "--network none" in joined  # no setup -> never any network
    assert "--cap-drop=ALL" in joined
    assert "--pids-limit" in joined and "--memory" in joined
    assert "no-new-privileges" in joined
    assert "anvil-run=run-1" in joined
    # copy-in/copy-out: sources cp'd in, nothing mounted.
    assert "cp" in fake.subcommands() and "-v" not in joined


def test_setup_runs_once_with_network_then_disconnects(
    tmp_path: pathlib.Path,
) -> None:
    fake = _FakeDocker(test_results=[(0, "installed"), (0, "ok"), (0, "ok")])
    ex = _executor(tmp_path, fake, setup_command="pip install -e . pytest")
    ex.run("pytest -q", timeout_s=60)
    ex.run("pytest -q", timeout_s=60)
    run_call = next(c for c in fake.calls if c[1] == "run")
    assert "bridge" in run_call  # setup needs network at creation...
    subs = fake.subcommands()
    assert subs.count("network") == 1  # ...and is disconnected exactly once
    disconnect_index = subs.index("network")
    setup_index = next(i for i, c in enumerate(fake.calls)
                       if c[1] == "exec" and c[-1] == "pip install -e . pytest")
    assert setup_index < disconnect_index  # disconnect happens after setup
    # Container started once; both rounds copied fresh sources in.
    assert subs.count("run") == 1
    assert subs.count("cp") == 3  # 1 for setup + 1 per test round


def test_red_test_run_is_a_result_not_an_error(tmp_path: pathlib.Path) -> None:
    fake = _FakeDocker(test_results=[(1, "failure in alpha.py")])
    ex = _executor(tmp_path, fake)
    result = ex.run("pytest -q", timeout_s=60)
    assert not result.passed and result.exit_code == 1
    assert "failure in alpha.py" in result.output_tail


def test_timeout_force_removes_container_and_next_run_restarts(
    tmp_path: pathlib.Path,
) -> None:
    fake = _FakeDocker(test_results=[(None, "timed out"), (0, "ok")])
    ex = _executor(tmp_path, fake)
    result = ex.run("pytest -q", timeout_s=5)
    assert result.timed_out and result.exit_code is None
    assert "force-removed" in result.output_tail
    assert fake.subcommands().count("rm") == 1  # never trusted to unwind
    second = ex.run("pytest -q", timeout_s=5)
    assert second.passed
    assert fake.subcommands().count("run") == 2  # fresh container


def test_docker_infrastructure_failure_raises(tmp_path: pathlib.Path) -> None:
    for stage in ("run", "cp"):
        fake = _FakeDocker(fail_on=stage)
        ex = _executor(tmp_path, fake)
        with pytest.raises(DockerError) as excinfo:
            ex.run("pytest -q", timeout_s=60)
        assert f"simulated {stage} failure" in str(excinfo.value)


def test_failed_network_disconnect_fails_closed(tmp_path: pathlib.Path) -> None:
    fake = _FakeDocker(test_results=[(0, "installed")], fail_on="network")
    ex = _executor(tmp_path, fake, setup_command="pip install -e .")
    with pytest.raises(DockerError) as excinfo:
        ex.run("pytest -q", timeout_s=60)  # tests must never run networked
    assert "disconnect" in str(excinfo.value)


def test_close_removes_container_and_is_idempotent(
    tmp_path: pathlib.Path,
) -> None:
    fake = _FakeDocker()
    ex = _executor(tmp_path, fake)
    ex.run("pytest -q", timeout_s=60)
    ex.close()
    ex.close()
    assert fake.subcommands().count("rm") == 1
    rm_call = next(c for c in fake.calls if c[1] == "rm")
    assert CID in rm_call and "-f" in rm_call


def test_probe_reports_reason_when_daemon_down() -> None:
    def down(args, timeout_s=None):  # noqa: ANN001, ANN202
        return 1, "Cannot connect to the Docker daemon"

    reason = docker_probe(down)
    assert reason is not None and "Cannot connect" in reason


def test_probe_none_when_available() -> None:
    def up(args, timeout_s=None):  # noqa: ANN001, ANN202
        assert args[:2] == ["docker", "info"]
        return 0, "27.0.1\n"

    assert docker_probe(up) is None
