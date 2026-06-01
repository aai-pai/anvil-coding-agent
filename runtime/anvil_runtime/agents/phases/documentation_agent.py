"""Documentation phase agent (phase id: documentation). Owns docs/documentation-plan.md."""

from __future__ import annotations

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.agents.phase_invocation import stub_phase_result
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent, PhaseInvocationPayload


class DocumentationAgent(BasePhaseAgent):
    phase_id = "documentation"

    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        return stub_phase_result(self, payload)


__all__ = ["DocumentationAgent"]
