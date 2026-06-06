"""Phase + subtask hybrid model routing.

Slice 5 deliverable (blueprint §3.1; spec FR-ML-001..006). Each phase has a
default model; subtask categories (planning, analysis, coding, debugging, review)
may route to a different model. Defaults (FR-ML-003): Gemma 4 for planning /
analysis / architecture-oriented work; DeepSeek Coder for coding-heavy and
implementation-debugging work; ``review`` inherits the phase default unless
overridden.

:meth:`route` returns the selected model string after applying configuration
overrides (FR-ML-005). :meth:`select` additionally enforces policy (FR-ML-004) —
attempting ``switch-to-allowed-model`` remediation before reporting a decision —
and emits ``ModelRouteSelected`` to the audit trail (FR-ML-006).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.rule_evaluator import PolicyActionContext
from anvil_runtime.state.event_bus import EventBus

# Default model identifiers (FR-ML-003). Slugs follow the policy examples'
# convention (e.g. "deepseek-coder", spec §4.3) for AllowedModels coherence.
DEFAULT_PLANNING_MODEL = "gemma-4"
DEFAULT_CODING_MODEL = "deepseek-coder"

SUBTASK_CATEGORIES: tuple[str, ...] = (
    "planning",
    "analysis",
    "coding",
    "debugging",
    "review",
)

# Subtask -> default model. ``review`` maps to None: inherit the phase default.
_SUBTASK_MODEL: dict[str, str | None] = {
    "planning": DEFAULT_PLANNING_MODEL,
    "analysis": DEFAULT_PLANNING_MODEL,
    "coding": DEFAULT_CODING_MODEL,
    "debugging": DEFAULT_CODING_MODEL,
    "review": None,
}

# Phase -> default model. Coding-heavy phases default to the coding model; all
# planning/analysis/architecture-oriented phases default to the planning model.
_CODING_PHASES = frozenset({"implementation", "qa"})


def _phase_default(phase_id: str) -> str:
    return DEFAULT_CODING_MODEL if phase_id in _CODING_PHASES else DEFAULT_PLANNING_MODEL


class ModelRouteDecision(BaseModel):
    """A policy-checked routing decision for a phase/subtask."""

    phase: str
    subtask: str | None = None
    model: str
    justification: str
    remediated: bool = False
    allowed: bool = True


class ModelRouter:
    """Selects a model by phase and subtask, subject to configuration and policy."""

    def __init__(
        self,
        phase_models: dict[str, str] | None = None,
        subtask_models: dict[str, str] | None = None,
        policy_engine: PolicyEngine | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # Configuration overrides (FR-ML-005): phase-level and subtask-level.
        self._phase_models = phase_models or {}
        self._subtask_models = subtask_models or {}
        self._policy = policy_engine
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def route(self, phase_id: str, subtask: str) -> str:
        """Return the configured/default model for a phase + subtask (FR-ML-001)."""
        # Precedence: subtask override > phase override > subtask default > phase default.
        if subtask in self._subtask_models:
            return self._subtask_models[subtask]
        if phase_id in self._phase_models:
            return self._phase_models[phase_id]
        subtask_default = _SUBTASK_MODEL.get(subtask)
        if subtask_default is not None:
            return subtask_default
        return _phase_default(phase_id)

    def select(self, phase_id: str, subtask: str) -> ModelRouteDecision:
        """Route then enforce policy, remediating a forbidden model (FR-ML-004/006)."""
        model = self.route(phase_id, subtask)
        justification = f"default routing for {subtask} in {phase_id}"
        remediated = False
        allowed = True

        if self._policy is not None:
            ctx = PolicyActionContext(
                action="model-selection", phase=phase_id, model=model
            )
            decision, outcome = self._policy.enforce(ctx)
            if not decision.allowed:
                if outcome is not None and outcome.success and outcome.replacement:
                    model = outcome.replacement
                    remediated = True
                    justification = (
                        f"policy remediation: switched to allowed model '{model}'"
                    )
                else:
                    allowed = False
                    justification = (
                        decision.violation.reason
                        if decision.violation
                        else "model not permitted by policy"
                    )

        self._emit("ModelRouteSelected", phase_id, data={
            "subtask": subtask,
            "model": model,
            "justification": justification,
            "remediated": remediated,
            "allowed": allowed,
        })
        return ModelRouteDecision(
            phase=phase_id, subtask=subtask, model=model,
            justification=justification, remediated=remediated, allowed=allowed,
        )

    def _emit(self, event_type: str, phase: str, data: dict | None = None) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=self._run_id,
            phase=phase, severity="info", data=data or {},
        ))


__all__ = [
    "ModelRouter",
    "ModelRouteDecision",
    "DEFAULT_PLANNING_MODEL",
    "DEFAULT_CODING_MODEL",
    "SUBTASK_CATEGORIES",
]
