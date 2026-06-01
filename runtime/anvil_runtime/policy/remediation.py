"""Policy auto-remediation strategies.

Slice 3 deliverable (spec §2.6.4; FR-PL-007/008). Attempts to auto-remediate a
remediable :class:`PolicyViolation` before escalation. v0.1.0 implements the
``switch-to-allowed-model`` strategy (FR-PL-008); non-remediable violations
return an unsuccessful outcome so the caller escalates.
"""

from __future__ import annotations

from pydantic import BaseModel

from anvil_runtime.policy.rule_evaluator import PolicyViolation

STRATEGY_SWITCH_MODEL = "switch-to-allowed-model"


class RemediationOutcome(BaseModel):
    """Result of an auto-remediation attempt."""

    success: bool
    strategy: str | None = None
    detail: str = ""
    # Replacement value produced by remediation (e.g., the substitute model).
    replacement: str | None = None


class Remediator:
    """Applies auto-remediation strategies to remediable violations."""

    def remediate(
        self, violation: PolicyViolation, allowed_models: list[str] | None = None
    ) -> RemediationOutcome:
        if not violation.remediable:
            return RemediationOutcome(
                success=False, detail=f"violation of '{violation.rule_name}' is not remediable"
            )
        if violation.remediationStrategy == STRATEGY_SWITCH_MODEL:
            return self._switch_model(violation, allowed_models or [])
        return RemediationOutcome(
            success=False,
            strategy=violation.remediationStrategy,
            detail=f"no handler for strategy '{violation.remediationStrategy}'",
        )

    def _switch_model(self, violation: PolicyViolation, allowed_models: list[str]) -> RemediationOutcome:
        # Prefer the allowlist carried on the violating rule's context, falling
        # back to the supplied allowed_models.
        candidates = allowed_models
        if not candidates:
            return RemediationOutcome(
                success=False, strategy=STRATEGY_SWITCH_MODEL,
                detail="no allowed model available to switch to",
            )
        replacement = candidates[0]
        return RemediationOutcome(
            success=True,
            strategy=STRATEGY_SWITCH_MODEL,
            detail=f"switched to allowed model '{replacement}'",
            replacement=replacement,
        )


__all__ = ["Remediator", "RemediationOutcome", "STRATEGY_SWITCH_MODEL"]
