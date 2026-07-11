"""Fetching Commit0 skeleton repositories.

Each Commit0 task repo lives at ``github.com/commit-0/<name>``; the stubbed
skeleton (function bodies replaced with ``pass``) is the ``commit0_combined``
branch. The official task list and splits are defined by the HuggingFace
dataset ``wentingzhao/commit0_combined`` (via ``pip install commit0``); this
adapter only needs the git skeletons, so it clones them directly.
"""

from __future__ import annotations

import pathlib
import subprocess

GITHUB_ORG = "https://github.com/commit-0"
SKELETON_BRANCH = "commit0_combined"

# A starter subset of small, light-dependency Commit0 repos for the local dev
# loop. This is NOT the official "lite" split — consult the commit0 package /
# HF dataset for official splits before a leaderboard submission.
STARTER_REPOS = ["tinydb", "simpy", "cachetools", "voluptuous", "wcwidth"]


class RepoError(RuntimeError):
    pass


def fetch_skeleton(repo: str, dest_root: pathlib.Path) -> pathlib.Path:
    """Clone ``repo``'s stubbed skeleton branch into ``dest_root/<repo>``.

    Reuses an existing clone if present (skeletons are read-only inputs;
    staging copies them, never mutates them).
    """
    dest = dest_root / repo
    if (dest / ".git").is_dir():
        return dest
    dest_root.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", "--depth", "1", "--branch", SKELETON_BRANCH,
               f"{GITHUB_ORG}/{repo}", str(dest)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RepoError(
            f"failed to clone {repo}@{SKELETON_BRANCH}: {proc.stderr.strip()}")
    return dest


def find_package_dir(repo_dir: pathlib.Path) -> pathlib.Path:
    """The library's importable package directory inside the repo.

    Heuristic: the top-level directory (not tests/docs/build tooling) that
    contains an ``__init__.py``. Single-module repos fall back to the repo
    root.
    """
    skip = {"tests", "test", "docs", "doc", "examples", "scripts", "benchmarks",
            "artwork", ".git", ".github"}
    candidates = [p for p in sorted(repo_dir.iterdir())
                  if p.is_dir() and p.name.lower() not in skip
                  and (p / "__init__.py").is_file()]
    if not candidates:
        # src-layout fallback: src/<pkg>/__init__.py
        src = repo_dir / "src"
        if src.is_dir():
            candidates = [p for p in sorted(src.iterdir())
                          if p.is_dir() and (p / "__init__.py").is_file()]
    if not candidates:
        return repo_dir
    # Prefer the package named like the repo, else the one with most .py files.
    for p in candidates:
        if p.name.replace("_", "-") == repo_dir.name.replace("_", "-"):
            return p
    return max(candidates, key=lambda p: len(list(p.rglob("*.py"))))


__all__ = ["fetch_skeleton", "find_package_dir", "RepoError",
           "STARTER_REPOS", "SKELETON_BRANCH"]
