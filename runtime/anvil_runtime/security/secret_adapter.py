"""Runtime-side secret resolution with environment fallback.

Slice 4 deliverable (blueprint §2.2 "Secret Storage Adapter"; spec NFR-SC-001,
NFR-SC-002, NFR-SC-003).

The VS Code extension stores the OpenRouter API key in ``vscode.SecretStorage``
and forwards it to the runtime (``extension/src/secrets/secretStore.ts``). When
Secret Storage is unavailable (CI / headless runs), the runtime falls back to the
``OPENROUTER_API_KEY`` environment variable (NFR-SC-002).

The key is never logged, printed, or echoed (NFR-SC-003). This adapter only
returns it to callers that need it for outbound LLM calls (wired in Slice 5).
``__repr__`` is overridden so the secret cannot leak through accidental logging
of the adapter itself.
"""

from __future__ import annotations

import os
from typing import Mapping

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"


class SecretAdapter:
    """Resolves the OpenRouter API key from an injected value or the environment.

    Resolution precedence (NFR-SC-001/002):

    1. ``provided_key`` — a key forwarded by the extension's Secret Storage.
    2. ``OPENROUTER_API_KEY`` environment variable (headless/CI fallback).
    """

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        provided_key: str | None = None,
    ) -> None:
        # Default to the real process environment; injectable for tests.
        self._environ = environ if environ is not None else os.environ
        self._provided = provided_key or None

    def get_openrouter_key(self) -> str | None:
        """Return the resolved key, or ``None`` if neither source supplies one."""
        if self._provided:
            return self._provided
        value = self._environ.get(OPENROUTER_API_KEY_ENV)
        return value or None

    def has_openrouter_key(self) -> bool:
        """True when a key is resolvable without revealing it (NFR-SC-003)."""
        return self.get_openrouter_key() is not None

    def __repr__(self) -> str:  # pragma: no cover - trivial, secret-safe
        return f"SecretAdapter(has_key={self.has_openrouter_key()})"


__all__ = ["SecretAdapter", "OPENROUTER_API_KEY_ENV"]
