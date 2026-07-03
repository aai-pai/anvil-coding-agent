"""Unit tests: standing-instructions resolution (#14, FR-INS-001..003).

Covers the run > base precedence, the no-file and empty-file cases, the 16k
hard cap, and prompt injection into the LLM backend (FR-INS-002).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.instructions import (
    MAX_INSTRUCTIONS_CHARS,
    resolve_instructions,
)
from anvil_runtime.sdk.openhands_adapter import LLMBackend, PhaseStep


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_run_level_wins_over_base(tmp_path: pathlib.Path) -> None:
    run = tmp_path / "runs" / "r1"
    _write(run / "domain-knowledge" / "anvil-instructions.md", "RUN LEVEL")
    _write(tmp_path / "anvil-instructions.md", "BASE LEVEL")
    resolved = resolve_instructions(str(run), str(tmp_path))
    assert resolved.text == "RUN LEVEL"
    assert resolved.path is not None and "domain-knowledge" in resolved.path


def test_base_level_fallback(tmp_path: pathlib.Path) -> None:
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    _write(tmp_path / "anvil-instructions.md", "BASE LEVEL")
    resolved = resolve_instructions(str(run), str(tmp_path))
    assert resolved.text == "BASE LEVEL"


def test_absence_is_not_an_error(tmp_path: pathlib.Path) -> None:
    resolved = resolve_instructions(str(tmp_path), str(tmp_path))
    assert resolved.text is None
    assert resolved.path is None
    assert resolved.truncated is False


def test_empty_file_is_skipped(tmp_path: pathlib.Path) -> None:
    run = tmp_path / "runs" / "r1"
    _write(run / "domain-knowledge" / "anvil-instructions.md", "   \n")
    _write(tmp_path / "anvil-instructions.md", "BASE LEVEL")
    resolved = resolve_instructions(str(run), str(tmp_path))
    assert resolved.text == "BASE LEVEL"


def test_hard_cap_applied(tmp_path: pathlib.Path) -> None:
    # FR-INS-003: oversize protection is a one-time 16k cap at resolution.
    _write(tmp_path / "anvil-instructions.md", "z" * (MAX_INSTRUCTIONS_CHARS + 500))
    resolved = resolve_instructions(str(tmp_path / "nope"), str(tmp_path))
    assert resolved.truncated is True
    assert resolved.text is not None and len(resolved.text) == MAX_INSTRUCTIONS_CHARS


def test_instructions_injected_into_doc_and_code_prompts(tmp_path: pathlib.Path) -> None:
    # FR-INS-002: every phase prompt carries the delimited block.
    backend = LLMBackend(
        provider=object(), workspace_root=str(tmp_path),
        instructions="Default to a single-file HTML app.",
    )
    doc_prompt = backend._doc_prompt(
        PhaseStep(phase="proposal", instruction="", output_paths=["docs/proposal.md"])
    )
    code_prompt = backend._code_prompt(
        PhaseStep(phase="implementation", instruction="", output_paths=["src/"])
    )
    for prompt in (doc_prompt, code_prompt):
        assert "Standing instructions" in prompt
        assert "Default to a single-file HTML app." in prompt


def test_no_instructions_no_block(tmp_path: pathlib.Path) -> None:
    backend = LLMBackend(provider=object(), workspace_root=str(tmp_path))
    prompt = backend._doc_prompt(
        PhaseStep(phase="proposal", instruction="", output_paths=["docs/proposal.md"])
    )
    assert "Standing instructions" not in prompt
