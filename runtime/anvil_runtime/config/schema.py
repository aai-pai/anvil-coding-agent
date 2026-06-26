"""Configuration schema and constants for the Anvil runtime.

This module is the Slice 1 source of truth for runtime defaults, well-known
paths, the mandatory secure-mode gates, and the :class:`EffectiveConfig`
contract. Values and names are taken verbatim from ``docs/blueprint.md`` §6.2
and §4.1 to avoid drift; later slices (config loader/merger/projection in
Slice 3) consume these without redefining them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Key constants (blueprint §6.2)
# ---------------------------------------------------------------------------

DEFAULT_MODE = "gated"
DEFAULT_SECURITY_PROFILE = "restricted"
DEFAULT_MAX_RETRIES_PER_PHASE = 2
DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS = 5
DEFAULT_ARTIFACT_VALIDATION_TIMEOUT_SECONDS = 30
DEFAULT_DRIFT_CHECK_TIMEOUT_SECONDS = 60
RUNTIME_API_VERSION_PREFIX = "/v1"
EVENTS_LOG_PATH = "logs/events.jsonl"
RUN_SUMMARY_LOG_PATH = "logs/run-summary.log"
CHECKPOINT_PATH = ".anvil/run-state.json"
MANDATORY_SECURE_GATES = [
    "post-proposal",
    "post-architecture",
    "post-blueprint",
    "pre-deployment",
]

# Closed value sets shared across the runtime. Kept as tuples so they are
# immutable and reusable for both validation and Literal documentation.
OPERATING_MODES: tuple[str, ...] = ("yolo", "gated", "secure")
SECURITY_PROFILES: tuple[str, ...] = ("open", "restricted", "strict")

CONFIG_VERSION = "0.1.0"

ModeLiteral = Literal["yolo", "gated", "secure"]
SecurityProfileLiteral = Literal["open", "restricted", "strict"]


# ---------------------------------------------------------------------------
# Effective configuration model (blueprint §4.1)
# ---------------------------------------------------------------------------


class EffectiveConfig(BaseModel):
    """Resolved configuration for a single run.

    Produced by the configuration resolver (Slice 3) after applying the
    four-level precedence merge (run flags > workspace > user root > built-in).
    Slice 1 only defines the contract so downstream modules can type against it.
    """

    configVersion: str = CONFIG_VERSION
    mode: ModeLiteral = DEFAULT_MODE
    allowedModels: list[str] = Field(default_factory=list)
    tokenBudgetPerPhase: dict[str, int] = Field(default_factory=dict)
    maxRetriesPerPhase: int = DEFAULT_MAX_RETRIES_PER_PHASE
    requiredApprovalGates: list[str] = Field(default_factory=list)
    mcpServers: list[dict[str, object]] = Field(default_factory=list)
    securityProfile: SecurityProfileLiteral = DEFAULT_SECURITY_PROFILE
    # #11 (FR-CX-006): optional complexity-tier override; when set it wins over the
    # proposal phase's assessed tier. None defers to the proposal's assessment.
    complexityTier: str | None = None


__all__ = [
    "DEFAULT_MODE",
    "DEFAULT_SECURITY_PROFILE",
    "DEFAULT_MAX_RETRIES_PER_PHASE",
    "DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS",
    "DEFAULT_ARTIFACT_VALIDATION_TIMEOUT_SECONDS",
    "DEFAULT_DRIFT_CHECK_TIMEOUT_SECONDS",
    "RUNTIME_API_VERSION_PREFIX",
    "EVENTS_LOG_PATH",
    "RUN_SUMMARY_LOG_PATH",
    "CHECKPOINT_PATH",
    "MANDATORY_SECURE_GATES",
    "OPERATING_MODES",
    "SECURITY_PROFILES",
    "CONFIG_VERSION",
    "ModeLiteral",
    "SecurityProfileLiteral",
    "EffectiveConfig",
]
