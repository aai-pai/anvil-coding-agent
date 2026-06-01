"""Skill discovery and precedence resolution.

Slice 5 deliverable (spec FR-SK-001/005/006). Discovers skills across the ordered
search roots (workspace-local, user-root, built-in) and resolves name collisions
by precedence: a workspace-local skill overrides a user-root skill of the same
name (FR-SK-005). Provides the phase-scoped subset for progressive disclosure
(FR-SK-006).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.skills.manifest import SkillRef, parse_manifest

# Highest precedence first: workspace overrides user overrides builtin.
SkillRoot = tuple[str, pathlib.Path]


class SkillResolver:
    """Resolves the effective skill set from precedence-ordered roots."""

    def __init__(self, roots: list[SkillRoot]) -> None:
        # ``roots`` is ordered highest-precedence first.
        self._roots = roots

    def discover(self) -> dict[str, SkillRef]:
        """Map skill name -> highest-precedence :class:`SkillRef`."""
        resolved: dict[str, SkillRef] = {}
        for source, root in self._roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                ref = parse_manifest(child, source)
                if ref is None:
                    continue
                # First writer wins because roots are highest-precedence first.
                resolved.setdefault(ref.name, ref)
        return resolved

    def resolve_for_phase(self, phase_id: str) -> list[SkillRef]:
        """Skills applicable to a phase, sorted by name (FR-SK-006)."""
        applicable = [
            ref for ref in self.discover().values() if ref.applies_to(phase_id)
        ]
        return sorted(applicable, key=lambda r: r.name)


__all__ = ["SkillResolver", "SkillRoot"]
