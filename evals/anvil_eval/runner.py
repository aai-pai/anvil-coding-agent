"""Suite orchestration: one isolated Anvil run per task, then scoring.

Each task gets a fresh base workspace under the results directory; the run
itself lands in ``<base>/runs/<date>-<slug>/`` via the runtime's own isolation
(FR-RUN-001), so tasks can never contaminate each other or the repo.
"""

from __future__ import annotations

import pathlib
import time

from anvil_eval.client import AnvilClient, AnvilClientError
from anvil_eval.config import EvalConfig
from anvil_eval.scoring import (
    analyze_events,
    check_artifacts,
    estimate_cost_usd,
    run_held_out_tests,
)
from anvil_eval.tasks import Task

# RunStatus values that mean the supervisor will not advance further on its own.
_TERMINAL = {"completed", "escalated", "stopped"}
# Pauses that must not happen in an unattended (yolo) benchmark run.
_PAUSED = {"awaiting_approval", "awaiting_clarification"}


def _drive_run(client: AnvilClient, run_id: str, timeout_s: float,
               log) -> tuple[str, dict]:
    """Advance a deferred run phase-by-phase until terminal, pause, or timeout."""
    deadline = time.monotonic() + timeout_s
    state = client.get_run(run_id)
    seen: set[str] = set(state.get("completed_phases", []))
    while state.get("status") == "running":
        if time.monotonic() > deadline:
            try:
                client.stop(run_id, reason=f"anvil-eval timeout after {timeout_s}s")
            except AnvilClientError:
                pass
            return "timeout", state
        state = client.advance(run_id)
        for phase in state.get("completed_phases", []):
            if phase not in seen:
                seen.add(phase)
                log(f"    phase done: {phase}")
    status = state.get("status", "unknown")
    if status in _PAUSED:
        # A yolo run should never pause; record it as a defect, then stop the
        # run so the server does not accumulate stuck runs.
        try:
            client.stop(run_id, reason="anvil-eval: unexpected pause in yolo run")
        except AnvilClientError:
            pass
    return status, state


def run_task(client: AnvilClient, task: Task, cfg: EvalConfig,
             task_results_dir: pathlib.Path, log=print) -> dict:
    """Execute and score one task; always returns a result dict, never raises."""
    task_results_dir.mkdir(parents=True, exist_ok=True)
    base_ws = task_results_dir / "workspace"
    base_ws.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "task_id": task.id,
        "title": task.title,
        "tags": task.tags,
        "resolved": False,
        "run_status": "not_started",
        "workspace": str(base_ws),
    }
    wall_start = time.monotonic()
    try:
        started = client.start_run(
            source_path=str(task.prompt_path), workspace=str(base_ws),
            mode=cfg.run_mode, security_profile=cfg.security_profile, defer=True,
        )
        run_id = started["run_id"]
        result["run_id"] = run_id
        log(f"    run {run_id[:12]} started")
        status, state = _drive_run(
            client, run_id, task.timeout_s or cfg.task_timeout_s, log
        )
        result["run_status"] = status
        result["completed_phases"] = state.get("completed_phases", [])
    except AnvilClientError as exc:
        result["run_status"] = "client_error"
        result["error"] = str(exc)
        log(f"    ERROR: {exc}")
    result["wall_clock_s"] = round(time.monotonic() - wall_start, 2)

    # The isolated run dir is the single directory the runtime created under
    # <base>/runs/ (the base workspace is fresh per task).
    runs_root = base_ws / "runs"
    run_dirs = sorted(p for p in runs_root.iterdir() if p.is_dir()) \
        if runs_root.is_dir() else []
    if not run_dirs:
        result["run_dir"] = None
        result["tests"] = {"passed": False, "total": 0,
                           "output_tail": "no run workspace was created"}
        result["events"] = analyze_events(pathlib.Path("/nonexistent"))
        result["artifacts"] = {}
        return result
    run_dir = run_dirs[0]
    result["run_dir"] = str(run_dir)

    events = analyze_events(run_dir)
    result["events"] = events
    result["artifacts"] = check_artifacts(run_dir)
    cost = estimate_cost_usd(events, cfg.pricing)
    if cost is not None:
        result["estimated_cost_usd"] = cost
    if task.expected_complexity:
        tier = events.get("complexity_tier")
        result["complexity"] = {
            "expected": task.expected_complexity,
            "actual": tier,
            # None (not False) when no tier was assessed at all — offline/stub
            # runs have no ComplexityAssessed event and should not read as a
            # misclassification.
            "match": (tier in task.expected_complexity) if tier else None,
        }

    tests = run_held_out_tests(
        task.held_out_dir, run_dir, task_results_dir / "held_out_sandbox",
        task.pytest_timeout_s or cfg.pytest_timeout_s,
    )
    result["tests"] = tests
    result["resolved"] = result["run_status"] == "completed" and tests["passed"]
    log(f"    tests: {tests.get('passed_count', 0)}/{tests.get('total', 0)} passed"
        f" -> {'RESOLVED' if result['resolved'] else 'unresolved'}")
    return result


def run_suite(client: AnvilClient, tasks: list[Task], cfg: EvalConfig,
              results_dir: pathlib.Path, log=print) -> list[dict]:
    results = []
    for index, task in enumerate(tasks, start=1):
        log(f"[{index}/{len(tasks)}] {task.id}")
        results.append(
            run_task(client, task, cfg, results_dir / "tasks" / task.id, log)
        )
    return results


__all__ = ["run_task", "run_suite"]
