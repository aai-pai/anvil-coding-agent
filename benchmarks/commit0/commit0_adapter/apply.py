"""Merge Anvil's generated ``src/`` output onto the skeleton package.

v1 policy (deliberately simple, and the source of the adapter's honesty):
a generated file replaces a package module only when it maps to one
unambiguously and parses as Python. Anything unmatched is reported, not
guessed — a low applied-count is a real Anvil finding (it means the run
did not honor the output contract), not something to paper over here.
"""

from __future__ import annotations

import ast
import pathlib
import shutil


def _is_valid_python(path: pathlib.Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        return True
    except SyntaxError:
        return False


def apply_generated(stage_dir: pathlib.Path, package_dir: pathlib.Path) -> dict:
    """Copy generated src/*.py over matching package modules.

    Matching, in order: exact package-relative path, then unique basename
    match anywhere in the package. Returns counts + the per-file decisions.
    """
    src_dir = stage_dir / "src"
    decisions: list[dict] = []
    applied = 0
    generated = [p for p in sorted(src_dir.rglob("*.py"))] if src_dir.is_dir() else []

    package_modules = list(package_dir.rglob("*.py"))
    by_basename: dict[str, list[pathlib.Path]] = {}
    for module in package_modules:
        by_basename.setdefault(module.name, []).append(module)

    for gen in generated:
        rel = gen.relative_to(src_dir)
        record = {"generated": rel.as_posix(), "target": None, "action": "unmatched"}
        target = package_dir / rel
        if not target.is_file():
            candidates = by_basename.get(gen.name, [])
            target = candidates[0] if len(candidates) == 1 else None
        if target is not None:
            if _is_valid_python(gen):
                shutil.copyfile(gen, target)
                applied += 1
                record.update(target=target.relative_to(stage_dir).as_posix(),
                              action="applied")
            else:
                record["action"] = "skipped_invalid_python"
        decisions.append(record)

    return {
        "generated_py_files": len(generated),
        "applied": applied,
        "unmatched": sum(1 for d in decisions if d["action"] == "unmatched"),
        "skipped_invalid": sum(1 for d in decisions
                               if d["action"] == "skipped_invalid_python"),
        "decisions": decisions,
    }


__all__ = ["apply_generated"]
