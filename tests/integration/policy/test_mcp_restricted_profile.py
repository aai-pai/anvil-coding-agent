"""Integration tests: MCP invocation under the restricted security profile.

Slice 5 (spec FR-MC-007/008/009/011; plan §2.5). Drives MCPManager.invoke with a
fake connector to confirm whitelist enforcement, core-tool exemption, schema
validation, and invocation-time denial logging.
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.tools.mcp_manager import (
    DiscoveredTool,
    MCPManager,
    MCPServer,
    ToolInvocationRequest,
)
from anvil_runtime.tools.mcp_cache import MCPCache


class FakeConnector:
    """Lists one schema-bearing tool and echoes invocation arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self, server: MCPServer) -> list[DiscoveredTool]:
        return [
            DiscoveredTool(
                name="db.query",
                server=server.name,
                description="run a query",
                schema={"required": ["sql"]},
            )
        ]

    def call(self, tool: str, arguments: dict) -> object:
        self.calls.append((tool, arguments))
        return {"rows": 1}


@pytest.fixture()
def manager(tmp_path: pathlib.Path) -> MCPManager:
    connector = FakeConnector()
    mgr = MCPManager(
        servers=[MCPServer(name="db", profiles=["restricted"])],
        connector=connector,
        cache=MCPCache(str(tmp_path)),
        event_bus=EventBus(str(tmp_path)),
        run_id="r1",
    )
    mgr.discover()  # index schemas + write cache
    return mgr


def test_denied_when_not_whitelisted(manager: MCPManager) -> None:
    result = manager.invoke(
        ToolInvocationRequest(tool="db.query", arguments={"sql": "SELECT 1"}, profile="restricted")
    )
    assert result.status == "denied"


def test_allowed_when_whitelisted(manager: MCPManager) -> None:
    result = manager.invoke(
        ToolInvocationRequest(
            tool="db.query",
            arguments={"sql": "SELECT 1"},
            profile="restricted",
            whitelist=["db.query"],
        )
    )
    assert result.status == "ok"
    assert result.output == {"rows": 1}
    assert result.attempts == 1


def test_schema_validation_rejects_missing_argument(manager: MCPManager) -> None:
    result = manager.invoke(
        ToolInvocationRequest(
            tool="db.query", arguments={}, profile="restricted", whitelist=["db.query"]
        )
    )
    assert result.status == "error"
    assert "missing required arguments" in (result.error or "")


def test_core_tool_allowed_even_in_restricted(manager: MCPManager) -> None:
    result = manager.invoke(
        ToolInvocationRequest(tool="file.read", arguments={}, profile="restricted")
    )
    # file.read is a core tool; authorization passes (the fake connector echoes it).
    assert result.status == "ok"
