"""Phase invocation helpers shared by concrete phase agents.

Slice 2 deliverable (blueprint §3.1). Builds the :class:`PhaseInvocationPayload`
from a phase contract and supplies the deterministic stub result used by the
v0.1.0 phase agents. Real LLM/OpenHands-backed execution replaces
:func:`stub_phase_result` via the SDK adapter in Slice 5; the supervisor
contract (input payload in, ``PhaseCompleteEvent`` out) stays unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anvil_runtime.core.phase_contracts import (
    PhaseContract,
    PhaseCompleteEvent,
    PhaseInvocationPayload,
)

if TYPE_CHECKING:
    from anvil_runtime.agents.base_phase_agent import BasePhaseAgent


def build_invocation_payload(
    contract: PhaseContract,
    phase_context: dict[str, object] | None = None,
    previous_phase_outputs: list[str] | None = None,
    input_schema: dict[str, object] | None = None,
) -> PhaseInvocationPayload:
    """Assemble the payload the supervisor hands to a phase agent."""
    return PhaseInvocationPayload(
        phase_name=contract.phase_id,
        input_files=list(contract.input_files),
        input_schema=dict(input_schema or {}),
        output_paths=list(contract.allowed_outputs),
        phase_context=dict(phase_context or {}),
        previous_phase_outputs=list(previous_phase_outputs or []),
    )


def stub_phase_result(
    agent: "BasePhaseAgent", payload: PhaseInvocationPayload
) -> PhaseCompleteEvent:
    """Deterministic success result for the v0.1.0 phase-agent stubs.

    Reports the phase's declared outputs as artifact paths with no checksums
    (the stub does not author artifacts). Slice 5 swaps in real execution.
    """
    return PhaseCompleteEvent(
        phase_name=agent.phase_id,
        status="success",
        artifact_paths=list(payload.output_paths or agent.allowed_outputs()),
        checksums={},
        duration_ms=0,
    )


__all__ = ["build_invocation_payload", "stub_phase_result"]
