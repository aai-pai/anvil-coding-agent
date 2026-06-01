"""MCP tool discovery cache.

Slice 5 deliverable (spec FR-MC-006, blueprint §6.1). Persists discovered MCP
tools and their schemas to ``.anvil/mcp-tools-cache.json`` so subsequent phases
and resume scenarios — and discovery fallback when a server is unavailable
(FR-MC-012) — can reuse them without re-contacting the servers.
"""

from __future__ import annotations

import json
import pathlib

from pydantic import BaseModel, Field

# blueprint §6.1 well-known path (kept local to avoid editing the Slice 1
# protected schema module).
MCP_TOOLS_CACHE_PATH = ".anvil/mcp-tools-cache.json"
MCP_CACHE_VERSION = "0.1.0"


class CachedTool(BaseModel):
    """A discovered MCP tool with its server and JSON input schema."""

    name: str
    server: str
    description: str = ""
    schema_: dict[str, object] = Field(default_factory=dict, alias="schema")

    model_config = {"populate_by_name": True}


class MCPCache:
    """Reads/writes the workspace-local MCP tool cache."""

    def __init__(self, workspace_root: str | pathlib.Path = ".") -> None:
        self._path = pathlib.Path(workspace_root) / MCP_TOOLS_CACHE_PATH

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def write(self, tools: list[CachedTool]) -> None:
        """Persist the discovered tool set (FR-MC-006)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cacheVersion": MCP_CACHE_VERSION,
            "tools": [t.model_dump(by_alias=True) for t in tools],
        }
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

    def read(self) -> list[CachedTool]:
        """Load cached tools, or an empty list when no cache exists."""
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw = payload.get("tools", []) if isinstance(payload, dict) else []
        return [CachedTool.model_validate(item) for item in raw]


__all__ = ["MCPCache", "CachedTool", "MCP_TOOLS_CACHE_PATH", "MCP_CACHE_VERSION"]
