"""Unit tests: per-run workspace resolution (#9, FR-RUN-001/004)."""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from anvil_runtime.api.run_workspace import resolve_run_workspace, slug


def test_slug_kebab_and_fallback() -> None:
    assert slug("Build A CLI tool!") == "build-a-cli-tool"
    assert slug("") == "run"
    assert slug(None) == "run"


def test_slug_truncated() -> None:
    assert len(slug("word " * 50)) <= 40


def test_resolve_creates_dated_workspace(tmp_path: pathlib.Path) -> None:
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    ws = pathlib.Path(resolve_run_workspace(str(tmp_path), "calculator", now))
    assert ws.is_dir()
    assert ws.parent == tmp_path / "runs"
    assert ws.name == "2026-06-26-calculator"


def test_resolve_collision_gets_suffix(tmp_path: pathlib.Path) -> None:
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    first = resolve_run_workspace(str(tmp_path), "x", now)
    second = resolve_run_workspace(str(tmp_path), "x", now)
    assert first != second
    assert pathlib.Path(second).name == "2026-06-26-x-2"
