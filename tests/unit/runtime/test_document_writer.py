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


class _CollectingBus:
    """Minimal EventBus stand-in capturing emitted envelopes."""

    def __init__(self) -> None:
        self.events = []

    def emit(self, envelope) -> None:  # noqa: ANN001
        self.events.append(envelope)


def test_default_input_limit_reads_large_file_in_full(tmp_path: pathlib.Path) -> None:
    # FR-CTX-001: the old hardcoded 2,500-char cap is gone; a rich input file is
    # read in full under the 20,000-char default.
    rel = "domain-knowledge/background-information.md"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x" * 5_000 + "TAIL_MARKER", encoding="utf-8")
    backend = _backend(tmp_path)
    ctx = backend._read_inputs(PhaseStep(phase="proposal", instruction="", input_files=[rel]))
    assert "TAIL_MARKER" in ctx


def test_truncation_emits_warning_event(tmp_path: pathlib.Path) -> None:
    # FR-CTX-002: an actual cut emits InputTruncated naming file, size, and limit.
    rel = "docs/spec.md"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("y" * 300, encoding="utf-8")
    bus = _CollectingBus()
    backend = LLMBackend(
        provider=object(), workspace_root=str(tmp_path),
        input_char_limit=100, event_bus=bus,
    )
    step = PhaseStep(
        phase="architecture", instruction="", input_files=[rel],
        context={"run_id": "run-42"},
    )
    ctx = backend._read_inputs(step)
    assert len(ctx) < 300
    assert len(bus.events) == 1
    event = bus.events[0]
    assert event.eventType == "InputTruncated"
    assert event.severity == "warning"
    assert event.runId == "run-42"
    assert event.data == {"file": rel, "size": 300, "limit": 100}


def test_no_truncation_no_event(tmp_path: pathlib.Path) -> None:
    rel = "docs/spec.md"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("short", encoding="utf-8")
    bus = _CollectingBus()
    backend = LLMBackend(
        provider=object(), workspace_root=str(tmp_path),
        input_char_limit=100, event_bus=bus,
    )
    backend._read_inputs(PhaseStep(phase="blueprint", instruction="", input_files=[rel]))
    assert bus.events == []


def test_generated_document_passes_validator(tmp_path: pathlib.Path) -> None:
    doc = _backend(tmp_path)._document(_step(), "placeholder body")
    target = tmp_path / "docs" / "proposal.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(doc, encoding="utf-8")
    result = ArtifactValidator(workspace_root=str(tmp_path)).validate(
        "proposal", ["docs/proposal.md"]
    )
    assert result.valid is True
