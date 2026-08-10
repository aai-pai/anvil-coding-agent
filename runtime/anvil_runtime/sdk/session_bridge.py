"""Session bridge: phase execution -> supervisor completion contract.

Slice 5 deliverable (blueprint §3.1; plan §3.3). Glues the OpenHands adapter,
model router, and usage tracker together and maps a phase invocation onto the
supervisor's ``PhaseInvocationPayload -> PhaseCompleteEvent`` contract — the same
contract the v0.1.0 stubs satisfy. This is the seam where real execution replaces
``stub_phase_result`` without changing the supervisor; wiring it into the phase
agents is a downstream integration step.
"""

from __future__ import annotations

from anvil_runtime.core.phase_contracts import PhaseCompleteEvent, PhaseInvocationPayload
from anvil_runtime.llm.model_router import ModelRouter
from anvil_runtime.llm.usage_tracker import UsageTracker
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    OpenHandsAdapter,
    PhaseStep,
)


class SessionBridge:
    """Executes a phase through an OpenHands session and reports completion."""

    def __init__(
        self,
        adapter: OpenHandsAdapter | None = None,
        model_router: ModelRouter | None = None,
        usage_tracker: UsageTracker | None = None,
        security_profile: str = "restricted",
        workspace_root: str = ".",
    ) -> None:
        self._adapter = adapter or OpenHandsAdapter()
        self._router = model_router or ModelRouter()
        self._usage = usage_tracker
        self._profile = security_profile
        self._root = workspace_root

    def execute_phase(
        self, payload: PhaseInvocationPayload, subtask: str = "coding"
    ) -> PhaseCompleteEvent:
        """Run a phase payload and return its :class:`PhaseCompleteEvent`."""
        phase = payload.phase_name
        # The supervisor passes the active run id via phase_context (FR-EVT-002);
        # thread it through routing + usage so their events carry the run id.
        run_id = ""
        if isinstance(payload.phase_context, dict):
            run_id = str(payload.phase_context.get("run_id", "") or "")
        decision = self._router.select(phase, subtask, run_id=run_id)
        if not decision.allowed:
            # FR-ML-004: a policy denial without a remediation replacement must
            # fail the phase — proceeding would call the forbidden model.
            return PhaseCompleteEvent(
                phase_name=phase,
                status="failure",
                duration_ms=0,
                failure_reason=(
                    f"model '{decision.model}' denied by policy: "
                    f"{decision.justification}"
                ),
            )
        cfg = AgentRuntimeConfig(
            model=decision.model,
            security_profile=self._profile,
            workspace_root=self._root,
        )
        session_id = self._adapter.start_session(cfg)
        step = PhaseStep(
            phase=phase,
            instruction=f"Execute phase '{phase}' producing {payload.output_paths}",
            subtask=subtask,
            output_paths=list(payload.output_paths),
            input_files=list(payload.input_files),
            context=dict(payload.phase_context),
        )
        result = self._adapter.run_phase_step(session_id, step)
        if self._usage is not None and result.usage:
            self._usage.record(phase, result.usage, run_id=run_id)
        return PhaseCompleteEvent(
            phase_name=phase,
            status=result.status,
            artifact_paths=list(result.artifacts),
            checksums={},
            duration_ms=0,
            token_usage=result.usage or None,
            failure_reason=result.failure_reason,
            complexity_tier=result.complexity_tier,
            questions=list(result.questions),
            assumptions=list(result.assumptions),
            # #24: unit-mode progress marker rides the completion contract.
            phase_complete=result.phase_complete,
        )


__all__ = ["SessionBridge"]
