"""Unit tests for the hook adapter (allow/deny/mutate). Slice 3 (spec §4.2.2)."""

from __future__ import annotations

from anvil_runtime.hooks.adapter import HookAdapter
from anvil_runtime.hooks.lifecycle_hooks import HookRule, TokenUsage


def test_before_tool_allows_by_default() -> None:
    adapter = HookAdapter()
    decision = adapter.before_tool_invocation("read_file", {"path": "x"})
    assert decision.action == "allow"
    assert decision.allowed is True


def test_before_tool_deny_rule_blocks_matching_tool() -> None:
    adapter = HookAdapter([
        HookRule(kind="BeforeToolInvocation", tool="shell*", effect="deny", reason="no shell"),
    ])
    decision = adapter.before_tool_invocation("shell_exec", {"cmd": "rm"})
    assert decision.action == "deny"
    assert decision.allowed is False
    assert decision.reason == "no shell"
    # Non-matching tool still allowed.
    assert adapter.before_tool_invocation("read_file", {}).action == "allow"


def test_before_tool_mutate_merges_args() -> None:
    adapter = HookAdapter([
        HookRule(
            kind="BeforeToolInvocation", tool="http_get", effect="mutate",
            set_args={"timeout": 5},
        ),
    ])
    decision = adapter.before_tool_invocation("http_get", {"url": "x"})
    assert decision.action == "mutate"
    assert decision.args == {"url": "x", "timeout": 5}


def test_before_prompt_deny_by_model_pattern() -> None:
    adapter = HookAdapter([
        HookRule(kind="BeforePromptSubmission", model="gpt-*", effect="deny", reason="blocked model"),
    ])
    assert adapter.before_prompt_submission("hi", "gpt-4o").action == "deny"
    assert adapter.before_prompt_submission("hi", "deepseek-coder").action == "allow"


def test_after_hooks_are_void_and_do_not_raise() -> None:
    adapter = HookAdapter()
    assert adapter.after_tool_invocation("read_file", {"ok": True}, 12) is None
    assert adapter.after_prompt_response("p", "r", TokenUsage(total_tokens=10)) is None
