"""Unit tests for the phase dependency DAG. Slice 2 (spec FR-SV-005)."""

from __future__ import annotations

import pytest

from anvil_runtime.core.phase_contracts import PHASE_IDS
from anvil_runtime.core.phase_dag import PhaseDAG


def test_default_graph_is_linear_pipeline() -> None:
    dag = PhaseDAG()
    assert dag.phases == list(PHASE_IDS)
    assert dag.dependencies_of("proposal") == []
    assert dag.dependencies_of("architecture") == ["specification"]


def test_ready_and_next_phase_progress_serially() -> None:
    dag = PhaseDAG()
    assert dag.ready_phases(set()) == ["proposal"]
    assert dag.next_phase(set()) == "proposal"
    assert dag.next_phase({"proposal"}) == "factory-init"
    assert dag.next_phase(set(PHASE_IDS)) is None


def test_validate_accepts_default_graph() -> None:
    PhaseDAG().validate()  # must not raise


def test_validate_rejects_unknown_dependency() -> None:
    dag = PhaseDAG({"a": ["ghost"], "b": ["a"]})
    with pytest.raises(ValueError):
        dag.validate()


def test_validate_rejects_cycle() -> None:
    dag = PhaseDAG({"a": ["b"], "b": ["a"]})
    with pytest.raises(ValueError):
        dag.validate()


def test_downstream_of_returns_transitive_dependents() -> None:
    dag = PhaseDAG()
    downstream = dag.downstream_of("architecture")
    assert "blueprint" in downstream
    assert "cleanup" in downstream
    # Upstream phases are not downstream.
    assert "proposal" not in downstream
    assert "specification" not in downstream
    # Returned in canonical order.
    assert downstream == [p for p in PHASE_IDS if p in set(downstream)]
