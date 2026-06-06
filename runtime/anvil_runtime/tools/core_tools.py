"""Built-in core tools — always available, never deniable.

Slice 5 deliverable (spec FR-MC-014). These tools do not require an external MCP
server and are available in every security profile (including ``strict``); the
tool authorizer must never deny them. They are declared here as a closed,
name-to-category registry so the authorizer and tests share one source of truth.
"""

from __future__ import annotations

# name -> category. Categories mirror the FR-MC-014 groupings.
CORE_TOOLS: dict[str, str] = {
    # File I/O
    "file.read": "file-io",
    "file.write": "file-io",
    "file.delete": "file-io",
    "file.list": "file-io",
    "file.move": "file-io",
    "file.copy": "file-io",
    # Version control (scoped to the project repo)
    "git.status": "version-control",
    "git.commit": "version-control",
    "git.push": "version-control",
    "git.fetch": "version-control",
    # Logging
    "log.write_event": "logging",
    "log.write_summary": "logging",
    # Shell execution (isolated container)
    "shell.run": "shell",
}

CORE_TOOL_NAMES: frozenset[str] = frozenset(CORE_TOOLS)


def is_core_tool(name: str) -> bool:
    """True when ``name`` is a built-in core tool (FR-MC-014)."""
    return name in CORE_TOOL_NAMES


__all__ = ["CORE_TOOLS", "CORE_TOOL_NAMES", "is_core_tool"]
