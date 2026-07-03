"""Standing-instructions resolution.

v0.1.2 #14 deliverable (blueprint §1; spec FR-INS-001..003). Anvil's equivalent
of ``copilot-instructions.md``: a markdown file of default actions for
underspecified inputs, fallback behaviors, and conventions that every phase
agent receives as a dedicated prompt block. This module only *resolves* the
file; injection is the LLM backend's job and the ``InstructionsResolved`` event
is the run-start caller's job (FR-INS-004).
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel

INSTRUCTIONS_FILENAME = "anvil-instructions.md"
# Run-level location, next to the run's background-information.md.
RUN_LEVEL_REL = f"domain-knowledge/{INSTRUCTIONS_FILENAME}"
# FR-INS-003: the block is never truncated by the input limit, so protect the
# prompt with a generous hard cap applied once at resolution time.
MAX_INSTRUCTIONS_CHARS = 16_000


class ResolvedInstructions(BaseModel):
    """Outcome of instructions resolution for one run."""

    text: str | None = None
    path: str | None = None
    truncated: bool = False


def resolve_instructions(
    run_root: str, base_root: str | None = None
) -> ResolvedInstructions:
    """Resolve the standing-instructions file for a run (FR-INS-001).

    Precedence: ``<run_root>/domain-knowledge/anvil-instructions.md`` →
    ``<base_root>/anvil-instructions.md`` → none. Absence is not an error.
    """
    candidates = [pathlib.Path(run_root) / RUN_LEVEL_REL]
    if base_root:
        candidates.append(pathlib.Path(base_root) / INSTRUCTIONS_FILENAME)
    for candidate in candidates:
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if not text:
                continue  # an empty file resolves nothing; keep looking
            truncated = len(text) > MAX_INSTRUCTIONS_CHARS
            if truncated:
                text = text[:MAX_INSTRUCTIONS_CHARS]
            return ResolvedInstructions(
                text=text, path=str(candidate), truncated=truncated
            )
    return ResolvedInstructions()


__all__ = [
    "INSTRUCTIONS_FILENAME",
    "RUN_LEVEL_REL",
    "MAX_INSTRUCTIONS_CHARS",
    "ResolvedInstructions",
    "resolve_instructions",
]
