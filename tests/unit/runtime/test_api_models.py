"""Unit tests for API request/response models and JSON-schema constants.

Slice 1 (blueprint §4.1, §4.2, §5.1).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from anvil_runtime.api.models import (
    APPROVAL_REQUEST_SCHEMA,
    EVENT_ENVELOPE_SCHEMA,
    OVERRIDE_REQUEST_SCHEMA,
    PHASE_COMPLETE_SCHEMA,
    ApprovalRequest,
    OverrideRequest,
    RunStarted,
    RunStartRequest,
)


def test_run_start_request_valid() -> None:
    req = RunStartRequest(mode="secure", security_profile="restricted")
    assert req.mode == "secure"
    assert req.phase_gates == []
    assert req.run_overrides == {}


def test_run_start_request_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        RunStartRequest(mode="turbo", security_profile="restricted")


def test_run_start_request_rejects_unknown_profile() -> None:
    with pytest.raises(ValidationError):
        RunStartRequest(mode="gated", security_profile="paranoid")


def test_approval_request_comments_optional() -> None:
    req = ApprovalRequest(
        gateId="post-architecture",
        gateName="Post-Architecture",
        approved=True,
        requesterId="user-1",
    )
    assert req.comments is None
    assert req.approved is True


def test_approval_request_requires_requester() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(gateId="g", gateName="G", approved=False)


def test_override_request_action_literal_enforced() -> None:
    ok = OverrideRequest(action="rollback", reason="bad drift", requesterId="u")
    assert ok.action == "rollback"
    assert ok.targetPhase is None
    with pytest.raises(ValidationError):
        OverrideRequest(action="delete-everything", reason="x", requesterId="u")


def test_run_started_parses_iso_datetime() -> None:
    started = RunStarted(run_id="r1", started_at="2026-05-31T00:00:00Z", mode="secure")
    assert isinstance(started.started_at, datetime)
    assert started.run_id == "r1"


@pytest.mark.parametrize(
    "schema",
    [
        APPROVAL_REQUEST_SCHEMA,
        OVERRIDE_REQUEST_SCHEMA,
        EVENT_ENVELOPE_SCHEMA,
        PHASE_COMPLETE_SCHEMA,
    ],
)
def test_schema_constants_are_object_schemas(schema: dict) -> None:
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    assert "properties" in schema


def test_approval_schema_exposes_known_properties() -> None:
    props = APPROVAL_REQUEST_SCHEMA["properties"]
    for field in ("gateId", "gateName", "approved", "requesterId"):
        assert field in props


def test_event_envelope_schema_derived_from_core_model() -> None:
    # EVENT_ENVELOPE_SCHEMA must describe the core EventEnvelope contract.
    props = EVENT_ENVELOPE_SCHEMA["properties"]
    for field in ("timestamp", "eventType", "runId", "phase", "severity"):
        assert field in props
