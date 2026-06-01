"""FastAPI dependency providers for the Anvil runtime API.

Slice 4 deliverable (blueprint §2.2, §5.1). The route modules depend on the
shared per-process singletons stashed on ``app.state`` by
:func:`anvil_runtime.app.create_app`: the supervisor (:class:`DevelopmentManager`),
the workspace root, the shared :class:`EventBus`, and the :class:`SecretAdapter`.

Keeping these as thin accessors lets tests build an app over a temporary
workspace and lets every route share one in-memory supervisor instance.
"""

from __future__ import annotations

from fastapi import Request

from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.security.secret_adapter import SecretAdapter
from anvil_runtime.state.event_bus import EventBus


def get_manager(request: Request) -> DevelopmentManager:
    """Return the shared supervisor for the running app."""
    return request.app.state.manager


def get_workspace_root(request: Request) -> str:
    """Return the workspace root the runtime reads/writes artifacts under."""
    return request.app.state.workspace_root


def get_event_bus(request: Request) -> EventBus:
    """Return the shared event bus (same instance the supervisor emits to)."""
    return request.app.state.event_bus


def get_secret_adapter(request: Request) -> SecretAdapter:
    """Return the secret resolver (OpenRouter key, env fallback)."""
    return request.app.state.secret_adapter


__all__ = [
    "get_manager",
    "get_workspace_root",
    "get_event_bus",
    "get_secret_adapter",
]
