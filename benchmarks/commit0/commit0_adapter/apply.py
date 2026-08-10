"""Merge Anvil's generated ``src/`` output onto the skeleton package.

v2 policy: a generated file must still map to exactly one package module
(exact relative path, else unique basename) — unmatched output is reported,
not guessed. But instead of replacing the whole module (which discarded
skeleton-provided aliases/classes and broke imports), the matched pair is
**grafted**: only the skeleton's stub function bodies are filled from the
generated module; every provided line stays (see ``graft.py``).
"""

from __future__ import annotations

import ast
import pathlib

from commit0_adapter.graft import graft_module


def _is_valid_python(path: pathlib.Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        return True
    except SyntaxError:
        return False


def apply_generated(stage_dir: pathlib.Path, package_dir: pathlib.Path,
                    exclude_dir: pathlib.Path | None = None) -> dict:
    """Copy generated src/*.py over matching package modules.

    Matching, in order: exact package-relative path, then unique basename
    match anywhere in the package. Returns counts + the per-file decisions.

    ``exclude_dir``: the directory whose files are skeleton, not generated
    output. Defaults to ``package_dir`` (in-place graft); the repair-signal
    entry point grafts onto a SCRATCH package and passes the original
    package dir here so a src-layout skeleton is still excluded.
    """
    src_dir = stage_dir / "src"
    decisions: list[dict] = []
    applied = 0
    # In a src-layout repo the real package lives INSIDE src/ (e.g.
    # src/cachetools/); its skeleton files are not generated output and must
    # never be grafted onto themselves.
    package_resolved = (exclude_dir or package_dir).resolve()
    generated = [p for p in sorted(src_dir.rglob("*.py"))
                 if package_resolved not in p.resolve().parents] \
        if src_dir.is_dir() else []

    package_modules = list(package_dir.rglob("*.py"))
    by_basename: dict[str, list[pathlib.Path]] = {}
    for module in package_modules:
        by_basename.setdefault(module.name, []).append(module)

    grafted_bodies = 0
    for gen in generated:
        rel = gen.relative_to(src_dir)
        record = {"generated": rel.as_posix(), "target": None, "action": "unmatched"}
        target = package_dir / rel
        if not target.is_file():
            candidates = by_basename.get(gen.name, [])
            target = candidates[0] if len(candidates) == 1 else None
        if target is not None:
            if _is_valid_python(gen):
                merged, stats = graft_module(
                    target.read_text(encoding="utf-8", errors="replace"),
                    gen.read_text(encoding="utf-8", errors="replace"))
                target.write_text(merged, encoding="utf-8")
                applied += 1
                grafted_bodies += stats["grafted"]
                record.update(target=target.relative_to(stage_dir).as_posix(),
                              action="grafted", graft=stats)
            else:
                record["action"] = "skipped_invalid_python"
        decisions.append(record)

    return {
        "generated_py_files": len(generated),
        "applied": applied,
        "grafted_bodies": grafted_bodies,
        "unmatched": sum(1 for d in decisions if d["action"] == "unmatched"),
        "skipped_invalid": sum(1 for d in decisions
                               if d["action"] == "skipped_invalid_python"),
        "decisions": decisions,
    }


__all__ = ["apply_generated"]
