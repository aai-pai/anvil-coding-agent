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
    # (Asserted on the body: the OKF `description` header field legitimately
    # carries the first content line, #16.)
    from anvil_runtime.artifacts.metadata import split_front_matter

    doc = _backend(tmp_path)._document(_step(), "UNIQUE_BODY_MARKER full generated proposal.")
    _, body = split_front_matter(doc)
    assert body.count("UNIQUE_BODY_MARKER") == 1


def test_missing_required_sections_get_placeholders(tmp_path: pathlib.Path) -> None:
    # proposal requires "Problem Statement" and "Scope"; absent from the body -> added.
    doc = _backend(tmp_path)._document(_step(), "body without section headings")
    assert "## Problem Statement" in doc
    assert "## Scope" in doc
    assert "_See above._" in doc  # explicit placeholder, never a copy of the body


def test_present_sections_kept_not_duplicated(tmp_path: pathlib.Path) -> None:
    # FR-DOC-002: sections the model produced are kept as-is and not re-added.
    from anvil_runtime.artifacts.metadata import split_front_matter

    content = "## Problem Statement\n\nThe specific problem.\n\n## Scope\n\nThe specific scope."
    doc = _backend(tmp_path)._document(_step(), content)
    _, body = split_front_matter(doc)
    assert body.count("## Problem Statement") == 1
    assert body.count("## Scope") == 1
    assert body.count("The specific problem.") == 1
    assert "_See above._" not in body


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


def test_document_header_is_okf_conformant(tmp_path: pathlib.Path) -> None:
    # #16 (FR-OKF-001): OKF standard fields present alongside the lineage fields.
    from anvil_runtime.artifacts.metadata import split_front_matter

    doc = _backend(tmp_path)._document(
        _step(), "A short proposal for a to-do list app.\n\nMore detail."
    )
    meta, _ = split_front_matter(doc)
    assert meta["type"] == "Proposal"
    assert meta["title"].startswith("Proposal — ")
    assert meta["description"] == "A short proposal for a to-do list app."
    assert meta["tags"] == ["anvil", "proposal"]
    assert meta["timestamp"] == meta["generatedAt"]
    # Lineage fields intact (OKF producer extensions).
    assert meta["artifactId"] == "proposal-v1"
    assert meta["phase"] == "proposal"
    assert meta["derivedFrom"]


def test_validator_rejects_document_missing_okf_type(tmp_path: pathlib.Path) -> None:
    # #16 (FR-OKF-002): `type`/`title` are now required metadata.
    target = tmp_path / "docs" / "proposal.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nartifactId: proposal-v1\nphase: proposal\ngeneratedAt: t\n"
        "derivedFrom: [x]\n---\n# Proposal\n\n## Problem Statement\np\n## Scope\ns\n",
        encoding="utf-8",
    )
    result = ArtifactValidator(workspace_root=str(tmp_path)).validate(
        "proposal", ["docs/proposal.md"]
    )
    assert result.valid is False
    assert any("type" in issue.detail for issue in result.issues)
    assert any("title" in issue.detail for issue in result.issues)


def test_doc_prompt_encourages_cross_links(tmp_path: pathlib.Path) -> None:
    # #16 (FR-OKF-004).
    prompt = _backend(tmp_path)._doc_prompt(_step())
    assert "relative markdown links" in prompt
