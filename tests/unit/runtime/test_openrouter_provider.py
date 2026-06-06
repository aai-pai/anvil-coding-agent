"""Unit tests: OpenRouter provider with secret resolution.

Slice 5 (spec §2.7.4, NFR-SC-001/002/003; plan §2.5). Verifies key resolution,
the missing-key failure, and that the offline transport returns content + usage
without ever leaking the key.
"""

from __future__ import annotations

from anvil_runtime.llm.openrouter_provider import (
    CompletionRequest,
    MissingApiKeyError,
    OpenRouterProvider,
)
from anvil_runtime.security.secret_adapter import SecretAdapter


def test_complete_with_offline_transport_returns_usage() -> None:
    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="test-key")
    )
    resp = provider.complete(
        CompletionRequest(model="gemma-4", prompt="hello world", phase="proposal")
    )
    assert resp.model == "gemma-4"
    assert resp.content
    assert resp.usage["total_tokens"] > 0


def test_missing_key_raises() -> None:
    provider = OpenRouterProvider(secret_adapter=SecretAdapter(environ={}))
    try:
        provider.complete(CompletionRequest(model="gemma-4", prompt="x"))
    except MissingApiKeyError as exc:
        assert "OpenRouter" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected MissingApiKeyError")


def test_env_fallback_key_is_used_and_not_leaked() -> None:
    captured: dict[str, str] = {}

    class SpyTransport:
        def complete(self, request: CompletionRequest, api_key: str) -> dict:
            captured["key"] = api_key
            return {"content": "ok", "usage": {"total_tokens": 5}}

    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(environ={"OPENROUTER_API_KEY": "env-key"}),
        transport=SpyTransport(),
    )
    resp = provider.complete(CompletionRequest(model="gemma-4", prompt="x"))
    assert captured["key"] == "env-key"  # transport receives it
    assert "env-key" not in resp.content  # response never echoes the key
