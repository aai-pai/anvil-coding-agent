"""Task-contract resolution: the contract/context split (v0.1.3 #20).

The v0.1.2 eval evidence showed the task's *binding facts* (file names,
signatures, return shapes) getting lossy-retold between phases: the spec
paraphrased them away and the implementation shipped the paraphrase. #20 gives
those facts their own channel: ``domain-knowledge/background-information.md``
may mark a contract section that is injected VERBATIM into every phase prompt
(the task-scoped analog of the #14 standing-instructions block), while the
remaining context stays a normal — summarizable — intake/proposal input.

This module only *splits and resolves* the file; injection is the LLM
backend's job, sealing (``ContractSealed``) is the supervisor's, and the
``contract-manifest`` mechanical check (#21) lives in ``manifest.py``.
Resolution happens at prompt-assembly time per dispatch, so intake appends and
resume need no extra state.

A file with no ``<!-- anvil:contract -->`` marker behaves exactly as v0.1.2:
all context, nothing pinned.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel

CONTRACT_MARKER = "<!-- anvil:contract -->"
CONTEXT_MARKER = "<!-- anvil:context -->"

# The run-relative file the contract lives in (same file intake reads).
DOMAIN_KNOWLEDGE_REL = "domain-knowledge/background-information.md"

# Fixed binding preamble prefixed to the injected block (proposal #20; the
# exact wording is part of the spec's acceptance criteria).
CONTRACT_PREAMBLE = (
    "Authoritative task contract — the facts below are binding and pinned. "
    "Never restate, never contradict, never rename: use every file name, "
    "symbol name, signature, and format exactly as written below."
)


class ContractSplit(BaseModel):
    """Outcome of splitting a domain-knowledge file into contract/context."""

    has_markers: bool = False
    contract: str = ""  # verbatim contract text (marker lines excluded)
    context: str = ""  # everything else; the full text when unmarkered


class ResolvedContract(BaseModel):
    """Outcome of contract resolution for one run."""

    present: bool = False
    text: str = ""
    length: int = 0
    path: str | None = None


def split_contract(text: str) -> ContractSplit:
    """Split a domain-knowledge file into its contract and context parts.

    ``<!-- anvil:contract -->`` opens a contract section; ``<!-- anvil:context -->``
    closes it (back to context). Text before the first marker is context.
    Without a contract marker the file is returned untouched (v0.1.2 behavior:
    all context, byte-for-byte).
    """
    if CONTRACT_MARKER not in text:
        return ContractSplit(has_markers=False, contract="", context=text)
    contract_lines: list[str] = []
    context_lines: list[str] = []
    in_contract = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == CONTRACT_MARKER:
            in_contract = True
            continue
        if stripped == CONTEXT_MARKER:
            in_contract = False
            continue
        (contract_lines if in_contract else context_lines).append(line)
    return ContractSplit(
        has_markers=True,
        contract="".join(contract_lines).strip("\n"),
        context="".join(context_lines),
    )


def resolve_contract(run_root: str | pathlib.Path) -> ResolvedContract:
    """Resolve the run's contract block from its domain-knowledge file.

    Read fresh on every call (prompt-assembly time), so intake appends and a
    resumed run always see the current block. Absence is not an error.
    """
    target = pathlib.Path(run_root) / DOMAIN_KNOWLEDGE_REL
    if not target.is_file():
        return ResolvedContract()
    split = split_contract(target.read_text(encoding="utf-8"))
    if not split.has_markers or not split.contract.strip():
        return ResolvedContract()
    return ResolvedContract(
        present=True,
        text=split.contract,
        length=len(split.contract),
        path=str(target),
    )


def append_block(text: str, addition: str) -> str:
    """Append ``addition`` *into the contract block* when the file is markered.

    Intake clarifications and recorded assumptions are binding facts, not
    prose (#20): on a markered file they land at the end of the (last)
    contract section, so re-resolution injects them into every later phase.
    On an unmarkered file this reproduces the v0.1.2 append-at-end format
    byte-for-byte.
    """
    if CONTRACT_MARKER not in text:
        return text.rstrip("\n") + "\n" + addition + "\n"
    lines = text.splitlines()
    insert_at: int | None = None
    in_contract = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == CONTRACT_MARKER:
            in_contract = True
        elif stripped == CONTEXT_MARKER:
            if in_contract:
                insert_at = index
            in_contract = False
    if in_contract:  # contract section runs to end-of-file
        insert_at = len(lines)
    if insert_at is None:  # defensive: marker present but never opened a section
        return text.rstrip("\n") + "\n" + addition + "\n"
    new_lines = lines[:insert_at] + addition.splitlines() + lines[insert_at:]
    return "\n".join(new_lines) + "\n"


__all__ = [
    "CONTRACT_MARKER",
    "CONTEXT_MARKER",
    "CONTRACT_PREAMBLE",
    "DOMAIN_KNOWLEDGE_REL",
    "ContractSplit",
    "ResolvedContract",
    "split_contract",
    "resolve_contract",
    "append_block",
]
