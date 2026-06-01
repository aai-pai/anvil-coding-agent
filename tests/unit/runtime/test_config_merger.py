"""Unit tests for config loading, merge semantics, and validation.

Slice 3 (spec §2.7.2; FR-CF-001/002/003/004/006).
"""

from __future__ import annotations

import pathlib

import pytest

from anvil_runtime.config.loader import ConfigLoader, ConfigSources
from anvil_runtime.config.merger import ConfigMerger, deep_merge
from anvil_runtime.config.validator import ConfigValidationError, ConfigValidator


def test_scalar_override_highest_wins() -> None:
    merged = deep_merge([{"mode": "yolo"}, {"mode": "gated"}, {"mode": "secure"}])
    assert merged["mode"] == "secure"


def test_list_union_lowest_first_per_spec_example() -> None:
    merged = deep_merge([
        {"allowedModels": ["claude-3-haiku"]},   # builtin
        {"allowedModels": ["deepseek-coder"]},   # user-root
        {"allowedModels": ["gpt-4o"]},           # workspace
        {"allowedModels": ["claude-opus"]},      # run-time
    ])
    assert merged["allowedModels"] == [
        "claude-3-haiku", "deepseek-coder", "gpt-4o", "claude-opus",
    ]


def test_list_union_dedupes() -> None:
    merged = deep_merge([{"x": ["a", "b"]}, {"x": ["b", "c"]}])
    assert merged["x"] == ["a", "b", "c"]


def test_deep_map_merge_retains_lower_keys() -> None:
    merged = deep_merge([
        {"tokenBudgetPerPhase": {"proposal": 10000, "specification": 15000}},
        {"tokenBudgetPerPhase": {"specification": 99999, "architecture": 20000}},
    ])
    assert merged["tokenBudgetPerPhase"] == {
        "proposal": 10000, "specification": 99999, "architecture": 20000,
    }


def test_merge_to_effective_config() -> None:
    sources = ConfigSources(
        builtin={"configVersion": "0.1.0", "mode": "gated", "securityProfile": "restricted"},
        run_flags={"mode": "secure"},
    )
    cfg = ConfigMerger().merge(sources)
    assert cfg.mode == "secure"
    assert cfg.securityProfile == "restricted"


def test_loader_reads_workspace_yaml(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".anvil"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("mode: secure\nallowedModels:\n  - gpt-4o\n", encoding="utf-8")
    # Point user_home at an empty dir so only workspace + builtin load.
    loader = ConfigLoader(workspace_root=tmp_path, user_home=tmp_path / "empty_home")
    sources = loader.load_sources({"securityProfile": "strict"})
    cfg = ConfigMerger().merge(sources)
    assert cfg.mode == "secure"
    assert cfg.securityProfile == "strict"  # run-flag overrides builtin
    assert "gpt-4o" in cfg.allowedModels


def test_loader_rejects_malformed_yaml(tmp_path: pathlib.Path) -> None:
    cfg_dir = tmp_path / ".anvil"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("mode: : : bad", encoding="utf-8")
    loader = ConfigLoader(workspace_root=tmp_path, user_home=tmp_path / "empty_home")
    with pytest.raises(ValueError):
        loader.load_sources()


def test_validator_rejects_unsupported_version() -> None:
    with pytest.raises(ConfigValidationError):
        ConfigValidator().validate({"configVersion": "9.9.9"})


def test_validator_accepts_default_config() -> None:
    from anvil_runtime.config.schema import EffectiveConfig

    validated = ConfigValidator().validate(EffectiveConfig())
    assert validated.configVersion == "0.1.0"


def test_validator_rejects_contradictory_settings() -> None:
    from anvil_runtime.config.schema import EffectiveConfig

    with pytest.raises(ConfigValidationError):
        ConfigValidator().validate(EffectiveConfig(maxRetriesPerPhase=-1))
    with pytest.raises(ConfigValidationError):
        ConfigValidator().validate(
            EffectiveConfig(tokenBudgetPerPhase={"proposal": -5})
        )
