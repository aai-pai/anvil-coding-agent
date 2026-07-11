"""Score a staged repo by running its own pytest suite.

This is the fast local dev loop: it runs the tests in the current Python
environment with the staged repo first on ``sys.path``. Repos whose tests
need heavier dependencies should be evaluated with the official tooling
(``pip install commit0``; ``commit0 test`` in its docker/modal backends) —
required for any leaderboard submission in any case.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from anvil_eval.scoring import _parse_junit


def run_repo_tests(stage_dir: pathlib.Path, timeout_s: float = 600.0,
                   junit_name: str = "commit0-junit.xml") -> dict:
    # The subprocess runs with cwd=stage_dir; every path handed to it must be
    # absolute or it resolves against the wrong base.
    stage_dir = stage_dir.resolve()
    tests_dir = next((stage_dir / name for name in ("tests", "test")
                      if (stage_dir / name).is_dir()), None)
    if tests_dir is None:
        return {"error": "no tests/ directory found", "total": 0,
                "failures": 0, "errors": 0, "skipped": 0, "passed_count": 0,
                "pass_rate": 0.0}

    junit_path = stage_dir / junit_name
    env = dict(os.environ)
    env["PYTHONPATH"] = str(stage_dir) + os.pathsep + env.get("PYTHONPATH", "")
    command = [sys.executable, "-m", "pytest", str(tests_dir), "-q",
               "--tb=no", "-p", "no:cacheprovider", f"--junitxml={junit_path}"]
    try:
        proc = subprocess.run(command, cwd=str(stage_dir), env=env,
                              timeout=timeout_s, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        exit_code: int | None = proc.returncode
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-1500:]
    except subprocess.TimeoutExpired:
        exit_code, tail = None, f"pytest timed out after {timeout_s}s"

    counts = _parse_junit(junit_path)
    counts.setdefault("passed_count", 0)
    total = counts["total"]
    return {
        **counts,
        "pass_rate": round(counts["passed_count"] / total, 4) if total else 0.0,
        "exit_code": exit_code,
        # Distinguish "the package cannot even be imported" (pytest usage/
        # collection abort, nothing collected) from "ran and failed".
        "collection_error": total == 0 and exit_code not in (0, 5),
        "output_tail": tail,
    }


__all__ = ["run_repo_tests"]
