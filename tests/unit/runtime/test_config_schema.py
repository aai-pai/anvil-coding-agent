"""Unit tests for configuration constants and the EffectiveConfig contract.

Slice 1 (blueprint §6.2, §4.1).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from anvil_runtime.config import schema


def test_default_constants_match_blueprint() -> None:
    assert schema.DEFAULT_MODE == "gated"
    assert schema.DEFAULT_SECURITY_PROFILE == "restricted"
    assert schema.DEFAULT_MAX_RETRIES_PER_PHASE == 2
    assert schema.DEFAULT_MCP_DISCOVERY_TIMEOUT_SECONDS == 5
    assert schema.DEFAULT_ARTIFACT_VALIDATION_TIMEOUT_SECONDS == 30
    assert schema.DEFAULT_DRIFT_CHECK_TIMEOUT_SECONDS == 60
    assert schema.RUNTIME_API_VERSION_PREFIX == "/v1"
    assert schema.EVENTS_LOG_PATH == "logs/events.jsonl"
    assert schema.CHECKPOINT_PATH == ".anvil/run-state.json"


def test_mandatory_secure_gates_are_the_four_immutable_gates() -> None:
    assert schema.MANDATORY_SECURE_GATES == [
        "post-proposal",
        "post-architecture",
        "post-blueprint",
        "pre-deployment",
    ]


def test_value_sets() -> None:
    assert schema.OPERATING_MODES == ("yolo", "gated", "secure")
    assert schema.SECURITY_PROFILES == ("open", "restricted", "strict")


def test_effective_config_defaults() -> None:
    cfg = schema.EffectiveConfig()
    assert cfg.configVersion == schema.CONFIG_VERSION
    assert cfg.mode == schema.DEFAULT_MODE
    assert cfg.securityProfile == schema.DEFAULT_SECURITY_PROFILE
    assert cfg.maxRetriesPerPhase == schema.DEFAULT_MAX_RETRIES_PER_PHASE
    assert cfg.allowedModels == []
    assert cfg.tokenBudgetPerPhase == {}
    assert cfg.mcpServers == []


def test_effective_config_rejects_bad_mode() -> None:
    with pytest.raises(ValidationError):
        schema.EffectiveConfig(mode="hyper")


def test_effective_config_rejects_bad_profile() -> None:
    with pytest.raises(ValidationError):
        schema.EffectiveConfig(securityProfile="loose")


def test_effective_config_accepts_overrides() -> None:
    cfg = schema.EffectiveConfig(
        mode="secure",
        securityProfile="strict",
        allowedModels=["deepseek-coder"],
        tokenBudgetPerPhase={"implementation": 25000},
    )
    assert cfg.mode == "secure"
    assert cfg.tokenBudgetPerPhase["implementation"] == 25000
