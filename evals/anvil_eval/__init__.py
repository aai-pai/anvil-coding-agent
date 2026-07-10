"""Anvil evaluation harness (Tier 1 internal benchmark).

Drives the Anvil runtime's ``/v1`` REST API over a suite of greenfield tasks,
grades each generated project against a *held-out* pytest suite the agent never
sees, and reports the leaderboard-shaped headline metrics:

- **resolve rate (pass@1)** — % of tasks whose generated project passes its
  held-out acceptance tests in a single unattended run
- **completion rate** — % of runs the pipeline finished without escalation
- **tokens / estimated cost / wall-clock** per task
- **artifact validity** — OKF frontmatter, lineage fields, docs/index.md
- **reliability signals** — escalations, validation failures, truncations,
  failure records

Stdlib-only by design so it runs in any environment that can run Anvil.
"""

__version__ = "0.1.0"
