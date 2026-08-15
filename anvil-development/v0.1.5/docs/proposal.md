# Anvil Proposal — v0.1.5

v0.1.5 is the localization release: Anvil starts repairing the *right*
file. Every feature traces to the v0.1.4 measurement, re-derived from the
stored run artifacts on 2026-08-15 and summarized in
[background-information.md](../domain-knowledge/background-information.md).
The [v0.1.4 proposal](../../v0.1.4/docs/proposal.md) remains in force; this
document covers only what changes.

**Stack.** Unchanged: OpenRouter + the localhost REST runtime + the
`@anvil` extension. The OpenHands adapter stays parked.

**Theme.** v0.1.4 closed the loop between *what Anvil ships* and *what
actually runs*, and the measurement says the loop is no longer limited by
its ability to fix code — it is limited by its ability to identify which
code is wrong. Two defects, both structural. The localizer matches source
basenames against traceback text, so it resolves crashes and goes blind on
assertions; in the healthiest v0.1.4 run that discarded 43 of 67 failures,
silently. And what it does resolve is the *failure site*, not the *fault
site*: `tinydb/table.py` is implicated in 20 of 28 recovered failures and
selected zero times, so a module producing wrong data for its consumers can
never be repaired. v0.1.5 separates candidate generation from fault
selection (#28), gives selection the dependent source it needs to reason
about data flow (#29), makes `qa` emit tests that actually run (#30), and
puts the pass counts on the wire that v0.1.4's acceptance criterion
required (#31) — plus four supervisor correctness fixes.

**Scope discipline.** The governance ring and Docker daemon validation are
deferred to v0.1.6 as one release. Both are real, neither produces a
number, and drift can only move a Commit0 score neutrally or downward —
bundling them here would make this release's delta unattributable. The
reasoning is recorded in the background doc.

## Features

### #28 — Fault-aware repair localization (the core feature)

Localization becomes two stages instead of one.

**Candidate generation (mechanical).** In addition to today's basename
match, a cluster's failure text is matched against the top-level symbols
defined in each generated file, built with the same plain `ast` muscle
`interface_map.py` already uses. Measured on the v0.1.4 artifacts this
attributes 53 of the 80 previously-unlocalized failures (66%). The output
is a candidate *set*, not a winner — typically three files.

**Fault selection (model).** The model receives the cluster excerpt, the
candidate signatures, and the dependency direction between them, and names
the file to repair. This is the step that can conclude "`B` asserts on a
shape `A` returned, so `A` is wrong" — an inference no name-frequency vote
can make.

Three supporting rules:

- **The write-set is the candidate set.** This overturns v0.1.4's "the
  write-set stays restricted to implicated files" constraint, deliberately
  and on the evidence: that constraint is exactly why `table.py` cannot be
  fixed. A three-file write-set remains far narrower than the existing
  all-artifacts fallback.
- **Candidates rank producer-first.** Where `interface_map.py`'s
  dependency edges show `A → B`, `A` ranks above `B`. Mention frequency is
  biased toward consumers because that is where assertions live, so the
  ranking is the inverse of the raw signal.
- **Unlocalized clusters are never silently dropped.** Today
  `openhands_adapter.py:799` discards them with no warning and no event.
  A cluster that survives both stages without a candidate emits an event
  and falls back to the existing behavior; it does not vanish.

Config-gated (`ANVIL_REPAIR_LOCALIZATION=symbols|basename`) so the
release can be decomposed after the fact, and so #28 can be shown not to
degrade currently-working basename localization.

### #29 — Dependency-slice repair context

v0.1.4's background doc pre-registered this: escalate from #27's
signature-only interface map to full dependent **source** if the
measurement showed cross-module clusters still killing repaired runs. It
does — 89% of recovered failures implicate more than one module.

The repair prompt gains the *bodies* of the candidate set's upstream
dependencies, not just their signatures. #27's rule that passing files are
never written is superseded only for files in the candidate set; every
other file remains read-only context. The existing 6k character cap
becomes a slice budget, dependency-ranked, so a large upstream module
degrades to signatures rather than blowing the prompt.

This is what makes #28's selection stage possible in practice: choosing
`A` over `B` requires seeing what `A` actually does.

Config-gated (`ANVIL_REPAIR_CONTEXT=slices|interfaces|minimal`), extending
v0.1.4's existing gate rather than adding a new one.

### #30 — `qa` produces executable tests

Today `LLMBackend.run` routes only `implementation` to the code path, so
`qa` falls to `_run_doc`; `_write_documents` handles the contract's
directory-shaped outputs by writing an identical `GENERATED.md` into each
of `tests/{unit,integration,e2e}/`. The phase emits a plan and three
markdown files and never a test. `ARTIFACT_SCHEMAS["qa"]` validates only
`docs/qa-test-plan.md`, so nothing detects it.

`qa` routes to the code path with its own prompt mode — the implementation
source in context, outputs under `tests/`, imports resolving against the
real package layout. The contract is **not** changed to file-shaped
outputs: test filenames are not knowable at contract-definition time, and
`_write_files` already treats `output_paths` as sandbox *prefixes*, which
is the correct behavior. Only the routing is wrong.

Validation is raised beyond existence and a `.py` extension, which three
files containing `assert True` would satisfy: `ARTIFACT_SCHEMAS["qa"]`
requires that `pytest --collect-only` succeeds and collects a non-zero
count. `_write_files`' unparseable-manifest fallback must not write
`GENERATED.md` under `tests/`.

**Generated tests are not authoritative for the repair loop.** An
LLM-written test can be wrong, and treating it as ground truth lets the
loop damage a correct implementation to satisfy a bad assertion — no gain
against Commit0's hidden reference tests, possibly a loss. Repair may
revise a test only under the **no-weakening guard**: the collected test
count must not decrease, checked mechanically via `--collect-only`.

Config-gated, so Commit0 runs can disable test generation and keep their
token cost and their measurement surface unchanged.

### #31 — Repair round telemetry (FR-RL-010)

`RepairRoundCompleted` carries exit code only, so v0.1.4's acceptance
criterion "per-round pass counts monotone non-decreasing" was never
checkable — recorded as a deviation in the v0.1.4 implementation log and
deferred here. Per-round pass/fail counts go on the event, parsed from the
JUnit report where one exists.

This is what makes #28 measurable round over round rather than only at the
final score, and it closes the one criterion v0.1.4 shipped without.

## Fixes

- **#32 — Resume ignores tier exclusions.** `development_manager.py:835`
  computes `next_phase(ctx.completed)` without `| ctx.excluded`; `step()`
  and `_progress()` both include exclusions. A resumed `simple` or
  `standard` run reports a resume target the next `step()` immediately
  skips. Regression test resumes an excluded-tier run.
- **#33 — Retry counters never persisted.** `RunState.retry_counters` and
  `RetryController.snapshot()` both exist; `snapshot()` has zero callers.
  A restart silently resets every phase's retry budget, which matters
  because resume is load-bearing. Persist at checkpoint, restore on
  resume, test across a simulated restart.
- **#34 — "Rounds exhausted" reported as failure.** On a benchmark this is
  the loop's normal successful exit — the full suite is unreachable on
  tinydb by construction — but it surfaces as failure in run status,
  distorting every benchmark run's reported outcome.
- **#35 — Health endpoint dishonest.** `routes_health.py:24-26` hardcodes
  `mcp_discovery` and `openhands` to `"pending"` with a "Slice 5 flips
  these" comment, long after Slice 5 shipped. `openhands` reports real
  state now; `mcp_discovery` reports honestly that the subsystem is not
  wired, pending v0.1.6.

Documentation and hygiene, non-numbered: `STATUS.md`'s stale header and
superseded "Immediate next step"; `benchmarks/commit0/README.md:79`
contradicting `STATUS.md` on the offline run; `extension/README.md:25`
linking to a non-existent `docs/QUICKSTART.md`; the 12-vs-13 phase
discrepancy across `phase_contracts.py:5`, `phase_dag.py:6`,
`runs/README.md:3` and the e2e test name; `anvil-instructions.md`
duplicated byte-for-byte at the repo root and in `workspace/`; tracked
`.pptx` files despite `.gitignore:35`; CI running twice per push on `v*`
branches; and no required status checks on `main`.

## Measurement protocol (binding for this release)

Two surfaces, one variable each.

- **Commit0 tinydb** measures #28+#29 as a bundle, under conditions
  **identical to v0.1.4**: `open` profile, `local` executor, same
  instances, median-of-3, full distribution quoted. No executor change and
  no governance wiring lands in this release, so the delta is attributable
  to localization. Baseline to beat: median 61/201 (30.3%), distribution
  {47, 61, 134}.
- **`evals/` smoke** measures #30. #30 is inert on Commit0 because
  `graft_and_test.py` runs the snapshotted original tests, so it cannot
  contaminate the tinydb number. Resolve rate must hold at 6/6.
- **cachetools** re-run as a regression check only; 177/215 must hold.
- **Ablation.** #28 and #29 are each config-gated, so the bundle can be
  decomposed after the fact if the delta warrants it.

**Stated in advance:** localizing is not repairing. The 66% recovery
figure is a ceiling on what becomes *visible* to the loop, not a
prediction of score. The claim under test is that more failures enter
repair and that this raises the median; a null result is a real outcome
and is reported as one.

## Out of scope

- **The governance ring and Docker daemon validation** — v0.1.6, together.
  Deferred on attribution grounds, not effort; drift additionally needs a
  `drift_context_provider` that does not exist and must land report-only,
  since `_post_phase_checks` fails phases on major/critical drift.
- **SWE-bench / the `patch` tier** — needs its own proposal. Roughly half
  its difficulty is localization in a large existing repo, which the
  greenfield waterfall has no phase for. #28's fault selection is the
  reusable asset; codebase MCP is worth revisiting there and nowhere
  earlier.
- **Reviving the agent layer.** All 13 `agents/phases/*.py` are stubs and
  `BridgeExecutor` never calls `agent.run()`. Known debt, separate
  question.
- **Renaming `openhands_adapter.py` / `OpenHandsBackend` / `OpenHandsAdapter`.**
  The repository is now `anvil-coding-agent`; the internal names still
  claim an adapter that was set aside at v0.1.1. Cosmetic, and not while
  the repair loop is being measured.
- **Wrong-idea persistence.** #29 gives a repair round more to work with,
  but a round re-reading the same context can re-choose the same wrong
  design. The explicitly-different-approach prompt stays open.

## Acceptance criteria

1. Unlocalized clusters are never silently discarded: every cluster
   without a candidate emits an event, and `openhands_adapter.py:799`'s
   silent drop is gone.
2. On the v0.1.4 stored artifacts, #28's candidate generation attributes
   at least 60% of previously-unlocalized failures, and #28 does not
   reduce the set of failures the basename matcher already localized.
3. A repair round demonstrably writes to an upstream producer that the
   v0.1.4 loop could not reach — the `table.py` case, shown end to end.
4. `RepairRoundCompleted` carries per-round pass/fail counts, and the
   monotonicity property v0.1.4 could not check is checked against real
   run data.
5. `qa` produces `.py` files that `pytest --collect-only` collects with a
   non-zero count, and no `GENERATED.md` appears under any `tests/`
   directory on a successful qa phase.
6. A resumed excluded-tier run targets a phase that is not immediately
   skipped, and retry budgets survive a restart.
7. Commit0 tinydb median-of-3 under v0.1.4-identical conditions, reported
   with its distribution against the 61/201 baseline — including if it
   fails to move. Smoke holds 6/6; cachetools holds 177/215.
