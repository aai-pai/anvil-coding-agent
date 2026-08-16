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
from anvil_runtime.security.redaction import Redactor
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
VALID_EXECUTION_MODES = ("stub", "offline-llm", "real")


def _load_effective_config(workspace_root: str) -> EffectiveConfig:
    """Resolve the four-level config precedence for a workspace (FR-CF-001..007).

    builtin defaults < ~/.anvil/config.yaml < <workspace>/.anvil/config.yaml.
    Raises loudly on malformed or inconsistent configuration.
    """
    from anvil_runtime.config.loader import ConfigLoader
    from anvil_runtime.config.merger import ConfigMerger
    from anvil_runtime.config.validator import ConfigValidator

    sources = ConfigLoader(workspace_root).load_sources()
    return ConfigValidator().validate(ConfigMerger().merge(sources))


def _build_real_manager(
    workspace_root: str,
    config: EffectiveConfig | None,
    bus: EventBus,
    secret_adapter: SecretAdapter,
    execution_mode: str,
    instructions: str | None = None,
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
    from anvil_runtime.policy.engine import PolicyEngine
    from anvil_runtime.policy.models import PolicyDocument, PolicyRule
    from anvil_runtime.sdk.openhands_adapter import LLMBackend, OpenHandsAdapter
    from anvil_runtime.sdk.session_bridge import SessionBridge

    cfg = config or _load_effective_config(workspace_root)
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
    # #18 (FR-CTX-001): env override > config field > default.
    input_char_limit = int(os.environ.get("ANVIL_INPUT_CHAR_LIMIT") or cfg.inputCharLimit)
    # v0.1.3 #19: same precedence for the output-side completion budgets.
    intake_max_tokens = int(
        os.environ.get("ANVIL_INTAKE_MAX_TOKENS") or cfg.intakeMaxTokens)
    doc_max_tokens = int(os.environ.get("ANVIL_DOC_MAX_TOKENS") or cfg.docMaxTokens)
    code_max_tokens = int(os.environ.get("ANVIL_CODE_MAX_TOKENS") or cfg.codeMaxTokens)
    # v0.1.3 #20: the task-contract cap follows the same precedence.
    contract_max_chars = int(
        os.environ.get("ANVIL_CONTRACT_MAX_CHARS") or cfg.contractMaxChars)
    # Pinned sampling temperature; "0" is a meaningful value, so test for
    # presence rather than truthiness. None -> provider default (historical).
    temperature_env = os.environ.get("ANVIL_TEMPERATURE")
    temperature = float(temperature_env) if temperature_env not in (None, "") \
        else cfg.temperature
    # v0.1.4 #23 (FR-RL-001): the repair loop's knobs, same precedence.
    external_test_command = (
        os.environ.get("ANVIL_TEST_COMMAND") or cfg.externalTestCommand)
    repair_max_rounds = int(
        os.environ.get("ANVIL_REPAIR_MAX_ROUNDS") or cfg.repairMaxRounds)
    test_timeout_s = int(
        os.environ.get("ANVIL_TEST_TIMEOUT_S") or cfg.testTimeoutS)
    # v0.1.4 #25 (FR-DX-001): where the command runs (host subprocess vs
    # hardened container), same precedence.
    test_executor = os.environ.get("ANVIL_TEST_EXECUTOR") or cfg.testExecutor
    test_image = os.environ.get("ANVIL_TEST_IMAGE") or cfg.testImage
    test_setup_command = (
        os.environ.get("ANVIL_TEST_SETUP_COMMAND") or cfg.testSetupCommand)
    # v0.1.4 #27 (FR-IC-004) / v0.1.5 #29 (FR-DS-004): repair-context gate.
    repair_context = os.environ.get("ANVIL_REPAIR_CONTEXT") or cfg.repairContext
    # v0.1.5 #28 (FR-FL-007): fault-localization gate, same precedence.
    repair_localization = (
        os.environ.get("ANVIL_REPAIR_LOCALIZATION") or cfg.repairLocalization)
    backend = LLMBackend(
        provider, workspace_root, input_char_limit=input_char_limit, event_bus=bus,
        instructions=instructions,
        intake_max_tokens=intake_max_tokens,
        doc_max_tokens=doc_max_tokens,
        code_max_tokens=code_max_tokens,
        contract_max_chars=contract_max_chars,
        temperature=temperature,
        external_test_command=external_test_command,
        repair_max_rounds=repair_max_rounds,
        test_timeout_s=test_timeout_s,
        test_executor=test_executor,
        test_image=test_image,
        test_setup_command=test_setup_command,
        repair_context=repair_context,
        repair_localization=repair_localization,
    )
    # FR-ML-004: a configured allowedModels list becomes an enforced whitelist
    # (with switch-to-allowed remediation); an empty list means unrestricted.
    policy_engine = None
    if cfg.allowedModels:
        policy_engine = PolicyEngine(
            PolicyDocument(policies=[PolicyRule(
                name="AllowedModels", type="whitelist", target="model-selection",
                values=list(cfg.allowedModels), remediable=True,
                remediationStrategy="switch-to-allowed-model",
            )]),
            event_bus=bus,
        )
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=backend),
        model_router=ModelRouter(
            subtask_models=overrides or None,
            policy_engine=policy_engine,
            event_bus=bus,
        ),
        usage_tracker=UsageTracker(budgets=cfg.tokenBudgetPerPhase, event_bus=bus),
        security_profile=cfg.securityProfile,
        workspace_root=workspace_root,
    )
    import time

    return DevelopmentManager(
        workspace_root=workspace_root,
        config=cfg,
        event_bus=bus,
        executor=BridgeExecutor(bridge),
        artifact_validator=ArtifactValidator(workspace_root, event_bus=bus),
        # Real retries must wait out the backoff (rate limits); offline-llm has
        # no provider to protect, and sleeping would only slow tests.
        retry_sleeper=time.sleep if execution_mode == "real" else None,
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
    instructions: str | None = None,
) -> tuple[DevelopmentManager, EventBus]:
    """Build a manager + its event bus rooted at ``workspace_root`` for a mode."""
    # NFR-OB-004: every production bus redacts before events reach disk or SSE.
    bus = EventBus(workspace_root, redactor=Redactor())
    if execution_mode == "stub":
        manager = DevelopmentManager(workspace_root=workspace_root, config=config, event_bus=bus)
    else:
        manager = _build_real_manager(
            workspace_root, config, bus, secret_adapter, execution_mode, instructions
        )
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

    bus = event_bus or EventBus(workspace_root, redactor=Redactor())
    secrets = secret_adapter or SecretAdapter()
    mode = (execution_mode or os.environ.get(EXECUTION_MODE_ENV) or DEFAULT_EXECUTION_MODE)
    if mode not in VALID_EXECUTION_MODES:
        # A typo ("Real", "offline") must fail loudly, not silently degrade to
        # a stub that reports placeholder artifacts as success.
        raise ValueError(
            f"Unknown execution mode '{mode}' "
            f"(expected one of: {', '.join(VALID_EXECUTION_MODES)})"
        )
    # FR-CF-001..007: resolve the file-based config levels unless the caller
    # supplied an explicit EffectiveConfig.
    config = config or _load_effective_config(workspace_root)

    if manager is not None:
        mgr = manager
    elif mode == "stub":
        mgr = DevelopmentManager(workspace_root=workspace_root, config=config, event_bus=bus)
    else:
        # Default manager runs at the server root: run-level == base-level here.
        from anvil_runtime.instructions import resolve_instructions

        resolved = resolve_instructions(workspace_root, workspace_root)
        mgr = _build_real_manager(workspace_root, config, bus, secrets, mode, resolved.text)

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
