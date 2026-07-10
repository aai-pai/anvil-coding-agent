"""Integration tests: file-based config and policy are wired into the app.

The config loader/merger/validator and the policy engine were individually
tested but historically never constructed by ``create_app`` — these tests pin
the production assembly so the guarantees are real, not aspirational.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from anvil_runtime.app import create_app
from anvil_runtime.sdk.session_bridge import SessionBridge
from anvil_runtime.llm.model_router import ModelRouter
from anvil_runtime.policy.engine import PolicyEngine
from anvil_runtime.policy.models import PolicyDocument, PolicyRule


def _write_workspace_config(root: pathlib.Path, body: str) -> None:
    cfg = root / ".anvil" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding="utf-8")


def test_workspace_config_yaml_is_honored(tmp_path: pathlib.Path) -> None:
    # requiredApprovalGates from .anvil/config.yaml must gate a run.
    _write_workspace_config(tmp_path, "requiredApprovalGates:\n  - specification\n")
    client = TestClient(create_app(workspace_root=str(tmp_path)))
    resp = client.post(
        "/v1/runs", json={"mode": "gated", "security_profile": "restricted"}
    )
    run_id = resp.json()["run_id"]
    state = client.get(f"/v1/runs/{run_id}").json()
    assert state["status"] == "awaiting_approval"
    assert state["pending_approval_gate"] == "post-specification"


def test_malformed_workspace_config_fails_loudly(tmp_path: pathlib.Path) -> None:
    _write_workspace_config(tmp_path, "mode: [unclosed\n")
    with pytest.raises(ValueError, match="config.yaml"):
        create_app(workspace_root=str(tmp_path))


def test_unknown_execution_mode_raises(tmp_path: pathlib.Path) -> None:
    # A typo must never silently degrade real execution to the offline stub.
    with pytest.raises(ValueError, match="Unknown execution mode"):
        create_app(workspace_root=str(tmp_path), execution_mode="Real")


def test_allowed_models_config_remediates_routing(tmp_path: pathlib.Path) -> None:
    # allowedModels in config becomes an enforced whitelist: the default
    # (forbidden) model is remediated to the first allowed one.
    _write_workspace_config(tmp_path, "allowedModels:\n  - allowed/model-x\n")
    app = create_app(workspace_root=str(tmp_path), execution_mode="offline-llm")
    client = TestClient(app)
    resp = client.post(
        "/v1/runs", json={"mode": "yolo", "security_profile": "open"}
    )
    assert resp.status_code == 201
    events = app.state.event_bus.read_all()
    routed = [e for e in events if e.eventType == "ModelRouteSelected"]
    assert routed, "no routing events emitted"
    assert all(e.data["model"] == "allowed/model-x" for e in routed)
    assert all(e.data["remediated"] for e in routed)


def test_policy_denial_without_remediation_fails_the_phase() -> None:
    # H5 regression: a denied, unremediable model must fail the phase, not be
    # silently used anyway.
    policy = PolicyEngine(PolicyDocument(policies=[PolicyRule(
        name="AllowedModels", type="whitelist", target="model-selection",
        values=["allowed/only"], remediable=False,
    )]))
    router = ModelRouter(policy_engine=policy)
    bridge = SessionBridge(model_router=router)
    from anvil_runtime.agents.phase_invocation import build_invocation_payload
    from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS

    event = bridge.execute_phase(build_invocation_payload(PHASE_CONTRACTS["proposal"]))
    assert event.status == "failure"
    assert "denied by policy" in (event.failure_reason or "")
