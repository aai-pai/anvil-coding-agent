"""Task-complexity gate for optional planning-doc phases (FR-002 issue 2).

Guidance (Sunil): the doc-only planning phases — ``packaging``, ``documentation``,
``deployment`` — are not worth emitting unless the task is complex enough to need
them. This module classifies a run into a complexity tier and maps that tier to
the set of optional phases that should execute. The canonical phases (proposal,
specification, architecture, blueprint, dev-plan), implementation, qa, and
cleanup always run; only those three doc-only phases are gated.

The classifier is LLM-backed (the chosen mechanism), but the supervisor depends
only on a ``Callable[[run_id], tier]`` so it stays decoupled and the gate is fully
testable with a stub classifier. The ``ANVIL_COMPLEXITY`` env var forces a tier
without an LLM call (config override).
"""

from __future__ import annotations

import os
from typing import Callable

# Doc-only planning phases gated by complexity (qa and cleanup always run).
OPTIONAL_PHASES: frozenset[str] = frozenset({"packaging", "documentation", "deployment"})

TIERS: tuple[str, ...] = ("simple", "standard", "complex", "full")

# tier -> optional phases enabled. ``full`` preserves the pre-gate behaviour (all
# on) and is the safe default when no classifier is wired (stub mode / tests).
_TIER_ENABLES: dict[str, frozenset[str]] = {
    "simple": frozenset(),
    "standard": frozenset({"documentation"}),
    "complex": OPTIONAL_PHASES,
    "full": OPTIONAL_PHASES,
}

COMPLEXITY_ENV = "ANVIL_COMPLEXITY"
DEFAULT_TIER = "full"


def normalize_tier(raw: str | None) -> str:
    """Map arbitrary/model text onto a known tier; unknown -> ``DEFAULT_TIER``."""
    if not raw:
        return DEFAULT_TIER
    text = raw.strip().lower()
    # Check the most specific words first so e.g. "complex" isn't shadowed.
    for tier in ("complex", "standard", "simple", "full"):
        if tier in text:
            return tier
    return DEFAULT_TIER


def enabled_optional_phases(tier: str) -> frozenset[str]:
    """The optional phases enabled for a tier."""
    return _TIER_ENABLES.get(normalize_tier(tier), OPTIONAL_PHASES)


def is_optional(phase_id: str) -> bool:
    """True if a phase is complexity-gated."""
    return phase_id in OPTIONAL_PHASES


_CLASSIFIER_PROMPT = (
    "You are triaging a software build to decide how much process it needs.\n"
    "Classify the project below into exactly one complexity tier:\n"
    "- simple: a single small script / CLI / library; no packaging, deployment, "
    "or separate documentation effort needed.\n"
    "- standard: a normal application that benefits from end-user documentation "
    "but no special packaging or deployment plan.\n"
    "- complex: a system that genuinely needs packaging, documentation, AND "
    "deployment planning (multiple services, distribution, infrastructure).\n"
    "Answer with ONLY one word: simple, standard, or complex.\n\n"
    "Project:\n{ctx}"
)


def make_llm_classifier(
    provider: object,
    model: str,
    workspace_root: str,
    inputs: tuple[str, ...] = ("docs/proposal.md", "docs/spec.md"),
    on_decision: Callable[[str, str], None] | None = None,
) -> Callable[[str], str]:
    """Build a ``run_id -> tier`` classifier backed by a single LLM call.

    Honors the ``ANVIL_COMPLEXITY`` override (returns it without a call). Reads the
    proposal/spec for context. Any error falls back to ``DEFAULT_TIER`` so the gate
    can never break a run. ``on_decision(tier, source)`` is an optional callback
    for auditing (source is ``override`` | ``llm`` | ``error``).
    """
    import pathlib

    from anvil_runtime.llm.openrouter_provider import CompletionRequest

    root = pathlib.Path(workspace_root)

    def classify(_run_id: str) -> str:
        override = os.environ.get(COMPLEXITY_ENV)
        if override:
            tier = normalize_tier(override)
            if on_decision:
                on_decision(tier, "override")
            return tier
        chunks: list[str] = []
        for rel in inputs:
            target = root / rel
            if target.is_file():
                chunks.append(target.read_text(encoding="utf-8")[:2000])
        ctx = "\n\n".join(chunks) or "(no project documents available)"
        try:
            resp = provider.complete(CompletionRequest(
                model=model,
                prompt=_CLASSIFIER_PROMPT.format(ctx=ctx),
                phase="complexity", subtask="analysis", max_tokens=8,
            ))
            tier = normalize_tier(resp.content)
            if on_decision:
                on_decision(tier, "llm")
            return tier
        except Exception:  # noqa: BLE001 - the gate must never break a run
            if on_decision:
                on_decision(DEFAULT_TIER, "error")
            return DEFAULT_TIER

    return classify


def fixed_classifier(tier: str) -> Callable[[str], str]:
    """A deterministic ``run_id -> tier`` classifier (tests / explicit config)."""
    normalized = normalize_tier(tier)
    return lambda _run_id: normalized


__all__ = [
    "OPTIONAL_PHASES",
    "TIERS",
    "COMPLEXITY_ENV",
    "DEFAULT_TIER",
    "normalize_tier",
    "enabled_optional_phases",
    "is_optional",
    "make_llm_classifier",
    "fixed_classifier",
]
