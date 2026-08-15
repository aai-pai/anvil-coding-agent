"""Dependency-slice repair context (v0.1.5 #29).

Mechanical, no LLM involvement. #27 put sibling *signatures* in the repair
prompt and deliberately stopped there; v0.1.4's background doc
pre-registered the escalation condition — "full dependency-slice source if
the measurement shows cross-module clusters still killing repaired runs".
It did: 89% of recovered failures implicate more than one module.

Selecting ``A`` over ``B`` requires seeing what ``A`` *does*, not merely
what it is called, so the candidates' upstream dependencies contribute
bodies. Everything else stays on signatures via #27. Slice source is
read-only context (FR-DS-003) — only candidate-set files are writable.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.verify.interface_map import (
    AstIndex,
    _file_interface,
)

SLICE_MAX_CHARS = 12_000  # FR-DS-002, separate from INTERFACE_MAP_MAX_CHARS


def upstream_of(candidates: list[str], index: AstIndex) -> list[str]:
    """Candidates' dependencies, most-depended-upon first, candidates excluded.

    A dependency two candidates rely on is more likely to be the shared
    cause than one only a single candidate touches, so it leads.
    """
    counts: dict[str, int] = {}
    for candidate in candidates:
        for dep in index.edges.get(candidate, []):
            if dep in candidates:
                continue  # a candidate's source is already in the prompt
            counts[dep] = counts.get(dep, 0) + 1
    return sorted(counts, key=lambda rel: (-counts[rel], rel))


def build(
    root: str | pathlib.Path,
    candidates: list[str],
    index: AstIndex,
    cap: int = SLICE_MAX_CHARS,
) -> str:
    """Upstream bodies under a character budget; overflow degrades to signatures.

    A file that will not fit is reduced to its signature block rather than
    truncated mid-body — half a function body is worse than none, because
    it reads as complete. Returns ``""`` when there is no upstream, so the
    caller can compose unconditionally.
    """
    base = pathlib.Path(root)
    ordered = upstream_of(candidates, index)
    if not ordered:
        return ""

    blocks: list[str] = []
    used = 0
    reduced = 0
    omitted = 0
    for rel in ordered:
        tree = index.trees.get(rel)
        if tree is None:
            # Unparseable upstream: #27 already established the convention.
            block, degraded = f"## `{rel}` (currently broken)", False
        else:
            source = _read(base / rel)
            full = f"## `{rel}`\n```python\n{source}```" if source else ""
            if full and used + len(full) <= cap:
                block, degraded = full, False
            else:
                block, degraded = "\n".join(_file_interface(rel, tree)), True
        if used + len(block) > cap and blocks:
            omitted += 1  # not even signatures fit; never counted as reduced
            continue
        blocks.append(block)
        used += len(block)
        reduced += 1 if degraded else 0
    notes = []
    if reduced:
        notes.append(f"({reduced} file(s) reduced to signatures)")
    if omitted:
        notes.append(f"({omitted} file(s) omitted)")
    return "\n\n".join(blocks + notes)


def _read(target: pathlib.Path) -> str:
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


__all__ = ["build", "upstream_of", "SLICE_MAX_CHARS"]
