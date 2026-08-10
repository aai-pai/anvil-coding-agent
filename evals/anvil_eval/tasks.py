"""Task and suite loading.

A suite is a directory of task directories. Each task directory contains:

- ``task.json`` — metadata (see :class:`Task`)
- ``prompt.md`` — the build request; becomes the run's
  ``background-information.md`` verbatim via the ``source_path`` flow, so its
  first ``#`` heading seeds the run slug. Must pin the interface contract
  (file names, function signatures, storage formats) that the held-out tests
  bind to.
- ``held_out_tests/`` — pytest files graded against the generated project.
  Never shown to the agent.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

from anvil_eval.config import SUITES_ROOT

VALID_TIERS = {"simple", "standard", "complex"}


@dataclasses.dataclass
class Task:
    id: str
    dir: pathlib.Path
    prompt_path: pathlib.Path
    held_out_dir: pathlib.Path
    title: str = ""
    # Soft check against the ComplexityAssessed event; empty = don't check.
    expected_complexity: list[str] = dataclasses.field(default_factory=list)
    tags: list[str] = dataclasses.field(default_factory=list)
    timeout_s: float | None = None
    pytest_timeout_s: float | None = None


class SuiteError(ValueError):
    """A malformed suite or task definition (caller error, not a run failure)."""


def resolve_suite_dir(suite: str) -> pathlib.Path:
    """Accept a suite name under ``evals/suites/`` or a filesystem path."""
    as_path = pathlib.Path(suite)
    if as_path.is_dir():
        return as_path.resolve()
    named = SUITES_ROOT / suite
    if named.is_dir():
        return named.resolve()
    raise SuiteError(f"suite not found: '{suite}' (not a directory, and no "
                     f"'{named}')")


def _load_task(task_dir: pathlib.Path) -> Task:
    meta_path = task_dir / "task.json"
    prompt_path = task_dir / "prompt.md"
    held_out = task_dir / "held_out_tests"
    if not meta_path.is_file():
        raise SuiteError(f"{task_dir.name}: missing task.json")
    if not prompt_path.is_file():
        raise SuiteError(f"{task_dir.name}: missing prompt.md")
    if not held_out.is_dir() or not list(held_out.glob("test_*.py")):
        raise SuiteError(f"{task_dir.name}: held_out_tests/ needs >=1 test_*.py")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    expected = list(meta.get("expected_complexity", []))
    unknown = set(expected) - VALID_TIERS
    if unknown:
        raise SuiteError(f"{task_dir.name}: unknown complexity tier(s) {unknown}")
    if not any(line.strip().startswith("#") for line in
               prompt_path.read_text(encoding="utf-8").splitlines()):
        raise SuiteError(f"{task_dir.name}: prompt.md needs a '#' heading "
                         f"(it seeds the run slug)")
    return Task(
        id=meta.get("id", task_dir.name),
        dir=task_dir.resolve(),
        prompt_path=prompt_path.resolve(),
        held_out_dir=held_out.resolve(),
        title=meta.get("title", task_dir.name),
        expected_complexity=expected,
        tags=list(meta.get("tags", [])),
        timeout_s=meta.get("timeout_s"),
        pytest_timeout_s=meta.get("pytest_timeout_s"),
    )


def load_suite(suite: str, only: list[str] | None = None) -> list[Task]:
    """Load every task in a suite (or the ``only`` subset), sorted by id."""
    suite_dir = resolve_suite_dir(suite)
    task_dirs = sorted(p for p in suite_dir.iterdir()
                       if p.is_dir() and (p / "task.json").is_file())
    if not task_dirs:
        raise SuiteError(f"no tasks found in suite '{suite_dir}'")
    tasks = [_load_task(p) for p in task_dirs]
    if only:
        by_id = {t.id: t for t in tasks}
        missing = [t for t in only if t not in by_id]
        if missing:
            raise SuiteError(f"unknown task id(s): {missing}; "
                             f"available: {sorted(by_id)}")
        tasks = [by_id[t] for t in only]
    return tasks


__all__ = ["Task", "SuiteError", "load_suite", "resolve_suite_dir"]
