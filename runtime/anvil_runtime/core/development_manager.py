"""Development manager: the supervisor state machine.

Slice 2 deliverable (blueprint §3.1; spec §2.1 FR-SV-*). Coordinates phase
lifecycle, operational-mode approval gates, bounded self-heal retries,
escalation, checkpointing, rollback, and resume. It delegates all phase work to
phase agents (FR-SV-007/008/ROLE-001) and only writes its own runtime-managed
state, logs, and approval/escalation records.

Phase execution is serial in topological order (proposal §8.6); the dependency
DAG is the durable, parallel-ready contract.
"""

from __future__ import annotations

import functools
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Literal

from pydantic import BaseModel, Field

from anvil_runtime.agents.factory import PhaseAgentFactory
from anvil_runtime.agents.phase_invocation import DefaultExecutor, build_invocation_payload
from anvil_runtime.api.models import (
    ApprovalRequest,
    OverrideRequest,
    OverrideResult,
    RunStarted,
    RunStartRequest,
)
from anvil_runtime.config.schema import (
    DEFAULT_MAX_RETRIES_PER_PHASE,
    EffectiveConfig,
    MANDATORY_SECURE_GATES,
)
from anvil_runtime.core.escalation_service import EscalationService
from anvil_runtime.core.failure_record import write_fr
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent
from anvil_runtime.core.phase_dag import PhaseDAG
from anvil_runtime.core.phase_registry import PhaseRegistry
from anvil_runtime.core.retry_controller import RetryController
from anvil_runtime.state.checkpoint_store import CheckpointStore, PhaseCheckpoint, compute_checksum
from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.state.run_summary import RunSummaryWriter

RunStatus = Literal[
    "running", "awaiting_approval", "awaiting_clarification",
    "completed", "escalated", "stopped",
]

# #15 (FR-INT-009): the clarification cycle runs at most once per run; the re-run
# after answers executes in assumption mode and can never pause again.
CLARIFICATION_MAX_ROUNDS = 1
DispatchStatus = Literal["success", "failure", "blocked", "escalated"]

# Secure-mode mandatory gates that fire *before* a phase begins (vs. after).
_PRE_GATE_PHASE = {"pre-deployment": "deployment"}

# #11 (spec FR-CX-002): auxiliary phases gated out per complexity tier. An unknown
# or absent tier gates nothing, so stub runs and unassessed runs execute fully.
_GATED_BY_TIER: dict[str, set[str]] = {
    "simple": {"qa", "packaging", "documentation", "deployment", "cleanup"},
    "standard": {"packaging", "documentation", "deployment", "cleanup"},
    "complex": set(),
}


def excluded_for_tier(tier: str | None) -> set[str]:
    """Phases to skip for a complexity tier; empty for unknown/None (no gating)."""
    return set(_GATED_BY_TIER.get(tier or "", set()))


# ---------------------------------------------------------------------------
# Result models (blueprint §3.1 forward types)
# ---------------------------------------------------------------------------


class RunProgress(BaseModel):
    run_id: str
    status: RunStatus
    current_phase: str | None = None
    completed_phases: list[str] = Field(default_factory=list)
    pending_approval_gate: str | None = None
    # #15 (FR-INT-007): intake questions awaiting user answers, when paused.
    pending_questions: list[str] = Field(default_factory=list)


class PhaseDispatchResult(BaseModel):
    run_id: str
    phase: str
    status: DispatchStatus
    attempt: int = 1
    complete_event: PhaseCompleteEvent | None = None
    detail: str | None = None


class ApprovalDecision(BaseModel):
    run_id: str
    gate_id: str
    gate_name: str
    approved: bool


class RollbackPlan(BaseModel):
    run_id: str
    target_phase: str
    invalidated_phases: list[str] = Field(default_factory=list)
    stale_phases: list[str] = Field(default_factory=list)
    reason: str


class ResumePlan(BaseModel):
    run_id: str
    resume_from: str | None = None
    skipped_phases: list[str] = Field(default_factory=list)
    invalidated_phases: list[str] = Field(default_factory=list)


class ClarificationDecision(BaseModel):
    """Outcome of recording clarification answers (#15, FR-INT-008)."""

    run_id: str
    round: int
    appended: bool


class _RunContext:
    """In-memory orchestration state for a single run."""

    def __init__(self, run_id: str, mode: str) -> None:
        self.run_id = run_id
        self.mode = mode
        self.status: RunStatus = "running"
        self.completed: set[str] = set()
        self.approved_gates: set[str] = set()
        self.pending_gate: str | None = None
        self.post_gates: dict[str, str] = {}
        self.pre_gates: dict[str, str] = {}
        # #11: phases gated out by the assessed complexity tier (set after proposal).
        self.excluded: set[str] = set()
        # #15: bounded-clarification state (FR-INT-007..009).
        self.clarification_round: int = 0
        self.pending_questions: list[str] = []
        # #20: True once the task-contract block is sealed (post-intake).
        self.contract_sealed: bool = False


def _locked(method: Callable) -> Callable:
    """Serialize a run-scoped method on that run's lock.

    FastAPI executes sync routes on a threadpool, so two requests can hit the
    same run concurrently; per-run reentrant locks make each public operation
    atomic without serializing unrelated runs against each other.
    """

    @functools.wraps(method)
    def wrapper(self: "DevelopmentManager", run_id: str, *args: object, **kwargs: object):
        with self._run_lock(run_id):
            return method(self, run_id, *args, **kwargs)

    return wrapper


class DevelopmentManager:
    """Coordinates phase lifecycle, approvals, retries, drift checks, and resume."""

    def __init__(
        self,
        workspace_root: str = ".",
        config: EffectiveConfig | None = None,
        dag: PhaseDAG | None = None,
        registry: PhaseRegistry | None = None,
        factory: PhaseAgentFactory | None = None,
        event_bus: EventBus | None = None,
        checkpoint_store: CheckpointStore | None = None,
        run_summary: RunSummaryWriter | None = None,
        retry_controller: RetryController | None = None,
        clock: Callable[[], datetime] | None = None,
        executor: object | None = None,
        artifact_validator: object | None = None,
        drift_checker: object | None = None,
        drift_context_provider: Callable[[str], object] | None = None,
        retry_sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._root = workspace_root
        self._config = config or EffectiveConfig()
        self._dag = dag or PhaseDAG()
        self._dag.validate()
        self._registry = registry or PhaseRegistry()
        self._factory = factory or PhaseAgentFactory()
        self._events = event_bus or EventBus(workspace_root)
        self._checkpoints = checkpoint_store or CheckpointStore(workspace_root)
        self._summary = run_summary or RunSummaryWriter(workspace_root)
        self._retries = retry_controller or RetryController(
            self._config.maxRetriesPerPhase or DEFAULT_MAX_RETRIES_PER_PHASE
        )
        self._escalation = EscalationService(self._events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Post-v0.1.0 integration: pluggable execution + post-phase gates. The
        # defaults preserve the deterministic stub behavior exactly.
        self._executor = executor or DefaultExecutor()
        self._validator = artifact_validator
        self._drift_checker = drift_checker
        self._drift_context_provider = drift_context_provider
        # NFR-RB-002: waits between self-heal retries. Injected as time.sleep
        # for real LLM execution (rate-limit protection); a no-op for stub /
        # offline modes, where there is no provider to protect.
        self._retry_sleep = retry_sleeper or (lambda _seconds: None)
        self._runs: dict[str, _RunContext] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _run_lock(self, run_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(run_id, threading.RLock())

    # -- lifecycle --------------------------------------------------------

    def start_run(self, request: RunStartRequest) -> RunStarted:
        run_id = uuid.uuid4().hex
        ctx = _RunContext(run_id, request.mode)
        ctx.pre_gates, ctx.post_gates = self._gate_maps(request)
        self._runs[run_id] = ctx
        self._checkpoints.initialize_run(run_id, request.mode)
        # Gates must survive a restart: a resumed secure run with empty gate
        # maps would silently skip every mandatory approval.
        self._checkpoints.save_run_meta(
            run_id, pre_gates=dict(ctx.pre_gates), post_gates=dict(ctx.post_gates)
        )
        self._emit(run_id, "SupervisorStarted", "", data={
            "mode": request.mode,
            "security_profile": request.security_profile,
            "phases": list(self._dag.phases),
        })
        return RunStarted(run_id=run_id, started_at=self._clock(), mode=request.mode)

    def _gate_maps(self, request: RunStartRequest) -> tuple[dict[str, str], dict[str, str]]:
        """Compute (pre_gates, post_gates) phase->gate maps for the run mode."""
        pre: dict[str, str] = {}
        post: dict[str, str] = {}
        if request.mode == "yolo":
            return pre, post  # user-facing gates skipped (FR-OM-002)
        if request.mode == "secure":
            # Four immutable mandatory gates (proposal §7; FR-OM-009/010).
            for gate in MANDATORY_SECURE_GATES:
                if gate in _PRE_GATE_PHASE:
                    pre[_PRE_GATE_PHASE[gate]] = gate
                else:
                    # "post-<phase>" fires after that phase completes.
                    post[gate[len("post-"):]] = gate
        # User-selected / config-required additional gates ("post-<phase>").
        extra = list(request.phase_gates) + list(self._config.requiredApprovalGates)
        for phase in extra:
            phase_id = phase[len("post-"):] if phase.startswith("post-") else phase
            if phase_id in self._registry.all_phase_ids():
                post.setdefault(phase_id, f"post-{phase_id}")
        return pre, post

    # -- single-phase dispatch -------------------------------------------

    @_locked
    def dispatch_phase(self, run_id: str, phase_id: str) -> PhaseDispatchResult:
        ctx = self._require_run(run_id)
        if not self._registry.has(phase_id):
            raise KeyError(f"Unknown phase '{phase_id}'")
        # Tier-excluded phases satisfy prerequisites just as they do in step()'s
        # next-phase selection — disagreeing here would spin run_until_pause.
        ready = self._dag.ready_phases(ctx.completed | ctx.excluded)
        if phase_id not in ready:
            return PhaseDispatchResult(
                run_id=run_id, phase=phase_id, status="blocked",
                detail="prerequisite phases incomplete",
            )
        contract = self._registry.get(phase_id)
        phase_context: dict[str, object] = {"run_id": run_id}
        if phase_id == "intake":
            # #15: tells the intake execution path whether it may ask (round 1,
            # interactive) or must record assumptions instead (yolo / final round).
            phase_context["clarification_mode"] = self._clarification_mode(ctx)
        payload = build_invocation_payload(contract, phase_context=phase_context)
        self._emit(run_id, "PhaseStarted", phase_id)
        agent = self._factory.create(phase_id)
        attempt = self._retries.attempts(run_id, phase_id) + 1
        # An executor crash (LLM/network/IO error) must enter the same
        # retry/escalation path as a reported failure, or the run wedges in
        # "running" with no failure record (FR-REC-001).
        try:
            event = self._executor.run(agent, payload)
        except Exception as exc:
            event = self._failure_event(phase_id, exc)
        if event.status != "success":
            return self._handle_failure(ctx, phase_id, event, attempt)
        # Post-phase gates: artifact validation (FR-SV-009) then drift (FR-SV-010).
        try:
            gate_failure = self._post_phase_checks(ctx, phase_id, event)
        except Exception as exc:
            gate_failure = self._failure_event(phase_id, exc)
        if gate_failure is not None:
            return self._handle_failure(ctx, phase_id, gate_failure, attempt)
        self._record_success(ctx, phase_id, event)
        return PhaseDispatchResult(
            run_id=run_id, phase=phase_id, status="success",
            attempt=attempt, complete_event=event,
        )

    @staticmethod
    def _failure_event(phase_id: str, exc: Exception) -> PhaseCompleteEvent:
        """A synthetic failure event for an exception escaping a phase dispatch."""
        return PhaseCompleteEvent(
            phase_name=phase_id,
            status="failure",
            duration_ms=0,
            failure_reason=f"{type(exc).__name__}: {exc}",
        )

    def _post_phase_checks(
        self, ctx: _RunContext, phase_id: str, event: PhaseCompleteEvent
    ) -> PhaseCompleteEvent | None:
        """Run optional artifact validation + drift; return a failure event or None."""
        if self._validator is not None:
            result = self._validator.validate(phase_id, event.artifact_paths)
            if not result.valid:
                reasons = "; ".join(i.detail for i in result.issues)
                return event.model_copy(update={
                    "status": "failure",
                    "failure_reason": f"artifact validation failed: {reasons}",
                })
        if (
            self._drift_checker is not None
            and self._drift_context_provider is not None
            and phase_id == "implementation"
        ):
            context = self._drift_context_provider(ctx.run_id)
            report = self._drift_checker.check(phase_id, context)
            if report.highest_severity in ("major", "critical"):
                return event.model_copy(update={
                    "status": "failure",
                    "failure_reason": f"{report.highest_severity} drift detected",
                })
        return None

    def _handle_failure(
        self, ctx: _RunContext, phase_id: str, event: PhaseCompleteEvent, attempt: int
    ) -> PhaseDispatchResult:
        count = self._retries.record_failure(ctx.run_id, phase_id)
        self._emit(ctx.run_id, "PhaseFailed", phase_id, severity="error", data={
            "attempt": count, "failure_reason": event.failure_reason,
        })
        # FR feature (FR-REC-001): write a failure record for EVERY failure, whether it
        # is about to be retried or escalated. One packet serves both purposes.
        packet = self._escalation.build_packet(
            ctx.run_id, phase_id,
            reason=event.failure_reason or "phase failed",
            attempts=count,
            recent_events=[e.model_dump(mode="json") for e in self._events.stream(ctx.run_id)][-50:],
        )
        self._write_failure_record(ctx, packet)
        if self._retries.should_retry(ctx.run_id, phase_id):
            return PhaseDispatchResult(
                run_id=ctx.run_id, phase=phase_id, status="failure",
                attempt=count, complete_event=event,
                detail=f"retry scheduled (backoff {self._retries.backoff_seconds(count)}s)",
            )
        # Retries exhausted -> escalate and pause (FR-SV-019).
        self._escalation.escalate(packet)
        ctx.status = "escalated"
        return PhaseDispatchResult(
            run_id=ctx.run_id, phase=phase_id, status="escalated",
            attempt=count, complete_event=event, detail="retry budget exhausted",
        )

    def _record_success(self, ctx: _RunContext, phase_id: str, event: PhaseCompleteEvent) -> None:
        checksums = self._compute_artifact_checksums(event.artifact_paths)
        self._checkpoints.save_phase_completion(
            ctx.run_id,
            PhaseCheckpoint(
                phase=phase_id,
                completed_at=self._clock().isoformat(),
                checksums=checksums,
            ),
        )
        ctx.completed.add(phase_id)
        self._retries.reset(ctx.run_id, phase_id)
        self._summary.write_phase_summary(ctx.run_id, event)
        self._emit(ctx.run_id, "PhaseCompleted", phase_id, data={
            "artifact_paths": event.artifact_paths,
        })
        # #15 (FR-INT-011): every intake completion is recorded for the audit trail.
        if phase_id == "intake":
            self._emit(ctx.run_id, "IntakeAssessed", phase_id, data={
                "complete": not event.questions and not event.assumptions,
                "questions": list(event.questions),
                "assumptions": list(event.assumptions),
                "round": ctx.clarification_round,
            })
        # #11: after the proposal phase, select the active phase set from the assessed
        # (or config-overridden) complexity tier; gated-out phases are never run.
        if phase_id == "proposal":
            tier = self._config.complexityTier or event.complexity_tier
            ctx.excluded = excluded_for_tier(tier)
            self._checkpoints.save_run_meta(
                ctx.run_id, excluded_phases=sorted(ctx.excluded)
            )
            self._emit(ctx.run_id, "ComplexityAssessed", phase_id, data={
                "tier": tier,
                "active": [p for p in self._dag.phases if p not in ctx.excluded],
                "excluded": sorted(ctx.excluded),
            })

    def _compute_artifact_checksums(self, paths: list[str]) -> dict[str, str]:
        import pathlib
        result: dict[str, str] = {}
        for rel in paths:
            target = pathlib.Path(self._root) / rel
            if target.is_file():
                result[rel] = compute_checksum(target)
        return result

    def _write_run_index(self, ctx: _RunContext) -> None:
        """Write ``docs/index.md`` — an OKF index of the run's artifacts (#16).

        FR-OKF-003: deterministic scan of ``docs/*.md`` frontmatter, no LLM call.
        Supervisor-owned like failure records, so write errors never break a run.
        """
        import pathlib

        try:
            from anvil_runtime.artifacts.metadata import split_front_matter

            docs = pathlib.Path(self._root) / "docs"
            if not docs.is_dir():
                return
            lines = ["# Index", ""]
            for path in sorted(docs.glob("*.md")):
                if path.name == "index.md":
                    continue
                meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
                okf_type = str(meta.get("type") or "Document")
                description = str(meta.get("description") or "").strip()
                suffix = f" — {description}" if description else ""
                lines.append(f"- **{okf_type}**: [{path.name}](/docs/{path.name}){suffix}")
            (docs / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001 - diagnostics must never fail a run
            pass

    def _write_failure_record(self, ctx: _RunContext, packet) -> None:  # noqa: ANN001
        """Persist an FR-style failure record (FR-REC-001).

        Diagnostics must never break orchestration, so any write error is swallowed.
        """
        exec_mode = os.environ.get("ANVIL_EXECUTION_MODE", "stub")
        try:
            write_fr(self._root, packet, ctx.mode, exec_mode, self._clock())
        except Exception:  # noqa: BLE001 - never fail a run because a record failed to write
            pass

    # -- orchestration loop ----------------------------------------------

    @_locked
    def step(self, run_id: str) -> RunProgress:
        """Advance exactly one phase (or stop at a gate/completion).

        One iteration of the orchestration loop, exposed so a client can drive
        the run phase-by-phase and stream progress between phases (Level 2).
        """
        ctx = self._require_run(run_id)
        if ctx.status != "running":
            return self._progress(ctx)
        # Complexity-gated phases (ctx.excluded) are treated as done for selection,
        # so the supervisor never dispatches them (#11; FR-CX-003).
        next_phase = self._dag.next_phase(ctx.completed | ctx.excluded)
        if next_phase is None:
            ctx.status = "completed"
            self._write_run_index(ctx)
            self._emit(run_id, "RunCompleted", "")
            return self._progress(ctx)
        # Pre-phase gate (e.g., pre-deployment).
        pre_gate = ctx.pre_gates.get(next_phase)
        if pre_gate and not self._gate_satisfied(ctx, pre_gate):
            return self._pause_for_gate(ctx, pre_gate, next_phase)
        result = self._dispatch_with_retries(ctx, next_phase)
        if result.status == "escalated":
            ctx.status = "escalated"
            return self._progress(ctx, current_phase=next_phase)
        # #15 (FR-INT-007): intake questions pause an interactive run once.
        if (
            next_phase == "intake"
            and result.complete_event is not None
            and result.complete_event.questions
            and self._clarification_mode(ctx) == "questions"
        ):
            return self._pause_for_clarification(ctx, result.complete_event.questions)
        # #20: intake finished without pausing -> the contract block is final.
        # Clarification answers and assumptions have been appended into it;
        # from here on it is sealed and later writes are rejected.
        if next_phase == "intake" and result.status == "success":
            self._seal_contract(ctx)
        # Post-phase gate (e.g., post-proposal).
        post_gate = ctx.post_gates.get(next_phase)
        if post_gate and not self._gate_satisfied(ctx, post_gate):
            return self._pause_for_gate(ctx, post_gate, next_phase)
        return self._progress(ctx)

    @_locked
    def run_until_pause(self, run_id: str) -> RunProgress:
        """Advance phases serially until a gate, escalation, stop, or completion."""
        ctx = self._require_run(run_id)
        while ctx.status == "running":
            progress = self.step(run_id)
            if ctx.status != "running":
                return progress
        return self._progress(ctx)

    def _dispatch_with_retries(self, ctx: _RunContext, phase_id: str) -> PhaseDispatchResult:
        """Dispatch a phase, retrying on failure within the budget."""
        result = self.dispatch_phase(ctx.run_id, phase_id)
        while result.status == "failure":
            # NFR-RB-002: back off before re-dispatching so retries never
            # hammer a rate-limited provider in a tight loop.
            failures = self._retries.attempts(ctx.run_id, phase_id)
            self._retry_sleep(self._retries.backoff_seconds(failures))
            result = self.dispatch_phase(ctx.run_id, phase_id)
        return result

    def _gate_satisfied(self, ctx: _RunContext, gate: str) -> bool:
        return ctx.mode == "yolo" or gate in ctx.approved_gates

    def _pause_for_gate(self, ctx: _RunContext, gate: str, phase: str) -> RunProgress:
        ctx.status = "awaiting_approval"
        ctx.pending_gate = gate
        self._checkpoints.save_run_meta(ctx.run_id, pending_gate=gate)
        self._emit(ctx.run_id, "ApprovalRequired", phase, data={"gate": gate})
        return self._progress(ctx, current_phase=phase)

    def _seal_contract(self, ctx: _RunContext) -> None:
        """Seal the run's task-contract block after final intake (#20).

        Only a markered file with a non-empty contract block is sealed; an
        unmarkered (v0.1.2-style) file has nothing to seal and its behavior
        stays byte-for-byte unchanged.
        """
        if ctx.contract_sealed:
            return
        from anvil_runtime.contract import resolve_contract

        resolved = resolve_contract(self._root)
        if not resolved.present:
            return
        ctx.contract_sealed = True
        self._checkpoints.save_run_meta(ctx.run_id, contract_sealed=True)
        self._emit(ctx.run_id, "ContractSealed", "intake", data={
            "length": resolved.length, "path": resolved.path,
        })

    # -- clarification (#15) ----------------------------------------------

    def _clarification_mode(self, ctx: _RunContext) -> str:
        """``questions`` only for an interactive run's first round (FR-INT-009/010)."""
        if ctx.mode == "yolo" or ctx.clarification_round >= CLARIFICATION_MAX_ROUNDS:
            return "assumptions"
        return "questions"

    def _pause_for_clarification(
        self, ctx: _RunContext, questions: list[str]
    ) -> RunProgress:
        ctx.status = "awaiting_clarification"
        ctx.pending_questions = list(questions)
        self._checkpoints.save_run_meta(ctx.run_id, pending_questions=list(questions))
        self._emit(ctx.run_id, "ClarificationRequired", "intake", data={
            "questions": list(questions), "round": ctx.clarification_round,
        })
        return self._progress(ctx, current_phase="intake")

    @_locked
    def submit_clarification(
        self, run_id: str, answers: list[str]
    ) -> ClarificationDecision:
        """Record the user's answers and set intake up for its final round.

        FR-INT-008: answers are appended to the run's domain-knowledge file
        under ``## Clarifications`` (a supervisor-owned deterministic write,
        exempt from phase single-writer rules like failure records), the intake
        checkpoint is invalidated, and the run resumes.
        """
        ctx = self._require_run(run_id)
        # #20: after ContractSealed the block is immutable — reject the write
        # explicitly (not just as a state error) so the caller learns why.
        if ctx.contract_sealed:
            raise ValueError(
                f"Run '{run_id}' contract is sealed (ContractSealed); "
                "post-intake writes to the contract block are rejected"
            )
        if ctx.status != "awaiting_clarification":
            raise ValueError(f"Run '{run_id}' is not awaiting clarification")
        self._append_clarifications(ctx, answers)
        # Intake re-runs (final round, assumption mode) with the enriched file.
        self._checkpoints.invalidate_phases(run_id, ["intake"])
        ctx.completed.discard("intake")
        self._retries.reset(run_id, "intake")
        ctx.clarification_round += 1
        ctx.pending_questions = []
        ctx.status = "running"
        self._checkpoints.save_run_meta(
            run_id,
            clarification_round=ctx.clarification_round,
            pending_questions=[],
        )
        self._emit(run_id, "ClarificationReceived", "intake", data={
            "answers": len(answers), "round": ctx.clarification_round,
        })
        return ClarificationDecision(
            run_id=run_id, round=ctx.clarification_round, appended=True
        )

    def _append_clarifications(self, ctx: _RunContext, answers: list[str]) -> None:
        """Record answers in the domain-knowledge file (FR-INT-008).

        #20: an answered question is a binding fact, not prose — on a
        contract-markered file the block lands *inside* the contract section
        so re-injection reflects it in every later phase. Unmarkered files
        keep the v0.1.2 append-at-end behavior byte-for-byte.
        """
        import pathlib

        from anvil_runtime.contract import append_block

        target = pathlib.Path(self._root) / "domain-knowledge" / "background-information.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        lines = ["", "## Clarifications", ""]
        questions = ctx.pending_questions
        for index, answer in enumerate(answers):
            question = questions[index] if index < len(questions) else "(additional)"
            lines.append(f"- **Q:** {question}")
            lines.append(f"  **A:** {answer}")
        target.write_text(append_block(existing, "\n".join(lines)), encoding="utf-8")

    # -- approvals & overrides -------------------------------------------

    @_locked
    def submit_approval(self, run_id: str, request: ApprovalRequest) -> ApprovalDecision:
        ctx = self._require_run(run_id)
        # A decision is only valid against the gate the run is actually paused
        # at: anything else could pre-approve future mandatory gates or revive
        # a stopped/escalated/completed run.
        if ctx.status != "awaiting_approval" or ctx.pending_gate is None:
            raise ValueError("no approval is pending for this run")
        if request.gateId != ctx.pending_gate:
            raise ValueError(
                f"gate '{request.gateId}' is not the pending gate '{ctx.pending_gate}'"
            )
        if request.approved:
            ctx.approved_gates.add(request.gateId)
            ctx.pending_gate = None
            ctx.status = "running"
            self._checkpoints.save_run_meta(
                run_id, approved_gates=sorted(ctx.approved_gates), pending_gate=None
            )
            self._emit(run_id, "ApprovalGranted", "", data={
                "gate": request.gateId, "requester": request.requesterId,
            })
        else:
            self._emit(run_id, "ApprovalDenied", "", severity="warning", data={
                "gate": request.gateId, "requester": request.requesterId,
            })
        return ApprovalDecision(
            run_id=run_id, gate_id=request.gateId,
            gate_name=request.gateName, approved=request.approved,
        )

    def await_approval(self, run_id: str, gate_id: str, gate_name: str) -> ApprovalDecision:
        """Report whether a gate is currently approved (FR-SV-012 boundary)."""
        ctx = self._require_run(run_id)
        return ApprovalDecision(
            run_id=run_id, gate_id=gate_id, gate_name=gate_name,
            approved=gate_id in ctx.approved_gates,
        )

    @_locked
    def apply_override(self, run_id: str, override: OverrideRequest) -> OverrideResult:
        ctx = self._require_run(run_id)
        if override.action == "stop":
            ctx.status = "stopped"
            self._emit(run_id, "RunStopped", "", severity="warning", data={
                "reason": override.reason,
            })
            return OverrideResult(status="accepted", action="stop")
        if override.action == "rollback":
            if not override.targetPhase:
                raise ValueError("rollback override requires targetPhase")
            plan = self.rollback(run_id, override.targetPhase, override.reason)
            # Rolling back abandons any pause that was active at the old point.
            ctx.pending_gate = None
            ctx.pending_questions = []
            self._checkpoints.save_run_meta(
                run_id, pending_gate=None, pending_questions=[]
            )
            ctx.status = "running"
            return OverrideResult(
                status="accepted", action="rollback", targetPhase=plan.target_phase,
            )
        # force-advance: bypass the current pending gate.
        if ctx.pending_gate:
            ctx.approved_gates.add(ctx.pending_gate)
            ctx.pending_gate = None
            self._checkpoints.save_run_meta(
                run_id, approved_gates=sorted(ctx.approved_gates), pending_gate=None
            )
        ctx.status = "running"
        self._emit(run_id, "OverrideForceAdvance", "", severity="warning", data={
            "reason": override.reason,
        })
        return OverrideResult(status="accepted", action="force-advance")

    # -- rollback & resume -----------------------------------------------

    @_locked
    def rollback(self, run_id: str, target_phase: str, reason: str) -> RollbackPlan:
        ctx = self._require_run(run_id)
        if not self._registry.has(target_phase):
            raise KeyError(f"Unknown rollback target '{target_phase}'")
        affected = [target_phase] + self._dag.downstream_of(target_phase)
        self._checkpoints.invalidate_phases(run_id, affected)
        ctx.completed -= set(affected)
        for phase in affected:
            self._retries.reset(run_id, phase)
        self._emit(run_id, "Rollback", target_phase, severity="warning", data={
            "reason": reason, "invalidated": affected,
        })
        return RollbackPlan(
            run_id=run_id, target_phase=target_phase,
            invalidated_phases=affected, stale_phases=affected, reason=reason,
        )

    @_locked
    def resume_run(self, run_id: str) -> ResumePlan:
        state = self._checkpoints.load_run_state(run_id)
        if state is None:
            raise KeyError(f"No persisted run state for '{run_id}'")
        ctx = self._runs.get(run_id)
        if ctx is None:
            ctx = _RunContext(run_id, state.mode)
            self._runs[run_id] = ctx
        # Rehydrate persisted orchestration state — approval gates, complexity
        # tier, and the clarification round — not just the completed set.
        ctx.pre_gates = dict(state.pre_gates)
        ctx.post_gates = dict(state.post_gates)
        ctx.approved_gates = set(state.approved_gates)
        ctx.excluded = set(state.excluded_phases)
        ctx.clarification_round = state.clarification_round
        # #20: a sealed contract stays sealed across restarts.
        ctx.contract_sealed = state.contract_sealed
        # A pause that was active at shutdown is restored, not skipped: a
        # post-gate is only ever checked in the step that completed its phase.
        if state.pending_gate and not self._gate_satisfied(ctx, state.pending_gate):
            ctx.status = "awaiting_approval"
            ctx.pending_gate = state.pending_gate
        elif state.pending_questions:
            ctx.status = "awaiting_clarification"
            ctx.pending_questions = list(state.pending_questions)
        ctx.completed = self._checkpoints.completed_phase_ids(run_id)
        invalidated: list[str] = []
        earliest_invalid = self._checkpoints.earliest_invalid_phase(run_id)
        if earliest_invalid is not None:
            # Re-validate failed: resume from the earliest invalid phase
            # rather than skipping it (FR-SV-022A).
            invalidated = [earliest_invalid] + self._dag.downstream_of(earliest_invalid)
            self._checkpoints.invalidate_phases(run_id, invalidated)
            ctx.completed -= set(invalidated)
            self._emit(run_id, "ResumeValidationFailed", earliest_invalid,
                       severity="warning", data={"invalidated": invalidated})
        resume_from = self._dag.next_phase(ctx.completed)
        self._emit(run_id, "ResumeFromCheckpoint", resume_from or "", data={
            "completed": sorted(ctx.completed),
        })
        return ResumePlan(
            run_id=run_id, resume_from=resume_from,
            skipped_phases=sorted(ctx.completed), invalidated_phases=invalidated,
        )

    def escalate(self, run_id: str, packet) -> None:  # noqa: ANN001 (blueprint signature)
        self._escalation.escalate(packet)
        ctx = self._runs.get(run_id)
        if ctx is not None:
            ctx.status = "escalated"

    # -- helpers ----------------------------------------------------------

    @_locked
    def get_progress(self, run_id: str) -> RunProgress:
        return self._progress(self._require_run(run_id))

    def _progress(self, ctx: _RunContext, current_phase: str | None = None) -> RunProgress:
        if current_phase is None and ctx.status not in ("completed", "stopped"):
            current_phase = self._dag.next_phase(ctx.completed | ctx.excluded)
        return RunProgress(
            run_id=ctx.run_id,
            status=ctx.status,
            current_phase=current_phase,
            completed_phases=[p for p in self._dag.phases if p in ctx.completed],
            pending_approval_gate=ctx.pending_gate,
            pending_questions=list(ctx.pending_questions),
        )

    def _require_run(self, run_id: str) -> _RunContext:
        ctx = self._runs.get(run_id)
        if ctx is None:
            raise KeyError(f"Unknown run '{run_id}'")
        return ctx

    def _emit(self, run_id: str, event_type: str, phase: str,
              severity: str = "info", data: dict | None = None) -> None:
        from anvil_runtime.core.phase_contracts import EventEnvelope
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=run_id,
            phase=phase, severity=severity, data=data or {},
        ))


__all__ = [
    "DevelopmentManager",
    "RunProgress",
    "PhaseDispatchResult",
    "ApprovalDecision",
    "ClarificationDecision",
    "RollbackPlan",
    "ResumePlan",
    "excluded_for_tier",
    "CLARIFICATION_MAX_ROUNDS",
]
