"""MCP manager: discovery, caching, authorization, and invocation.

Slice 5 deliverable (blueprint §3.1; spec §2.8). Coordinates the MCP tool
lifecycle:

* ``discover`` connects to each declared server, lists its tools, and caches the
  result (FR-MC-004/006). On a server failure it emits ``MCPDiscoveryFailed`` and
  falls back to the cached tools when available; if no cache exists the failure is
  surfaced for the supervisor to escalate (FR-MC-012).
* ``invoke`` authorizes the tool against the active security profile (FR-MC-007/
  008/009), validates arguments against the tool schema (FR-MC-011), and calls the
  server with a single retry on transient failure (FR-MC-013).

The server transport is injected (``ServerConnector``) so discovery/invocation are
testable without live MCP servers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from anvil_runtime.config.schema import DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS
from anvil_runtime.core.phase_contracts import EventEnvelope
from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.tools.mcp_cache import CachedTool, MCPCache
from anvil_runtime.tools.tool_authorizer import ToolAuthorizer


class MCPServer(BaseModel):
    """A declared MCP server (FR-MC-001)."""

    name: str
    version: str | None = None
    connection: str = "stdio"
    timeout_seconds: int = DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS
    profiles: list[str] = Field(default_factory=list)


class DiscoveredTool(BaseModel):
    """A tool listed by a server during discovery (with its input schema)."""

    name: str
    server: str
    description: str = ""
    schema_: dict[str, object] = Field(default_factory=dict, alias="schema")

    model_config = {"populate_by_name": True}


class MCPDiscoveryResult(BaseModel):
    """Outcome of a discovery pass across all declared servers."""

    tools: list[DiscoveredTool] = Field(default_factory=list)
    failures: list[dict[str, str]] = Field(default_factory=list)
    from_cache: bool = False
    escalate: bool = False


class ToolInvocationRequest(BaseModel):
    """A request to invoke a discovered tool (FR-MC-009)."""

    tool: str
    arguments: dict[str, object] = Field(default_factory=dict)
    profile: str = "restricted"
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)


class ToolInvocationResult(BaseModel):
    """Result of a tool invocation attempt."""

    tool: str
    status: str  # "ok" | "denied" | "error"
    output: object | None = None
    error: str | None = None
    attempts: int = 0


@runtime_checkable
class ServerConnector(Protocol):
    """Transport contract for talking to MCP servers (injected for tests)."""

    def list_tools(self, server: MCPServer) -> list[DiscoveredTool]: ...

    def call(self, tool: str, arguments: dict[str, object]) -> object: ...


class EmptyConnector:
    """Default connector: no servers reachable (offline / no MCP configured)."""

    def list_tools(self, server: MCPServer) -> list[DiscoveredTool]:
        return []

    def call(self, tool: str, arguments: dict[str, object]) -> object:
        raise RuntimeError(f"no transport configured for tool '{tool}'")


class MCPManager:
    """Discovers MCP tools, caches metadata, and executes authorized invocations."""

    def __init__(
        self,
        servers: list[MCPServer] | None = None,
        connector: ServerConnector | None = None,
        cache: MCPCache | None = None,
        authorizer: ToolAuthorizer | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._servers = servers or []
        self._connector = connector or EmptyConnector()
        self._cache = cache or MCPCache()
        self._authorizer = authorizer or ToolAuthorizer()
        self._events = event_bus
        self._run_id = run_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Schemas captured at discovery, used for argument validation (FR-MC-011).
        self._schemas: dict[str, dict[str, object]] = {}

    # -- discovery --------------------------------------------------------

    def discover(self) -> MCPDiscoveryResult:
        """Connect to each server, list tools, cache them, fall back on failure."""
        result = MCPDiscoveryResult()
        for server in self._servers:
            try:
                tools = self._connector.list_tools(server)
            except Exception as exc:  # noqa: BLE001 - any transport failure is transient
                self._emit("MCPDiscoveryFailed", severity="warning", data={
                    "server": server.name, "error": str(exc),
                })
                result.failures.append({"server": server.name, "error": str(exc)})
                continue
            result.tools.extend(tools)

        if result.failures and not result.tools:
            # Every contacted server failed: fall back to cache (FR-MC-012).
            cached = self._cache.read()
            if cached:
                result.tools = [self._from_cached(t) for t in cached]
                result.from_cache = True
                self._emit("MCPDiscoveryCacheFallback", data={"count": len(cached)})
            else:
                # No cache to fall back on -> caller must escalate.
                result.escalate = True
                self._emit("MCPDiscoveryEscalation", severity="error", data={
                    "servers": [f["server"] for f in result.failures],
                })

        self._index_schemas(result.tools)
        if result.tools and not result.from_cache:
            self._cache.write([self._to_cached(t) for t in result.tools])
        return result

    # -- invocation -------------------------------------------------------

    def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        """Authorize, validate, and call a tool with one retry (FR-MC-009/011/013)."""
        decision = self._authorizer.authorize(
            request.tool, request.profile, request.whitelist, request.blacklist
        )
        if not decision.allowed:
            self._emit("MCPToolDenied", severity="warning", data={
                "tool": request.tool, "reason": decision.reason,
            })
            return ToolInvocationResult(
                tool=request.tool, status="denied", error=decision.reason
            )

        schema_error = self._validate_arguments(request.tool, request.arguments)
        if schema_error is not None:
            self._emit("MCPToolSchemaMismatch", severity="error", data={
                "tool": request.tool, "error": schema_error,
            })
            return ToolInvocationResult(
                tool=request.tool, status="error", error=schema_error
            )

        last_error = ""
        for attempt in range(1, 3):  # up to 2 attempts total (FR-MC-013)
            try:
                output = self._connector.call(request.tool, request.arguments)
                return ToolInvocationResult(
                    tool=request.tool, status="ok", output=output, attempts=attempt
                )
            except Exception as exc:  # noqa: BLE001 - transient tool failure
                last_error = str(exc)
        self._emit("MCPToolInvocationFailed", severity="error", data={
            "tool": request.tool, "error": last_error,
        })
        return ToolInvocationResult(
            tool=request.tool, status="error", error=last_error, attempts=2
        )

    # -- helpers ----------------------------------------------------------

    def _validate_arguments(self, tool: str, arguments: dict[str, object]) -> str | None:
        """Check that required schema keys are present (FR-MC-011)."""
        schema = self._schemas.get(tool)
        if not schema:
            return None  # unknown/typeless tool: nothing to validate against
        required = schema.get("required")
        if isinstance(required, list):
            missing = [key for key in required if key not in arguments]
            if missing:
                return f"missing required arguments for '{tool}': {missing}"
        return None

    def _index_schemas(self, tools: list[DiscoveredTool]) -> None:
        for tool in tools:
            self._schemas[tool.name] = tool.schema_

    @staticmethod
    def _to_cached(tool: DiscoveredTool) -> CachedTool:
        return CachedTool(
            name=tool.name, server=tool.server,
            description=tool.description, schema=tool.schema_,
        )

    @staticmethod
    def _from_cached(tool: CachedTool) -> DiscoveredTool:
        return DiscoveredTool(
            name=tool.name, server=tool.server,
            description=tool.description, schema=tool.schema_,
        )

    def _emit(self, event_type: str, severity: str = "info", data: dict | None = None) -> None:
        if self._events is None:
            return
        self._events.emit(EventEnvelope(
            timestamp=self._clock(), eventType=event_type, runId=self._run_id,
            phase="", severity=severity, data=data or {},
        ))


__all__ = [
    "MCPManager",
    "MCPServer",
    "DiscoveredTool",
    "MCPDiscoveryResult",
    "ToolInvocationRequest",
    "ToolInvocationResult",
    "ServerConnector",
    "EmptyConnector",
]
