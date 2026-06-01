"""Integration: forbidden-model violation is remediated and audited.

Slice 3 (spec FR-PL-005/007/008).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.models import PolicyDocument, PolicyRule
from anvil_runtime.policy.rule_evaluator import PolicyActionContext
from anvil_runtime.state.event_bus import EventBus


def test_forbidden_model_remediation_emits_audit_trail(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    policy = PolicyDocument(policies=[
        PolicyRule(
            name="AllowedModels", type="whitelist", target="model-selection",
            values=["deepseek-coder"], remediable=True,
            remediationStrategy="switch-to-allowed-model",
        ),
    ])
    engine = PolicyEngine(policy, event_bus=bus, run_id="run-1")

    decision, outcome = engine.enforce(
        PolicyActionContext(action="model-selection", model="gpt-4o", phase="implementation")
    )

    assert decision.allowed is False
    assert outcome is not None and outcome.success
    assert outcome.replacement == "deepseek-coder"

    event_types = [e.eventType for e in bus.read_all()]
    assert "PolicyViolation" in event_types
    assert "PolicyRemediation" in event_types
