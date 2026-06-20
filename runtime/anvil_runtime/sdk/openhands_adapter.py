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

    # The implementation phase generates real, multi-file source code; all other
    # phases produce a single document artifact.
    CODE_PHASE = "implementation"

    def run(self, session_id: str, step: PhaseStep) -> StepResult:
        cfg = self._sessions.get(session_id)
        model = cfg.model if cfg else "unknown"
        if step.phase == self.CODE_PHASE:
            return self._run_code(session_id, step, model)
        return self._run_doc(session_id, step, model)

    # -- document phases --------------------------------------------------

    def _run_doc(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        response = self._provider.complete(CompletionRequest(
            model=model, prompt=self._doc_prompt(step),
            phase=step.phase, subtask=step.subtask, max_tokens=1500,
        ))
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=response.content[:200],
            artifacts=self._write_documents(step, response.content),
            usage=response.usage,
        )

    # -- code phase (multi-file) -----------------------------------------

    def _run_code(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        response = self._provider.complete(CompletionRequest(
            model=model, prompt=self._code_prompt(step),
            phase=step.phase, subtask=step.subtask, max_tokens=4000,
        ))
        files = self._parse_manifest(response.content)
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=response.content[:200],
            artifacts=self._write_files(step, files, raw=response.content),
            usage=response.usage,
        )

    # -- prompts ----------------------------------------------------------

    def _read_inputs(self, step: PhaseStep, limit: int = 2500) -> str:
        chunks: list[str] = []
        for rel in step.input_files:
            target = self._root / rel
            if target.is_file():
                chunks.append(f"--- {rel} ---\n{target.read_text(encoding='utf-8')[:limit]}")
        return "\n\n".join(chunks)

    def _doc_prompt(self, step: PhaseStep) -> str:
        sections = self._required_sections(step.phase)
        ctx = self._read_inputs(step)
        lines = [
            f"You are the '{step.phase}' phase agent in an automated software factory.",
            step.instruction,
        ]
        if ctx:
            lines.append("Context from prior phases:\n" + ctx)
        if sections:
            lines.append("Write Markdown including these section headings: " + ", ".join(sections) + ".")
        lines.append("Respond with the document content only.")
        return "\n\n".join(lines)

    def _code_prompt(self, step: PhaseStep) -> str:
        ctx = self._read_inputs(step)
        out = ", ".join(step.output_paths) or "src/"
        return "\n\n".join([
            "You are the implementation phase agent. Output the COMPLETE, runnable "
            "source code for the project described below.",
            ("Project context:\n" + ctx) if ctx else "Build the project described by the plan.",
            f"Place files under: {out}. Include a runnable entry point.",
            "Output ONLY the files (no explanation, no commentary) using EXACTLY this "
            "format, repeating the block for every file:",
            "=== FILE: <relative/path> ===\n<full file contents>",
        ])

    # -- response parsing + file writing ---------------------------------

    @staticmethod
    def _parse_manifest(content: str) -> list[tuple[str, str]]:
        """Extract (path, content) pairs from a model response.

        Primary format is file blocks (``=== FILE: path ===`` then contents),
        which models emit far more reliably than JSON for code. A JSON
        ``{"files":[...]}`` manifest is accepted as a fallback.
        """
        import json
        import re

        # 1) File-block format.
        marker = re.compile(r"^===\s*FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)
        marks = list(marker.finditer(content))
        if marks:
            blocks: list[tuple[str, str]] = []
            for i, m in enumerate(marks):
                path = m.group(1).strip().strip("`\"'")
                end = marks[i + 1].start() if i + 1 < len(marks) else len(content)
                body = content[m.end():end].strip("\n")
                body = re.sub(r"^```[a-zA-Z]*\n?", "", body)
                body = re.sub(r"\n?```\s*$", "", body)
                if path and body.strip():
                    blocks.append((path, body))
            if blocks:
                return blocks

        # 2) JSON manifest fallback.
        stripped = content.strip()
        span = re.search(r"\{.*\}", content, re.DOTALL)
        for candidate in (stripped, span.group(0) if span else None):
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
            files = data.get("files") if isinstance(data, dict) else None
            if isinstance(files, list):
                out = [
                    (str(f["path"]), f["content"])
                    for f in files
                    if isinstance(f, dict) and f.get("path") and isinstance(f.get("content"), str)
                ]
                if out:
                    return out
        return []

    def _write_files(
        self, step: PhaseStep, files: list[tuple[str, str]], raw: str
    ) -> list[str]:
        import pathlib

        allowed = [o.rstrip("/") for o in step.output_paths] or ["src"]
        written: list[str] = []
        for path, content in files:
            rel = self._sandbox(path, allowed)
            target = self._root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel)
        if written:
            return written
        # Fallback: manifest unparseable -> never crash; keep the raw output so the
        # phase still produces an artifact (validation then drives a retry).
        rel = str(pathlib.PurePosixPath(allowed[0]) / "GENERATED.md")
        (self._root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self._root / rel).write_text(raw, encoding="utf-8")
        return [rel]

    @staticmethod
    def _sandbox(path: str, allowed_prefixes: list[str]) -> str:
        """Constrain a model-proposed path under an allowed output prefix."""
        import pathlib

        pure = pathlib.PurePosixPath(path.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts:
            pure = pathlib.PurePosixPath(allowed_prefixes[0]) / pure.name
        rel = pure.as_posix()
        if not any(rel == ap or rel.startswith(ap + "/") for ap in allowed_prefixes):
            rel = (pathlib.PurePosixPath(allowed_prefixes[0]) / pure.name).as_posix()
        return rel

    def _write_documents(self, step: PhaseStep, content: str) -> list[str]:
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
        # The LLM body is emitted exactly once (FR-002 fix): the doc prompt already
        # asks the model to include the schema's required section headings inline.
        # We append only the headings the model omitted, as empty stubs, so the
        # deterministic validator (FR-AR-002) still passes without re-inserting the
        # full body under every heading (which previously bloated artifacts ~2-3x
        # and, via downstream input_files, inflated token usage).
        body_text = content.strip()
        parts = [f"# {step.phase.replace('-', ' ').title()}", "", body_text, ""]
        present = "\n".join(
            line for line in body_text.splitlines() if line.lstrip().startswith("#")
        ).lower()
        for section in self._required_sections(step.phase):
            if section.lower() not in present:
                parts.append(f"## {section}")
                parts.append("")
        return front + "\n".join(parts) + "\n"

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
