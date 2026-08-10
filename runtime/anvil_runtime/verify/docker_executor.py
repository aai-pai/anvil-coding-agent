"""Docker-isolated external-test execution (v0.1.4 #25).

The safety-motivated executor behind ``testExecutor: docker``: the
user-configured verification command runs inside a hardened, long-lived
container instead of on the host. The isolation decisions (recorded in the
v0.1.4 background information):

* **Copy-in/copy-out, no bind mount** — sources are ``docker cp``'d into the
  container before every round; only exit code and output come back, so the
  container can never write to the host workspace.
* **Network only during setup** — ``testSetupCommand`` (e.g. ``pip install
  -e . pytest``) runs once with network; the container is disconnected
  before any test round. With no setup command the container is created
  with ``--network=none`` outright.
* **Resource caps + dropped capabilities** — a runaway test becomes a
  contained OOM, not a host problem.
* **Host-side timeout** — a timed-out container is force-removed, never
  trusted to unwind on its own; the next round starts fresh.

Driven through the docker CLI via ``subprocess`` (no new dependency); the
CLI seam (``exec_fn``) is injectable for tests. Docker itself being broken
or absent raises :class:`DockerError` — an infrastructure failure must
surface as a step failure with a clear reason, never be mistaken for a red
test run and never silently skip verification.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

from anvil_runtime.verify.runner import PROMPT_TAIL_CHARS, TestRunResult

WORKDIR = "/workspace"
DEFAULT_MEMORY = "2g"
DEFAULT_CPUS = "2"
DEFAULT_PIDS_LIMIT = 256
# Infra commands (run/cp/mkdir/rm) are fast or broken — keep them bounded.
INFRA_TIMEOUT_S = 120
# Setup (dependency install) is the one legitimately slow infra step.
SETUP_TIMEOUT_S = 600
PROBE_TIMEOUT_S = 15
_ERROR_TAIL = 300


class DockerError(RuntimeError):
    """Docker infrastructure failure (daemon, CLI, container lifecycle)."""


def _default_exec(args: list[str], timeout_s: float | None = None):
    """Run a docker CLI command; (returncode, output), None code on timeout."""
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        raise DockerError("docker CLI not found on PATH")
    except subprocess.TimeoutExpired:
        return None, f"docker command timed out after {timeout_s}s"


def docker_probe(exec_fn=None) -> str | None:  # noqa: ANN001
    """None when docker is usable, else a human-readable reason."""
    runner = exec_fn or _default_exec
    try:
        code, output = runner(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            PROBE_TIMEOUT_S,
        )
    except DockerError as exc:
        return str(exc)
    if code != 0:
        detail = output.strip()[-_ERROR_TAIL:] or "no output"
        return f"docker daemon unavailable: {detail}"
    return None


class DockerExecutor:
    """One long-lived hardened container per verification pass.

    ``run`` copies the current workspace in and execs the command; repair
    rounds pay only the copy + exec, never container start or setup again
    (unless a timeout forced a fresh container). ``close`` must always be
    called (the adapter does so in a ``finally``); containers are labeled
    ``anvil-run=<run_id>`` so leaked ones are identifiable.
    """

    def __init__(
        self,
        image: str,
        workspace: str | pathlib.Path,
        setup_command: str | None = None,
        run_id: str = "",
        exec_fn=None,  # noqa: ANN001
        memory: str = DEFAULT_MEMORY,
        cpus: str = DEFAULT_CPUS,
        pids_limit: int = DEFAULT_PIDS_LIMIT,
    ) -> None:
        self._image = image
        self._workspace = pathlib.Path(workspace)
        self._setup = setup_command
        self._run_id = run_id
        self._exec = exec_fn or _default_exec
        self._memory = memory
        self._cpus = cpus
        self._pids_limit = pids_limit
        self._cid: str | None = None

    def run(
        self, command: str, timeout_s: float, copy_out_rel: str | None = None
    ) -> TestRunResult:
        """Copy the workspace in and run ``command``; never raises on a red
        test — :class:`DockerError` is reserved for docker itself failing.

        ``copy_out_rel`` (FR-JL-002): a workspace-relative report path to
        copy back after the run — the only copy-out beyond exit code and
        output. Best-effort: a command that died before writing it must
        degrade downstream, not fail here.
        """
        self._ensure_container()
        self._copy_in()
        code, output = self._exec(
            ["docker", "exec", "-w", WORKDIR, self._cid, "sh", "-c", command],
            timeout_s,
        )
        if code is not None and copy_out_rel:
            rel = copy_out_rel.replace("\\", "/")
            host_target = self._workspace / copy_out_rel
            host_target.parent.mkdir(parents=True, exist_ok=True)
            self._exec(
                ["docker", "cp", f"{self._cid}:{WORKDIR}/{rel}",
                 str(host_target)],
                INFRA_TIMEOUT_S,
            )
        if code is None:
            # Host-side timeout: the container may hold a wedged process —
            # remove it; the next round (if any) starts fresh.
            self.close()
            return TestRunResult(
                exit_code=None, timed_out=True,
                output_tail=(
                    f"external test command timed out after {timeout_s}s "
                    "(container force-removed)"
                ),
            )
        return TestRunResult(
            exit_code=code, output_tail=output[-PROMPT_TAIL_CHARS:]
        )

    def close(self) -> None:
        if self._cid:
            self._exec(["docker", "rm", "-f", self._cid], INFRA_TIMEOUT_S)
            self._cid = None

    # -- lifecycle ---------------------------------------------------------

    def _ensure_container(self) -> None:
        if self._cid:
            return
        args = [
            "docker", "run", "-d",
            "--label", f"anvil-run={self._run_id}",
            "--memory", self._memory,
            "--cpus", self._cpus,
            "--pids-limit", str(self._pids_limit),
            "--cap-drop=ALL",
            "--security-opt", "no-new-privileges",
        ]
        # Setup alone needs the network (dependency install); it is created
        # on the explicit default bridge so the post-setup disconnect below
        # has a known network to detach. No setup -> never any network.
        args += ["--network", "bridge"] if self._setup else ["--network", "none"]
        args += [self._image, "sleep", "infinity"]
        code, output = self._exec(args, INFRA_TIMEOUT_S)
        if code != 0:
            raise DockerError(
                f"could not start test container from image {self._image!r}: "
                + output.strip()[-_ERROR_TAIL:]
            )
        self._cid = output.strip().splitlines()[-1].strip()
        self._must(
            ["docker", "exec", self._cid, "mkdir", "-p", WORKDIR],
            "create container workdir",
        )
        if self._setup:
            self._copy_in()
            self._must(
                ["docker", "exec", "-w", WORKDIR, self._cid,
                 "sh", "-c", self._setup],
                f"setup command {self._setup!r}",
                timeout_s=SETUP_TIMEOUT_S,
            )
            # Fail-closed: tests must never run with network access.
            self._must(
                ["docker", "network", "disconnect", "bridge", self._cid],
                "disconnect network after setup",
            )

    def _copy_in(self) -> None:
        source = str(self._workspace) + os.sep + "."
        self._must(
            ["docker", "cp", source, f"{self._cid}:{WORKDIR}"],
            "copy workspace into container",
        )

    def _must(
        self, args: list[str], what: str, timeout_s: float = INFRA_TIMEOUT_S
    ) -> None:
        code, output = self._exec(args, timeout_s)
        if code != 0:
            raise DockerError(
                f"docker step failed ({what}): "
                + (output.strip()[-_ERROR_TAIL:] or "no output")
            )


__all__ = [
    "DockerError",
    "DockerExecutor",
    "docker_probe",
    "WORKDIR",
    "DEFAULT_MEMORY",
    "DEFAULT_CPUS",
    "DEFAULT_PIDS_LIMIT",
]
