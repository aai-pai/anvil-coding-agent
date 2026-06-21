"""Unit tests: task-complexity gate for optional planning phases (FR-002 #2)."""

from __future__ import annotations

import pathlib

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.artifacts.validator import ArtifactValidator
from anvil_runtime.core.complexity_gate import (
    DEFAULT_TIER,
    OPTIONAL_PHASES,
    enabled_optional_phases,
    fixed_classifier,
    is_optional,
    make_llm_classifier,
    normalize_tier,
)
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.core.phase_contracts import PHASE_IDS
from anvil_runtime.llm.openrouter_provider import OfflineTransport, OpenRouterProvider
from anvil_runtime.sdk.openhands_adapter import LLMBackend, OpenHandsAdapter
from anvil_runtime.sdk.session_bridge import SessionBridge
from anvil_runtime.security.secret_adapter import SecretAdapter
from anvil_runtime.state.event_bus import EventBus
from anvil_runtime.agents.phase_invocation import BridgeExecutor


# -- pure mapping ------------------------------------------------------------


def test_normalize_tier_maps_words_and_falls_back() -> None:
    assert normalize_tier("simple") == "simple"
    assert normalize_tier("  STANDARD ") == "standard"
    assert normalize_tier("This looks complex to me") == "complex"
    assert normalize_tier("nonsense") == DEFAULT_TIER
    assert normalize_tier(None) == DEFAULT_TIER


def test_enabled_optional_phases_by_tier() -> None:
    assert enabled_optional_phases("simple") == frozenset()
    assert enabled_optional_phases("standard") == frozenset({"documentation"})
    assert enabled_optional_phases("complex") == OPTIONAL_PHASES
    assert enabled_optional_phases("full") == OPTIONAL_PHASES
    # Unknown tier is conservative: keep everything.
    assert enabled_optional_phases("???") == OPTIONAL_PHASES


def test_only_doc_only_phases_are_gated() -> None:
    assert OPTIONAL_PHASES == frozenset({"packaging", "documentation", "deployment"})
    for phase in OPTIONAL_PHASES:
        assert is_optional(phase)
    for always_on in ("proposal", "specification", "implementation", "qa", "cleanup"):
        assert not is_optional(always_on)


# -- supervisor integration (offline pipeline + fixed classifier) ------------


def _manager(tmp_path: pathlib.Path, bus: EventBus, classifier):
    provider = OpenRouterProvider(
        secret_adapter=SecretAdapter(provided_key="k"), transport=OfflineTransport()
    )
    bridge = SessionBridge(
        adapter=OpenHandsAdapter(backend=LLMBackend(provider, str(tmp_path))),
        workspace_root=str(tmp_path),
    )
    return DevelopmentManager(
        workspace_root=str(tmp_path),
        event_bus=bus,
        executor=BridgeExecutor(bridge),
        artifact_validator=ArtifactValidator(workspace_root=str(tmp_path), event_bus=bus),
        complexity_classifier=classifier,
    )


def _run(manager: DevelopmentManager):
    started = manager.start_run(RunStartRequest(mode="yolo", security_profile="open"))
    return manager.run_until_pause(started.run_id)


def test_simple_tier_skips_all_optional_docs(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    progress = _run(_manager(tmp_path, bus, fixed_classifier("simple")))

    assert progress.status == "completed"
    # Every phase is accounted for (skipped phases count as completed).
    assert len(progress.completed_phases) == len(PHASE_IDS)
    # The three optional planning docs are NOT written.
    for name in ("packaging-plan.md", "documentation-plan.md", "deployment-plan.md"):
        assert not (tmp_path / "docs" / name).is_file()
    # Canonical + always-on docs ARE written.
    for name in ("proposal.md", "spec.md", "qa-test-plan.md", "phase-summary-log.md"):
        assert (tmp_path / "docs" / name).is_file()
    skipped = {e.phase for e in bus.read_all() if e.eventType == "PhaseSkipped"}
    assert skipped == OPTIONAL_PHASES
    assert any(e.eventType == "ComplexityClassified" for e in bus.read_all())


def test_standard_tier_keeps_only_documentation(tmp_path: pathlib.Path) -> None:
    bus = EventBus(str(tmp_path))
    _run(_manager(tmp_path, bus, fixed_classifier("standard")))

    assert (tmp_path / "docs" / "documentation-plan.md").is_file()
    assert not (tmp_path / "docs" / "packaging-plan.md").is_file()
    assert not (tmp_path / "docs" / "deployment-plan.md").is_file()


def test_no_classifier_runs_every_phase(tmp_path: pathlib.Path) -> None:
    # Backward compatible: without a classifier nothing is skipped.
    bus = EventBus(str(tmp_path))
    _run(_manager(tmp_path, bus, None))

    for name in ("packaging-plan.md", "documentation-plan.md", "deployment-plan.md"):
        assert (tmp_path / "docs" / name).is_file()
    assert not any(e.eventType == "PhaseSkipped" for e in bus.read_all())


# -- env override ------------------------------------------------------------


def test_make_llm_classifier_honors_env_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANVIL_COMPLEXITY", "simple")
    calls: list = []

    class _Provider:
        def complete(self, req):  # pragma: no cover - must not be called
            calls.append(req)
            raise AssertionError("override must not hit the LLM")

    classifier = make_llm_classifier(_Provider(), "m", str(tmp_path))
    assert classifier("run-1") == "simple"
    assert calls == []
