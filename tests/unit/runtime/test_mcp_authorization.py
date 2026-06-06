"""Unit tests: MCP tool authorization by security profile.

Slice 5 (spec FR-MC-007/008/014; plan §2.5). Verifies core tools are always
allowed, and that open/restricted/strict profiles apply whitelist/blacklist
semantics correctly.
"""

from __future__ import annotations

from anvil_runtime.tools.tool_authorizer import ToolAuthorizer


def test_core_tools_always_allowed_in_every_profile() -> None:
    auth = ToolAuthorizer()
    for profile in ("open", "restricted", "strict"):
        assert auth.authorize("file.read", profile).allowed is True
        # Even an explicit blacklist cannot deny a core tool (FR-MC-014).
        assert auth.authorize("shell.run", profile, blacklist=["shell.run"]).allowed


def test_open_profile_allows_unless_blacklisted() -> None:
    auth = ToolAuthorizer()
    assert auth.authorize("web.search", "open").allowed is True
    denied = auth.authorize("web.search", "open", blacklist=["web.*"])
    assert denied.allowed is False
    assert "blacklist" in denied.reason.lower()


def test_restricted_profile_requires_whitelist() -> None:
    auth = ToolAuthorizer()
    assert auth.authorize("web.search", "restricted").allowed is False
    assert auth.authorize("web.search", "restricted", whitelist=["web.search"]).allowed
    # Glob patterns are honored.
    assert auth.authorize("db.query", "restricted", whitelist=["db.*"]).allowed


def test_restricted_blacklist_overrides_whitelist() -> None:
    auth = ToolAuthorizer()
    decision = auth.authorize(
        "web.search", "restricted", whitelist=["web.*"], blacklist=["web.search"]
    )
    assert decision.allowed is False


def test_strict_profile_only_core_plus_explicit_enable() -> None:
    auth = ToolAuthorizer()
    assert auth.authorize("web.search", "strict").allowed is False
    # A per-tool explicit enable (whitelist) is required in strict mode.
    assert auth.authorize("web.search", "strict", whitelist=["web.search"]).allowed


def test_unknown_profile_fails_closed() -> None:
    assert ToolAuthorizer().authorize("web.search", "lax").allowed is False
