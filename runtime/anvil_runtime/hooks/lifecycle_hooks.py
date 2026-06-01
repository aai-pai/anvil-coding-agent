"""Lifecycle hook contracts and decision types.

Slice 3 deliverable (spec §4.2.2; blueprint §3.1). Hooks are lifecycle-boundary
interceptors with a stable allow/deny/mutate contract. This module defines the
hook kinds, the rule shape authored in policy/config, the :class:`HookDecision`
returned by interceptors, and the :class:`TokenUsage` carried by prompt-response
hooks.
"""

from __future__ import annotations

import fnmatch
from typing import Literal

from pydantic import BaseModel, Field

HookKind = Literal[
    "BeforeToolInvocation",
    "AfterToolInvocation",
    "BeforePromptSubmission",
    "AfterPromptResponse",
    "PhaseStart",
    "PhaseComplete",
]

HookEffect = Literal["allow", "deny", "mutate"]


class TokenUsage(BaseModel):
    """Token accounting carried by ``AfterPromptResponse`` hooks."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class HookRule(BaseModel):
    """A single compiled hook rule (authored in policy/config files).

    For tool hooks, ``tool`` is a glob matched against the tool name. For prompt
    hooks, ``model`` is a glob matched against the model name. ``set_args``
    carries the argument overrides applied when ``effect == "mutate"``.
    """

    kind: HookKind
    tool: str | None = None
    model: str | None = None
    effect: HookEffect = "allow"
    set_args: dict[str, object] | None = None
    reason: str | None = None


class HookDecision(BaseModel):
    """Outcome of a before-* hook: allow, deny, or mutate the call."""

    action: HookEffect = "allow"
    args: dict[str, object] | None = None
    prompt: str | None = None
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action != "deny"


def allow() -> HookDecision:
    return HookDecision(action="allow")


def deny(reason: str | None = None) -> HookDecision:
    return HookDecision(action="deny", reason=reason)


def rule_matches_tool(rule: HookRule, tool_name: str) -> bool:
    return rule.tool is not None and fnmatch.fnmatch(tool_name, rule.tool)


def rule_matches_model(rule: HookRule, model_name: str) -> bool:
    return rule.model is None or fnmatch.fnmatch(model_name, rule.model)


__all__ = [
    "HookKind",
    "HookEffect",
    "HookRule",
    "HookDecision",
    "TokenUsage",
    "allow",
    "deny",
    "rule_matches_tool",
    "rule_matches_model",
]
