"""Integration: hook adapter enforces deny/mutate and writes audit events.

Slice 3 (spec §4.2.2; FR enforcement + audit logging).
"""

from __future__ import annotations

import pathlib

from anvil_runtime.hooks.adapter import HookAdapter
from anvil_runtime.hooks.lifecycle_hooks import HookRule
from anvil_runtime.state.event_bus import EventBus


def test_denied_tool_emits_blocked_event(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    adapter = HookAdapter(
        rules=[HookRule(kind="BeforeToolInvocation", tool="net-*", effect="deny", reason="restricted profile")],
        event_bus=bus,
        run_id="run-1",
    )
    decision = adapter.before_tool_invocation("net-fetch", {"url": "http://x"})
    assert decision.action == "deny"

    events = bus.read_all()
    blocked = [e for e in events if e.eventType == "ToolInvocationBlocked"]
    assert len(blocked) == 1
    assert blocked[0].severity == "warning"
    assert blocked[0].data["reason"] == "restricted profile"


def test_allowed_tool_emits_allow_event(tmp_path: pathlib.Path) -> None:
    bus = EventBus(tmp_path)
    adapter = HookAdapter(event_bus=bus, run_id="run-1")
    adapter.before_tool_invocation("read_file", {"path": "x"})
    assert any(e.eventType == "ToolInvocationAllowed" for e in bus.read_all())
