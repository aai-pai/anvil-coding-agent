"""Artifact metadata header parsing and validation.

Slice 6 deliverable (spec FR-AR-005). Each artifact carries a YAML front-matter
header recording its lineage: artifact id, phase, generated timestamp, and the
hashes of the inputs it was derived from (used by drift detection). This module
parses that header and reports any missing required fields.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

# Core required fields (FR-AR-005): identity, phase, timestamp, and input lineage.
# v0.1.2 #16 (FR-OKF-002) adds the OKF interoperability surface: `type` (the only
# field the OKF spec itself mandates) and `title`.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "artifactId", "phase", "generatedAt", "type", "title",
)
LINEAGE_FIELDS: tuple[str, ...] = ("derivedFrom", "inputHashes")


class ArtifactMetadata(BaseModel):
    """Parsed front-matter lineage + OKF surface for an artifact."""

    artifactId: str
    phase: str
    generatedAt: str | None = None
    derivedFrom: list[str] = Field(default_factory=list)
    inputHashes: dict[str, str] = Field(default_factory=dict)
    runId: str | None = None
    # OKF standard fields (#16): only `type` is mandated by the OKF spec; the
    # rest are its standard optional fields.
    type: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: str | None = None


def split_front_matter(text: str) -> tuple[dict, str]:
    """Split a ``--- yaml --- body`` document into ``(metadata, body)``."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            header = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            meta = yaml.safe_load(header) or {}
            if isinstance(meta, dict):
                return meta, body
    return {}, text


def parse_metadata(path: str | pathlib.Path) -> dict:
    """Read an artifact file and return its raw front-matter mapping."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    meta, _ = split_front_matter(text)
    return meta


def validate_metadata(meta: dict) -> list[str]:
    """Return a list of issues (empty == valid) for a metadata mapping.

    Requires the FR-AR-005 core fields and at least one lineage field so drift
    detection has inputs to hash against.
    """
    issues: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        if not meta.get(field):
            issues.append(f"missing required metadata field '{field}'")
    if not any(meta.get(field) for field in LINEAGE_FIELDS):
        issues.append("missing input lineage (need 'derivedFrom' or 'inputHashes')")
    return issues


__all__ = [
    "ArtifactMetadata",
    "parse_metadata",
    "validate_metadata",
    "split_front_matter",
    "REQUIRED_METADATA_FIELDS",
    "LINEAGE_FIELDS",
]
