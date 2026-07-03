"""Intake phase agent (phase id: intake). v0.1.2 #15.

Assesses the completeness of ``domain-knowledge/background-information.md``
before the proposal phase. The stub reports success with no questions and no
file writes (FR-INT-004), preserving pre-v0.1.2 pipeline behavior exactly; real
completeness assessment runs through the LLM backend's intake path.
"""

from __future__ import annotations

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent, PhaseInvocationPayload


class IntakeAgent(BasePhaseAgent):
    phase_id = "intake"

    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        return PhaseCompleteEvent(
            phase_name=self.phase_id,
            status="success",
            artifact_paths=[],
            checksums={},
            duration_ms=0,
        )


__all__ = ["IntakeAgent"]
