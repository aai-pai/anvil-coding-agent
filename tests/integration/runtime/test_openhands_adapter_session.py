"""Integration tests: OpenHands adapter session + phase bridge.

Slice 5 (blueprint §3.1; plan §2.5). Verifies the in-process adapter starts
sessions and runs steps deterministically, and that the SessionBridge maps a
phase payload onto the supervisor's ``PhaseCompleteEvent`` contract while routing
the model and recording usage.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.core.phase_contracts import PHASE_CONTRACTS
from anvil_runtime.agents.phase_invocation import build_invocation_payload
from anvil_runtime.llm.model_router import DEFAULT_CODING_MODEL, ModelRouter
from anvil_runtime.llm.usage_tracker import UsageTracker
from anvil_runtime.sdk.openhands_adapter import (
    AgentRuntimeConfig,
    OpenHandsAdapter,
    PhaseStep,
)
from anvil_runtime.sdk.session_bridge import SessionBridge
from anvil_runtime.state.event_bus import EventBus


def test_adapter_sessions_are_deterministic() -> None:
    adapter = OpenHandsAdapter()
    s1 = adapter.start_session(AgentRuntimeConfig(model="gemma-4"))
    s2 = adapter.start_session(AgentRuntimeConfig(model="gemma-4"))
    assert s1 == "session-1"
    assert s2 == "session-2"
    result = adapter.run_phase_step(
        s1, PhaseStep(phase="proposal", instruction="draft", output_paths=["docs/proposal.md"])
    )
    assert result.status == "success"
    assert result.artifacts == ["docs/proposal.md"]
    assert result.usage["total_tokens"] > 0


def test_session_bridge_produces_phase_complete_event(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    tracker = UsageTracker(event_bus=bus, run_id="r1")
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(),
        model_router=ModelRouter(event_bus=bus, run_id="r1"),
        usage_tracker=tracker,
    )
    payload = build_invocation_payload(PHASE_CONTRACTS["implementation"])

    event = bridge.execute_phase(payload, subtask="coding")

    assert event.phase_name == "implementation"
    assert event.status == "success"
    assert event.artifact_paths == ["src/"]
    assert event.token_usage is not None
    # Usage was tracked and the model route was audited.
    assert tracker.total_for("implementation") > 0
    types = {e.eventType for e in bus.read_all()}
    assert "ModelRouteSelected" in types
    assert "TokenUsageReported" in types


def test_session_bridge_routes_coding_model_by_default() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend:
        def start(self, cfg: AgentRuntimeConfig) -> str:
            captured["model"] = cfg.model
            return "session-1"

        def run(self, session_id, step):  # type: ignore[no-untyped-def]
            from anvil_runtime.sdk.openhands_adapter import StepResult

            return StepResult(session_id=session_id, phase=step.phase, status="success")

    bridge = SessionBridge(adapter=OpenHandsAdapter(backend=RecordingBackend()))
    payload = build_invocation_payload(PHASE_CONTRACTS["implementation"])
    bridge.execute_phase(payload, subtask="coding")
    assert captured["model"] == DEFAULT_CODING_MODEL
