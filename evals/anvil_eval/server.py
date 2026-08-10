"""Optionally spawn a local Anvil runtime server for the duration of a suite.

The harness can also target an already-running server (``--base-url``); this
module exists so ``run --start-server`` is a one-command experience with a
pinned execution mode.
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time

from anvil_eval.client import AnvilClient, AnvilClientError

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RUNTIME_DIR = REPO_ROOT / "runtime"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AnvilServer:
    """A uvicorn subprocess running ``anvil_runtime.app:app`` in a given mode."""

    def __init__(self, execution_mode: str, workspace: pathlib.Path,
                 port: int | None = None, log_path: pathlib.Path | None = None) -> None:
        self.execution_mode = execution_mode
        self.workspace = workspace
        self.port = port or free_port()
        self.log_path = log_path or workspace / "server.log"
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._process: subprocess.Popen | None = None
        self._log_handle = None

    def start(self, wait_s: float = 30.0) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["ANVIL_EXECUTION_MODE"] = self.execution_mode
        # Works with or without `pip install -e runtime` (mirrors start-anvil.ps1).
        env["PYTHONPATH"] = str(RUNTIME_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        self._process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "anvil_runtime.app:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(self.workspace), env=env,
            stdout=self._log_handle, stderr=subprocess.STDOUT,
        )
        client = AnvilClient(self.base_url)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"Anvil server exited early (code {self._process.returncode}); "
                    f"see {self.log_path}"
                )
            try:
                client.health(timeout_s=2.0)
                return
            except AnvilClientError:
                time.sleep(0.5)
        self.stop()
        raise RuntimeError(f"Anvil server did not become healthy within {wait_s}s")

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def __enter__(self) -> "AnvilServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


__all__ = ["AnvilServer", "free_port"]
