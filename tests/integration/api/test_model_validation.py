"""Integration tests: cross-module model validation and schema coherence.

Slice 1 (blueprint §4.1, §4.2). Verifies that the API models, the core phase
contracts, and the derived JSON-schema constants stay coherent across module
boundaries.
"""

from __future__ import annotations

from anvil_runtime.api import models
from anvil_runtime.core.phase_contracts import EventEnvelope, PhaseCompleteEvent
from anvil_runtime.policy.models import POLICY_RULE_SCHEMA, PolicyDocument


def test_event_envelope_schema_matches_core_model_fields() -> None:
    # The api-layer constant must be exactly the core model's schema.
    assert models.EVENT_ENVELOPE_SCHEMA == EventEnvelope.model_json_schema()


def test_phase_complete_schema_matches_core_model_fields() -> None:
    assert models.PHASE_COMPLETE_SCHEMA == PhaseCompleteEvent.model_json_schema()


def test_run_start_request_roundtrip_through_dict() -> None:
    raw = {
        "mode": "secure",
        "security_profile": "restricted",
        "phase_gates": ["proposal", "architecture"],
        "run_overrides": {"tokenBudgetPerPhase": {"implementation": 25000}},
    }
    req = models.RunStartRequest.model_validate(raw)
    assert req.phase_gates == ["proposal", "architecture"]
    # Round-trips back to an equivalent payload.
    assert req.model_dump()["run_overrides"]["tokenBudgetPerPhase"]["implementation"] == 25000


def test_approval_request_from_spec_example_payload() -> None:
    raw = {
        "gateId": "post-architecture",
        "gateName": "Post-Architecture",
        "approved": True,
        "comments": "looks good",
        "requesterId": "user-1",
    }
    req = models.ApprovalRequest.model_validate(raw)
    assert req.approved is True
    assert req.comments == "looks good"


def test_event_envelope_serialize_then_revalidate() -> None:
    ev = EventEnvelope(
        timestamp="2026-05-31T00:00:00Z",
        eventType="PolicyViolation",
        runId="r1",
        phase="implementation",
        severity="error",
        data={"policy": "AllowedModels"},
    )
    dumped = ev.model_dump(mode="json")
    restored = EventEnvelope.model_validate(dumped)
    assert restored.severity == "error"
    assert restored.data["policy"] == "AllowedModels"


def test_policy_document_loads_spec_example_rules() -> None:
    # Mirrors the spec §4.3 example policy file.
    doc = PolicyDocument.model_validate(
        {
            "policyVersion": "0.1.0",
            "policies": [
                {
                    "name": "AllowedModels",
                    "type": "whitelist",
                    "target": "model-selection",
                    "values": ["claude-3-haiku", "deepseek-coder"],
                    "remediable": True,
                    "remediationStrategy": "switch-to-allowed-model",
                },
                {
                    "name": "TokenBudgetPerPhase",
                    "type": "numeric-limit",
                    "target": "token-consumption",
                    "limits": {"proposal": 10000},
                },
            ],
        }
    )
    assert doc.policies[0].remediable is True
    # FR-PL-003A: remediable defaults to False when omitted.
    assert doc.policies[1].remediable is False
    assert POLICY_RULE_SCHEMA["type"] == "object"
