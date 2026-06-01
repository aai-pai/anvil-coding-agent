"""Unit tests: on-demand skill loading and phase scoping.

Slice 5 (spec FR-SK-004/005/006/008; plan §2.5). Verifies precedence override,
phase-scoped resolution, on-demand load with ``SkillLoaded`` emission, and
escalation on a missing skill.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.skills.loader import SkillLoader, SkillNotAvailableError
from anvil_runtime.skills.resolver import SkillResolver
from anvil_runtime.state.event_bus import EventBus


def _write_skill(root: pathlib.Path, name: str, phases: list[str], body: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    phases_yaml = ", ".join(phases)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nphases: [{phases_yaml}]\ndescription: test {name}\n---\n{body}",
        encoding="utf-8",
    )


@pytest.fixture()
def roots(tmp_path: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    workspace = tmp_path / "workspace" / ".anvil" / "skills"
    user = tmp_path / "user" / ".anvil" / "skills"
    workspace.mkdir(parents=True)
    user.mkdir(parents=True)
    # Same-named skill in both roots; workspace must win (FR-SK-005).
    _write_skill(workspace, "review-helper", ["qa"], "workspace body")
    _write_skill(user, "review-helper", ["qa"], "user body")
    _write_skill(user, "planning-helper", ["proposal", "architecture"], "plan body")
    return [("workspace", workspace), ("user", user)]


def test_workspace_overrides_user_root(roots) -> None:
    resolver = SkillResolver(roots)
    discovered = resolver.discover()
    assert discovered["review-helper"].source == "workspace"


def test_resolve_for_phase_is_scoped(roots) -> None:
    resolver = SkillResolver(roots)
    qa_skills = {r.name for r in resolver.resolve_for_phase("qa")}
    assert qa_skills == {"review-helper"}
    proposal_skills = {r.name for r in resolver.resolve_for_phase("proposal")}
    assert proposal_skills == {"planning-helper"}


def test_load_emits_skill_loaded(roots, tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    loader = SkillLoader(SkillResolver(roots), event_bus=bus, run_id="r1")
    bundle = loader.load("review-helper")
    assert "workspace body" in bundle.content
    assert bundle.token_estimate > 0
    loaded = [e for e in bus.read_all() if e.eventType == "SkillLoaded"]
    assert loaded and loaded[0].data["skill"] == "review-helper"


def test_missing_skill_raises(roots) -> None:
    loader = SkillLoader(SkillResolver(roots))
    with pytest.raises(SkillNotAvailableError):
        loader.load("does-not-exist")
