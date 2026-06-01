"""Concrete phase agents (one per pipeline phase).

Slice 2 provides deterministic stub agents that honor the phase contracts and
single-writer output boundaries. Real execution is wired via the OpenHands SDK
adapter in Slice 5 without changing these classes' public contract.
"""

from __future__ import annotations

from anvil_runtime.agents.phases.architecture_agent import ArchitectureAgent
from anvil_runtime.agents.phases.blueprint_agent import BlueprintAgent
from anvil_runtime.agents.phases.cleanup_agent import CleanupAgent
from anvil_runtime.agents.phases.deployment_agent import DeploymentAgent
from anvil_runtime.agents.phases.dev_plan_agent import DevPlanAgent
from anvil_runtime.agents.phases.documentation_agent import DocumentationAgent
from anvil_runtime.agents.phases.factory_init_agent import FactoryInitAgent
from anvil_runtime.agents.phases.implementation_agent import ImplementationAgent
from anvil_runtime.agents.phases.packaging_agent import PackagingAgent
from anvil_runtime.agents.phases.proposal_agent import ProposalAgent
from anvil_runtime.agents.phases.qa_agent import QAAgent
from anvil_runtime.agents.phases.specification_agent import SpecificationAgent

__all__ = [
    "ProposalAgent",
    "FactoryInitAgent",
    "SpecificationAgent",
    "ArchitectureAgent",
    "BlueprintAgent",
    "DevPlanAgent",
    "ImplementationAgent",
    "QAAgent",
    "PackagingAgent",
    "DocumentationAgent",
    "DeploymentAgent",
    "CleanupAgent",
]
