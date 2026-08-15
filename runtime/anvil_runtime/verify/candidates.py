"""Fault candidate generation for repair localization (v0.1.5 #28).

Mechanical, no LLM involvement — the selection *among* candidates is a
completion and lives in ``LLMBackend`` (architecture §"The boundary
question"). This module only narrows the field, deterministically.

Why it exists: FR-JL-003's basename match implicates the deepest traceback
frame naming a generated file, which resolves crashes and goes blind on
assertions. Once generated code mostly works, what remains are assertion
mismatches that fail *inside the test function*, so every frame is in
``tests/`` and no source basename appears. Measured on the v0.1.4 runs,
that discarded 43 of 67 failures in the healthiest run.

Crashes name files. Assertions name symbols. So candidates come from
symbols — but by *set*, never by argmax. On the same measurement,
``tinydb/table.py`` was implicated in 20 of 28 recovered failures and
would have been chosen by hit count in **none** of them: a module
producing wrong data is always outvoted by the consumers that assert on
it. Hence FR-FL-003 ranks producer-first, which is the inverse of the raw
signal.
"""

from __future__ import annotations

import re

from anvil_runtime.verify.interface_map import AstIndex
from anvil_runtime.verify.localize import FailureCluster

MAX_CANDIDATES = 4  # FR-FL-005 write-set cap
MIN_SYMBOL_CHARS = 4  # FR-FL-001: shorter names are noise

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _cluster_text(cluster: FailureCluster) -> str:
    parts: list[str] = []
    for record in cluster.records:
        parts.append(record.message)
        parts.append(record.excerpt)
    return "\n".join(parts)


def symbol_hits(cluster: FailureCluster, index: AstIndex) -> dict[str, int]:
    """File -> how many indexed symbols the cluster's text names.

    Tokenizing once and intersecting is equivalent to word-boundary
    matching for identifiers, and does not walk the symbol table per name.
    """
    tokens = set(_IDENTIFIER.findall(_cluster_text(cluster)))
    hits: dict[str, int] = {}
    for name in tokens:
        if len(name) < MIN_SYMBOL_CHARS:
            continue
        rel = index.symbols.get(name)
        if rel is not None:
            hits[rel] = hits.get(rel, 0) + 1
    return hits


def _rank_key(rel: str, pool: list[str], index: AstIndex,
              hits: dict[str, int]) -> tuple[int, int, int, str]:
    """FR-FL-003: producer-first, then hit count, then path.

    ``consumers`` counts candidates that depend on ``rel``; ``deps`` counts
    candidates ``rel`` depends on. A file many candidates depend on and
    which depends on few of them is upstream, and sorts first. Counting
    rather than topologically sorting keeps this total and cycle-safe —
    v0.1.3 saw a genuine query/middleware recursion cycle.
    """
    edges = index.edges
    deps = sum(1 for other in pool
               if other != rel and other in edges.get(rel, []))
    consumers = sum(1 for other in pool
                    if other != rel and rel in edges.get(other, []))
    return (-consumers, deps, -hits.get(rel, 0), rel)


def build(cluster: FailureCluster, index: AstIndex) -> list[str]:
    """Ranked candidate set for one cluster — possibly empty (FR-FL-006).

    ``cluster.file`` (the FR-JL-003 basename result, when there is one) is
    always a member and always survives the cap, so candidate generation is
    strictly additive and FR-FL-008's no-regression guarantee holds by
    construction rather than by test.
    """
    hits = symbol_hits(cluster, index)
    pool = set(hits)
    seed = cluster.file
    if seed is not None:
        pool.add(seed)
    if not pool:
        return []

    ordered = sorted(pool, key=lambda rel: _rank_key(rel, sorted(pool),
                                                     index, hits))
    selected = ordered[:MAX_CANDIDATES]
    if seed is not None and seed not in selected:
        selected = selected[:MAX_CANDIDATES - 1] + [seed]
    return selected


__all__ = ["build", "symbol_hits", "MAX_CANDIDATES", "MIN_SYMBOL_CHARS"]
