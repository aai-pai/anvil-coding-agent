"""E2E: restricted-profile flow ties config -> projection -> policy -> hooks.

Slice 3 (proposal §8.5; spec §2.6, §2.7, §4.2.2). Resolves config from files,
writes the runtime projection, then enforces policy and hooks against the
restricted profile, asserting the full audit trail.
"""

from __future__ import annotations

import json
import pathlib

from anvil_runtime.config.loader import ConfigLoader
from anvil_runtime.config.merger import ConfigMerger
from anvil_runtime.config.projection import POLICY_SNAPSHOT_RELPATH, RuntimeProjectionWriter
from anvil_runtime.config.validator import ConfigValidator
from anvil_runtime.hooks.adapter import HookAdapter
from anvil_runtime.hooks.lifecycle_hooks import HookRule
from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.models import PolicyDocument, PolicyRule
from anvil_runtime.policy.rule_evaluator import PolicyActionContext
from anvil_runtime.state.event_bus import EventBus


def test_restricted_profile_end_to_end(tmp_path: pathlib.Path) -> None:
    # 1) Author a workspace config selecting the restricted profile.
    cfg_dir = tmp_path / ".anvil"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "mode: secure\n"
        "securityProfile: restricted\n"
        "allowedModels:\n  - deepseek-coder\n",
        encoding="utf-8",
    )

    # 2) Resolve effective config through the precedence + validation chain.
    loader = ConfigLoader(workspace_root=tmp_path, user_home=tmp_path / "no_home")
    cfg = ConfigValidator().validate(ConfigMerger().merge(loader.load_sources()))
    assert cfg.securityProfile == "restricted"
    assert "deepseek-coder" in cfg.allowedModels

    # 3) Write the runtime projection and confirm the policy snapshot.
    RuntimeProjectionWriter(tmp_path).write_projection(cfg, hook_rules=[
        HookRule(kind="BeforeToolInvocation", tool="net-*", effect="deny", reason="restricted: no network"),
    ])
    snapshot = json.loads((tmp_path / POLICY_SNAPSHOT_RELPATH).read_text(encoding="utf-8"))
    assert snapshot["securityProfile"] == "restricted"

    # 4) Enforce policy + hooks against the restricted profile over one bus.
    bus = EventBus(tmp_path)
    engine = PolicyEngine(
        PolicyDocument(policies=[
            PolicyRule(
                name="AllowedModels", type="whitelist", target="model-selection",
                values=cfg.allowedModels, remediable=True,
                remediationStrategy="switch-to-allowed-model",
            ),
        ]),
        event_bus=bus, run_id="run-1",
    )
    decision, outcome = engine.enforce(
        PolicyActionContext(action="model-selection", model="gpt-4o", phase="implementation")
    )
    assert decision.allowed is False
    assert outcome is not None and outcome.replacement == "deepseek-coder"

    adapter = HookAdapter(
        rules=[HookRule(kind="BeforeToolInvocation", tool="net-*", effect="deny")],
        event_bus=bus, run_id="run-1",
    )
    assert adapter.before_tool_invocation("net-fetch", {"url": "x"}).action == "deny"

    # 5) The audit trail captured both enforcement layers.
    event_types = {e.eventType for e in bus.read_all()}
    assert {"PolicyViolation", "PolicyRemediation", "ToolInvocationBlocked"} <= event_types
