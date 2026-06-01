"""Unit tests: drift detection, ordering, and classification.

Slice 6 (spec §2.5, FR-DR-002A/004/005/006/007; plan §2.6). Verifies the
Blueprint -> Architecture -> Spec ordering, severity classification, coverage
drift, inconclusive handling, and DriftCheckResult emission.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.drift.checker import DriftChecker, DriftContext, DriftReport
from anvil_runtime.drift.classifier import classify, highest
from anvil_runtime.drift.remediation import DriftRemediator
from anvil_runtime.state.event_bus import EventBus


def test_classifier_severity_mapping() -> None:
    assert classify("missing_docstring") == "minor"
    assert classify("missing_module") == "major"
    assert classify("architectural_violation") == "critical"
    assert classify("unknown_kind") == "major"  # fail-safe default
    assert highest(["minor", "critical", "major"]) == "critical"
    assert highest([]) is None


def test_missing_module_is_major() -> None:
    report = DriftChecker().check(
        "implementation",
        DriftContext(blueprint_modules=["a", "b"], code_modules=["a"]),
    )
    assert report.highest_severity == "major"
    kinds = {f.kind for f in report.findings}
    assert "missing_module" in kinds


def test_findings_follow_blueprint_arch_spec_order() -> None:
    report = DriftChecker().check(
        "implementation",
        DriftContext(
            blueprint_modules=["bp"], code_modules=[],
            architecture_components=["arch"], implemented_components=[],
            spec_requirements=["NFR-X"], verified_requirements=[],
        ),
    )
    references = [f.reference for f in report.findings]
    assert references == ["blueprint", "architecture", "spec"]


def test_low_coverage_flagged() -> None:
    report = DriftChecker().check(
        "qa", DriftContext(coverage=0.5, coverage_threshold=0.7)
    )
    assert any(f.kind == "low_coverage" for f in report.findings)


def test_clean_check_has_no_findings() -> None:
    report = DriftChecker().check(
        "implementation",
        DriftContext(blueprint_modules=["a"], code_modules=["a"]),
    )
    assert report.findings == []
    assert report.highest_severity is None


def test_inconclusive_short_circuits() -> None:
    report = DriftChecker().check("implementation", DriftContext(inconclusive=True))
    assert report.inconclusive is True
    assert report.findings == []


def test_emits_drift_check_result(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    DriftChecker(event_bus=bus, run_id="r1").check(
        "implementation", DriftContext(blueprint_modules=["a"], code_modules=[])
    )
    events = [e for e in bus.read_all() if e.eventType == "DriftCheckResult"]
    assert events and events[0].data["highest_severity"] == "major"


def test_remediation_routing() -> None:
    rem = DriftRemediator()
    minor = DriftChecker().check(
        "x", DriftContext(spec_requirements=["r"], verified_requirements=[])
    )
    # unverified_nfr is major -> rollback-reexecute within budget.
    assert rem.plan(minor, attempt=1).action == "rollback-reexecute"

    critical = DriftChecker().check(
        "x",
        DriftContext(architecture_components=[], implemented_components=["ghost"]),
    )
    # extra implemented component vs architecture is a boundary_violation (critical).
    assert rem.plan(critical, attempt=1).action == "escalate"


def test_remediation_budget_and_tolerance() -> None:
    rem = DriftRemediator(max_attempts=2)

    # No drift -> no action.
    clean = DriftReport(phase="x", findings=[], highest_severity=None)
    assert rem.plan(clean).action == "none"

    # Inconclusive -> escalate (FR-DR-003).
    inconclusive = DriftReport(phase="x", inconclusive=True)
    assert rem.plan(inconclusive).escalate is True

    minor = DriftReport(phase="x", highest_severity="minor")
    # Within budget: auto-remediate (FR-DR-005).
    assert rem.plan(minor, attempt=1).action == "auto-remediate"
    # Budget exhausted: minor tolerated (FR-DR-009).
    tolerated = rem.plan(minor, attempt=3)
    assert tolerated.action == "tolerate"
    assert tolerated.escalate is False

    # Budget exhausted: major escalates (FR-DR-009).
    major = DriftReport(phase="x", highest_severity="major")
    assert rem.plan(major, attempt=3).escalate is True
