"""Per-run workspace resolution (spec FR-RUN-001..004).

Each ``build`` run (one carrying a ``task``) executes in its own isolated workspace
under ``<base>/runs/<date>-<slug>/`` so a fresh prompt cannot be overridden by
unrelated repository artifacts already present at the base (the FR-001 failure).
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime

_SLUG_MAX = 40


def slug(task: str | None) -> str:
    """Kebab-case slug from a task string; ``"run"`` when empty."""
    text = re.sub(r"[^a-z0-9]+", "-", (task or "").lower()).strip("-")
    if not text:
        return "run"
    return text[:_SLUG_MAX].rstrip("-") or "run"


def resolve_run_workspace(base: str, task: str | None, now: datetime) -> str:
    """Create and return an isolated ``<base>/runs/<date>-<slug>/`` workspace.

    A numeric suffix is appended on collision so same-day runs with the same slug
    do not clash.
    """
    runs_root = pathlib.Path(base) / "runs"
    stem = f"{now:%Y-%m-%d}-{slug(task)}"
    candidate = runs_root / stem
    counter = 2
    while candidate.exists():
        candidate = runs_root / f"{stem}-{counter}"
        counter += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate)


__all__ = ["slug", "resolve_run_workspace"]
