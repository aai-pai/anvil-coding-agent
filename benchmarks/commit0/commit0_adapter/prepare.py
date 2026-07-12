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
from commit0_adapter.stubs import (
    render_inventory,
    scan_package,
    scan_package_missing,
)

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

# Behavioral documentation first; project-process files never (they spend
# input budget without describing library behavior).
DOC_PRIORITY = ("usage", "getting-started", "getting_started", "quickstart",
                "tutorial", "intro", "index", "api", "extend", "advanced")
DOC_SKIP = {"changelog", "changes", "contribute", "contributing", "conf",
            "authors", "license", "history", "upgrade", "deprecation",
            "release", "news", "make", "makefile"}


def _doc_rank(stem: str) -> int:
    stem = stem.lower()
    for rank, token in enumerate(DOC_PRIORITY):
        if stem.startswith(token):
            return rank
    return len(DOC_PRIORITY)


def _docs_excerpt(repo_dir: pathlib.Path, char_budget: int = 25000,
                  per_file_cap: int = 8000) -> str:
    """Plain-text spec excerpts from the repo's Sphinx/markdown docs.

    Commit0 repos ship their specification as ``docs/*.rst`` (and a rendered
    ``spec.pdf.bz2`` this adapter deliberately ignores — same content, and
    Anvil only ingests text). Files are included in behavioral-relevance
    order until the budget runs out.
    """
    docs_dir = next((repo_dir / name for name in ("docs", "doc")
                     if (repo_dir / name).is_dir()), None)
    if docs_dir is None:
        return ""
    candidates = [p for suffix in ("*.rst", "*.md", "*.txt")
                  for p in docs_dir.glob(suffix)
                  if p.stem.lower() not in DOC_SKIP]
    candidates.sort(key=lambda p: (_doc_rank(p.stem), p.name))
    sections: list[str] = []
    used = 0
    skipped: list[str] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        text = text[:per_file_cap] + ("\n..." if len(text) > per_file_cap else "")
        block = f"### From `docs/{path.name}`\n\n{text}"
        if used + len(block) > char_budget:
            skipped.append(path.name)
            continue
        sections.append(block)
        used += len(block)
    if skipped:
        sections.append(f"(further docs omitted for space: {', '.join(skipped)})")
    return "\n\n".join(sections)


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
    missing = scan_package_missing(package_dir)
    inventory = render_inventory(entries, missing_by_module=missing)

    task = TASK_TEMPLATE.format(repo=repo,
                                readme_excerpt=_readme_excerpt(stage_dir),
                                inventory=inventory)
    # Docs go AFTER the stub inventory: if a server's ANVIL_INPUT_CHAR_LIMIT
    # is lower than this file, truncation cuts the tail — losing doc excerpts
    # is survivable, losing the pinned contract is not.
    docs = _docs_excerpt(stage_dir)
    if docs:
        task += f"\n## Library documentation (excerpts)\n\n{docs}\n"

    dk_dir = stage_dir / "domain-knowledge"
    dk_dir.mkdir(exist_ok=True)
    (dk_dir / "background-information.md").write_text(task, encoding="utf-8")
    (dk_dir / "anvil-instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")
    return {
        "package_dir": str(package_dir),
        "package_rel": str(package_dir.relative_to(stage_dir)),
        "modules": len({e.module for e in entries}),
        "functions": len(entries),
        "stubs": stub_count,
        "task_chars": len(task),
        "doc_chars": len(docs),
    }


__all__ = ["stage_workspace", "INSTRUCTIONS", "TASK_TEMPLATE"]
