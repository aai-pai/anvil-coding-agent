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

import uuid
from datetime import datetime, timezone
from typing import Callable, Literal

from pydantic import BaseModel, Field

from anvil_runtime.agents.factory import PhaseAgentFactory
from anvil_runtime.agents.phase_invocation import build_invocation_payload
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
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent
from anvil_runtime.core.phase_dag import PhaseDAG
from anvil_runtime.core.phase_registry import PhaseRegistry
from anvil_runtime.core.retry_controller import RetryController
from anvil_runtime.state.checkpoint_store import CheckpointStore, PhaseCheckpoint, compute_checksum
from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.state.run_summary import RunSummaryWriter

RunStatus = Literal["running", "awaiting_approval", "completed", "escalated", "stopped"]
DispatchStatus = Literal["success", "failure", "blocked", "escalated"]

# Secure-mode mandatory gates that fire *before* a phase begins (vs. after).
_PRE_GATE_PHASE = {"pre-deployment": "deployment"}


# ---------------------------------------------------------------------------
# Result models (blueprint §3.1 forward types)
# ---------------------------------------------------------------------------


class RunProgress(BaseModel):
    run_id: str
    status: RunStatus
    current_phase: str | None = None
    completed_phases: list[str] = Field(default_factory=list)
    pending_approval_gate: str | None = None


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
        self._runs: dict[str, _RunContext] = {}

    # -- lifecycle --------------------------------------------------------

    def start_run(self, request: RunStartRequest) -> RunStarted:
        run_id = uuid.uuid4().hex
        ctx = _RunContext(run_id, request.mode)
        ctx.pre_gates, ctx.post_gates = self._gate_maps(request)
        self._runs[run_id] = ctx
        self._checkpoints.initialize_run(run_id, request.mode)
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

    def dispatch_phase(self, run_id: str, phase_id: str) -> PhaseDispatchResult:
        ctx = self._require_run(run_id)
        if not self._registry.has(phase_id):
            raise KeyError(f"Unknown phase '{phase_id}'")
        ready = self._dag.ready_phases(ctx.completed)
        if phase_id not in ready:
            return PhaseDispatchResult(
                run_id=run_id, phase=phase_id, status="blocked",
                detail="prerequisite phases incomplete",
            )
        contract = self._registry.get(phase_id)
        payload = build_invocation_payload(contract, phase_context={"run_id": run_id})
        self._emit(run_id, "PhaseStarted", phase_id)
        agent = self._factory.create(phase_id)
        event = agent.run(payload)
        attempt = self._retries.attempts(run_id, phase_id) + 1
        if event.status != "success":
            return self._handle_failure(ctx, phase_id, event, attempt)
        self._record_success(ctx, phase_id, event)
        return PhaseDispatchResult(
            run_id=run_id, phase=phase_id, status="success",
            attempt=attempt, complete_event=event,
        )

    def _handle_failure(
        self, ctx: _RunContext, phase_id: str, event: PhaseCompleteEvent, attempt: int
    ) -> PhaseDispatchResult:
        count = self._retries.record_failure(ctx.run_id, phase_id)
        self._emit(ctx.run_id, "PhaseFailed", phase_id, severity="error", data={
            "attempt": count, "failure_reason": event.failure_reason,
        })
        if self._retries.should_retry(ctx.run_id, phase_id):
            return PhaseDispatchResult(
                run_id=ctx.run_id, phase=phase_id, status="failure",
                attempt=count, complete_event=event,
                detail=f"retry scheduled (backoff {self._retries.backoff_seconds(count)}s)",
            )
        # Retries exhausted -> escalate and pause (FR-SV-019).
        packet = self._escalation.build_packet(
            ctx.run_id, phase_id,
            reason=event.failure_reason or "phase failed",
            attempts=count,
            recent_events=[e.model_dump(mode="json") for e in self._events.stream(ctx.run_id)][-50:],
        )
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

    def _compute_artifact_checksums(self, paths: list[str]) -> dict[str, str]:
        import pathlib
        result: dict[str, str] = {}
        for rel in paths:
            target = pathlib.Path(self._root) / rel
            if target.is_file():
                result[rel] = compute_checksum(target)
        return result

    # -- orchestration loop ----------------------------------------------

    def run_until_pause(self, run_id: str) -> RunProgress:
        """Advance phases serially until a gate, escalation, stop, or completion."""
        ctx = self._require_run(run_id)
        while ctx.status == "running":
            next_phase = self._dag.next_phase(ctx.completed)
            if next_phase is None:
                ctx.status = "completed"
                self._emit(run_id, "RunCompleted", "")
                break
            # Pre-phase gate (e.g., pre-deployment).
            pre_gate = ctx.pre_gates.get(next_phase)
            if pre_gate and not self._gate_satisfied(ctx, pre_gate):
                return self._pause_for_gate(ctx, pre_gate, next_phase)
            result = self._dispatch_with_retries(ctx, next_phase)
            if result.status == "escalated":
                ctx.status = "escalated"
                return self._progress(ctx, current_phase=next_phase)
            # Post-phase gate (e.g., post-proposal).
            post_gate = ctx.post_gates.get(next_phase)
            if post_gate and not self._gate_satisfied(ctx, post_gate):
                return self._pause_for_gate(ctx, post_gate, next_phase)
        return self._progress(ctx)

    def _dispatch_with_retries(self, ctx: _RunContext, phase_id: str) -> PhaseDispatchResult:
        """Dispatch a phase, retrying on failure within the budget."""
        result = self.dispatch_phase(ctx.run_id, phase_id)
        while result.status == "failure":
            result = self.dispatch_phase(ctx.run_id, phase_id)
        return result

    def _gate_satisfied(self, ctx: _RunContext, gate: str) -> bool:
        return ctx.mode == "yolo" or gate in ctx.approved_gates

    def _pause_for_gate(self, ctx: _RunContext, gate: str, phase: str) -> RunProgress:
        ctx.status = "awaiting_approval"
        ctx.pending_gate = gate
        self._emit(ctx.run_id, "ApprovalRequired", phase, data={"gate": gate})
        return self._progress(ctx, current_phase=phase)

    # -- approvals & overrides -------------------------------------------

    def submit_approval(self, run_id: str, request: ApprovalRequest) -> ApprovalDecision:
        ctx = self._require_run(run_id)
        if request.approved:
            ctx.approved_gates.add(request.gateId)
            if ctx.pending_gate == request.gateId:
                ctx.pending_gate = None
            ctx.status = "running"
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
            ctx.status = "running"
            return OverrideResult(
                status="accepted", action="rollback", targetPhase=plan.target_phase,
            )
        # force-advance: bypass the current pending gate.
        if ctx.pending_gate:
            ctx.approved_gates.add(ctx.pending_gate)
            ctx.pending_gate = None
        ctx.status = "running"
        self._emit(run_id, "OverrideForceAdvance", "", severity="warning", data={
            "reason": override.reason,
        })
        return OverrideResult(status="accepted", action="force-advance")

    # -- rollback & resume -----------------------------------------------

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

    def resume_run(self, run_id: str) -> ResumePlan:
        state = self._checkpoints.load_run_state(run_id)
        if state is None:
            raise KeyError(f"No persisted run state for '{run_id}'")
        ctx = self._runs.get(run_id)
        if ctx is None:
            ctx = _RunContext(run_id, state.mode)
            self._runs[run_id] = ctx
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

    def get_progress(self, run_id: str) -> RunProgress:
        return self._progress(self._require_run(run_id))

    def _progress(self, ctx: _RunContext, current_phase: str | None = None) -> RunProgress:
        if current_phase is None and ctx.status not in ("completed", "stopped"):
            current_phase = self._dag.next_phase(ctx.completed)
        return RunProgress(
            run_id=ctx.run_id,
            status=ctx.status,
            current_phase=current_phase,
            completed_phases=[p for p in self._dag.phases if p in ctx.completed],
            pending_approval_gate=ctx.pending_gate,
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
    "RollbackPlan",
    "ResumePlan",
]
