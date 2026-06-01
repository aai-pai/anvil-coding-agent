"""MCP tool authorization by security profile and policy.

Slice 5 deliverable (spec FR-MC-007/008/009). Decides — at invocation time —
whether a phase agent may use a given tool, based on the active security profile
and the ``MCPToolWhitelist`` / ``MCPToolBlacklist`` policies. Core tools
(FR-MC-014) are always allowed and can never be denied.

Profile rules (FR-MC-008):

* ``open``       — all tools allowed unless explicitly blacklisted.
* ``restricted`` — tools must be explicitly whitelisted; others denied.
* ``strict``     — only core tools, plus any tool explicitly enabled (whitelisted)
                   per-tool; all other external tools denied.
"""

from __future__ import annotations

from fnmatch import fnmatch

from pydantic import BaseModel, Field

from anvil_runtime.tools.core_tools import is_core_tool


class AuthorizationDecision(BaseModel):
    """Allow/deny verdict for a single tool, with a human-readable reason."""

    tool: str
    allowed: bool
    reason: str


class ToolAuthorizer:
    """Profile- and policy-aware tool authorization (FR-MC-007/008/009)."""

    def authorize(
        self,
        tool: str,
        profile: str,
        whitelist: list[str] | None = None,
        blacklist: list[str] | None = None,
    ) -> AuthorizationDecision:
        allow = whitelist or []
        deny = blacklist or []

        # Core tools are unconditionally available (FR-MC-014) and cannot be
        # denied — checked before any profile/blacklist rule.
        if is_core_tool(tool):
            return self._allow(tool, "core tool (always available)")

        if profile == "open":
            if self._matches(tool, deny):
                return self._deny(tool, "explicitly blacklisted (MCPToolBlacklist)")
            return self._allow(tool, "open profile: allowed by default")

        if profile == "restricted":
            if self._matches(tool, deny):
                return self._deny(tool, "explicitly blacklisted (MCPToolBlacklist)")
            if self._matches(tool, allow):
                return self._allow(tool, "whitelisted (MCPToolWhitelist)")
            return self._deny(tool, "restricted profile: not in MCPToolWhitelist")

        if profile == "strict":
            # Only core tools (handled above) and per-tool explicit enables.
            if self._matches(tool, allow):
                return self._allow(tool, "strict profile: explicitly enabled per-tool")
            return self._deny(tool, "strict profile: external tools disabled")

        # Unknown profile -> deny by default (fail closed).
        return self._deny(tool, f"unknown security profile '{profile}'")

    @staticmethod
    def _matches(tool: str, patterns: list[str]) -> bool:
        """Exact or glob (fnmatch) match against a name/pattern list."""
        return any(tool == p or fnmatch(tool, p) for p in patterns)

    @staticmethod
    def _allow(tool: str, reason: str) -> AuthorizationDecision:
        return AuthorizationDecision(tool=tool, allowed=True, reason=reason)

    @staticmethod
    def _deny(tool: str, reason: str) -> AuthorizationDecision:
        return AuthorizationDecision(tool=tool, allowed=False, reason=reason)


__all__ = ["ToolAuthorizer", "AuthorizationDecision"]
