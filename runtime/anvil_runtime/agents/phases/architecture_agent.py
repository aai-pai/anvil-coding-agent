"""Architecture phase agent (phase id: architecture). Owns docs/architecture.md."""

from __future__ import annotations

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.agents.phase_invocation import stub_phase_result
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent, PhaseInvocationPayload


class ArchitectureAgent(BasePhaseAgent):
    phase_id = "architecture"

    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        return stub_phase_result(self, payload)


__all__ = ["ArchitectureAgent"]
