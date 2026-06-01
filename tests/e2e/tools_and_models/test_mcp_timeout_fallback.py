"""E2E: MCP discovery timeout -> cache fallback / escalation.

Slice 5 (spec FR-MC-012; plan §2.5). When every declared server fails discovery,
the manager falls back to the cached tool set if one exists, or signals
escalation when no cache is available.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.tools.mcp_cache import CachedTool, MCPCache
from anvil_runtime.tools.mcp_manager import MCPManager, MCPServer


class TimeoutConnector:
    """Connector that always fails discovery (simulated server timeout)."""

    def list_tools(self, server: MCPServer):  # type: ignore[no-untyped-def]
        raise TimeoutError(f"server '{server.name}' did not respond within timeout")

    def call(self, tool: str, arguments: dict) -> object:
        raise RuntimeError("unreachable")


def test_discovery_falls_back_to_cache(tmp_path: pathlib.Path) -> None:
    cache = MCPCache(str(tmp_path))
    cache.write([CachedTool(name="db.query", server="db", schema={"required": ["sql"]})])
    bus = EventBus(str(tmp_path))

    mgr = MCPManager(
        servers=[MCPServer(name="db")],
        connector=TimeoutConnector(),
        cache=cache,
        event_bus=bus,
        run_id="r1",
    )
    result = mgr.discover()

    assert result.from_cache is True
    assert result.escalate is False
    assert [t.name for t in result.tools] == ["db.query"]
    types = {e.eventType for e in bus.read_all()}
    assert "MCPDiscoveryFailed" in types
    assert "MCPDiscoveryCacheFallback" in types


def test_discovery_escalates_without_cache(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    mgr = MCPManager(
        servers=[MCPServer(name="db")],
        connector=TimeoutConnector(),
        cache=MCPCache(str(tmp_path)),  # no cache file written
        event_bus=bus,
        run_id="r1",
    )
    result = mgr.discover()

    assert result.tools == []
    assert result.escalate is True
    types = {e.eventType for e in bus.read_all()}
    assert "MCPDiscoveryFailed" in types
    assert "MCPDiscoveryEscalation" in types
