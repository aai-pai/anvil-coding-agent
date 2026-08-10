"""Unit tests: OpenRouter provider with secret resolution.

Slice 5 (spec §2.7.4, NFR-SC-001/002/003; plan §2.5). Verifies key resolution,
the missing-key failure, and that the offline transport returns content + usage
without ever leaking the key.
"""

from __future__ import annotations

import httpx
import pytest

from anvil_runtime.llm.openrouter_provider import (
    CompletionRequest,
    HttpxTransport,
    MissingApiKeyError,
    OpenRouterProvider,
    OpenRouterResponseError,
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


class _FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._data


class _FakeClient:
    """httpx.Client stand-in: yields queued responses/exceptions in order."""

    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_error_payload_raises_instead_of_empty_success() -> None:
    # OpenRouter reports upstream errors in the body, sometimes with HTTP 200.
    client = _FakeClient([_FakeResponse({"error": {"message": "model not found"}})])
    transport = HttpxTransport(client=client)
    with pytest.raises(OpenRouterResponseError, match="model not found"):
        transport.complete(CompletionRequest(model="m", prompt="x"), api_key="k")


def test_transport_errors_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)
    ok = _FakeResponse({
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })
    client = _FakeClient([httpx.ConnectError("boom"), httpx.ReadTimeout("slow"), ok])
    transport = HttpxTransport(client=client, max_retries=4)
    data = transport.complete(CompletionRequest(model="m", prompt="x"), api_key="k")
    assert client.calls == 3
    assert data["content"] == "hi"
    assert data["finish_reason"] == "stop"


def test_transport_error_reraised_when_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)
    client = _FakeClient([httpx.ConnectError("boom")] * 3)
    transport = HttpxTransport(client=client, max_retries=2)
    with pytest.raises(httpx.ConnectError):
        transport.complete(CompletionRequest(model="m", prompt="x"), api_key="k")
    assert client.calls == 3


def test_finish_reason_and_nonnumeric_usage_survive_normalization() -> None:
    class Transport:
        def complete(self, request: CompletionRequest, api_key: str) -> dict:
            return {
                "content": "partial",
                "finish_reason": "length",
                "usage": {
                    "total_tokens": 9,
                    "cost": 0.002,
                    "prompt_tokens_details": {"cached_tokens": 0},  # non-numeric
                },
            }

    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="k"), transport=Transport()
    )
    resp = provider.complete(CompletionRequest(model="m", prompt="x"))
    assert resp.finish_reason == "length"
    assert resp.usage["total_tokens"] == 9
    assert "prompt_tokens_details" not in resp.usage  # skipped, not crashed
