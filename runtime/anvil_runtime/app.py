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

import os

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

# Execution modes (post-v0.1.0 integration), selected via ANVIL_EXECUTION_MODE.
#   "stub"        - deterministic stub agents, no artifact writing (v0.1.0 default).
#   "offline-llm" - real execution pipeline + validation, but offline LLM transport
#                   (writes placeholder artifacts; proves plumbing, needs no key).
#   "real"        - real OpenRouter LLM execution (requires OPENROUTER_API_KEY).
EXECUTION_MODE_ENV = "ANVIL_EXECUTION_MODE"
DEFAULT_EXECUTION_MODE = "stub"


def _build_real_manager(
    workspace_root: str,
    config: EffectiveConfig | None,
    bus: EventBus,
    secret_adapter: SecretAdapter,
    execution_mode: str,
) -> DevelopmentManager:
    """Assemble an LLM-backed supervisor (offline or real OpenRouter transport)."""
    from anvil_runtime.agents.phase_invocation import BridgeExecutor
    from anvil_runtime.artifacts.validator import ArtifactValidator
    from anvil_runtime.llm.model_router import ModelRouter, SUBTASK_CATEGORIES
    from anvil_runtime.llm.openrouter_provider import (
        HttpxTransport,
        OfflineTransport,
        OpenRouterProvider,
    )
    from anvil_runtime.llm.usage_tracker import UsageTracker
    from anvil_runtime.sdk.openhands_adapter import LLMBackend, OpenHandsAdapter
    from anvil_runtime.sdk.session_bridge import SessionBridge

    cfg = config or EffectiveConfig()
    if execution_mode == "real":
        transport = HttpxTransport()
        secrets = secret_adapter  # resolves the real OPENROUTER_API_KEY
    else:
        transport = OfflineTransport()
        # Offline transport ignores the key; supply a placeholder so the provider's
        # key check passes without requiring a real credential.
        secrets = SecretAdapter(provided_key="offline")
    provider = OpenRouterProvider(secret_adapter=secrets, transport=transport)
    # Phase-aware routing defaults live in ModelRouter (google/gemma-4-31b-it for
    # planning/design, deepseek/deepseek-v4-flash for coding). Build subtask
    # overrides ONLY from explicitly-set env vars so those defaults stay
    # authoritative (spec FR-RT-002); a more specific var wins over a global one.
    overrides: dict[str, str] = {}
    global_model = os.environ.get("ANVIL_MODEL")
    if global_model:
        overrides = {category: global_model for category in SUBTASK_CATEGORIES}
    planning_model = os.environ.get("ANVIL_PLANNING_MODEL")
    if planning_model:
        overrides.update(planning=planning_model, analysis=planning_model, review=planning_model)
    coding_model = os.environ.get("ANVIL_CODING_MODEL")
    if coding_model:
        overrides.update(coding=coding_model, debugging=coding_model)
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=LLMBackend(provider, workspace_root)),
        model_router=ModelRouter(subtask_models=overrides or None, event_bus=bus),
        usage_tracker=UsageTracker(budgets=cfg.tokenBudgetPerPhase, event_bus=bus),
        security_profile=cfg.securityProfile,
        workspace_root=workspace_root,
    )
    return DevelopmentManager(
        workspace_root=workspace_root,
        config=cfg,
        event_bus=bus,
        executor=BridgeExecutor(bridge),
        artifact_validator=ArtifactValidator(workspace_root, event_bus=bus),
    )


class RunHandle:
    """A run's manager + event bus + workspace (per-run, possibly client-chosen)."""

    def __init__(self, manager: DevelopmentManager, event_bus: EventBus, workspace_root: str) -> None:
        self.manager = manager
        self.event_bus = event_bus
        self.workspace_root = workspace_root


def build_manager(
    workspace_root: str,
    execution_mode: str,
    config: EffectiveConfig | None,
    secret_adapter: SecretAdapter,
) -> tuple[DevelopmentManager, EventBus]:
    """Build a manager + its event bus rooted at ``workspace_root`` for a mode."""
    bus = EventBus(workspace_root)
    if execution_mode == "stub":
        manager = DevelopmentManager(workspace_root=workspace_root, config=config, event_bus=bus)
    else:
        manager = _build_real_manager(workspace_root, config, bus, secret_adapter, execution_mode)
    return manager, bus


def create_app(
    workspace_root: str = ".",
    config: EffectiveConfig | None = None,
    manager: DevelopmentManager | None = None,
    event_bus: EventBus | None = None,
    secret_adapter: SecretAdapter | None = None,
    execution_mode: str | None = None,
) -> FastAPI:
    """Build the runtime app, wiring shared singletons onto ``app.state``.

    The supervisor and SSE route share one :class:`EventBus`. ``execution_mode``
    (or the ``ANVIL_EXECUTION_MODE`` env var) selects stub / offline-llm / real
    execution. When a custom ``manager`` is supplied it is used as-is.
    """
    app = FastAPI(title=API_TITLE, version=API_VERSION)

    bus = event_bus or EventBus(workspace_root)
    secrets = secret_adapter or SecretAdapter()
    mode = (execution_mode or os.environ.get(EXECUTION_MODE_ENV) or DEFAULT_EXECUTION_MODE)

    if manager is not None:
        mgr = manager
    elif mode == "stub":
        mgr = DevelopmentManager(workspace_root=workspace_root, config=config, event_bus=bus)
    else:
        mgr = _build_real_manager(workspace_root, config, bus, secrets, mode)

    app.state.workspace_root = workspace_root
    app.state.event_bus = bus
    app.state.manager = mgr
    app.state.secret_adapter = secrets
    app.state.execution_mode = mode
    app.state.config = config
    # Default handle + per-run registry (per-run client-chosen workspaces).
    app.state.default_handle = RunHandle(mgr, bus, workspace_root)
    app.state.runs = {}

    app.include_router(routes_runs.router)
    app.include_router(routes_events.router)
    app.include_router(routes_artifacts.router)
    app.include_router(routes_health.router)
    return app


# Module-level ASGI app for `uvicorn anvil_runtime.app:app` (workspace = CWD).
# Honors ANVIL_EXECUTION_MODE; defaults to the safe stub pipeline.
app = create_app()


__all__ = ["create_app", "app", "API_TITLE", "API_VERSION", "EXECUTION_MODE_ENV"]
