"""Stage an Anvil workspace for one Commit0 repo.

The stage directory is a disposable copy of the skeleton plus the two files
that drive an in-place Anvil run: ``domain-knowledge/background-information.md``
(the task, with the stub inventory as the pinned contract) and
``domain-knowledge/anvil-instructions.md`` (interface-fidelity standing
instructions — the mechanism that took the smoke suite from 50% to 100%).
"""

from __future__ import annotations

import pathlib
import shutil

from commit0_adapter.repos import find_package_dir
from commit0_adapter.stubs import render_inventory, scan_package

INSTRUCTIONS = """\
# Anvil standing instructions

## This is a fill-in-the-skeleton task

The workspace already contains a real Python library whose function bodies
have been removed. Your ONLY job is to implement those bodies. The package
structure, module names, class names, function signatures, and docstrings
are a fixed contract:

- Never rename, move, or delete an existing module, class, or function.
- Never change a signature or a docstring.
- Generate each module as a COMPLETE file at `src/<module path>` mirroring
  the package-relative path from the task description (e.g. the package's
  `storages.py` is generated as `src/storages.py`), containing the full
  original module with every stub body implemented.
- Implement behavior exactly as the docstrings and the library's
  documentation describe; the library's own unit tests will be run against
  your implementation.
- Use only the library's existing dependencies; no new packages.

## Every derived document

Proposal, spec, architecture, blueprint, and plan must quote the module and
function inventory VERBATIM — never summarize or paraphrase it. A correct
implementation under a different name is a failure.
"""

TASK_TEMPLATE = """\
# Implement the `{repo}` library from its skeleton

This workspace contains the real `{repo}` Python library with every function
body stripped to `pass`. Signatures, docstrings, and module structure are
intact and MUST NOT change. Implement every stub so the library's own unit
test suite (in `tests/`) passes.

## About the library

{readme_excerpt}

## Output contract (must be followed exactly)

Generate one file per module listed below at `src/<module path>` — the full
module content (imports, provided helpers, and all classes/functions) with
every stub implemented. Package-relative paths, names, signatures, and
docstrings must match the skeleton exactly.

## Module and stub inventory

{inventory}
"""


def _readme_excerpt(repo_dir: pathlib.Path, limit: int = 1500) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        path = repo_dir / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            return text[:limit] + ("\n..." if len(text) > limit else "")
    return "(no README found)"


def stage_workspace(repo: str, skeleton_dir: pathlib.Path,
                    stage_dir: pathlib.Path) -> dict:
    """Copy the skeleton and write the Anvil task files. Returns stage info."""
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    shutil.copytree(skeleton_dir, stage_dir, ignore=shutil.ignore_patterns(".git"))

    package_dir = find_package_dir(stage_dir)
    entries = scan_package(package_dir)
    stub_count = sum(1 for e in entries if e.is_stub)
    inventory = render_inventory(entries)

    dk_dir = stage_dir / "domain-knowledge"
    dk_dir.mkdir(exist_ok=True)
    (dk_dir / "background-information.md").write_text(
        TASK_TEMPLATE.format(repo=repo,
                             readme_excerpt=_readme_excerpt(stage_dir),
                             inventory=inventory),
        encoding="utf-8")
    (dk_dir / "anvil-instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")
    return {
        "package_dir": str(package_dir),
        "package_rel": str(package_dir.relative_to(stage_dir)),
        "modules": len({e.module for e in entries}),
        "functions": len(entries),
        "stubs": stub_count,
    }


__all__ = ["stage_workspace", "INSTRUCTIONS", "TASK_TEMPLATE"]
