"""QA phase agent (phase id: qa). Owns docs/qa-test-plan.md and tests/*."""

from __future__ import annotations

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.agents.phase_invocation import stub_phase_result
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent, PhaseInvocationPayload


class QAAgent(BasePhaseAgent):
    phase_id = "qa"

    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        return stub_phase_result(self, payload)


__all__ = ["QAAgent"]
