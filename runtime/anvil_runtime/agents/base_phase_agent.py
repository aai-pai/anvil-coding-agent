"""Base contract for all phase agents.

Slice 1 deliverable (blueprint §3.1). ``BasePhaseAgent`` is the abstract base
every concrete phase agent (Slice 2) extends. It fixes the invocation contract
(``run``) and the single-writer output boundary (``allowed_outputs``) without
embedding any orchestration or model-routing logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from anvil_runtime.core.phase_contracts import (
    PHASE_CONTRACTS,
    PhaseCompleteEvent,
    PhaseInvocationPayload,
)


class BasePhaseAgent(ABC):
    """Abstract base for phase agents.

    Subclasses set ``phase_id`` and implement :meth:`run`. The default
    :meth:`allowed_outputs` resolves the phase's declared output boundary from
    :data:`anvil_runtime.core.phase_contracts.PHASE_CONTRACTS`, enforcing
    single-writer ownership without each agent restating its paths.
    """

    phase_id: str

    def __init__(self, phase_id: str | None = None) -> None:
        # Allow either a class-level ``phase_id`` or constructor injection.
        if phase_id is not None:
            self.phase_id = phase_id
        if not getattr(self, "phase_id", None):
            raise ValueError("BasePhaseAgent requires a non-empty phase_id")

    @abstractmethod
    def run(self, payload: PhaseInvocationPayload) -> PhaseCompleteEvent:
        """Execute the phase and report a structured completion event."""
        raise NotImplementedError

    def allowed_outputs(self) -> list[str]:
        """Return the closed set of output paths this phase may write."""
        contract = PHASE_CONTRACTS.get(self.phase_id)
        if contract is None:
            return []
        return list(contract.allowed_outputs)


__all__ = ["BasePhaseAgent"]
