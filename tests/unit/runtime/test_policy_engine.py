"""Unit tests for the policy engine, rule evaluator, and remediation.

Slice 3 (spec §2.6; FR-PL-004/005/007/008).
"""

from __future__ import annotations

from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.models import PolicyDocument, PolicyRule
from anvil_runtime.policy.rule_evaluator import PolicyActionContext


def _policy() -> PolicyDocument:
    return PolicyDocument(policies=[
        PolicyRule(
            name="AllowedModels", type="whitelist", target="model-selection",
            values=["claude-3-haiku", "deepseek-coder"],
            remediable=True, remediationStrategy="switch-to-allowed-model",
        ),
        PolicyRule(
            name="TokenBudgetPerPhase", type="numeric-limit", target="token-consumption",
            limits={"specification": 15000}, remediable=False,
        ),
    ])


def test_allowed_model_passes() -> None:
    engine = PolicyEngine(_policy())
    decision = engine.check(PolicyActionContext(action="model-selection", model="deepseek-coder"))
    assert decision.allowed is True
    assert decision.violation is None


def test_forbidden_model_denied_and_remediable() -> None:
    engine = PolicyEngine(_policy())
    decision = engine.check(PolicyActionContext(action="model-selection", model="gpt-4o"))
    assert decision.allowed is False
    assert decision.violation is not None
    assert decision.violation.remediable is True


def test_enforce_auto_remediates_forbidden_model() -> None:
    engine = PolicyEngine(_policy())
    decision, outcome = engine.enforce(
        PolicyActionContext(action="model-selection", model="gpt-4o")
    )
    assert decision.allowed is False
    assert outcome is not None
    assert outcome.success is True
    assert outcome.replacement == "claude-3-haiku"  # first allowed model


def test_token_budget_exceeded_is_unremediable() -> None:
    engine = PolicyEngine(_policy())
    decision, outcome = engine.enforce(
        PolicyActionContext(action="token-consumption", phase="specification", tokens=20000)
    )
    assert decision.allowed is False
    assert outcome is None  # not remediable -> escalate


def test_token_within_budget_allowed() -> None:
    engine = PolicyEngine(_policy())
    decision = engine.check(
        PolicyActionContext(action="token-consumption", phase="specification", tokens=10000)
    )
    assert decision.allowed is True


def test_allowed_models_helper_unions_rule_values() -> None:
    engine = PolicyEngine(_policy())
    assert engine.allowed_models() == ["claude-3-haiku", "deepseek-coder"]


def test_mandatory_gates_rule_flags_missing_gate() -> None:
    engine = PolicyEngine(PolicyDocument(policies=[
        PolicyRule(
            name="RequiredApprovalGates", type="list-mandatory",
            target="approval-checkpoints",
            gates=["post-proposal", "post-architecture"],
        ),
    ]))
    # Only one of the two required gates present -> violation.
    missing = engine.check(
        PolicyActionContext(action="approval-checkpoints", gates=["post-proposal"])
    )
    assert missing.allowed is False
    # All required gates present -> allowed.
    present = engine.check(
        PolicyActionContext(
            action="approval-checkpoints",
            gates=["post-proposal", "post-architecture"],
        )
    )
    assert present.allowed is True
