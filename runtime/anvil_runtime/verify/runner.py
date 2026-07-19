"""External-test execution for the repair loop (v0.1.4 #23).

Three mechanical pieces, no LLM involvement:

* :func:`run_external_tests` — run the user-configured command in the run
  workspace, bounded by a timeout, capturing output (FR-RL-004/006).
* :func:`compile_smoke` — round-zero syntax check of generated Python
  artifacts; two of five measured v0.1.3 tinydb runs died before a single
  test could run, so the cheapest failures are caught without spending a
  command run (FR-RL-005).
* :func:`implicated_files` — deterministic failure→file mapping: a generated
  target is implicated when its basename or relative path appears in the
  command output (FR-RL-007).

Execution is NOT sandboxed in v0.1.4 (documented limitation): the command is
user-supplied, runs at the same trust level as the user typing it, and is
honored only under the ``open`` security profile (refused at intake
otherwise — the backend enforces that, FR-RL-003).
"""

from __future__ import annotations

import pathlib
import subprocess

from pydantic import BaseModel

# Output kept for repair prompts / events. Prompts get the larger excerpt;
# events record a shorter tail.
PROMPT_TAIL_CHARS = 4_000
EVENT_TAIL_CHARS = 1_500


class TestRunResult(BaseModel):
    """Outcome of one external-test command run."""

    exit_code: int | None = None  # None -> the command timed out
    output_tail: str = ""
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def run_external_tests(
    command: str, workspace: str | pathlib.Path, timeout_s: float
) -> TestRunResult:
    """Run ``command`` in the workspace; never raises on command failure."""
    try:
        proc = subprocess.run(
            command, cwd=str(workspace), shell=True, timeout=timeout_s,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return TestRunResult(
            exit_code=proc.returncode, output_tail=output[-PROMPT_TAIL_CHARS:]
        )
    except subprocess.TimeoutExpired:
        return TestRunResult(
            exit_code=None, timed_out=True,
            output_tail=f"external test command timed out after {timeout_s}s",
        )


def compile_smoke(
    root: str | pathlib.Path, artifacts: list[str]
) -> list[tuple[str, str]]:
    """Syntax-check generated ``.py`` artifacts; return (rel, error) pairs."""
    base = pathlib.Path(root)
    broken: list[tuple[str, str]] = []
    for rel in artifacts:
        if not rel.endswith(".py"):
            continue
        target = base / rel
        if not target.is_file():
            continue
        try:
            compile(target.read_text(encoding="utf-8", errors="replace"),
                    rel, "exec")
        except SyntaxError as exc:
            broken.append((rel, f"SyntaxError: {exc.msg} (line {exc.lineno})"))
    return broken


def implicated_files(output: str, targets: list[str]) -> list[str]:
    """Targets the command output names, in target order; empty if none.

    Matching is deliberately permissive: tracebacks reference the file under
    its *installed/merged* path (e.g. ``tinydb\\utils.py``) while the target
    is ``src/utils.py`` — the basename is the stable join key. Callers treat
    an empty result as "implicate everything" (FR-RL-007).
    """
    normalized = output.replace("\\", "/")
    implicated: list[str] = []
    for rel in targets:
        name = rel.replace("\\", "/").rsplit("/", 1)[-1]
        if name and (name in normalized or rel.replace("\\", "/") in normalized):
            implicated.append(rel)
    return implicated


__all__ = [
    "TestRunResult",
    "run_external_tests",
    "compile_smoke",
    "implicated_files",
    "PROMPT_TAIL_CHARS",
    "EVENT_TAIL_CHARS",
]
