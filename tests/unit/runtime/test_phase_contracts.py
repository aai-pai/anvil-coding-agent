"""Unit tests for phase contracts, core payloads, and the base phase agent.

Slice 1 (blueprint §3.1, §4.1; proposal §9).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.core.phase_contracts import (
    PHASE_CONTRACTS,
    PHASE_IDS,
    EventEnvelope,
    PhaseCompleteEvent,
    PhaseContract,
    PhaseInvocationPayload,
    RunState,
)


def test_twelve_canonical_phases() -> None:
    assert len(PHASE_IDS) == 12
    # Kebab-case identifiers from blueprint §6.3.
    assert "factory-init" in PHASE_IDS
    assert "dev-plan" in PHASE_IDS
    assert PHASE_IDS[0] == "proposal"
    assert PHASE_IDS[-1] == "cleanup"


def test_every_phase_has_a_consistent_contract() -> None:
    assert set(PHASE_CONTRACTS) == set(PHASE_IDS)
    for phase_id, contract in PHASE_CONTRACTS.items():
        assert isinstance(contract, PhaseContract)
        assert contract.phase_id == phase_id
        assert contract.agent_name.endswith("_agent")
        assert contract.allowed_outputs, f"{phase_id} must declare outputs"


def test_phase_invocation_payload_defaults() -> None:
    payload = PhaseInvocationPayload(phase_name="architecture")
    assert payload.input_files == []
    assert payload.phase_context == {}
    assert payload.previous_phase_outputs == []


def test_phase_complete_event_requires_status_and_duration() -> None:
    ev = PhaseCompleteEvent(phase_name="qa", status="success", duration_ms=1200)
    assert ev.status == "success"
    assert ev.token_usage is None
    with pytest.raises(ValidationError):
        PhaseCompleteEvent(phase_name="qa", status="maybe", duration_ms=1)
    with pytest.raises(ValidationError):
        PhaseCompleteEvent(phase_name="qa", status="success")  # missing duration


def test_event_envelope_severity_default_and_validation() -> None:
    ev = EventEnvelope(
        timestamp="2026-05-31T00:00:00Z",
        eventType="PhaseStarted",
        runId="r1",
        phase="proposal",
    )
    assert ev.severity == "info"
    with pytest.raises(ValidationError):
        EventEnvelope(
            timestamp="2026-05-31T00:00:00Z",
            eventType="X",
            runId="r1",
            phase="proposal",
            severity="fatal",
        )


def test_run_state_defaults() -> None:
    state = RunState(runStateVersion="0.1.0", run_id="r1", mode="secure")
    assert state.completed_phases == []
    assert state.retry_counters == {}


def test_base_phase_agent_is_abstract() -> None:
    with pytest.raises(TypeError):
        BasePhaseAgent(phase_id="proposal")  # type: ignore[abstract]


def test_concrete_phase_agent_resolves_allowed_outputs() -> None:
    class _Dummy(BasePhaseAgent):
        def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
            return PhaseCompleteEvent(
                phase_name=self.phase_id, status="success", duration_ms=0
            )

    agent = _Dummy(phase_id="proposal")
    assert agent.allowed_outputs() == ["docs/proposal.md"]
    result = agent.run(PhaseInvocationPayload(phase_name="proposal"))
    assert result.status == "success"


def test_phase_agent_requires_phase_id() -> None:
    class _Dummy(BasePhaseAgent):
        def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
            return PhaseCompleteEvent(
                phase_name=self.phase_id, status="success", duration_ms=0
            )

    with pytest.raises(ValueError):
        _Dummy(phase_id="")
