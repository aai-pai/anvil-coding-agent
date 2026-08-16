"""Phase dependency DAG and topological readiness.

Slice 2 deliverable (blueprint §3.1; spec FR-SV-005/006; architecture §4.2,
§686). v0.1.0 executes phases serially in topological order, but the
dependencies are declared as a DAG so a future scheduler can parallelize without
changing phase contracts. The default graph is the linear 13-phase pipeline
(each phase depends on its predecessor).
"""

from __future__ import annotations

from anvil_runtime.core.phase_contracts import PHASE_IDS


def _default_linear_dependencies() -> dict[str, list[str]]:
    """Each phase depends on the one before it (proposal has no prerequisite)."""
    deps: dict[str, list[str]] = {PHASE_IDS[0]: []}
    for prev, phase in zip(PHASE_IDS, PHASE_IDS[1:]):
        deps[phase] = [prev]
    return deps


class PhaseDAG:
    """Declares phase dependencies and validates topological ordering."""

    def __init__(self, dependencies: dict[str, list[str]] | None = None) -> None:
        self._dependencies: dict[str, list[str]] = (
            dict(dependencies)
            if dependencies is not None
            else _default_linear_dependencies()
        )
        # Canonical ordering used to break ties deterministically. Falls back to
        # insertion order for custom graphs whose nodes are not standard phases.
        self._order = [p for p in PHASE_IDS if p in self._dependencies]
        for node in self._dependencies:
            if node not in self._order:
                self._order.append(node)

    @property
    def phases(self) -> list[str]:
        """All phase IDs in this graph, in canonical/topological order."""
        return list(self._order)

    def dependencies_of(self, phase_id: str) -> list[str]:
        return list(self._dependencies.get(phase_id, []))

    def ready_phases(self, completed: set[str]) -> list[str]:
        """Return not-yet-completed phases whose prerequisites are all done.

        Result is in canonical order so serial execution is deterministic.
        """
        ready: list[str] = []
        for phase in self._order:
            if phase in completed:
                continue
            if all(dep in completed for dep in self._dependencies[phase]):
                ready.append(phase)
        return ready

    def next_phase(self, completed: set[str]) -> str | None:
        """The single next phase to execute under serial topological order."""
        ready = self.ready_phases(completed)
        return ready[0] if ready else None

    def downstream_of(self, phase_id: str) -> list[str]:
        """All phases that (transitively) depend on ``phase_id``.

        Used by rollback to mark a phase and everything after it incomplete
        (FR-SV-020A).
        """
        result: list[str] = []
        frontier = {phase_id}
        # Repeatedly pull in any phase whose deps intersect the frontier.
        changed = True
        while changed:
            changed = False
            for phase in self._order:
                if phase in result or phase == phase_id:
                    continue
                if any(dep in frontier for dep in self._dependencies[phase]):
                    result.append(phase)
                    frontier.add(phase)
                    changed = True
        return [p for p in self._order if p in result]

    def validate(self) -> None:
        """Raise ``ValueError`` if the graph references unknown nodes or has a cycle."""
        known = set(self._dependencies)
        for node, deps in self._dependencies.items():
            for dep in deps:
                if dep not in known:
                    raise ValueError(
                        f"Phase '{node}' depends on unknown phase '{dep}'"
                    )
        # Cycle detection: repeatedly resolve nodes whose deps are all resolved.
        # If a fixpoint leaves nodes unresolved, those nodes form a cycle.
        resolved: set[str] = set()
        progressing = True
        while progressing:
            progressing = False
            for node in known:
                if node in resolved:
                    continue
                if all(dep in resolved for dep in self._dependencies[node]):
                    resolved.add(node)
                    progressing = True
        if len(resolved) != len(known):
            unresolved = sorted(known - resolved)
            raise ValueError(f"Phase DAG contains a cycle among: {unresolved}")


__all__ = ["PhaseDAG"]
