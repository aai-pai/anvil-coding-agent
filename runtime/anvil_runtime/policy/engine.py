"""Policy engine: evaluation, remediation, and escalation routing.

Slice 3 deliverable (blueprint §3.1; spec §2.6). Evaluates gated actions against
the loaded policy document, emits ``PolicyViolation`` audit events, and
orchestrates auto-remediation before escalation (FR-PL-005/007). Remediable
violations are auto-fixed when possible; unremediable ones (or failed
remediation) are returned for the supervisor to escalate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.policy.models import PolicyDocument
from anvil_runtime.policy.remediation import RemediationOutcome, Remediator
from anvil_runtime.policy.rule_evaluator import (
    PolicyActionContext,
    PolicyViolation,
    RuleEvaluator,
)

if TYPE_CHECKING:
    from anvil_runtime.state.event_bus import EventBus


class PolicyDecision(BaseModel):
    """Outcome of a policy check for a single action."""

    allowed: bool
    violation: PolicyViolation | None = None


class PolicyEngine:
    """Evaluates policy checks and orchestrates remediation before escalation."""

    def __init__(
        self,
        policy: PolicyDocument | None = None,
        event_bus: "EventBus | None" = None,
        evaluator: RuleEvaluator | None = None,
        remediator: Remediator | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy or PolicyDocument()
        self._event_bus = event_bus
        self._evaluator = evaluator or RuleEvaluator()
        self._remediator = remediator or Remediator()
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, ctx: PolicyActionContext) -> PolicyDecision:
        """Evaluate the action against every rule; first violation denies."""
        for rule in self._policy.policies:
            violation = self._evaluator.evaluate(rule, ctx)
            if violation is not None:
                self._emit_violation(violation)
                return PolicyDecision(allowed=False, violation=violation)
        return PolicyDecision(allowed=True)

    def apply_remediation(self, violation: PolicyViolation) -> RemediationOutcome:
        outcome = self._remediator.remediate(violation, self.allowed_models())
        self._emit(
            "PolicyRemediation",
            severity="info" if outcome.success else "warning",
            data={
                "rule": violation.rule_name,
                "success": outcome.success,
                "detail": outcome.detail,
                "replacement": outcome.replacement,
            },
        )
        return outcome

    def enforce(self, ctx: PolicyActionContext) -> tuple[PolicyDecision, RemediationOutcome | None]:
        """Check then auto-remediate remediable violations (FR-PL-007)."""
        decision = self.check(ctx)
        if decision.allowed or decision.violation is None:
            return decision, None
        if decision.violation.remediable:
            return decision, self.apply_remediation(decision.violation)
        return decision, None

    def allowed_models(self) -> list[str]:
        """Union of AllowedModels values declared by model-selection rules."""
        models: list[str] = []
        for rule in self._policy.policies:
            if rule.target == "model-selection" and rule.values:
                for model in rule.values:
                    if model not in models:
                        models.append(model)
        return models

    # -- audit ------------------------------------------------------------

    def _emit_violation(self, violation: PolicyViolation) -> None:
        self._emit(
            "PolicyViolation",
            severity="warning",
            data={
                "rule": violation.rule_name,
                "target": violation.target,
                "reason": violation.reason,
                "remediable": violation.remediable,
            },
        )

    def _emit(self, event_type: str, severity: str, data: dict) -> None:
        if self._event_bus is None:
            return
        self._event_bus.emit(
            EventEnvelope(
                timestamp=self._clock(),
                eventType=event_type,
                runId=self._run_id,
                phase="",
                severity=severity,
                data=data,
            )
        )


__all__ = ["PolicyEngine", "PolicyDecision"]
