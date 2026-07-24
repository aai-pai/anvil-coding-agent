"""Structured failure localization from JUnit XML (v0.1.4 #26).

Mechanical, no LLM involvement. When ``externalTestCommand`` carries the
``{junit_xml}`` token, the command writes a JUnit report to a canonical
workspace path; this module turns that report into root-cause clusters:

* :func:`substitute_report_token` — the FR-JL-001 token contract.
* :func:`try_parse_report` — report → :class:`FailureRecord` list; a
  missing/malformed report returns ``None`` (the command may have died
  before writing it — the caller degrades to basename mapping, FR-JL-002).
* :func:`cluster` — records → :class:`FailureCluster` keyed by
  **(error type, implicated file)**, size-descending (FR-JL-003). The four
  v0.1.3 tinydb clusters explained ~160 of 177 red tests; one repair round
  should attack one cause, not one file-name coincidence.
* :func:`cluster_excerpt` — the cause-focused prompt excerpt that replaces
  the raw output tail (FR-JL-004).

Implication reuses FR-RL-007's join key: the deepest traceback line whose
basename matches a generated target.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

JUNIT_TOKEN = "{junit_xml}"
REPORT_REL = ".anvil/junit-report.xml"
EXCERPT_FAILURES = 3  # representative failures per cluster excerpt
_FRAME_EXCERPT_CHARS = 700


def substitute_report_token(command: str) -> tuple[str, str | None]:
    """(effective command, report_rel) — report_rel None without the token."""
    if JUNIT_TOKEN not in command:
        return command, None
    return command.replace(JUNIT_TOKEN, REPORT_REL), REPORT_REL


class FailureRecord(BaseModel):
    """One failed/errored testcase, mapped to a generated artifact."""

    test_id: str
    error_type: str
    message: str = ""
    file: str | None = None  # implicated generated target, if any
    excerpt: str = ""


class FailureCluster(BaseModel):
    """Failures sharing a root-cause key: (error type, implicated file)."""

    error_type: str
    file: str | None = None
    records: list[FailureRecord] = Field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.records)


def _implicated_target(text: str, targets: list[str]) -> str | None:
    """Deepest traceback line naming a target (FR-RL-007's basename key)."""
    normalized = text.replace("\\", "/")
    names = {rel.replace("\\", "/").rsplit("/", 1)[-1]: rel for rel in targets}
    found: str | None = None
    for line in normalized.splitlines():
        for name, rel in names.items():
            if name and name in line:
                found = rel  # keep scanning: deepest match wins
    return found


def try_parse_report(
    path: str | pathlib.Path, targets: list[str]
) -> list[FailureRecord] | None:
    """Records from a JUnit report; None when missing/unreadable/malformed."""
    target = pathlib.Path(path)
    if not target.is_file():
        return None
    try:
        root = ET.fromstring(target.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError:
        return None
    records: list[FailureRecord] = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            for node in case.findall(kind):
                text = node.text or ""
                records.append(FailureRecord(
                    test_id=".".join(filter(None, [
                        case.get("classname", ""), case.get("name", "")])),
                    error_type=node.get("type") or kind,
                    message=(node.get("message") or "").strip(),
                    file=_implicated_target(text, targets),
                    excerpt=text.strip()[-_FRAME_EXCERPT_CHARS:],
                ))
    return records


def cluster(records: list[FailureRecord]) -> list[FailureCluster]:
    """Group by (error type, implicated file), largest cause first (stable)."""
    grouped: dict[tuple[str, str | None], FailureCluster] = {}
    for record in records:
        key = (record.error_type, record.file)
        grouped.setdefault(key, FailureCluster(
            error_type=record.error_type, file=record.file,
        )).records.append(record)
    return sorted(grouped.values(), key=lambda c: -c.size)


def cluster_excerpt(target: FailureCluster, limit: int = EXCERPT_FAILURES) -> str:
    """Cause-focused failure summary for one repair prompt (FR-JL-004)."""
    lines = [
        f"{target.size} test failure(s) share one root cause — "
        f"{target.error_type}"
        + (f" implicating `{target.file}`" if target.file else "")
        + ". Representative failures:"
    ]
    for record in target.records[:limit]:
        lines.append(f"- {record.test_id}: {record.message}".rstrip(": "))
        if record.excerpt:
            lines.append("  " + record.excerpt.replace("\n", "\n  "))
    if target.size > limit:
        lines.append(f"(and {target.size - limit} more with the same cause)")
    return "\n".join(lines)


__all__ = [
    "JUNIT_TOKEN",
    "REPORT_REL",
    "FailureRecord",
    "FailureCluster",
    "substitute_report_token",
    "try_parse_report",
    "cluster",
    "cluster_excerpt",
]
