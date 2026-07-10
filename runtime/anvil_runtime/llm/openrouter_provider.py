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
    # Provider-reported stop cause; "length" means the output was truncated at
    # max_tokens and callers must not treat the content as complete.
    finish_reason: str | None = None


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

    # Status codes worth retrying (rate limit / transient upstream errors).
    _RETRYABLE = frozenset({429, 502, 503, 504})

    def __init__(
        self,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = 90.0,
        client: object | None = None,
        max_retries: int = 4,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client  # an httpx.Client-like object; lazily created if None
        self._max_retries = max_retries

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
        import time

        import httpx  # a declared dependency; lazy to match _send

        last_response = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._send(url, payload, headers)
            except httpx.TransportError:
                # Timeouts/connection blips are the most common transient
                # failures — retry them like retryable statuses.
                if attempt < self._max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise
            status = getattr(response, "status_code", 200)
            if status in self._RETRYABLE and attempt < self._max_retries:
                last_response = response
                time.sleep(min(2 ** attempt, 8))  # 1s, 2s, 4s, 8s backoff
                continue
            response.raise_for_status()
            return response.json()
        # Exhausted retries on a retryable status: surface the last error.
        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("OpenRouter request failed")

    def _send(self, url: str, payload: dict, headers: dict):
        if self._client is not None:
            return self._client.post(url, json=payload, headers=headers)
        import httpx  # imported lazily so offline runs never need the dep loaded

        with httpx.Client(timeout=self._timeout) as owned:
            return owned.post(url, json=payload, headers=headers)

    @staticmethod
    def _normalize(data: dict) -> dict[str, object]:
        # OpenRouter reports upstream failures as an `error` body, sometimes
        # with HTTP 200 — treating those as empty successes masks real errors.
        error = data.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else None
            raise OpenRouterResponseError(
                f"OpenRouter returned an error: {message or error}"
            )
        choices = data.get("choices") or []
        content = ""
        finish_reason = None
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content", "") or ""
            finish_reason = choices[0].get("finish_reason")
        usage = data.get("usage") or {}
        return {
            "content": content,
            "finish_reason": finish_reason,
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


class OpenRouterResponseError(RuntimeError):
    """Raised when OpenRouter returns an error payload instead of a completion."""


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
        finish = raw.get("finish_reason") if isinstance(raw, dict) else None
        return CompletionResponse(
            model=req.model,
            content=str(raw.get("content", "")) if isinstance(raw, dict) else "",
            # Skip non-numeric entries (e.g. OpenRouter's nested
            # prompt_tokens_details) instead of crashing on int().
            usage=(
                {k: int(v) for k, v in usage.items() if isinstance(v, (int, float))}
                if isinstance(usage, dict) else {}
            ),
            finish_reason=str(finish) if finish is not None else None,
        )


__all__ = [
    "OpenRouterProvider",
    "CompletionRequest",
    "CompletionResponse",
    "CompletionTransport",
    "OfflineTransport",
    "HttpxTransport",
    "MissingApiKeyError",
    "OpenRouterResponseError",
    "OPENROUTER_BASE_URL",
]
