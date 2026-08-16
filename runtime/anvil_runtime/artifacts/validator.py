"""Deterministic artifact validation.

Slice 6 deliverable (blueprint §3.1; spec FR-SV-009, FR-AR-001/002/005).
Validates that a phase's required outputs exist and conform to their schema:
the canonical document exists and is non-empty, carries a valid metadata header
(FR-AR-005) when required, and contains the schema's required section headings.
Validation is deterministic pass/fail — no warnings or soft errors (FR-AR-002) —
and emits ``ArtifactValidationFailed`` on any issue.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from anvil_runtime.artifacts.metadata import (
    split_front_matter,
    validate_metadata,
)
from anvil_runtime.artifacts.schemas import ARTIFACT_SCHEMAS, ArtifactSchema
from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.state.event_bus import EventBus


class ArtifactIssue(BaseModel):
    """A single deterministic validation failure."""

    path: str
    kind: str  # "missing" | "empty" | "metadata" | "section" | "contract"
    detail: str


class ArtifactValidationResult(BaseModel):
    """Pass/fail outcome of validating a phase's artifacts."""

    phase: str
    valid: bool
    issues: list[ArtifactIssue] = Field(default_factory=list)


def collect_count(tests_root: pathlib.Path) -> int | None:
    """Tests pytest can collect under ``tests_root``; None if it cannot run.

    ``None`` means the question could not be asked (no pytest, timeout) and
    must not be read as "zero tests" — that would fail a qa phase for an
    environment problem. Collection is the minimum bar for calling something
    a test: it proves the module imports and defines test functions.
    """
    import subprocess
    import sys

    if not tests_root.is_dir():
        return 0
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             str(tests_root)],
            capture_output=True, text=True, timeout=120,
            cwd=str(tests_root.parent),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    import re

    match = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout or "")
    if match:
        return int(match.group(1))
    if "no tests ran" in (proc.stdout or "") or proc.returncode != 0:
        return 0
    return None


class ArtifactValidator:
    """Validates phase artifacts against schema and structure requirements."""

    def __init__(
        self,
        workspace_root: str | pathlib.Path = ".",
        schemas: dict[str, ArtifactSchema] | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
        qa_collect: Callable[[pathlib.Path], int | None] | None = None,
    ) -> None:
        self._root = pathlib.Path(workspace_root)
        self._schemas = schemas if schemas is not None else ARTIFACT_SCHEMAS
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # #30: injectable, and OFF unless wired. The offline transport writes
        # placeholder artifacts by design, so a collection gate would fail
        # every offline plumbing run for a reason that says nothing about the
        # plumbing. `app.py` wires :func:`collect_count` for real execution
        # only — the mode where a qa phase claiming to ship tests should be
        # made to prove it. Injectable so unit tests never spawn pytest.
        self._qa_collect = qa_collect

    def validate(self, phase_id: str, artifact_paths: list[str]) -> ArtifactValidationResult:
        """Validate the phase's required outputs (FR-SV-009)."""
        issues: list[ArtifactIssue] = []
        schema = self._schemas.get(phase_id)

        if schema is None:
            # Directory-only phase: require each declared output path to exist.
            for rel in artifact_paths:
                if not (self._root / rel).exists():
                    issues.append(ArtifactIssue(
                        path=rel, kind="missing", detail="declared output does not exist"
                    ))
        else:
            issues.extend(self._validate_document(schema))

        # v0.1.3 #21: the generated code is checked mechanically against the
        # task contract's manifest (when one is pinned). Deterministic AST
        # checks, no LLM — violations fail the phase into the retry path.
        if phase_id == "implementation":
            issues.extend(self._validate_contract_manifest())

        # v0.1.5 #30 (FR-QT-004): a qa phase that emits .py files which do not
        # COLLECT has not produced tests. Existence and a .py extension would
        # be satisfied by three files containing `assert True`.
        if phase_id == "qa" and self._qa_collect is not None:
            issues.extend(self._validate_tests_collect())

        result = ArtifactValidationResult(
            phase=phase_id, valid=not issues, issues=issues
        )
        if not result.valid:
            self._emit_failure(result)
        return result

    def _validate_tests_collect(self) -> list[ArtifactIssue]:
        """FR-QT-004: the qa phase's tests must collect, and be non-zero."""
        tests_root = self._root / "tests"
        collected = self._qa_collect(tests_root)
        if collected is None:
            return []  # unknown, not zero — never fail on a tooling problem
        if collected == 0:
            return [ArtifactIssue(
                path="tests/", kind="empty",
                detail="pytest collected 0 tests from the qa phase's output",
            )]
        return []

    def _validate_document(self, schema: ArtifactSchema) -> list[ArtifactIssue]:
        issues: list[ArtifactIssue] = []
        target = self._root / schema.path
        if not target.is_file():
            return [ArtifactIssue(
                path=schema.path, kind="missing", detail="required artifact is missing"
            )]
        text = target.read_text(encoding="utf-8")
        if not text.strip():
            return [ArtifactIssue(path=schema.path, kind="empty", detail="artifact is empty")]

        meta, body = split_front_matter(text)
        if schema.require_metadata:
            for problem in validate_metadata(meta):
                issues.append(ArtifactIssue(
                    path=schema.path, kind="metadata", detail=problem
                ))
        # Required sections are checked against heading lines only (not body
        # prose), so a passing mention in paragraph text cannot mask a missing
        # section heading.
        headings = "\n".join(
            line for line in body.splitlines() if line.lstrip().startswith("#")
        ).lower()
        for heading in schema.required_sections:
            if heading.lower() not in headings:
                issues.append(ArtifactIssue(
                    path=schema.path, kind="section",
                    detail=f"missing required section '{heading}'",
                ))
        return issues

    def _validate_contract_manifest(self) -> list[ArtifactIssue]:
        """Check ``src/`` against the contract's manifest (#21), if any.

        A prose-only contract (or no contract at all) validates as today; a
        malformed manifest fence fails loudly rather than silently skipping
        the mechanical check.
        """
        from anvil_runtime.contract import (
            DOMAIN_KNOWLEDGE_REL,
            parse_contract_manifest,
            resolve_contract,
            validate_manifest,
        )

        resolved = resolve_contract(self._root)
        if not resolved.present:
            return []
        manifest, error = parse_contract_manifest(resolved.text)
        if error is not None:
            return [ArtifactIssue(
                path=DOMAIN_KNOWLEDGE_REL, kind="contract", detail=error
            )]
        if manifest is None:
            return []
        return [
            ArtifactIssue(path="src/", kind="contract", detail=violation)
            for violation in validate_manifest(manifest, self._root / "src")
        ]

    def _emit_failure(self, result: ArtifactValidationResult) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType="ArtifactValidationFailed",
            runId=self._run_id, phase=result.phase, severity="error",
            data={"issues": [i.model_dump() for i in result.issues]},
        ))


__all__ = ["ArtifactValidator", "ArtifactValidationResult", "ArtifactIssue"]
