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
    # Supervisor phase_context passthrough (run_id per FR-EVT-002; #15 adds
    # clarification_mode). Keeps backend events attributable to the active run.
    context: dict[str, object] = Field(default_factory=dict)


class StepResult(BaseModel):
    """Structured result of running a :class:`PhaseStep`."""

    session_id: str
    phase: str
    status: str  # "success" | "failure"
    output: str = ""
    artifacts: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    failure_reason: str | None = None
    complexity_tier: str | None = None  # #11: set by the proposal phase only
    # #15: set by the intake phase only (clarifying questions / recorded assumptions).
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    # v0.1.4 #24 (FR-AG-002): False marks one successful unit of a phase
    # still in progress; the supervisor re-dispatches for the next unit.
    phase_complete: bool = True


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
        input_char_limit: int | None = None,
        event_bus: "object | None" = None,
        instructions: str | None = None,
        intake_max_tokens: int | None = None,
        doc_max_tokens: int | None = None,
        code_max_tokens: int | None = None,
        contract_max_chars: int | None = None,
        temperature: float | None = None,
        external_test_command: str | None = None,
        repair_max_rounds: int | None = None,
        test_timeout_s: int | None = None,
    ) -> None:
        from anvil_runtime.config.schema import (
            DEFAULT_CODE_MAX_TOKENS,
            DEFAULT_CONTRACT_MAX_CHARS,
            DEFAULT_DOC_MAX_TOKENS,
            DEFAULT_INPUT_CHAR_LIMIT,
            DEFAULT_INTAKE_MAX_TOKENS,
            DEFAULT_REPAIR_MAX_ROUNDS,
            DEFAULT_TEST_TIMEOUT_S,
        )

        self._provider = provider
        self._root = __import__("pathlib").Path(workspace_root)
        self._counter = 0
        self._sessions: dict[str, AgentRuntimeConfig] = {}
        # #18 (FR-CTX-001): per-file cap when assembling inputs into prompts.
        self._input_char_limit = input_char_limit or DEFAULT_INPUT_CHAR_LIMIT
        # v0.1.3 #19: completion budgets per step category. A budget smaller
        # than the artifact a task needs fails the step with
        # finish_reason=length on every retry, so these must scale with task
        # size (config field or ANVIL_*_MAX_TOKENS env override).
        self._intake_max_tokens = intake_max_tokens or DEFAULT_INTAKE_MAX_TOKENS
        self._doc_max_tokens = doc_max_tokens or DEFAULT_DOC_MAX_TOKENS
        self._code_max_tokens = code_max_tokens or DEFAULT_CODE_MAX_TOKENS
        # v0.1.3 #20: the task-contract block is injected verbatim (never
        # truncated); an over-cap contract fails the run at intake instead.
        self._contract_max_chars = contract_max_chars or DEFAULT_CONTRACT_MAX_CHARS
        # Pinned sampling temperature for every completion; None keeps the
        # provider default (ANVIL_TEMPERATURE / config `temperature`).
        self._temperature = temperature
        # v0.1.4 #23 (FR-RL-001/002): the repair loop exists only when a
        # command is configured; None keeps v0.1.3 behavior byte-for-byte.
        self._test_command = external_test_command
        self._repair_max_rounds = (
            repair_max_rounds if repair_max_rounds is not None
            else DEFAULT_REPAIR_MAX_ROUNDS
        )
        self._test_timeout_s = test_timeout_s or DEFAULT_TEST_TIMEOUT_S
        self._events = event_bus
        # #14 (FR-INS-002/003): standing instructions, injected as a dedicated
        # block in every prompt; resolved (and capped) upstream, never truncated
        # by the input limit here.
        self._instructions = instructions
        from datetime import datetime, timezone

        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def start(self, cfg: AgentRuntimeConfig) -> str:
        self._counter += 1
        session_id = f"llm-session-{self._counter}"
        self._sessions[session_id] = cfg
        return session_id

    # The implementation phase generates real, multi-file source code; the intake
    # phase assesses completeness (#15); all other phases produce a single
    # document artifact.
    CODE_PHASE = "implementation"
    INTAKE_PHASE = "intake"
    MAX_INTAKE_QUESTIONS = 5  # FR-INT-005

    def run(self, session_id: str, step: PhaseStep) -> StepResult:
        cfg = self._sessions.get(session_id)
        model = cfg.model if cfg else "unknown"
        if step.phase == self.CODE_PHASE:
            return self._run_code(session_id, step, model)
        if step.phase == self.INTAKE_PHASE:
            return self._run_intake(session_id, step, model)
        return self._run_doc(session_id, step, model)

    @staticmethod
    def _response_failure(response: "object") -> str | None:
        """A failure reason when a completion is unusable, else None.

        An empty or max_tokens-truncated response must fail the step (and enter
        the supervisor's retry path) rather than be papered over with
        placeholder artifacts that pass validation.
        """
        if not str(getattr(response, "content", "")).strip():
            return "LLM returned an empty response"
        if getattr(response, "finish_reason", None) == "length":
            return "LLM response truncated at max_tokens (finish_reason=length)"
        return None

    def _failed_step(
        self, session_id: str, step: PhaseStep, reason: str, usage: dict[str, int]
    ) -> StepResult:
        return StepResult(
            session_id=session_id, phase=step.phase, status="failure",
            failure_reason=reason, usage=usage,
        )

    # -- intake phase (#15) -------------------------------------------------

    def _run_intake(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        # #23 (FR-RL-003): executing workspace code is an `open`-profile
        # capability. A configured command under any other profile fails the
        # run AT INTAKE — silently skipping verification the user asked for
        # would be worse than refusing loudly.
        cfg = self._sessions.get(session_id)
        # The RUN's profile (phase context) is authoritative; the session
        # config carries the manager-level fallback.
        profile = str(step.context.get("security_profile") or "") or (
            cfg.security_profile if cfg else "restricted")
        if self._test_command and profile != "open":
            return self._failed_step(
                session_id, step,
                f"externalTestCommand is configured ({self._test_command!r}) "
                f"but security profile '{profile}' does not permit executing "
                "workspace code; use profile 'open' or remove the command",
                usage={},
            )
        # #20: an over-cap contract fails the run AT INTAKE with a clear
        # reason — the block is exempt from the input limit and must never be
        # clipped (a clipped contract is worse than none).
        contract = self._resolve_contract()
        if contract.present and contract.length > self._contract_max_chars:
            return self._failed_step(
                session_id, step,
                f"contract block is {contract.length:,} chars, over the "
                f"{self._contract_max_chars:,}-char cap "
                "(ANVIL_CONTRACT_MAX_CHARS); the contract is injected verbatim "
                "into every phase and is never truncated — shrink the contract "
                "block (move prose to the context section) or raise the cap",
                usage={},
            )
        mode = str(step.context.get("clarification_mode", "questions"))
        response = self._provider.complete(CompletionRequest(
            model=model, prompt=self._intake_prompt(step, mode),
            phase=step.phase, subtask=step.subtask,
            max_tokens=self._intake_max_tokens,
            temperature=self._temperature,
        ))
        reason = self._response_failure(response)
        if reason:
            return self._failed_step(session_id, step, reason, response.usage)
        questions, assumptions = self._parse_intake(response.content)
        artifacts: list[str] = []
        if mode == "assumptions":
            questions = []  # assumption mode never pauses a run (FR-INT-009/010)
            if assumptions:
                artifacts = [self._append_assumptions(step, assumptions)]
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=response.content[:200],
            artifacts=artifacts,
            usage=response.usage,
            questions=questions,
            assumptions=assumptions,
        )

    def _intake_prompt(self, step: PhaseStep, mode: str) -> str:
        ctx = self._read_inputs(step)
        lines = [
            "You are the 'intake' agent in an automated software factory. Assess "
            "whether the project background information below is complete enough "
            "to design and build the project.",
            *self._instructions_block(),
            *self._contract_block(),
            ("Background information:\n" + ctx) if ctx else "Background information: (empty)",
        ]
        if mode == "assumptions":
            lines.append(
                "Do NOT ask questions. If information needed to build is missing, "
                "output one line per gap, exactly `ASSUMPTION: <the default you will "
                "proceed with>`, using the standing instructions' defaults where "
                "applicable. If nothing important is missing, output exactly "
                "`INTAKE: complete`."
            )
        else:
            lines.append(
                f"If the information is sufficient, output exactly `INTAKE: complete`. "
                f"Otherwise output at most {self.MAX_INTAKE_QUESTIONS} lines, each "
                "exactly `QUESTION: <a clarifying question>`. Only ask a question "
                "whose answer would change what gets built AND is not answered by "
                "the standing instructions' defaults."
            )
        lines.append("Output only these marker lines, nothing else.")
        return "\n\n".join(lines)

    def _parse_intake(self, content: str) -> tuple[list[str], list[str]]:
        """Extract ``QUESTION:`` / ``ASSUMPTION:`` marker lines (FR-INT-005)."""
        import re

        questions = re.findall(r"(?im)^[ \t>*-]*QUESTION:[ \t]*(.+?)[ \t]*$", content)
        assumptions = re.findall(r"(?im)^[ \t>*-]*ASSUMPTION:[ \t]*(.+?)[ \t]*$", content)
        return questions[: self.MAX_INTAKE_QUESTIONS], assumptions

    def _append_assumptions(self, step: PhaseStep, assumptions: list[str]) -> str:
        """Append recorded assumptions to the domain-knowledge file (FR-INT-010).

        #20: on a contract-markered file the assumptions land *inside* the
        contract block — a recorded default is a binding fact, not prose — so
        every later phase receives them verbatim. Unmarkered files keep the
        v0.1.2 append-at-end behavior byte-for-byte.
        """
        from anvil_runtime.contract import append_block

        rel = step.input_files[0] if step.input_files else (
            "domain-knowledge/background-information.md"
        )
        target = self._root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        block = "\n## Assumptions\n\n" + "\n".join(f"- {a}" for a in assumptions)
        target.write_text(append_block(existing, block), encoding="utf-8")
        return rel

    # -- document phases --------------------------------------------------

    def _run_doc(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        response = self._provider.complete(CompletionRequest(
            model=model, prompt=self._doc_prompt(step),
            phase=step.phase, subtask=step.subtask,
            max_tokens=self._doc_max_tokens,
            temperature=self._temperature,
        ))
        reason = self._response_failure(response)
        if reason:
            return self._failed_step(session_id, step, reason, response.usage)
        content = response.content
        tier: str | None = None
        if step.phase == "proposal":
            # #11: the proposal carries a trailing COMPLEXITY marker; pull it out of
            # the written document and report it for complexity gating.
            content, tier = self._extract_tier(content)
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=content[:200],
            artifacts=self._write_documents(step, content),
            usage=response.usage,
            complexity_tier=tier,
        )

    @staticmethod
    def _extract_tier(content: str) -> tuple[str, str | None]:
        """Pull a trailing ``COMPLEXITY: <tier>`` marker; return (cleaned, tier|None).

        Absent/unparseable -> ``None`` (the supervisor then applies no gating).
        """
        import re

        pattern = re.compile(
            r"(?im)^[ \t]*COMPLEXITY:[ \t]*(simple|standard|complex)[ \t]*$"
        )
        match = pattern.search(content)
        tier = match.group(1).lower() if match else None
        cleaned = pattern.sub("", content).rstrip() + "\n"
        return cleaned, tier

    # -- code phase (multi-file) -----------------------------------------

    # #22: bounded in-step retry per target file, so one flaky completion
    # re-runs that file only — never the files already generated.
    PER_FILE_ATTEMPTS = 2
    # Safety valve on plan-derived target lists (a runaway plan should fail
    # visibly through the single-completion path, not spawn hundreds of calls).
    MAX_PLAN_TARGETS = 40

    def _run_code(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        """Implementation phase (#22): per-artifact when a file list is known.

        The v0.1.2 single completion for all of ``src/`` capped the whole
        project at one ``codeMaxTokens`` budget and regenerated files it had
        never seen (skeleton blindness — the Commit0 tinydb import-fail).
        When the contract manifest or the plan names the output files, each
        file gets its own completion (and its own budget), and an existing
        target's current source is included in that file's prompt. With no
        derivable file list the v0.1.2 single-completion behavior is
        preserved exactly.
        """
        targets = self._code_targets(step)
        # v0.1.4 #24 (FR-AG-002): when the supervisor drives unit mode, one
        # call performs one artifact (or the final verification unit).
        if targets and step.context.get("unit_mode"):
            return self._run_code_unit(session_id, step, model, targets)
        if not targets:
            result = self._run_code_single(session_id, step, model)
        else:
            result = self._run_code_per_file(session_id, step, model, targets)
        # v0.1.4 #23: with a configured command, generation is followed by
        # verification-by-execution + bounded repair. No command -> the
        # result above is final (v0.1.3 behavior, FR-RL-002).
        if result.status != "success" or not self._test_command:
            return result
        return self._verify_and_repair(session_id, step, model, result)

    def _run_code_unit(
        self, session_id: str, step: PhaseStep, model: str, targets: list[str]
    ) -> StepResult:
        """One unit of implementation work (#24): the next ungenerated
        artifact, or — once all exist — the whole verification/repair pass.

        Completed artifacts arrive via ``step.context["completed_artifacts"]``
        (supervisor-checkpointed, FR-AG-003), so a retry or restart never
        regenerates what is already on disk.
        """
        done = {str(rel) for rel in step.context.get("completed_artifacts") or []}
        remaining = [rel for rel in targets if rel not in done]
        if remaining:
            rel = remaining[0]
            total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            self._emit_progress(step, rel, targets.index(rel), len(targets), "generate")
            reason = self._generate_one(step, model, rel, targets, total)
            if reason is not None:
                return self._failed_step(session_id, step, reason, total)
            last = len(remaining) == 1
            if last and not self._test_command:
                # Phase finishes with this unit; report the full artifact set
                # so checkpoint checksums cover every generated file.
                return StepResult(
                    session_id=session_id, phase=step.phase, status="success",
                    output=f"generated {len(targets)} files", artifacts=list(targets),
                    usage=total,
                )
            return StepResult(
                session_id=session_id, phase=step.phase, status="success",
                output=f"generated {rel}", artifacts=[rel], usage=total,
                phase_complete=False,
            )
        # All artifacts exist -> the final unit is verification (+ repair).
        base = StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=f"generated {len(targets)} files", artifacts=list(targets),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        if not self._test_command:
            return base
        return self._verify_and_repair(session_id, step, model, base)

    def _run_code_single(self, session_id: str, step: PhaseStep, model: str) -> StepResult:
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        response = self._provider.complete(CompletionRequest(
            model=model, prompt=self._code_prompt(step),
            phase=step.phase, subtask=step.subtask,
            max_tokens=self._code_max_tokens,
            temperature=self._temperature,
        ))
        reason = self._response_failure(response)
        if reason:
            return self._failed_step(session_id, step, reason, response.usage)
        files = self._parse_manifest(response.content)
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=response.content[:200],
            artifacts=self._write_files(step, files, raw=response.content),
            usage=response.usage,
        )

    def _code_targets(self, step: PhaseStep) -> list[str]:
        """The phase's output-file list: contract manifest first, then plan.

        Order is preserved (manifest order, else first mention in the plan
        docs); paths are sandboxed under the phase's allowed outputs.
        """
        allowed = [o.rstrip("/") for o in step.output_paths] or ["src"]
        targets: list[str] = []

        def add(path: str) -> None:
            rel = path.replace("\\", "/").strip()
            if not rel:
                return
            if not any(rel == a or rel.startswith(a + "/") for a in allowed):
                rel = f"{allowed[0]}/{rel}"
            rel = self._sandbox(rel, allowed)
            if rel not in targets:
                targets.append(rel)

        # 1) The contract-manifest file list (#21) is authoritative when present.
        from anvil_runtime.contract import parse_contract_manifest

        contract = self._resolve_contract()
        if contract.present:
            manifest, _error = parse_contract_manifest(contract.text)
            if manifest is not None and manifest.files:
                for rel in manifest.files:
                    add(rel)
                return targets

        # 2) Files the plan/blueprint name explicitly under an output prefix.
        import re

        prefixes = "|".join(re.escape(a) for a in allowed)
        pattern = re.compile(rf"\b(?:{prefixes})/[A-Za-z0-9_\-./]*\.[A-Za-z0-9]+")
        for rel in step.input_files:
            source = self._root / rel
            if not source.is_file():
                continue
            for match in pattern.findall(source.read_text(encoding="utf-8")):
                add(match)
                if len(targets) >= self.MAX_PLAN_TARGETS:
                    return targets
        return targets

    def _run_code_per_file(
        self, session_id: str, step: PhaseStep, model: str, targets: list[str]
    ) -> StepResult:
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        written: list[str] = []
        for position, rel in enumerate(targets):
            self._emit_progress(step, rel, position, len(targets), "generate")
            reason = self._generate_one(step, model, rel, targets, total)
            if reason is not None:
                # Partial output stays on disk: a phase retry regenerates it,
                # and the failure names the offending file for the record.
                return self._failed_step(session_id, step, reason, total)
            written.append(rel)
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=f"generated {len(written)} files: " + ", ".join(written[:8]),
            artifacts=written,
            usage=total,
        )

    def _generate_one(
        self, step: PhaseStep, model: str, rel: str, targets: list[str],
        total: dict[str, int],
    ) -> str | None:
        """Generate one target file (bounded in-step retry); None on success.

        Shared by whole-phase per-file generation (#22) and unit-mode
        advancement (#24). Usage accumulates into ``total``; per-file usage
        is reported on the artifact-tagged event (FR-PA-004).
        """
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        reason: str | None = None
        response = None
        for _attempt in range(self.PER_FILE_ATTEMPTS):
            response = self._provider.complete(CompletionRequest(
                model=model, prompt=self._file_prompt(step, rel, targets),
                phase=step.phase, subtask=step.subtask,
                max_tokens=self._code_max_tokens,
                temperature=self._temperature,
            ))
            for key in total:
                total[key] += int(response.usage.get(key, 0))
            reason = self._response_failure(response)
            if reason is None:
                break
        if reason is not None:
            return f"{rel}: {reason}"
        target = self._root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._strip_fences(response.content), encoding="utf-8")
        self._emit_artifact_usage(step, rel, dict(response.usage))
        return None

    def _file_prompt(self, step: PhaseStep, rel: str, targets: list[str]) -> str:
        ctx = self._read_inputs(step)
        lines = [
            "You are the implementation phase agent. Generate exactly ONE file "
            f"of the project: `{rel}`.",
            *self._instructions_block(),
            *self._contract_block(),
            ("Project context:\n" + ctx) if ctx else "Build the file described by the plan.",
            "All files being generated in this phase: " + ", ".join(targets) + ".",
        ]
        existing = self._existing_source(step, rel)
        if existing is not None:
            lines.append(
                f"Current content of `{rel}` — complete it IN PLACE: keep every "
                "existing import, name, signature, docstring, and provided "
                "definition exactly as written; implement only the missing "
                "bodies:\n" + existing
            )
        lines.append(
            f"Output ONLY the complete, final contents of `{rel}` — no "
            "commentary, no file markers, no surrounding code fences."
        )
        return "\n\n".join(lines)

    def _existing_source(self, step: PhaseStep, rel: str) -> str | None:
        """The target file's current source, when it already exists (#22).

        A stub, partial, or prior version of the file the phase is about to
        generate is the ground truth it must preserve; subject to the #18
        input cap (truncation is never silent).
        """
        target = self._root / rel
        if not target.is_file():
            return None
        text = target.read_text(encoding="utf-8")
        if len(text) > self._input_char_limit:
            self._emit_truncation(step, rel, len(text), self._input_char_limit)
            text = text[: self._input_char_limit]
        return text

    @staticmethod
    def _strip_fences(content: str) -> str:
        """Unwrap a single-file response from stray fences/markers."""
        import re

        body = content.strip("\n")
        # Tolerate a model that emits the multi-file marker despite the
        # single-file instruction.
        body = re.sub(r"^===\s*FILE:.*?===\s*\n", "", body)
        if body.startswith("```"):
            body = re.sub(r"^```[a-zA-Z0-9_+-]*\n", "", body)
            body = re.sub(r"\n?```\s*$", "", body)
        return body

    def _emit_artifact_usage(self, step: PhaseStep, rel: str, usage: dict[str, int]) -> None:
        if self._events is None or not usage:
            return
        from anvil_runtime.core.phase_contracts import EventEnvelope

        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType="TokenUsageReported",
            runId=str(step.context.get("run_id", "") or ""),
            phase=step.phase, severity="info",
            data={"artifact": rel, **usage},
        ))

    def _emit_backend_event(
        self, step: PhaseStep, event_type: str, data: dict, severity: str = "info"
    ) -> None:
        if self._events is None:
            return
        from anvil_runtime.core.phase_contracts import EventEnvelope

        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type,
            runId=str(step.context.get("run_id", "") or ""),
            phase=step.phase, severity=severity, data=data,
        ))

    # -- external-test repair loop (v0.1.4 #23) ---------------------------

    def _verify_and_repair(
        self, session_id: str, step: PhaseStep, model: str, result: StepResult
    ) -> StepResult:
        """Run the configured command; feed failures into bounded repair.

        FR-RL-005..011. The result's artifacts/usage are carried forward and
        extended by repair completions; rounds exhausted with red tests fail
        the step into the normal retry path with the last output tail.
        """
        from anvil_runtime.verify import (
            EVENT_TAIL_CHARS,
            compile_smoke,
            implicated_files,
            run_external_tests,
        )

        artifacts = list(result.artifacts)
        total = dict(result.usage)

        # Round zero (FR-RL-005): syntax-broken artifacts are repaired before
        # spending a command run — the cheapest failure class of all.
        broken = compile_smoke(self._root, artifacts)
        if broken:
            files = [rel for rel, _ in broken]
            tail = "\n".join(f"{rel}: {err}" for rel, err in broken)
            self._emit_backend_event(step, "RepairRoundStarted", {
                "round": 0, "stage": "compile", "implicated": files,
            }, severity="warning")
            failure = self._repair_files(step, model, files, artifacts, tail, total)
            if failure is not None:
                return self._failed_step(session_id, step, failure, total)
            self._emit_backend_event(step, "RepairRoundCompleted", {
                "round": 0, "stage": "compile", "repaired": files,
            })

        run = run_external_tests(self._test_command, self._root, self._test_timeout_s)
        self._emit_test_outcome(step, run, EVENT_TAIL_CHARS)
        rounds = 0
        while not run.passed and rounds < self._repair_max_rounds:
            rounds += 1
            implicated = implicated_files(run.output_tail, artifacts) or list(artifacts)
            self._emit_backend_event(step, "RepairRoundStarted", {
                "round": rounds, "stage": "repair", "implicated": implicated,
            }, severity="warning")
            failure = self._repair_files(
                step, model, implicated, artifacts, run.output_tail, total
            )
            if failure is not None:
                return self._failed_step(session_id, step, failure, total)
            # FR-RL-009: the contract outranks the tests — a repair that
            # un-pins a manifest symbol is treated as a still-red round.
            violations = self._manifest_violations()
            if violations:
                run = run.model_copy(update={
                    "exit_code": 1,
                    "output_tail": "contract violations introduced by repair: "
                                   + "; ".join(violations),
                })
            else:
                run = run_external_tests(
                    self._test_command, self._root, self._test_timeout_s
                )
            self._emit_backend_event(step, "RepairRoundCompleted", {
                "round": rounds, "exit_code": run.exit_code,
                "passed": run.passed,
            })
            self._emit_test_outcome(step, run, EVENT_TAIL_CHARS)
        if not run.passed:
            return self._failed_step(
                session_id, step,
                f"external tests still failing after {rounds} repair round(s) "
                f"(exit {run.exit_code}): {run.output_tail[-800:]}",
                total,
            )
        return StepResult(
            session_id=session_id, phase=step.phase, status="success",
            output=f"external tests passed after {rounds} repair round(s)",
            artifacts=artifacts, usage=total,
        )

    def _emit_test_outcome(self, step: PhaseStep, run, tail_chars: int) -> None:  # noqa: ANN001
        self._emit_backend_event(
            step,
            "ExternalTestsPassed" if run.passed else "ExternalTestsFailed",
            {"exit_code": run.exit_code, "timed_out": run.timed_out,
             "output_tail": run.output_tail[-tail_chars:]},
            severity="info" if run.passed else "warning",
        )

    def _repair_files(
        self, step: PhaseStep, model: str, files: list[str],
        artifacts: list[str], failure_tail: str, total: dict[str, int],
    ) -> str | None:
        """One repair completion per implicated file; returns a failure reason
        or None. Non-implicated files are never touched (FR-RL-008); with no
        per-file targets the whole-src fallback regenerates in one completion
        (FR-RL-011)."""
        from anvil_runtime.llm.openrouter_provider import CompletionRequest

        for index, rel in enumerate(files):
            self._emit_progress(step, rel, index, len(files), "repair")
            response = self._provider.complete(CompletionRequest(
                model=model, prompt=self._repair_prompt(step, rel, failure_tail),
                phase=step.phase, subtask=step.subtask,
                max_tokens=self._code_max_tokens,
                temperature=self._temperature,
            ))
            for key in total:
                total[key] += int(response.usage.get(key, 0))
            reason = self._response_failure(response)
            if reason is not None:
                return f"repair of {rel}: {reason}"
            target = self._root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._strip_fences(response.content), encoding="utf-8")
            self._emit_artifact_usage(step, rel, dict(response.usage))
        return None

    def _repair_prompt(self, step: PhaseStep, rel: str, failure_tail: str) -> str:
        existing = self._existing_source(step, rel) or "(file is missing)"
        return "\n\n".join([
            "You are the implementation phase agent in REPAIR mode. The "
            f"project's verification failed; fix `{rel}`.",
            *self._instructions_block(),
            *self._contract_block(),
            "Verification output (excerpt):\n" + failure_tail,
            f"Current content of `{rel}`:\n" + existing,
            "Fix ONLY what the failures require. Keep every existing name, "
            "signature, and docstring exactly as written. Output ONLY the "
            f"complete, final contents of `{rel}` — no commentary, no file "
            "markers, no surrounding code fences.",
        ])

    def _manifest_violations(self) -> list[str]:
        """The #21 mechanical check, re-run inside the repair loop (FR-RL-009)."""
        from anvil_runtime.contract import (
            parse_contract_manifest,
            resolve_contract,
            validate_manifest,
        )

        contract = self._resolve_contract()
        if not contract.present:
            return []
        manifest, error = parse_contract_manifest(contract.text)
        if error is not None:
            return [error]
        if manifest is None:
            return []
        return validate_manifest(manifest, self._root / "src")

    def _emit_progress(
        self, step: PhaseStep, rel: str, index: int, count: int, stage: str
    ) -> None:
        """FR-AG-001: progress inside a long phase, observable over SSE."""
        self._emit_backend_event(step, "PhaseProgress", {
            "artifact": rel, "index": index, "count": count, "stage": stage,
        })

    # -- prompts ----------------------------------------------------------

    def _read_inputs(self, step: PhaseStep) -> str:
        from anvil_runtime.contract import DOMAIN_KNOWLEDGE_REL, split_contract

        limit = self._input_char_limit
        chunks: list[str] = []
        for rel in step.input_files:
            target = self._root / rel
            if target.is_file():
                text = target.read_text(encoding="utf-8")
                if rel == DOMAIN_KNOWLEDGE_REL:
                    # #20: on a markered file only the CONTEXT part travels as
                    # a normal (truncatable) input; the contract block is
                    # injected verbatim via _contract_block instead, so it is
                    # never duplicated and never clipped. Unmarkered files
                    # pass through untouched (v0.1.2 behavior).
                    split = split_contract(text)
                    if split.has_markers:
                        text = split.context
                if len(text) > limit:
                    # FR-CTX-002: truncation is never silent.
                    self._emit_truncation(step, rel, len(text), limit)
                    text = text[:limit]
                chunks.append(f"--- {rel} ---\n{text}")
        return "\n\n".join(chunks)

    def _emit_truncation(self, step: PhaseStep, rel: str, size: int, limit: int) -> None:
        if self._events is None:
            return
        from anvil_runtime.core.phase_contracts import EventEnvelope

        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType="InputTruncated",
            runId=str(step.context.get("run_id", "") or ""),
            phase=step.phase, severity="warning",
            data={"file": rel, "size": size, "limit": limit},
        ))

    def _instructions_block(self) -> list[str]:
        """The standing-instructions prompt block, or empty (FR-INS-002)."""
        if not self._instructions:
            return []
        return [
            "Standing instructions (anvil-instructions.md) — follow these for "
            "defaults, fallbacks, and conventions:\n" + self._instructions
        ]

    def _resolve_contract(self):  # noqa: ANN202 - ResolvedContract
        """Resolve the run's task contract fresh (per prompt assembly, #20)."""
        from anvil_runtime.contract import resolve_contract

        return resolve_contract(self._root)

    def _contract_block(self) -> list[str]:
        """The verbatim task-contract prompt block, or empty (#20).

        The task-scoped analog of the #14 instructions block: resolved at
        prompt-assembly time from the run's domain-knowledge file, prefixed
        with the fixed binding preamble, exempt from the input char limit,
        and injected into EVERY phase prompt (intake through cleanup).
        """
        from anvil_runtime.contract import CONTRACT_PREAMBLE

        contract = self._resolve_contract()
        if not contract.present:
            return []
        return [CONTRACT_PREAMBLE + "\n\n" + contract.text]

    def _doc_prompt(self, step: PhaseStep) -> str:
        sections = self._required_sections(step.phase)
        ctx = self._read_inputs(step)
        lines = [
            f"You are the '{step.phase}' phase agent in an automated software factory.",
            *self._instructions_block(),
            *self._contract_block(),
            step.instruction,
        ]
        if ctx:
            lines.append("Context from prior phases:\n" + ctx)
        if sections:
            lines.append("Write Markdown including these section headings: " + ", ".join(sections) + ".")
        # #16 (FR-OKF-004): encourage OKF cross-links between sibling artifacts.
        lines.append(
            "When referencing other project documents, use relative markdown links "
            "(e.g. [spec](/docs/spec.md))."
        )
        lines.append("Respond with the document content only.")
        if step.phase == "proposal":
            lines.append(
                "Then, on a final separate line, output exactly one of "
                "`COMPLEXITY: simple`, `COMPLEXITY: standard`, or `COMPLEXITY: complex` "
                "reflecting the project's overall complexity."
            )
        return "\n\n".join(lines)

    def _code_prompt(self, step: PhaseStep) -> str:
        ctx = self._read_inputs(step)
        out = ", ".join(step.output_paths) or "src/"
        return "\n\n".join([
            "You are the implementation phase agent. Output the COMPLETE, runnable "
            "source code for the project described below.",
            *self._instructions_block(),
            *self._contract_block(),
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

        from anvil_runtime.artifacts.schemas import okf_type_for

        generated_at = self._clock().isoformat()
        okf_type = okf_type_for(step.phase)
        # #16 (FR-OKF-001): OKF standard fields first (type is the only field the
        # OKF spec mandates), then Anvil's lineage fields as producer extensions.
        meta = {
            "type": okf_type,
            "title": f"{okf_type} — {self._root.name}",
            "description": self._okf_description(content),
            "tags": ["anvil", step.phase],
            "timestamp": generated_at,
            "artifactId": f"{step.phase}-v1",
            "phase": step.phase,
            "generatedAt": generated_at,
            "derivedFrom": list(step.input_files) or ["(none)"],
        }
        front = "---\n" + yaml.safe_dump(meta, sort_keys=False) + "---\n"
        # Write the generated body exactly once (FR-DOC-001). The doc prompt asks the
        # model to include the required section headings, so they normally appear
        # within `content`; only synthesize a placeholder for any heading the model
        # omitted (FR-DOC-002) — never re-emit the full body under each section.
        body = [f"# {step.phase.replace('-', ' ').title()}", "", content.strip(), ""]
        for section in self._required_sections(step.phase):
            if not self._has_heading(content, section):
                body.append(f"## {section}")
                body.append("_See above._")
                body.append("")
        return front + "\n".join(body) + "\n"

    @staticmethod
    def _okf_description(content: str, limit: int = 140) -> str:
        """First non-heading content line, truncated (deterministic; FR-OKF-001)."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                return stripped[:limit]
        return ""

    @staticmethod
    def _has_heading(content: str, section: str) -> bool:
        """True if a Markdown heading line in ``content`` mentions ``section``.

        Mirrors the artifact validator's heading check (case-insensitive substring
        over heading lines) so a section the model already produced is not
        re-emitted as a placeholder.
        """
        headings = "\n".join(
            line for line in content.splitlines() if line.lstrip().startswith("#")
        ).lower()
        return section.lower() in headings

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
