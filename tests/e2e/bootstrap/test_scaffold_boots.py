"""End-to-end bootstrap test: the Slice 1 scaffold imports and exposes contracts.

Slice 1 completion criterion: "All skeleton modules exist and pass static
checks; no unresolved import or type errors." This walks the full Slice 1 module
surface, imports each module, and asserts the headline symbols resolve.
"""

from __future__ import annotations

import importlib

import pytest

SLICE1_MODULES = [
    "anvil_runtime",
    "anvil_runtime.api",
    "anvil_runtime.api.models",
    "anvil_runtime.core",
    "anvil_runtime.core.phase_contracts",
    "anvil_runtime.config",
    "anvil_runtime.config.schema",
    "anvil_runtime.policy",
    "anvil_runtime.policy.models",
    "anvil_runtime.agents",
    "anvil_runtime.agents.base_phase_agent",
]


@pytest.mark.parametrize("module_name", SLICE1_MODULES)
def test_slice1_module_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module is not None


def test_package_version_exposed() -> None:
    import anvil_runtime

    assert anvil_runtime.__version__ == "0.1.0"


def test_headline_contracts_resolve() -> None:
    from anvil_runtime.agents.base_phase_agent import BasePhaseAgent
    from anvil_runtime.api.models import RunStartRequest, RunStarted
    from anvil_runtime.config.schema import EffectiveConfig, MANDATORY_SECURE_GATES
    from anvil_runtime.core.phase_contracts import PHASE_IDS, EventEnvelope
    from anvil_runtime.policy.models import PolicyRule

    # Smoke-construct one representative object per contract surface.
    assert RunStartRequest(mode="gated", security_profile="restricted").mode == "gated"
    assert RunStarted(run_id="r", started_at="2026-05-31T00:00:00Z", mode="gated").mode
    assert EffectiveConfig().securityProfile == "restricted"
    assert len(PHASE_IDS) == 13
    assert len(MANDATORY_SECURE_GATES) == 4
    assert EventEnvelope(
        timestamp="2026-05-31T00:00:00Z", eventType="Boot", runId="r", phase="proposal"
    ).severity == "info"
    assert PolicyRule(name="X", type="whitelist", target="model-selection").remediable is False
    assert issubclass(BasePhaseAgent, object)
