"""Integration tests: complexity-gated phase selection (#11, FR-CX-002..006).

Drives the supervisor with an executor that tags the proposal phase with a tier and
asserts the active phase set, the ComplexityAssessed event, and the config override.
"""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.config.schema import EffectiveConfig
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PhaseCompleteEvent
from anvil_runtime.state.event_bus import EventBus

_CORE = [
    "proposal", "factory-init", "specification", "architecture",
    "blueprint", "dev-plan", "implementation",
]


class _TierExecutor:
    """Reports success for every phase; tags only the proposal with a tier."""

    def __init__(self, tier: str | None) -> None:
        self._tier = tier

    def run(self, agent, payload):  # noqa: ANN001 - matches executor protocol
        tier = self._tier if agent.phase_id == "proposal" else None
        return PhaseCompleteEvent(
            phase_name=agent.phase_id,
            status="success",
            artifact_paths=list(payload.output_paths),
            checksums={},
            duration_ms=0,
            complexity_tier=tier,
        )


def _run(tmp_path: pathlib.Path, executor, config=None):
    bus = EventBus(str(tmp_path))
    manager = DevelopmentManager(
        workspace_root=str(tmp_path), config=config, event_bus=bus, executor=executor
    )
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    progress = manager.run_until_pause(started.run_id)
    return progress, bus


def test_simple_tier_runs_core_only(tmp_path: pathlib.Path) -> None:
    progress, bus = _run(tmp_path, _TierExecutor("simple"))
    assert progress.status == "completed"
    assert progress.completed_phases == _CORE  # no qa/packaging/.../cleanup
    assert any(e.eventType == "ComplexityAssessed" for e in bus.read_all())


def test_complex_tier_runs_all_phases(tmp_path: pathlib.Path) -> None:
    progress, _ = _run(tmp_path, _TierExecutor("complex"))
    assert progress.status == "completed"
    assert len(progress.completed_phases) == 12


def test_standard_tier_adds_qa_only(tmp_path: pathlib.Path) -> None:
    progress, _ = _run(tmp_path, _TierExecutor("standard"))
    assert progress.completed_phases == _CORE + ["qa"]


def test_no_tier_runs_all_phases(tmp_path: pathlib.Path) -> None:
    # Unassessed (e.g. stub) -> gate nothing (backward compatible).
    progress, _ = _run(tmp_path, _TierExecutor(None))
    assert len(progress.completed_phases) == 12


def test_config_tier_override_wins(tmp_path: pathlib.Path) -> None:
    # FR-CX-006: config tier overrides the proposal's assessment.
    progress, _ = _run(
        tmp_path, _TierExecutor("complex"), config=EffectiveConfig(complexityTier="simple")
    )
    assert progress.completed_phases == _CORE
