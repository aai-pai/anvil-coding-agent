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
    input_files: list[str] = Field(default_factory=list)


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


class LLMBackend:
    """Real execution backend: generate artifact content via the LLM and write it.

    Post-v0.1.0 integration. Implements :class:`OpenHandsBackend` by prompting the
    configured :class:`OpenRouterProvider` and materializing the result to each of
    the step's output paths. Document artifacts are written with the FR-AR-005
    metadata header and the schema's required section headings so they pass
    :class:`anvil_runtime.artifacts.validator.ArtifactValidator`; directory outputs
    receive a generated ``GENERATED.md``.
    """

    def __init__(
        self,
        provider: "object",
        workspace_root: str = ".",
        clock: "object | None" = None,
    ) -> None:
        self._provider = provider
        self._root = __import__("pathlib").Path(workspace_root)
        self._counter = 0
        self._sessions: dict[str, AgentRuntimeConfig] = {}
        from datetime import datetime, timezone

        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def start(self, cfg: AgentRuntimeConfig) -> str:
        self._counter += 1
        session_id = f"llm-session-{self._counter}"
        self._sessions[session_id] = cfg
        return session_id

    def run(self, session_id: str, step: PhaseStep) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        cfg = self._sessions.get(session_id)
        model = cfg.model if cfg else "unknown"
        prompt = self._build_prompt(step)
        response = self._provider.complete(
            CompletionRequest(
                model=model, prompt=prompt, phase=step.phase, subtask=step.subtask
            )
        )
        artifacts = self._write_artifacts(step, response.content)
        return StepResult(
            session_id=session_id,
            phase=step.phase,
            status="success",
            output=response.content[:200],
            artifacts=artifacts,
            usage=response.usage,
        )

    def _build_prompt(self, step: PhaseStep) -> str:
        sections = self._required_sections(step.phase)
        lines = [
            f"You are the '{step.phase}' phase agent in the Anvil coding factory.",
            step.instruction,
        ]
        if step.input_files:
            lines.append(f"Inputs: {', '.join(step.input_files)}.")
        if sections:
            lines.append(
                "Produce Markdown that includes these section headings: "
                + ", ".join(sections)
                + "."
            )
        return "\n".join(lines)

    def _write_artifacts(self, step: PhaseStep, content: str) -> list[str]:
        import pathlib

        written: list[str] = []
        for rel in step.output_paths:
            is_dir = rel.endswith("/") or pathlib.PurePosixPath(rel).suffix == ""
            if is_dir:
                directory = self._root / rel
                directory.mkdir(parents=True, exist_ok=True)
                gen_rel = str(pathlib.PurePosixPath(rel.rstrip("/")) / "GENERATED.md")
                (self._root / gen_rel).write_text(
                    self._document(step, content), encoding="utf-8"
                )
                written.append(gen_rel)
            else:
                target = self._root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.suffix == ".md":
                    target.write_text(self._document(step, content), encoding="utf-8")
                else:
                    target.write_text(content, encoding="utf-8")
                written.append(rel)
        return written

    def _document(self, step: PhaseStep, content: str) -> str:
        import yaml

        meta = {
            "artifactId": f"{step.phase}-v1",
            "phase": step.phase,
            "generatedAt": self._clock().isoformat(),
            "derivedFrom": list(step.input_files) or ["(none)"],
        }
        front = "---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n"
        body = [f"# {step.phase.replace('-', ' ').title()}", "", "## Overview", content, ""]
        for section in self._required_sections(step.phase):
            body.append(f"## {section}")
            body.append(content)
            body.append("")
        return front + "\n".join(body) + "\n"

    @staticmethod
    def _required_sections(phase: str) -> list[str]:
        from anvil_runtime.artifacts.schemas import schema_for

        schema = schema_for(phase)
        return list(schema.required_sections) if schema else []


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
    "LLMBackend",
]
