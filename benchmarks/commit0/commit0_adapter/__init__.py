"""Commit0 adapter: run Anvil on Commit0 library-generation tasks.

Commit0 (https://commit-0.github.io) gives an agent a real Python library's
skeleton — every function body replaced with ``pass``, signatures and
docstrings intact — plus the library's own unit-test suite. The agent must
implement the library; the metric is the repo's test pass rate.

This adapter reuses the Anvil eval harness (``evals/anvil_eval``) and adds the
Commit0-specific stages:

    fetch    clone the stubbed skeleton (github.com/commit-0/<repo>,
             branch ``commit0_combined``)
    prepare  stage an Anvil workspace: skeleton + generated
             background-information.md (stub inventory) + anvil-instructions.md
    run      drive an in-place Anvil run (the task-less "start" flow)
    apply    merge Anvil's generated src/ modules onto the package stubs
    score    run the repo's own pytest suite and report pass counts

Adapter-only logic lives here; anything Anvil itself is missing (skeleton-
aware implementation, external-test repair loop) is future *core* work.
"""

__version__ = "0.1.0"
