"""Hook adapter: executes lifecycle hooks with allow/deny/mutate semantics.

Slice 3 deliverable (blueprint §3.1; spec §4.2.2). Evaluates compiled hook rules
at the four tool/prompt lifecycle boundaries, returning a :class:`HookDecision`
and writing an audit event for every decision. ``deny`` short-circuits; ``mutate``
applies the rule's ``set_args`` overrides; otherwise the call is allowed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.hooks.lifecycle_hooks import (
    HookDecision,
    HookRule,
    TokenUsage,
    rule_matches_model,
    rule_matches_tool,
)

if TYPE_CHECKING:
    from anvil_runtime.state.event_bus import EventBus


class HookAdapter:
    """Applies hook rules at lifecycle boundaries and audits each decision."""

    def __init__(
        self,
        rules: list[HookRule] | None = None,
        event_bus: "EventBus | None" = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._event_bus = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _rules_of_kind(self, kind: str) -> list[HookRule]:
        return [r for r in self._rules if r.kind == kind]

    def before_tool_invocation(self, tool: str, args: dict[str, object]) -> HookDecision:
        matching = [r for r in self._rules_of_kind("BeforeToolInvocation") if rule_matches_tool(r, tool)]
        for rule in matching:
            if rule.effect == "deny":
                decision = HookDecision(action="deny", reason=rule.reason or f"tool '{tool}' denied by hook")
                self._audit("ToolInvocationBlocked", tool, severity="warning", reason=decision.reason)
                return decision
        for rule in matching:
            if rule.effect == "mutate":
                merged = dict(args)
                merged.update(rule.set_args or {})
                self._audit("ToolInvocationMutated", tool, reason=rule.reason)
                return HookDecision(action="mutate", args=merged, reason=rule.reason)
        self._audit("ToolInvocationAllowed", tool)
        return HookDecision(action="allow")

    def after_tool_invocation(self, tool: str, result: object, duration_ms: int) -> None:
        self._audit("AfterToolInvocation", tool, data={"duration_ms": duration_ms})

    def before_prompt_submission(self, prompt: str, model: str) -> HookDecision:
        matching = [r for r in self._rules_of_kind("BeforePromptSubmission") if rule_matches_model(r, model)]
        for rule in matching:
            if rule.effect == "deny":
                decision = HookDecision(action="deny", reason=rule.reason or f"model '{model}' denied by hook")
                self._audit("PromptSubmissionBlocked", "", severity="warning", reason=decision.reason)
                return decision
        for rule in matching:
            if rule.effect == "mutate":
                new_prompt = str((rule.set_args or {}).get("prompt", prompt))
                self._audit("PromptSubmissionMutated", "", reason=rule.reason)
                return HookDecision(action="mutate", prompt=new_prompt, reason=rule.reason)
        return HookDecision(action="allow")

    def after_prompt_response(self, prompt: str, response: str, usage: TokenUsage) -> None:
        self._audit("AfterPromptResponse", "", data={"total_tokens": usage.total_tokens})

    def _audit(
        self,
        event_type: str,
        phase: str,
        severity: str = "info",
        reason: str | None = None,
        data: dict | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        payload = dict(data or {})
        if reason is not None:
            payload["reason"] = reason
        self._event_bus.emit(
            EventEnvelope(
                timestamp=self._clock(),
                eventType=event_type,
                runId=self._run_id,
                phase=phase,
                severity=severity,
                data=payload,
            )
        )


__all__ = ["HookAdapter"]
