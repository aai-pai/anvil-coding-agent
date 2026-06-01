"""Unit tests: runtime secret resolution with env fallback.

Slice 4 (blueprint §2.2; spec NFR-SC-001/002/003). The OpenRouter key resolves
from an injected (Secret-Storage-forwarded) value first, then the
``OPENROUTER_API_KEY`` environment variable, and is never embedded in ``repr``.
"""

from __future__ import annotations

from anvil_runtime.security.secret_adapter import (
    OPENROUTER_API_KEY_ENV,
    SecretAdapter,
)


def test_provided_key_takes_precedence_over_env() -> None:
    adapter = SecretAdapter(
        environ={OPENROUTER_API_KEY_ENV: "from-env"}, provided_key="from-storage"
    )
    assert adapter.get_openrouter_key() == "from-storage"
    assert adapter.has_openrouter_key() is True


def test_env_fallback_when_no_provided_key() -> None:
    adapter = SecretAdapter(environ={OPENROUTER_API_KEY_ENV: "from-env"})
    assert adapter.get_openrouter_key() == "from-env"


def test_missing_key_resolves_to_none() -> None:
    adapter = SecretAdapter(environ={})
    assert adapter.get_openrouter_key() is None
    assert adapter.has_openrouter_key() is False


def test_repr_never_leaks_the_secret() -> None:
    adapter = SecretAdapter(environ={}, provided_key="super-secret-value")
    assert "super-secret-value" not in repr(adapter)
    assert "has_key=True" in repr(adapter)
