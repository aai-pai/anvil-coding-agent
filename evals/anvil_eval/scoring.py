"""Scoring: held-out pytest execution, audit-trail metrics, artifact checks.

The three scorers are independent and each degrades gracefully — a run that
produced no ``src/`` still gets event metrics; a run with no events.jsonl
still gets its tests executed (they will fail, which is the honest score).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

# ---------------------------------------------------------------------------
# Held-out tests
# ---------------------------------------------------------------------------

# Injected next to the copied held-out tests so they can `import <module>`
# straight from the generated project's src/.
_CONFTEST = '''\
import os
import sys

_src = os.environ.get("ANVIL_GENERATED_SRC")
if _src and _src not in sys.path:
    sys.path.insert(0, _src)
'''


def run_held_out_tests(held_out_dir: pathlib.Path, run_dir: pathlib.Path,
                       sandbox_dir: pathlib.Path, timeout_s: float) -> dict:
    """Copy the held-out tests into a sandbox and run pytest against the run.

    Tests see the generated project through two channels: ``src/`` is on
    ``sys.path`` (via an injected conftest), and the ``ANVIL_GENERATED_SRC`` /
    ``ANVIL_RUN_DIR`` env vars point at the run for subprocess/file-based
    assertions. Returns counts plus pass/fail; never raises.
    """
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    shutil.copytree(held_out_dir, sandbox_dir)
    (sandbox_dir / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
    junit_path = sandbox_dir / "junit.xml"

    src_dir = run_dir / "src"
    env = dict(os.environ)
    env["ANVIL_GENERATED_SRC"] = str(src_dir)
    env["ANVIL_RUN_DIR"] = str(run_dir)

    command = [sys.executable, "-m", "pytest", "-q", "--tb=short",
               "-p", "no:cacheprovider", f"--junitxml={junit_path}", "."]
    try:
        proc = subprocess.run(
            command, cwd=str(sandbox_dir), env=env, timeout=timeout_s,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        exit_code: int | None = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        output = f"pytest timed out after {timeout_s}s\n" + str(exc)

    counts = _parse_junit(junit_path)
    passed_all = (
        exit_code == 0
        and counts["total"] > 0
        and counts["failures"] + counts["errors"] == 0
    )
    return {
        "passed": passed_all,
        "exit_code": exit_code,
        "src_exists": src_dir.is_dir(),
        **counts,
        "output_tail": output[-2000:],
    }


def _parse_junit(junit_path: pathlib.Path) -> dict:
    """Counts from pytest's built-in junit XML; zeros when it was never written."""
    counts = {"total": 0, "failures": 0, "errors": 0, "skipped": 0}
    if not junit_path.is_file():
        return counts
    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError:
        return counts
    suites = root.iter("testsuite") if root.tag == "testsuites" else [root]
    for suite in suites:
        counts["total"] += int(suite.get("tests", 0))
        counts["failures"] += int(suite.get("failures", 0))
        counts["errors"] += int(suite.get("errors", 0))
        counts["skipped"] += int(suite.get("skipped", 0))
    counts["passed_count"] = (counts["total"] - counts["failures"]
                              - counts["errors"] - counts["skipped"])
    return counts


# ---------------------------------------------------------------------------
# Audit-trail (events.jsonl) metrics
# ---------------------------------------------------------------------------


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def analyze_events(run_dir: pathlib.Path) -> dict:
    """Tokens, timings, routing, tier, and reliability signals from the trail."""
    events_path = run_dir / "logs" / "events.jsonl"
    metrics: dict = {
        "events_found": events_path.is_file(),
        "complexity_tier": None,
        "phases": {},          # phase -> {tokens, model, duration_s}
        "total_tokens": 0,
        "duration_s": None,
        "run_completed_event": False,
        "escalations": 0,
        "artifact_validation_failures": 0,
        "input_truncations": 0,
        "warnings_or_errors": 0,
        "instructions_path": None,
    }
    if not events_path.is_file():
        return metrics

    events = []
    for raw in events_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    phases: dict[str, dict] = {}
    started_at: dict[str, datetime] = {}
    first_ts = last_ts = None
    for event in events:
        ts = _parse_ts(event.get("timestamp", ""))
        if ts is not None:
            first_ts = first_ts or ts
            last_ts = ts
        etype = event.get("eventType", "")
        phase = event.get("phase", "")
        data = event.get("data", {}) or {}
        entry = phases.setdefault(phase, {}) if phase else None
        if etype == "PhaseStarted" and ts is not None:
            started_at[phase] = ts
        elif etype == "PhaseCompleted":
            if ts is not None and phase in started_at:
                entry["duration_s"] = round((ts - started_at[phase]).total_seconds(), 2)
            entry["artifacts"] = data.get("artifact_paths", [])
        elif etype == "TokenUsageReported" and entry is not None:
            # The tracker emits *accumulated* per-phase totals; keep the max.
            entry["tokens"] = max(entry.get("tokens", 0),
                                  int(data.get("total_tokens", 0)))
        elif etype == "ModelRouteSelected" and entry is not None:
            entry["model"] = data.get("model")
        elif etype == "ComplexityAssessed":
            metrics["complexity_tier"] = data.get("tier")
        elif etype == "RunCompleted":
            metrics["run_completed_event"] = True
        elif etype == "PhaseEscalation":
            metrics["escalations"] += 1
        elif etype == "ArtifactValidationFailed":
            metrics["artifact_validation_failures"] += 1
        elif etype == "InputTruncated":
            metrics["input_truncations"] += 1
        elif etype == "InstructionsResolved":
            metrics["instructions_path"] = data.get("path")
        if event.get("severity") in ("warning", "error"):
            metrics["warnings_or_errors"] += 1

    metrics["phases"] = {p: v for p, v in phases.items() if p}
    metrics["total_tokens"] = sum(v.get("tokens", 0) for v in phases.values())
    if first_ts is not None and last_ts is not None:
        metrics["duration_s"] = round((last_ts - first_ts).total_seconds(), 2)
    return metrics


def estimate_cost_usd(event_metrics: dict, pricing: dict[str, float]) -> float | None:
    """Blended-rate estimate: per-phase tokens x the routed model's $/Mtok."""
    if not pricing:
        return None
    total = 0.0
    priced_any = False
    for info in event_metrics.get("phases", {}).values():
        model, tokens = info.get("model"), info.get("tokens", 0)
        if model in pricing and tokens:
            total += tokens * pricing[model] / 1_000_000
            priced_any = True
    return round(total, 6) if priced_any else None


# ---------------------------------------------------------------------------
# Artifact / OKF checks
# ---------------------------------------------------------------------------

_FRONTMATTER_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", re.MULTILINE)
_OKF_REQUIRED = {"type", "title"}
_LINEAGE_FIELDS = {"artifactId", "phase"}


def _frontmatter_keys(markdown: str) -> set[str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return set()
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1)
                   if line.strip() == "---")
    except StopIteration:
        return set()
    block = "\n".join(lines[1:end])
    return set(_FRONTMATTER_KEY.findall(block))


def check_artifacts(run_dir: pathlib.Path) -> dict:
    """OKF conformance of docs/*.md, index.md presence, src size, failure records."""
    docs_dir = run_dir / "docs"
    doc_files = sorted(docs_dir.glob("*.md")) if docs_dir.is_dir() else []
    doc_files = [p for p in doc_files if p.name.lower() != "index.md"]
    okf_valid = lineage_valid = 0
    for doc in doc_files:
        keys = _frontmatter_keys(doc.read_text(encoding="utf-8", errors="replace"))
        if _OKF_REQUIRED <= keys:
            okf_valid += 1
        if _LINEAGE_FIELDS <= keys:
            lineage_valid += 1
    src_dir = run_dir / "src"
    src_files = ([p for p in src_dir.rglob("*") if p.is_file()]
                 if src_dir.is_dir() else [])
    failure_dir = docs_dir / "failure_records"
    return {
        "docs_total": len(doc_files),
        "okf_valid": okf_valid,
        "lineage_valid": lineage_valid,
        "index_md_present": (docs_dir / "index.md").is_file(),
        "src_file_count": len(src_files),
        "failure_records": (len(list(failure_dir.glob("*.md")))
                            if failure_dir.is_dir() else 0),
    }


__all__ = ["run_held_out_tests", "analyze_events", "estimate_cost_usd",
           "check_artifacts"]
