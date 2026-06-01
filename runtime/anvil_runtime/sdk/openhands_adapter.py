"""OpenHands execution adapter.

Slice 5 deliverable (blueprint §3.1; architecture "OpenHands Execution Adapter").
Bridges phase execution into OpenHands sessions and tools. v0.1.0 runs in-process
through an injected ``OpenHandsBackend`` so the runtime has no hard dependency on
the OpenHands SDK package; the default :class:`InProcessBackend` is deterministic.
A real SDK-backed (or out-of-process) backend can replace it later without
changing the ``start_session`` / ``run_phase_step`` contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AgentRuntimeConfig(BaseModel):
    """Configuration for an OpenHands agent session."""

    model: str
    security_profile: str = "restricted"
    workspace_root: str = "."
    tools: list[str] = Field(default_factory=list)


class PhaseStep(BaseModel):
    """A single unit of phase work handed to a session."""

    phase: str
    instruction: str
    subtask: str | None = None
    output_paths: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    """Structured result of running a :class:`PhaseStep`."""

    session_id: str
    phase: str
    status: str  # "success" | "failure"
    output: str = ""
    artifacts: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    failure_reason: str | None = None


@runtime_checkable
class OpenHandsBackend(Protocol):
    """Execution backend contract (injected; default is in-process)."""

    def start(self, cfg: AgentRuntimeConfig) -> str: ...

    def run(self, session_id: str, step: PhaseStep) -> StepResult: ...


class InProcessBackend:
    """Deterministic in-process backend for v0.1.0 (no external SDK, no I/O).

    Session ids are sequential (``session-1``, ``session-2``, …) so behavior is
    reproducible across runs and resumes.
    """

    def __init__(self) -> None:
        self._counter = 0
        self._sessions: dict[str, AgentRuntimeConfig] = {}

    def start(self, cfg: AgentRuntimeConfig) -> str:
        self._counter += 1
        session_id = f"session-{self._counter}"
        self._sessions[session_id] = cfg
        return session_id

    def run(self, session_id: str, step: PhaseStep) -> StepResult:
        cfg = self._sessions.get(session_id)
        model = cfg.model if cfg else "unknown"
        prompt_tokens = max(1, len(step.instruction) // 4)
        return StepResult(
            session_id=session_id,
            phase=step.phase,
            status="success",
            output=f"[{model}] completed {step.phase}",
            artifacts=list(step.output_paths),
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 8,
                "total_tokens": prompt_tokens + 8,
            },
        )


class OpenHandsAdapter:
    """Bridges phase execution into OpenHands sessions and tools."""

    def __init__(self, backend: OpenHandsBackend | None = None) -> None:
        self._backend = backend or InProcessBackend()

    def start_session(self, cfg: AgentRuntimeConfig) -> str:
        """Start a session and return its id."""
        return self._backend.start(cfg)

    def run_phase_step(self, session_id: str, step: PhaseStep) -> StepResult:
        """Run one phase step inside an existing session."""
        return self._backend.run(session_id, step)


__all__ = [
    "OpenHandsAdapter",
    "AgentRuntimeConfig",
    "PhaseStep",
    "StepResult",
    "OpenHandsBackend",
    "InProcessBackend",
]
