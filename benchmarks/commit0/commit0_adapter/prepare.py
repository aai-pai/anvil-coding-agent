"""Stage an Anvil workspace for one Commit0 repo.

The stage directory is a disposable copy of the skeleton plus the two files
that drive an in-place Anvil run: ``domain-knowledge/background-information.md``
(the task, with the stub inventory as the pinned contract) and
``domain-knowledge/anvil-instructions.md`` (interface-fidelity standing
instructions — the mechanism that took the smoke suite from 50% to 100%).
"""

from __future__ import annotations

import json
import pathlib
import shutil

from commit0_adapter.repos import find_package_dir
from commit0_adapter.stubs import (
    render_inventory,
    render_manifest,
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

# #20: the binding facts live in a marked contract block (injected VERBATIM
# into every Anvil phase prompt, never truncated); the readme/doc excerpts are
# context (summarizable, intake/proposal input only). The fenced
# contract-manifest (#21) lets Anvil's validator AST-check the generated code
# against the pinned inventory mechanically.
TASK_TEMPLATE = """\
# Implement the `{repo}` library from its skeleton

<!-- anvil:contract -->

This workspace contains the real `{repo}` Python library with every function
body stripped to `pass`. Signatures, docstrings, and module structure are
intact and MUST NOT change. Implement every stub so the library's own unit
test suite (in `tests/`) passes.

## Output contract (must be followed exactly)

Generate one file per module listed below at `src/<module path>` — the full
module content (imports, provided helpers, and all classes/functions) with
every stub implemented. Package-relative paths, names, signatures, and
docstrings must match the skeleton exactly.

## Module and stub inventory

{inventory}

```contract-manifest
{manifest}
```

<!-- anvil:context -->

## About the library

{readme_excerpt}
"""

# v0.1.4 spec §3: staging-time metadata for the repair-signal entry point
# (graft_and_test.py) and for qa-leak-proof scoring. The pristine package
# copy exists because grafting fills only STUB bodies — repairs can never
# propagate through an already-grafted package, so every repair round must
# re-graft from pristine.
META_NAME = "commit0-meta.json"
PRISTINE_DIR = ".commit0-pristine"
SCRATCH_DIR = ".commit0-scratch"


def is_test_file(rel: str) -> bool:
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py")


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
    manifest = render_manifest(entries, missing_by_module=missing)

    task = TASK_TEMPLATE.format(repo=repo,
                                readme_excerpt=_readme_excerpt(stage_dir),
                                inventory=inventory,
                                manifest=manifest)
    # Docs land in the context section (after the anvil:context marker): the
    # contract block is injected verbatim and never truncated (#20), while
    # context is a normal truncatable intake/proposal input — losing doc
    # excerpts to the input cap is survivable, losing the contract is not.
    docs = _docs_excerpt(stage_dir)
    if docs:
        task += f"\n## Library documentation (excerpts)\n\n{docs}\n"

    # #22: pre-stage every module needing work under src/ so Anvil's
    # per-artifact implementation reads exactly the stub file it is
    # completing (and generated files land on the same relative paths
    # apply_generated maps back onto the package).
    manifest_files = [e.module for e in entries if e.is_stub]
    for module in missing:
        if module not in manifest_files:
            manifest_files.append(module)
    seen: list[str] = []
    for module in manifest_files:
        if module in seen:
            continue
        seen.append(module)
        source = package_dir / module
        if not source.is_file():
            continue
        src_target = stage_dir / "src" / module
        src_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, src_target)

    dk_dir = stage_dir / "domain-knowledge"
    dk_dir.mkdir(exist_ok=True)
    (dk_dir / "background-information.md").write_text(task, encoding="utf-8")
    (dk_dir / "anvil-instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")

    # v0.1.4 spec §3 — snapshot the repo's ORIGINAL test files (Anvil's own
    # qa-generated tests can never enter the repair signal or the score) and
    # keep a pristine package copy for the per-round re-graft.
    tests_dir = next((stage_dir / name for name in ("tests", "test")
                      if (stage_dir / name).is_dir()), None)
    test_snapshot = sorted(
        p.relative_to(stage_dir).as_posix()
        for p in tests_dir.rglob("*.py")
        if is_test_file(p.name)
    ) if tests_dir else []
    pristine = stage_dir / PRISTINE_DIR / package_dir.name
    if pristine.parent.exists():
        shutil.rmtree(pristine.parent)
    shutil.copytree(package_dir, pristine)
    (stage_dir / META_NAME).write_text(json.dumps({
        "repo": repo,
        "package_rel": package_dir.relative_to(stage_dir).as_posix(),
        "package_name": package_dir.name,
        "tests": test_snapshot,
    }, indent=2), encoding="utf-8")

    return {
        "package_dir": str(package_dir),
        "package_rel": str(package_dir.relative_to(stage_dir)),
        "modules": len({e.module for e in entries}),
        "functions": len(entries),
        "stubs": stub_count,
        "manifest_files": len(seen),
        "prestaged_src": len(seen),
        "task_chars": len(task),
        "doc_chars": len(docs),
        "test_snapshot": len(test_snapshot),
    }


__all__ = ["stage_workspace", "INSTRUCTIONS", "TASK_TEMPLATE",
           "META_NAME", "PRISTINE_DIR", "SCRATCH_DIR", "is_test_file"]
