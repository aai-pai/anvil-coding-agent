"""Phase registry: lookup of phase contracts by ID.

Slice 2 deliverable (blueprint §2.2; spec FR-SV-005/006). Thin read-only view
over :data:`anvil_runtime.core.phase_contracts.PHASE_CONTRACTS` so the
development manager and agent factory resolve a phase's contract without
importing the contract table directly everywhere.
"""

from __future__ import annotations

from anvil_runtime.core.phase_contracts import (
    PHASE_CONTRACTS,
    PHASE_IDS,
    PhaseContract,
)


class PhaseRegistry:
    """Resolves phase IDs to their declared contracts."""

    def __init__(self, contracts: dict[str, PhaseContract] | None = None) -> None:
        self._contracts = dict(contracts) if contracts is not None else dict(PHASE_CONTRACTS)

    def all_phase_ids(self) -> list[str]:
        """Phase IDs in canonical order."""
        return [p for p in PHASE_IDS if p in self._contracts]

    def has(self, phase_id: str) -> bool:
        return phase_id in self._contracts

    def get(self, phase_id: str) -> PhaseContract:
        try:
            return self._contracts[phase_id]
        except KeyError as exc:
            raise KeyError(f"Unknown phase '{phase_id}'") from exc

    def agent_name(self, phase_id: str) -> str:
        return self.get(phase_id).agent_name


__all__ = ["PhaseRegistry"]
