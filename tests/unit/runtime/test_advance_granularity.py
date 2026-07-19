"""Unit tests: per-artifact advance granularity (v0.1.4 #24).

One `/advance` (supervisor `step`) performs at most one unit of
implementation work; progress is checkpointed so retries and restarts resume
from the last completed artifact; stub/single-shot behavior is unchanged.
"""

from __future__ import annotations

import pathlib
import textwrap

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.agents.phase_invocation import BridgeExecutor
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.sdk.openhands_adapter import LLMBackend, OpenHandsAdapter
from anvil_runtime.sdk.session_bridge import SessionBridge
from anvil_runtime.state.event_bus import EventBus

DOMAIN_REL = "domain-knowledge/background-information.md"

THREE_FILE_DOMAIN = textwrap.dedent("""\
    # Task

    <!-- anvil:contract -->
    ```contract-manifest
    {"files": ["a.py", "b.py", "c.py"], "symbols": []}
    ```
    <!-- anvil:context -->
    prose
    """)

PRE_IMPL = {"intake", "proposal", "factory-init", "specification",
            "architecture", "blueprint", "dev-plan"}


class _ScriptedProvider:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):  # noqa: ANN001
        self.requests.append(request)

        class _Response:
            content = "def generated():\n    return 1\n"
            finish_reason = "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        return _Response()


def _manager(tmp_path: pathlib.Path) -> tuple[DevelopmentManager, _ScriptedProvider, EventBus]:
    bus = EventBus(str(tmp_path))
    provider = _ScriptedProvider()
    backend = LLMBackend(provider=provider, workspace_root=str(tmp_path),
                         event_bus=bus)
    bridge = SessionBridge(adapter=OpenHandsAdapter(backend=backend),
                           workspace_root=str(tmp_path))
    manager = DevelopmentManager(workspace_root=str(tmp_path), event_bus=bus,
                                 executor=BridgeExecutor(bridge))
    return manager, provider, bus


def _start_at_implementation(manager: DevelopmentManager,
                             tmp_path: pathlib.Path) -> str:
    target = tmp_path / DOMAIN_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(THREE_FILE_DOMAIN, encoding="utf-8")
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager._runs[run_id].completed = set(PRE_IMPL)
    return run_id


def test_one_advance_generates_one_artifact(tmp_path: pathlib.Path) -> None:
    manager, provider, bus = _manager(tmp_path)
    run_id = _start_at_implementation(manager, tmp_path)

    manager.step(run_id)
    assert len(provider.requests) == 1
    assert (tmp_path / "src" / "a.py").is_file()
    assert not (tmp_path / "src" / "b.py").exists()
    assert "implementation" not in manager._runs[run_id].completed

    manager.step(run_id)
    assert len(provider.requests) == 2
    assert (tmp_path / "src" / "b.py").is_file()
    assert "implementation" not in manager._runs[run_id].completed

    manager.step(run_id)  # third unit finishes the phase (no test command)
    assert len(provider.requests) == 3
    assert (tmp_path / "src" / "c.py").is_file()
    assert "implementation" in manager._runs[run_id].completed

    types = [e.eventType for e in bus.stream(run_id)]
    assert types.count("PhaseUnitCompleted") == 2  # a, b; c completes the phase
    # The phase is announced exactly once, not once per unit.
    assert types.count("PhaseStarted") == 1
    assert types.count("PhaseCompleted") == 1


def test_mid_phase_restart_resumes_from_checkpoint(tmp_path: pathlib.Path) -> None:
    manager, provider, _bus = _manager(tmp_path)
    run_id = _start_at_implementation(manager, tmp_path)
    manager.step(run_id)  # a.py generated, checkpointed
    assert len(provider.requests) == 1

    # Server restart: fresh manager/backend over the same workspace.
    restarted, provider2, _bus2 = _manager(tmp_path)
    restarted.resume_run(run_id)
    ctx = restarted._runs[run_id]
    assert ctx.phase_progress.get("implementation") == ["src/a.py"]
    ctx.completed |= PRE_IMPL  # stub checkpoints don't cover the fake history

    restarted.step(run_id)
    # Only b.py is generated — a.py was never regenerated (FR-AG-003).
    assert len(provider2.requests) == 1
    assert "`src/b.py`" in provider2.requests[0].prompt


def test_unit_failure_retries_only_remaining_units(tmp_path: pathlib.Path) -> None:
    manager, provider, _bus = _manager(tmp_path)
    run_id = _start_at_implementation(manager, tmp_path)
    manager.step(run_id)  # a.py ok
    # Make the next completion fail hard (empty content twice = step failure).
    empty_calls = {"n": 0}
    original = provider.complete

    def flaky(request):  # noqa: ANN001
        if "`src/b.py`" in request.prompt and empty_calls["n"] < 2:
            empty_calls["n"] += 1
            response = original(request)
            response.content = ""
            return response
        return original(request)

    provider.complete = flaky
    progress = manager.step(run_id)  # b.py unit fails -> phase failure recorded
    assert progress.status == "running"  # retry budget not exhausted
    manager.step(run_id)  # retry: regenerates b only (a is checkpointed)
    prompts = [r.prompt for r in provider.requests]
    assert not any("`src/a.py`" in p for p in prompts[1:])


def test_single_shot_mode_completes_in_one_advance(tmp_path: pathlib.Path) -> None:
    manager, provider, _bus = _manager(tmp_path)
    target = tmp_path / DOMAIN_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Task\n\nno markers\n", encoding="utf-8")
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager._runs[run_id].completed = set(PRE_IMPL)
    manager.step(run_id)
    assert "implementation" in manager._runs[run_id].completed
    assert len(provider.requests) == 1  # v0.1.2 single completion, unchanged
