"""Drift remediation routing.

Slice 6 deliverable (spec §2.5.3/2.5.4, FR-DR-005..010, NFR-RB-003). Maps a drift
report's highest severity and the remediation attempt count to a concrete action:

* ``minor``    -> auto-remediate (re-invoke phase agent with the drift report);
                  tolerated after the attempt budget is exhausted (FR-DR-009).
* ``major``    -> rollback + re-execute Blueprint/Implementation (FR-DR-006);
                  escalate once the budget is exhausted.
* ``critical`` -> escalate immediately, never auto-remediated (FR-DR-007).

Remediation attempts are bounded (max 2, FR-DR-008/NFR-RB-003) and counted
separately from self-heal retries.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from anvil_runtime.drift.checker import DriftReport

DriftAction = Literal["none", "auto-remediate", "rollback-reexecute", "escalate", "tolerate"]

MAX_DRIFT_REMEDIATION_ATTEMPTS = 2  # FR-DR-008 / NFR-RB-003


class DriftRemediationPlan(BaseModel):
    """The action to take for a drift report at a given attempt."""

    severity: str | None
    action: DriftAction
    attempt: int
    escalate: bool
    detail: str


class DriftRemediator:
    """Decides the remediation action for a drift report (FR-DR-005..009)."""

    def __init__(self, max_attempts: int = MAX_DRIFT_REMEDIATION_ATTEMPTS) -> None:
        self._max_attempts = max_attempts

    def plan(self, report: DriftReport, attempt: int = 1) -> DriftRemediationPlan:
        severity = report.highest_severity

        if report.inconclusive:
            return self._plan(severity, "escalate", attempt, True,
                              "drift check inconclusive; escalating for review")

        if severity is None:
            return self._plan(None, "none", attempt, False, "no drift detected")

        # Critical drift is never auto-remediated (FR-DR-007).
        if severity == "critical":
            return self._plan(severity, "escalate", attempt, True,
                              "critical drift cannot be auto-remediated")

        # Budget exhausted: minor is tolerated, major escalates (FR-DR-009).
        if attempt > self._max_attempts:
            if severity == "minor":
                return self._plan(severity, "tolerate", attempt, False,
                                  "minor drift tolerated after remediation budget")
            return self._plan(severity, "escalate", attempt, True,
                              f"{severity} drift unresolved after {self._max_attempts} attempts")

        # Within budget: route by severity (FR-DR-005/006).
        if severity == "minor":
            return self._plan(severity, "auto-remediate", attempt, False,
                              "re-invoke phase agent with drift report")
        return self._plan(severity, "rollback-reexecute", attempt, False,
                          "rollback and re-execute with failure context")

    @staticmethod
    def _plan(
        severity: str | None, action: DriftAction, attempt: int, escalate: bool, detail: str
    ) -> DriftRemediationPlan:
        return DriftRemediationPlan(
            severity=severity, action=action, attempt=attempt,
            escalate=escalate, detail=detail,
        )


__all__ = ["DriftRemediator", "DriftRemediationPlan", "DriftAction", "MAX_DRIFT_REMEDIATION_ATTEMPTS"]
