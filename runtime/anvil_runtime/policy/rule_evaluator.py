"""Policy rule evaluation.

Slice 3 deliverable (spec §2.6, §4.3). Evaluates an action against the policy
rules and produces a :class:`PolicyViolation` when a rule is breached. v0.1.0
supports the three spec-defined rule families: ``whitelist`` (model-selection),
``numeric-limit`` (token-consumption), and ``list-mandatory`` (approval gates).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from anvil_runtime.policy.models import PolicyRule


class PolicyActionContext(BaseModel):
    """Describes the gated action being checked (spec FR-PL-004)."""

    action: str  # e.g. "model-selection", "token-consumption"
    phase: str | None = None
    model: str | None = None
    tokens: int | None = None
    gates: list[str] = Field(default_factory=list)


class PolicyViolation(BaseModel):
    """A breached policy rule with the context needed to remediate or escalate."""

    rule_name: str
    target: str
    reason: str
    remediable: bool = False
    remediationStrategy: str | None = None
    context: PolicyActionContext | None = None


class RuleEvaluator:
    """Evaluates a single rule against an action context."""

    def evaluate(self, rule: PolicyRule, ctx: PolicyActionContext) -> PolicyViolation | None:
        if rule.target == "model-selection" and ctx.action == "model-selection":
            return self._eval_whitelist_model(rule, ctx)
        if rule.target == "token-consumption" and ctx.action == "token-consumption":
            return self._eval_token_limit(rule, ctx)
        if rule.target == "approval-checkpoints" and ctx.action == "approval-checkpoints":
            return self._eval_mandatory_gates(rule, ctx)
        return None

    def _violation(self, rule: PolicyRule, reason: str, ctx: PolicyActionContext) -> PolicyViolation:
        return PolicyViolation(
            rule_name=rule.name,
            target=rule.target,
            reason=reason,
            remediable=rule.remediable,
            remediationStrategy=rule.remediationStrategy,
            context=ctx,
        )

    def _eval_whitelist_model(self, rule: PolicyRule, ctx: PolicyActionContext) -> PolicyViolation | None:
        allowed = rule.values or []
        if ctx.model is not None and ctx.model not in allowed:
            return self._violation(rule, f"model '{ctx.model}' is not in AllowedModels", ctx)
        return None

    def _eval_token_limit(self, rule: PolicyRule, ctx: PolicyActionContext) -> PolicyViolation | None:
        limits = rule.limits or {}
        if ctx.phase is None or ctx.tokens is None:
            return None
        limit = limits.get(ctx.phase)
        if limit is not None and ctx.tokens > limit:
            return self._violation(
                rule, f"phase '{ctx.phase}' used {ctx.tokens} tokens (limit {limit})", ctx
            )
        return None

    def _eval_mandatory_gates(self, rule: PolicyRule, ctx: PolicyActionContext) -> PolicyViolation | None:
        required = rule.gates or []
        missing = [g for g in required if g not in ctx.gates]
        if missing:
            return self._violation(rule, f"missing mandatory gates: {missing}", ctx)
        return None


__all__ = ["RuleEvaluator", "PolicyActionContext", "PolicyViolation"]
