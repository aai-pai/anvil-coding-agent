"""Anvil runtime FastAPI application factory.

Slice 4 deliverable (blueprint §2.1, §2.2, §5.1). Assembles the ``/v1`` REST +
SSE surface over a single in-process :class:`DevelopmentManager`. The supervisor
and the API share one :class:`EventBus` instance so the SSE route streams exactly
the events the supervisor emitted.

Run in production with::

    uvicorn anvil_runtime.app:app --host 127.0.0.1 --port 8765

The host/port mirror ``extension/src/config/modeSelector.ts`` (``API_BASE_URL``).
"""

from __future__ import annotations

from fastapi import FastAPI

from anvil_runtime.api import (
    routes_artifacts,
    routes_events,
    routes_health,
    routes_runs,
)
from anvil_runtime.config.schema import EffectiveConfig
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.security.secret_adapter import SecretAdapter
from anvil_runtime.state.event_bus import EventBus

API_TITLE = "Anvil Runtime"
API_VERSION = "0.1.0"


def create_app(
    workspace_root: str = ".",
    config: EffectiveConfig | None = None,
    manager: DevelopmentManager | None = None,
    event_bus: EventBus | None = None,
    secret_adapter: SecretAdapter | None = None,
) -> FastAPI:
    """Build the runtime app, wiring shared singletons onto ``app.state``.

    The supervisor and SSE route share one :class:`EventBus`. When a custom
    ``manager`` is supplied, pass its event bus as ``event_bus`` so the stream
    and the supervisor stay consistent.
    """
    app = FastAPI(title=API_TITLE, version=API_VERSION)

    bus = event_bus or EventBus(workspace_root)
    mgr = manager or DevelopmentManager(
        workspace_root=workspace_root, config=config, event_bus=bus
    )

    app.state.workspace_root = workspace_root
    app.state.event_bus = bus
    app.state.manager = mgr
    app.state.secret_adapter = secret_adapter or SecretAdapter()

    app.include_router(routes_runs.router)
    app.include_router(routes_events.router)
    app.include_router(routes_artifacts.router)
    app.include_router(routes_health.router)
    return app


# Module-level ASGI app for `uvicorn anvil_runtime.app:app` (workspace = CWD).
app = create_app()


__all__ = ["create_app", "app", "API_TITLE", "API_VERSION"]
