"""Phase agent factory.

Slice 2 deliverable (blueprint §3.1). Builds the concrete phase agent for a
phase ID. Policy/model/tool constraints are layered onto agents in later slices
(Slice 3 policy, Slice 5 model routing + OpenHands); the factory's public
contract ``create(phase_id) -> BasePhaseAgent`` is fixed here.
"""

from __future__ import annotations

from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
from anvil_runtime.agents.phases import (
    ArchitectureAgent,
    BlueprintAgent,
    CleanupAgent,
    DeploymentAgent,
    DevPlanAgent,
    DocumentationAgent,
    FactoryInitAgent,
    ImplementationAgent,
    PackagingAgent,
    ProposalAgent,
    QAAgent,
    SpecificationAgent,
)

# Phase ID -> concrete agent class. Keys are the kebab-case phase IDs.
_AGENT_CLASSES: dict[str, type[BasePhaseAgent]] = {
    "proposal": ProposalAgent,
    "factory-init": FactoryInitAgent,
    "specification": SpecificationAgent,
    "architecture": ArchitectureAgent,
    "blueprint": BlueprintAgent,
    "dev-plan": DevPlanAgent,
    "implementation": ImplementationAgent,
    "qa": QAAgent,
    "packaging": PackagingAgent,
    "documentation": DocumentationAgent,
    "deployment": DeploymentAgent,
    "cleanup": CleanupAgent,
}


class PhaseAgentFactory:
    """Constructs phase agents by phase ID."""

    def __init__(self, agent_classes: dict[str, type[BasePhaseAgent]] | None = None) -> None:
        self._classes = dict(agent_classes) if agent_classes is not None else dict(_AGENT_CLASSES)

    def supported_phases(self) -> list[str]:
        return list(self._classes)

    def create(self, phase_id: str) -> BasePhaseAgent:
        try:
            agent_cls = self._classes[phase_id]
        except KeyError as exc:
            raise KeyError(f"No phase agent registered for '{phase_id}'") from exc
        return agent_cls()


__all__ = ["PhaseAgentFactory"]
