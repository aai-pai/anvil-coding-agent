"""Hooks subpackage.

Slice 3 provides the lifecycle hook contracts (:mod:`lifecycle_hooks`), the
compiler that materializes ``.openhands/hooks.json`` (:mod:`compiler`), and the
adapter that enforces allow/deny/mutate decisions at lifecycle boundaries
(:mod:`adapter`).

STATUS (v0.1.2): built and unit-tested but NOT yet wired into the
production app factory (`anvil_runtime.app`) — nothing on the live run
path invokes this package. Wire it in (or remove it) before relying on
its guarantees.
"""

from __future__ import annotations
