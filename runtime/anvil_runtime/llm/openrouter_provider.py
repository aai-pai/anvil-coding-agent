"""OpenRouter completion provider.

Slice 5 deliverable (blueprint §3.1; spec §2.7.4, NFR-SC-003). Submits prompts to
OpenRouter using a policy-approved model. The API key is resolved through the
:class:`SecretAdapter` (env fallback) and is never logged. The HTTP transport is
injected (``CompletionTransport``); the default offline transport returns a
deterministic stub so the runtime and tests work without network access — real
HTTP wiring swaps in a transport without changing this contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from anvil_runtime.security.secret_adapter import SecretAdapter

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class CompletionRequest(BaseModel):
    """A single completion request bound to a routed model."""

    model: str
    prompt: str
    phase: str | None = None
    subtask: str | None = None
    max_tokens: int | None = None


class CompletionResponse(BaseModel):
    """A completion result with token usage for the usage tracker."""

    model: str
    content: str
    usage: dict[str, int] = Field(default_factory=dict)


@runtime_checkable
class CompletionTransport(Protocol):
    """Transport contract: turn a request + key into a raw response dict."""

    def complete(self, request: CompletionRequest, api_key: str) -> dict[str, object]: ...


class OfflineTransport:
    """Deterministic offline transport (no network); used by default and in tests."""

    def complete(self, request: CompletionRequest, api_key: str) -> dict[str, object]:
        # The key is accepted but never echoed back or logged (NFR-SC-003).
        prompt_tokens = max(1, len(request.prompt) // 4)
        completion_tokens = 16
        return {
            "content": f"[offline:{request.model}] acknowledged {len(request.prompt)} chars",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


class HttpxTransport:
    """Real OpenRouter transport over HTTP (post-v0.1.0 integration).

    Calls the OpenRouter chat-completions endpoint with the resolved API key in
    the ``Authorization`` header (never logged, NFR-SC-003) and normalizes the
    response to ``{content, usage}``. The HTTP client is injectable so the
    request shaping is testable without network access.
    """

    def __init__(
        self,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = 60.0,
        client: object | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client  # an httpx.Client-like object; lazily created if None

    def complete(self, request: CompletionRequest, api_key: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = self._post(f"{self._base_url}/chat/completions", payload, headers)
        return self._normalize(data)

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        client = self._client
        if client is None:
            import httpx  # imported lazily so offline runs never need the dep loaded

            with httpx.Client(timeout=self._timeout) as owned:
                response = owned.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize(data: dict) -> dict[str, object]:
        choices = data.get("choices") or []
        content = ""
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content", "") or ""
        usage = data.get("usage") or {}
        return {
            "content": content,
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": int(
                    usage.get("total_tokens", 0)
                    or usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                ),
            },
        }


class MissingApiKeyError(RuntimeError):
    """Raised when no OpenRouter key can be resolved (NFR-SC-001/002)."""


class OpenRouterProvider:
    """Submits prompts to OpenRouter with policy-approved model routing."""

    def __init__(
        self,
        secret_adapter: SecretAdapter | None = None,
        transport: CompletionTransport | None = None,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        self._secrets = secret_adapter or SecretAdapter()
        self._transport = transport or OfflineTransport()
        self._base_url = base_url

    def complete(self, req: CompletionRequest) -> CompletionResponse:
        """Submit a completion, requiring a resolvable API key."""
        api_key = self._secrets.get_openrouter_key()
        if not api_key:
            raise MissingApiKeyError(
                "OpenRouter API key unavailable (set it in Secret Storage or "
                "OPENROUTER_API_KEY)"
            )
        raw = self._transport.complete(req, api_key)
        usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
        return CompletionResponse(
            model=req.model,
            content=str(raw.get("content", "")) if isinstance(raw, dict) else "",
            usage={k: int(v) for k, v in usage.items()} if isinstance(usage, dict) else {},
        )


__all__ = [
    "OpenRouterProvider",
    "CompletionRequest",
    "CompletionResponse",
    "CompletionTransport",
    "OfflineTransport",
    "HttpxTransport",
    "MissingApiKeyError",
    "OPENROUTER_BASE_URL",
]
