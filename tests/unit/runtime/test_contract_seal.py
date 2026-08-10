"""Unit tests: contract sealing after intake (v0.1.3 #20).

At the final intake completion the contract block is sealed: a
``ContractSealed`` event is emitted, later contract writes are rejected, and
a resume rehydrates the seal. Unmarkered (v0.1.2-style) files seal nothing.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from anvil_runtime.api.models import RunStartRequest
from anvil_runtime.core.development_manager import DevelopmentManager
from anvil_runtime.state.event_bus import EventBus

MARKERED = textwrap.dedent("""\
    # Task

    <!-- anvil:contract -->
    - PINNED_FACT: output is a dict
    <!-- anvil:context -->
    prose
    """)


def _write_domain(tmp_path: pathlib.Path, text: str) -> None:
    target = tmp_path / "domain-knowledge" / "background-information.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _manager(tmp_path: pathlib.Path) -> tuple[DevelopmentManager, EventBus]:
    bus = EventBus(str(tmp_path))
    return DevelopmentManager(workspace_root=str(tmp_path), event_bus=bus), bus


def _events_of(bus: EventBus, run_id: str, event_type: str) -> list:
    return [e for e in bus.stream(run_id) if e.eventType == event_type]


def test_intake_completion_seals_a_markered_contract(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    manager, bus = _manager(tmp_path)
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager.run_until_pause(run_id)
    sealed = _events_of(bus, run_id, "ContractSealed")
    assert len(sealed) == 1
    assert sealed[0].phase == "intake"


def test_unmarkered_file_never_emits_contract_sealed(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, "# Task\n\nplain prose\n")
    manager, bus = _manager(tmp_path)
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager.run_until_pause(run_id)
    assert _events_of(bus, run_id, "ContractSealed") == []


def test_writes_after_seal_are_rejected(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    manager, _bus = _manager(tmp_path)
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager.run_until_pause(run_id)
    with pytest.raises(ValueError, match="sealed"):
        manager.submit_clarification(run_id, ["late answer"])


def test_resume_preserves_the_seal(tmp_path: pathlib.Path) -> None:
    _write_domain(tmp_path, MARKERED)
    manager, _bus = _manager(tmp_path)
    run_id = manager.start_run(
        RunStartRequest(mode="yolo", security_profile="open")).run_id
    manager.run_until_pause(run_id)

    # Fresh manager over the same workspace (server restart).
    restarted, _bus2 = _manager(tmp_path)
    restarted.resume_run(run_id)
    with pytest.raises(ValueError, match="sealed"):
        restarted.submit_clarification(run_id, ["late answer"])


def test_clarification_answers_land_inside_contract_block(
    tmp_path: pathlib.Path,
) -> None:
    from anvil_runtime.contract import split_contract

    _write_domain(tmp_path, MARKERED)
    manager, _bus = _manager(tmp_path)
    run_id = manager.start_run(
        RunStartRequest(mode="gated", security_profile="open")).run_id
    # Simulate the intake pause (#15): stub agents never ask, so stage the
    # awaiting state directly and exercise the supervisor's append path.
    ctx = manager._runs[run_id]
    ctx.status = "awaiting_clarification"
    ctx.pending_questions = ["Which format?"]
    manager.submit_clarification(run_id, ["JSON, always"])

    updated = (tmp_path / "domain-knowledge" / "background-information.md"
               ).read_text(encoding="utf-8")
    split = split_contract(updated)
    assert "JSON, always" in split.contract
    assert "JSON, always" not in split.context
    assert "## Clarifications" in split.contract
