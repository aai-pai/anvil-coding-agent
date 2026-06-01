"""Skill manifest models and metadata parsing.

Slice 5 deliverable (spec FR-SK-002). A skill is a directory containing a
``SKILL.md`` (YAML frontmatter + Markdown body) or a ``skill.json`` manifest. This
module defines the lightweight references the resolver/loader pass around and the
parser that reads a skill's metadata without loading its full body (progressive
disclosure, FR-SK-006).
"""

from __future__ import annotations

import json
import pathlib

import yaml
from pydantic import BaseModel, Field

SKILL_MD = "SKILL.md"
SKILL_JSON = "skill.json"

SkillSource = str  # "workspace" | "user" | "builtin"


def estimate_tokens(text: str) -> int:
    """Coarse token estimate (~4 chars/token) for SkillLoaded budgeting (FR-SK-004)."""
    return max(1, len(text) // 4)


class SkillRef(BaseModel):
    """A discovered skill: identity, location, applicable phases, token estimate."""

    name: str
    path: str
    source: SkillSource
    phases: list[str] = Field(default_factory=list)  # empty / ["all"] => every phase
    description: str = ""
    token_estimate: int = 0

    def applies_to(self, phase_id: str) -> bool:
        if not self.phases or "all" in self.phases:
            return True
        return phase_id in self.phases


class SkillBundle(BaseModel):
    """A fully loaded skill: body content plus metadata (FR-SK-004)."""

    name: str
    content: str
    token_estimate: int
    metadata: dict[str, object] = Field(default_factory=dict)


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a ``--- yaml --- body`` document into (metadata, body)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            header = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            meta = yaml.safe_load(header) or {}
            if isinstance(meta, dict):
                return meta, body
    return {}, text


def parse_manifest(skill_dir: pathlib.Path, source: SkillSource) -> SkillRef | None:
    """Read a skill directory's manifest into a :class:`SkillRef`, or ``None``."""
    md = skill_dir / SKILL_MD
    js = skill_dir / SKILL_JSON
    if md.is_file():
        meta, body = _split_frontmatter(md.read_text(encoding="utf-8"))
        estimate = estimate_tokens(body)
    elif js.is_file():
        meta = json.loads(js.read_text(encoding="utf-8"))
        estimate = int(meta.get("token_estimate", 0)) if isinstance(meta, dict) else 0
    else:
        return None
    if not isinstance(meta, dict):
        return None
    name = str(meta.get("name") or skill_dir.name)
    phases_raw = meta.get("phases", [])
    phases = [str(p) for p in phases_raw] if isinstance(phases_raw, list) else []
    return SkillRef(
        name=name,
        path=str(skill_dir),
        source=source,
        phases=phases,
        description=str(meta.get("description", "")),
        token_estimate=estimate,
    )


__all__ = [
    "SkillRef",
    "SkillBundle",
    "parse_manifest",
    "estimate_tokens",
    "SKILL_MD",
    "SKILL_JSON",
]
