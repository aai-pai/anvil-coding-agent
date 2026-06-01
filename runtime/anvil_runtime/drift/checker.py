"""Drift detection across Blueprint, Architecture, and Spec.

Slice 6 deliverable (blueprint §3.1; spec §2.5.2, FR-DR-001/002/002A/003/004).
Compares the implemented code against the controlling artifacts and reports any
divergence, in the required order — Blueprint -> Architecture -> Spec
(FR-DR-002A) — with each finding classified by severity. Emits ``DriftCheckResult``
(FR-DR-004). A check that cannot be completed is reported as inconclusive
(FR-DR-003).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.drift.classifier import DriftSeverity, classify, highest
from anvil_runtime.state.event_bus import EventBus


class DriftContext(BaseModel):
    """Inputs for a drift check: declared vs. implemented surfaces."""

    blueprint_modules: list[str] = Field(default_factory=list)
    architecture_components: list[str] = Field(default_factory=list)
    spec_requirements: list[str] = Field(default_factory=list)
    code_modules: list[str] = Field(default_factory=list)
    implemented_components: list[str] = Field(default_factory=list)
    verified_requirements: list[str] = Field(default_factory=list)
    coverage: float | None = None
    coverage_threshold: float | None = None
    inconclusive: bool = False


class DriftFinding(BaseModel):
    """One detected divergence with its reference artifact and severity."""

    kind: str
    severity: DriftSeverity
    reference: str  # "blueprint" | "architecture" | "spec" | "coverage"
    detail: str
    remediation_suggestion: str = ""


class DriftReport(BaseModel):
    """Ordered findings + overall severity for a phase's drift check."""

    phase: str
    findings: list[DriftFinding] = Field(default_factory=list)
    highest_severity: DriftSeverity | None = None
    inconclusive: bool = False


class DriftChecker:
    """Finds and classifies blueprint/architecture/spec drift."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, phase_id: str, context: DriftContext) -> DriftReport:
        """Run drift checks in Blueprint -> Architecture -> Spec order."""
        if context.inconclusive:
            report = DriftReport(phase=phase_id, inconclusive=True)
            self._emit(report)
            return report

        findings: list[DriftFinding] = []
        # 1. Blueprint: module-level divergence (FR-DR-002A order).
        findings += self._diff(
            "blueprint", context.blueprint_modules, context.code_modules,
            missing_kind="missing_module", extra_kind="extra_module", unit="module",
        )
        # 2. Architecture: component/interface divergence.
        findings += self._diff(
            "architecture", context.architecture_components, context.implemented_components,
            missing_kind="missing_core_feature", extra_kind="boundary_violation",
            unit="component",
        )
        # 3. Spec: unverified requirements.
        for req in context.spec_requirements:
            if req not in context.verified_requirements:
                findings.append(self._finding(
                    "unverified_nfr", "spec",
                    f"spec requirement '{req}' is not verified in code",
                    "add verification/enforcement for the requirement",
                ))
        # Coverage threshold (FR-DR-001 #5).
        if context.coverage is not None and context.coverage_threshold is not None:
            if context.coverage < context.coverage_threshold:
                findings.append(self._finding(
                    "low_coverage", "coverage",
                    f"coverage {context.coverage:.0%} below threshold "
                    f"{context.coverage_threshold:.0%}",
                    "add tests to meet the QA coverage target",
                ))

        report = DriftReport(
            phase=phase_id,
            findings=findings,
            highest_severity=highest([f.severity for f in findings]),
        )
        self._emit(report)
        return report

    def _diff(
        self,
        reference: str,
        declared: list[str],
        implemented: list[str],
        missing_kind: str,
        extra_kind: str,
        unit: str,
    ) -> list[DriftFinding]:
        findings: list[DriftFinding] = []
        declared_set, implemented_set = set(declared), set(implemented)
        for name in declared:
            if name not in implemented_set:
                findings.append(self._finding(
                    missing_kind, reference,
                    f"{unit} '{name}' declared in {reference} but missing in code",
                    f"implement the missing {unit}",
                ))
        for name in implemented:
            if name not in declared_set:
                findings.append(self._finding(
                    extra_kind, reference,
                    f"{unit} '{name}' in code is not declared in {reference}",
                    f"remove the {unit} or update the {reference}",
                ))
        return findings

    @staticmethod
    def _finding(kind: str, reference: str, detail: str, suggestion: str) -> DriftFinding:
        return DriftFinding(
            kind=kind, severity=classify(kind), reference=reference,
            detail=detail, remediation_suggestion=suggestion,
        )

    def _emit(self, report: DriftReport) -> None:
        if self._events is None:
            return
        severity = "error" if report.highest_severity == "critical" else (
            "warning" if report.findings or report.inconclusive else "info"
        )
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType="DriftCheckResult",
            runId=self._run_id, phase=report.phase, severity=severity,
            data={
                "inconclusive": report.inconclusive,
                "highest_severity": report.highest_severity,
                "findings": [f.model_dump() for f in report.findings],
            },
        ))


__all__ = ["DriftChecker", "DriftContext", "DriftReport", "DriftFinding"]
