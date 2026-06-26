"""Unit tests: section-specific document generation (#10, FR-DOC-001/002).

Verifies the LLMBackend document writer emits the body once and synthesizes
placeholders only for missing required-section headings — never a verbatim copy of
the body under each section (the FR-002 §A duplication bug).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.sdk.openhands_adapter import LLMBackend, PhaseStep


def _backend(tmp_path: pathlib.Path) -> LLMBackend:
    # _document uses only the clock + schema lookup, not the provider.
    return LLMBackend(provider=object(), workspace_root=str(tmp_path))


def _step() -> PhaseStep:
    return PhaseStep(phase="proposal", instruction="", output_paths=["docs/proposal.md"])


def test_body_written_once_no_duplication(tmp_path: pathlib.Path) -> None:
    # FR-DOC-001: the body appears exactly once, not repeated per required section.
    doc = _backend(tmp_path)._document(_step(), "UNIQUE_BODY_MARKER full generated proposal.")
    assert doc.count("UNIQUE_BODY_MARKER") == 1


def test_missing_required_sections_get_placeholders(tmp_path: pathlib.Path) -> None:
    # proposal requires "Problem Statement" and "Scope"; absent from the body -> added.
    doc = _backend(tmp_path)._document(_step(), "body without section headings")
    assert "## Problem Statement" in doc
    assert "## Scope" in doc
    assert "_See above._" in doc  # explicit placeholder, never a copy of the body


def test_present_sections_kept_not_duplicated(tmp_path: pathlib.Path) -> None:
    # FR-DOC-002: sections the model produced are kept as-is and not re-added.
    content = "## Problem Statement\n\nThe specific problem.\n\n## Scope\n\nThe specific scope."
    doc = _backend(tmp_path)._document(_step(), content)
    assert doc.count("## Problem Statement") == 1
    assert doc.count("## Scope") == 1
    assert doc.count("The specific problem.") == 1
    assert "_See above._" not in doc


def test_generated_document_passes_validator(tmp_path: pathlib.Path) -> None:
    doc = _backend(tmp_path)._document(_step(), "placeholder body")
    target = tmp_path / "docs" / "proposal.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(doc, encoding="utf-8")
    result = ArtifactValidator(workspace_root=str(tmp_path)).validate(
        "proposal", ["docs/proposal.md"]
    )
    assert result.valid is True
