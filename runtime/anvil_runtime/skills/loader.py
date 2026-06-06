"""On-demand skill loader with progressive disclosure.

Slice 5 deliverable (blueprint §3.1; spec FR-SK-003/004/006/007/008). Skills are
never preloaded wholesale (FR-SK-003): :meth:`resolve_for_phase` returns just the
references relevant to a phase (finalized at phase start, FR-SK-007), and
:meth:`load` reads a single skill's body on demand, emitting ``SkillLoaded`` with
a token estimate (FR-SK-004). Requesting an unavailable skill raises
:class:`SkillNotAvailableError` so the supervisor can escalate (FR-SK-008).
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Callable

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.skills.manifest import SkillBundle, SkillRef, estimate_tokens
from anvil_runtime.skills.resolver import SkillResolver
from anvil_runtime.state.event_bus import EventBus


class SkillNotAvailableError(KeyError):
    """Raised when an agent requests a skill that is not available (FR-SK-008)."""


class SkillLoader:
    """Resolves phase-relevant skills and loads them on demand."""

    def __init__(
        self,
        resolver: SkillResolver,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolver = resolver
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve_for_phase(self, phase_id: str) -> list[SkillRef]:
        """The phase-scoped skill references (no bodies loaded yet)."""
        return self._resolver.resolve_for_phase(phase_id)

    def load(self, skill_name: str) -> SkillBundle:
        """Load a single skill's body on demand and emit ``SkillLoaded``."""
        ref = self._resolver.discover().get(skill_name)
        if ref is None:
            self._emit("SkillLoadFailed", severity="error", data={"skill": skill_name})
            raise SkillNotAvailableError(
                f"skill '{skill_name}' is not available"
            )
        content = self._read_body(ref)
        estimate = ref.token_estimate or estimate_tokens(content)
        self._emit("SkillLoaded", data={
            "skill": ref.name, "source": ref.source, "token_estimate": estimate,
        })
        return SkillBundle(
            name=ref.name,
            content=content,
            token_estimate=estimate,
            metadata={
                "source": ref.source,
                "phases": ref.phases,
                "description": ref.description,
            },
        )

    @staticmethod
    def _read_body(ref: SkillRef) -> str:
        skill_dir = pathlib.Path(ref.path)
        md = skill_dir / "SKILL.md"
        if md.is_file():
            return md.read_text(encoding="utf-8")
        js = skill_dir / "skill.json"
        if js.is_file():
            return js.read_text(encoding="utf-8")
        return ""

    def _emit(self, event_type: str, severity: str = "info", data: dict | None = None) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=self._run_id,
            phase="", severity=severity, data=data or {},
        ))


__all__ = ["SkillLoader", "SkillNotAvailableError"]
