"""Per-phase artifact schemas.

Slice 6 deliverable (spec §4.1, FR-AR-001/002). Declares, for each phase that
owns a document artifact, the canonical output path, whether a metadata header is
required, and a small set of required section headings. Validation against these
schemas is deterministic pass/fail (FR-AR-002). Directory-owning phases
(factory-init, implementation) have no single-document schema and validate by
output existence only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArtifactSchema(BaseModel):
    """Deterministic requirements for a phase's document artifact."""

    phase_id: str
    path: str
    require_metadata: bool = True
    required_sections: list[str] = Field(default_factory=list)


# Representative required headings per document artifact (spec §4.1). Kept small
# and deterministic; the full section lists live in the spec.
ARTIFACT_SCHEMAS: dict[str, ArtifactSchema] = {
    "proposal": ArtifactSchema(
        phase_id="proposal",
        path="docs/proposal.md",
        required_sections=["Problem Statement", "Scope"],
    ),
    "specification": ArtifactSchema(
        phase_id="specification",
        path="docs/spec.md",
        required_sections=["Requirements"],
    ),
    "architecture": ArtifactSchema(
        phase_id="architecture",
        path="docs/architecture.md",
        required_sections=["Components"],
    ),
    "blueprint": ArtifactSchema(
        phase_id="blueprint",
        path="docs/blueprint.md",
        required_sections=["Module Structure"],
    ),
    "dev-plan": ArtifactSchema(
        phase_id="dev-plan",
        path="docs/plan.md",
        required_sections=["Implementation Slices"],
    ),
    "qa": ArtifactSchema(
        phase_id="qa",
        path="docs/qa-test-plan.md",
        required_sections=["Test"],
    ),
    "packaging": ArtifactSchema(phase_id="packaging", path="docs/packaging-plan.md"),
    "documentation": ArtifactSchema(
        phase_id="documentation", path="docs/documentation-plan.md"
    ),
    "deployment": ArtifactSchema(phase_id="deployment", path="docs/deployment-plan.md"),
    "cleanup": ArtifactSchema(
        phase_id="cleanup", path="docs/phase-summary-log.md", require_metadata=False
    ),
}


def schema_for(phase_id: str) -> ArtifactSchema | None:
    """The document-artifact schema for a phase, or ``None`` (directory-only)."""
    return ARTIFACT_SCHEMAS.get(phase_id)


__all__ = ["ArtifactSchema", "ARTIFACT_SCHEMAS", "schema_for"]
