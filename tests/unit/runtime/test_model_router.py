"""Unit tests: phase + subtask model routing and policy enforcement.

Slice 5 (spec FR-ML-001..006; plan §2.5). Verifies default routing, override
precedence, and policy-driven remediation when a routed model is forbidden.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.llm.model_router import (
    DEFAULT_CODING_MODEL,
    DEFAULT_PLANNING_MODEL,
    ModelRouter,
)
from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.models import PolicyDocument
from anvil_runtime.state.event_bus import EventBus


def test_default_routing_by_subtask() -> None:
    router = ModelRouter()
    assert router.route("proposal", "planning") == DEFAULT_PLANNING_MODEL
    assert router.route("specification", "analysis") == DEFAULT_PLANNING_MODEL
    assert router.route("implementation", "coding") == DEFAULT_CODING_MODEL
    assert router.route("implementation", "debugging") == DEFAULT_CODING_MODEL


def test_review_subtask_inherits_phase_default() -> None:
    router = ModelRouter()
    # review -> phase default: coding phase vs planning phase.
    assert router.route("implementation", "review") == DEFAULT_CODING_MODEL
    assert router.route("architecture", "review") == DEFAULT_PLANNING_MODEL


def test_override_precedence_subtask_over_phase() -> None:
    router = ModelRouter(
        phase_models={"implementation": "phase-model"},
        subtask_models={"coding": "subtask-model"},
    )
    # subtask override wins over phase override.
    assert router.route("implementation", "coding") == "subtask-model"
    # phase override applies when no subtask override matches.
    assert router.route("implementation", "review") == "phase-model"


def _policy_allowing(models: list[str]) -> PolicyDocument:
    return PolicyDocument.model_validate(
        {
            "policyVersion": "0.1.0",
            "policies": [
                {
                    "name": "AllowedModels",
                    "type": "whitelist",
                    "target": "model-selection",
                    "values": models,
                    "remediable": True,
                    "remediationStrategy": "switch-to-allowed-model",
                }
            ],
        }
    )


def test_select_remediates_forbidden_model(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    engine = PolicyEngine(policy=_policy_allowing([DEFAULT_PLANNING_MODEL]), event_bus=bus)
    router = ModelRouter(policy_engine=engine, event_bus=bus, run_id="r1")

    # coding routes to DeepSeek Coder, which is not allowed -> remediate to gemma-4.
    decision = router.select("implementation", "coding")
    assert decision.remediated is True
    assert decision.model == DEFAULT_PLANNING_MODEL
    assert decision.allowed is True

    types = {e.eventType for e in bus.read_all()}
    assert "ModelRouteSelected" in types


def test_select_allows_permitted_model(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    engine = PolicyEngine(policy=_policy_allowing([DEFAULT_CODING_MODEL]), event_bus=bus)
    router = ModelRouter(policy_engine=engine, event_bus=bus)

    decision = router.select("implementation", "coding")
    assert decision.model == DEFAULT_CODING_MODEL
    assert decision.remediated is False
    assert decision.allowed is True


def test_select_marks_not_allowed_when_unremediable(tmp_path: pathlib.Path) -> None:
    # Allowlist with no remediation and an empty intersection -> not allowed.
    doc = PolicyDocument.model_validate(
        {
            "policyVersion": "0.1.0",
            "policies": [
                {
                    "name": "AllowedModels",
                    "type": "whitelist",
                    "target": "model-selection",
                    "values": ["claude-3-haiku"],
                    "remediable": False,
                }
            ],
        }
    )
    bus = EventBus(str(tmp_path))
    router = ModelRouter(policy_engine=PolicyEngine(policy=doc, event_bus=bus), event_bus=bus)
    decision = router.select("implementation", "coding")
    assert decision.allowed is False
