"""Phase contracts and core runtime data models.

Slice 1 deliverable. This module defines:

* The canonical ordered list of twelve phase IDs (kebab-case per blueprint
  §6.3) and their per-phase input/output contracts (proposal §9).
* The deterministic phase-invocation and phase-completion payloads exchanged
  between the supervisor and phase agents (blueprint §4.1).
* The structured :class:`EventEnvelope` audit record and the :class:`RunState`
  checkpoint schema (blueprint §4.1).

It intentionally contains no orchestration logic: the phase DAG, registry, and
development manager are Slice 2. Keeping these contracts in one import-light
module lets every later slice type against a stable surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Canonical phase identifiers (proposal §9, blueprint §6.3)
# ---------------------------------------------------------------------------

PHASE_IDS: tuple[str, ...] = (
    "proposal",
    "factory-init",
    "specification",
    "architecture",
    "blueprint",
    "dev-plan",
    "implementation",
    "qa",
    "packaging",
    "documentation",
    "deployment",
    "cleanup",
)

PhaseStatus = Literal["success", "failure"]
EventSeverity = Literal["info", "warning", "error", "critical"]


# ---------------------------------------------------------------------------
# Phase contract (per-phase input/output ownership)
# ---------------------------------------------------------------------------


class PhaseContract(BaseModel):
    """Declares a phase's identity, owning agent, and artifact boundaries.

    ``allowed_outputs`` is the closed set of paths/prefixes a phase agent may
    write; the supervisor and artifact validator enforce single-writer
    ownership against it. This mirrors proposal §8.2 ("Defined input/output
    files; allowed tools and behaviors").
    """

    phase_id: str
    agent_name: str
    input_files: list[str] = Field(default_factory=list)
    allowed_outputs: list[str] = Field(default_factory=list)


# Per-phase contracts derived from proposal §9. Output paths follow the
# documentation-first scope (no build/ or deployment/ execution outputs).
PHASE_CONTRACTS: dict[str, PhaseContract] = {
    "proposal": PhaseContract(
        phase_id="proposal",
        agent_name="proposal_agent",
        input_files=["domain-knowledge/background-information.md"],
        allowed_outputs=["docs/proposal.md"],
    ),
    "factory-init": PhaseContract(
        phase_id="factory-init",
        agent_name="factory_init_agent",
        input_files=["docs/proposal.md"],
        allowed_outputs=["docs/", "src/", "tests/", "logs/"],
    ),
    "specification": PhaseContract(
        phase_id="specification",
        agent_name="specification_agent",
        input_files=["docs/proposal.md"],
        allowed_outputs=["docs/spec.md"],
    ),
    "architecture": PhaseContract(
        phase_id="architecture",
        agent_name="architecture_agent",
        input_files=["docs/spec.md", "docs/proposal.md"],
        allowed_outputs=["docs/architecture.md"],
    ),
    "blueprint": PhaseContract(
        phase_id="blueprint",
        agent_name="blueprint_agent",
        input_files=["docs/spec.md", "docs/architecture.md"],
        allowed_outputs=["docs/blueprint.md"],
    ),
    "dev-plan": PhaseContract(
        phase_id="dev-plan",
        agent_name="dev_plan_agent",
        input_files=["docs/blueprint.md", "docs/architecture.md", "docs/spec.md"],
        allowed_outputs=["docs/plan.md"],
    ),
    "implementation": PhaseContract(
        phase_id="implementation",
        agent_name="implementation_agent",
        input_files=["docs/plan.md", "docs/blueprint.md"],
        allowed_outputs=["src/"],
    ),
    "qa": PhaseContract(
        phase_id="qa",
        agent_name="qa_agent",
        input_files=["docs/plan.md", "src/"],
        allowed_outputs=[
            "docs/qa-test-plan.md",
            "tests/unit/",
            "tests/integration/",
            "tests/e2e/",
        ],
    ),
    "packaging": PhaseContract(
        phase_id="packaging",
        agent_name="packaging_agent",
        input_files=["docs/architecture.md", "src/"],
        allowed_outputs=["docs/packaging-plan.md"],
    ),
    "documentation": PhaseContract(
        phase_id="documentation",
        agent_name="documentation_agent",
        input_files=["docs/spec.md", "src/"],
        allowed_outputs=["docs/documentation-plan.md"],
    ),
    "deployment": PhaseContract(
        phase_id="deployment",
        agent_name="deployment_agent",
        input_files=["docs/architecture.md", "docs/packaging-plan.md"],
        allowed_outputs=["docs/deployment-plan.md"],
    ),
    "cleanup": PhaseContract(
        phase_id="cleanup",
        agent_name="cleanup_agent",
        input_files=["logs/"],
        allowed_outputs=["docs/phase-summary-log.md"],
    ),
}


# ---------------------------------------------------------------------------
# Phase invocation / completion payloads (blueprint §4.1)
# ---------------------------------------------------------------------------


class PhaseInvocationPayload(BaseModel):
    """Input handed to a phase agent when the supervisor dispatches a phase."""

    phase_name: str
    input_files: list[str] = Field(default_factory=list)
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_paths: list[str] = Field(default_factory=list)
    phase_context: dict[str, object] = Field(default_factory=dict)
    previous_phase_outputs: list[str] = Field(default_factory=list)


class PhaseCompleteEvent(BaseModel):
    """Structured result a phase agent reports back to the supervisor."""

    phase_name: str
    status: PhaseStatus
    artifact_paths: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)
    duration_ms: int
    token_usage: dict[str, int] | None = None
    failure_reason: str | None = None
    # #11: the proposal phase reports an assessed complexity tier here
    # (simple|standard|complex); other phases leave it None.
    complexity_tier: str | None = None


# ---------------------------------------------------------------------------
# Event envelope and run-state checkpoint (blueprint §4.1)
# ---------------------------------------------------------------------------


class EventEnvelope(BaseModel):
    """One structured record on the audit/event stream (`logs/events.jsonl`)."""

    timestamp: datetime
    eventType: str
    runId: str
    phase: str
    severity: EventSeverity = "info"
    userId: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


class RunState(BaseModel):
    """Persisted checkpoint for resume-from-last-completed-phase semantics."""

    runStateVersion: str
    run_id: str
    mode: str
    completed_phases: list[dict[str, object]] = Field(default_factory=list)
    stale_phases: list[str] = Field(default_factory=list)
    retry_counters: dict[str, int] = Field(default_factory=dict)


__all__ = [
    "PHASE_IDS",
    "PHASE_CONTRACTS",
    "PhaseStatus",
    "EventSeverity",
    "PhaseContract",
    "PhaseInvocationPayload",
    "PhaseCompleteEvent",
    "EventEnvelope",
    "RunState",
]
