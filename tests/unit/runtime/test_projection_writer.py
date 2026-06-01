"""Unit tests for the runtime projection writer. Slice 3 (spec §8.5; blueprint §6.1)."""

from __future__ import annotations

import json
import pathlib

from anvil_runtime.config.projection import (
    MCP_PROJECTION_RELPATH,
    POLICY_SNAPSHOT_RELPATH,
    RuntimeProjectionWriter,
)
from anvil_runtime.config.schema import EffectiveConfig
from anvil_runtime.hooks.lifecycle_hooks import HookRule


def test_write_projection_creates_expected_files(tmp_path: pathlib.Path) -> None:
    cfg = EffectiveConfig(
        mode="secure",
        securityProfile="restricted",
        allowedModels=["deepseek-coder"],
        tokenBudgetPerPhase={"implementation": 25000},
        mcpServers=[{"name": "filesystem"}],
    )
    writer = RuntimeProjectionWriter(tmp_path)
    manifest = writer.write_projection(cfg, hook_rules=[
        HookRule(kind="BeforeToolInvocation", tool="shell", effect="deny"),
    ])

    assert (tmp_path / MCP_PROJECTION_RELPATH).exists()
    assert (tmp_path / POLICY_SNAPSHOT_RELPATH).exists()
    assert (tmp_path / ".openhands" / "hooks.json").exists()
    assert (tmp_path / "logs").is_dir()

    # Manifest records every written file with a checksum.
    assert MCP_PROJECTION_RELPATH in manifest.written_files
    assert all(f in manifest.checksums for f in manifest.written_files)


def test_policy_snapshot_content(tmp_path: pathlib.Path) -> None:
    cfg = EffectiveConfig(securityProfile="strict", allowedModels=["gemma-4"])
    RuntimeProjectionWriter(tmp_path).write_projection(cfg)
    snapshot = json.loads((tmp_path / POLICY_SNAPSHOT_RELPATH).read_text(encoding="utf-8"))
    assert snapshot["securityProfile"] == "strict"
    assert snapshot["allowedModels"] == ["gemma-4"]


def test_hooks_projection_content(tmp_path: pathlib.Path) -> None:
    cfg = EffectiveConfig()
    RuntimeProjectionWriter(tmp_path).write_projection(cfg, hook_rules=[
        HookRule(kind="BeforeToolInvocation", tool="net-*", effect="deny", reason="restricted"),
    ])
    hooks = json.loads((tmp_path / ".openhands" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"][0]["tool"] == "net-*"
    assert hooks["hooks"][0]["effect"] == "deny"


def test_projection_is_reproducible(tmp_path: pathlib.Path) -> None:
    cfg = EffectiveConfig(allowedModels=["a", "b"])
    writer = RuntimeProjectionWriter(tmp_path)
    first = writer.write_projection(cfg)
    second = writer.write_projection(cfg)
    assert first.checksums == second.checksums
