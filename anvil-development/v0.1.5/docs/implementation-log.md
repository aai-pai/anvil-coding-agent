# Anvil v0.1.5 — implementation log

What was built, where it lives, what deviated from the plan, and what is
still owed. Derived from [plan.md](plan.md); slices are its numbering.

**Status: slices 1–8 and 10 complete. Slice 9 (the measurement) is NOT
done** — it needs an OpenRouter key, real spend, and several hours of
wall-clock. Nothing in this release may be called measured until it runs.

Suite: **441 tests, green** (397 at the v0.1.4 baseline; +44).

## Slice 1 — the fixture

`tests/unit/runtime/fixtures/junit-v0.1.4-fix-r3.xml` (19 testcases, 15
failures, 15.8 KB), generated programmatically from the real `fix-r3`
report rather than hand-written, so failure shapes are faithful. Hostname
and user paths scrubbed. It reproduces the pathology in miniature:
`file=None` is the largest cluster (8 of 15) and `tinydb/table.py` is a
candidate 6 times and hit-count winner 0 times — the same 20/0 ratio as the
full report. `benchmarks/commit0/results/` is gitignored, so without this
the release's central invariant could not run in CI.

## Slice 2 — shared AST index

`verify/interface_map.py` gains `AstIndex(symbols, edges, broken, trees)`
and `index()`. `build()` takes an optional prebuilt index; the acceptance
gate was behavior preservation and `build(ast_index=…) == build()` holds
for every file, by test. Symbols include class-level methods deliberately:
an assertion names `QueryInstance.is_cacheable` far more often than the
module defining it.

## Slice 3 — mechanical modules (#28/#29)

`verify/candidates.py` (candidate sets, producer-first ranking) and
`verify/slices.py` (upstream bodies under a budget). Both provider-free.

**The slice-3 stop condition passed.** Against the fixture, the
previously-discarded cluster now yields `['tinydb/table.py',
'tinydb/queries.py', 'tinydb/database.py']` — the producer ranked *first*,
the file argmax never selected — and FR-FL-008 (symbols ⊇ basename) holds.

## Slice 4 — loop integration

The silent drop at `openhands_adapter.py:799` is deleted. `_implicate`
accounts for every cluster; `_select_fault` is the release's only new LLM
call and lives in `LLMBackend`, keeping `verify/` provider-free. Gates
`ANVIL_REPAIR_LOCALIZATION` and `ANVIL_REPAIR_CONTEXT=slices` wired with
the usual env > config > default precedence.

## Slice 5 — telemetry (#31)

`localize.try_parse_counts` + `tests_passed`/`tests_failed`/
`tests_collected` on `RepairRoundCompleted`. Absent means unknown, never
zero.

## Slice 6 — qa produces tests (#30)

`_run_qa` produces the plan **and** the tests; `_qa_targets`,
`_qa_file_prompt`, the `tests/` bar on the `GENERATED.md` fallback, and
`ArtifactValidator`'s collect-only gate.

## Slice 7 — supervisor correctness (#32–#35)

Resume unions exclusions; `RetryController.restore` wired to checkpoint and
resume; `RepairRoundsExhausted` distinguishes a bounded exit from a
malfunction; health reports `openhands: ok` and `mcp_discovery: not-wired`.

## Slice 8 — hygiene

Phase count corrected to 13 in `phase_contracts.py`, `phase_dag.py`,
`runs/README.md`; `extension/README.md` points at `RUNNING.md`;
`benchmarks/commit0/README.md` no longer contradicts STATUS.md on the
offline run; STATUS.md's header and "Immediate next step" refreshed; CI's
push trigger narrowed to `main` so `v*` branches with an open PR stop
running every job twice.

## Deviations from the plan and spec

Recorded because v0.1.4's FR-RL-010 deviation went unrecorded until it
became a v0.1.5 feature.

1. **FR-FL-005 wording vs. architecture step 6 — resolved toward the
   architecture.** The spec says "the write-set for a cluster is its
   candidate set"; the architecture says the write-set is the *selected*
   files. Implemented as: the candidate set is the permitted write
   *boundary*, the selected file is what is written. Repairing all four
   candidates per cluster would have quadrupled token cost for no benefit,
   and each completion emits one file, so the boundary holds by
   construction. The spec sentence should be reworded in v0.1.6.
2. **`candidates.build()` signature.** Blueprint specified
   `build(cluster, index, basename_file)`; implemented as
   `build(cluster, index)`, reading `cluster.file` directly — it *is* the
   basename result, and passing it separately invites the two disagreeing.
3. **`AstIndex` is pydantic with `arbitrary_types_allowed`**, because it
   carries `ast.Module` objects. It is an in-process value, never
   serialized.
4. **The collect-only gate is wired for `real` execution only** (`app.py`),
   not by default in `ArtifactValidator`. The offline transport writes
   placeholder artifacts by design, so a collection gate would fail every
   offline plumbing run for a reason that says nothing about plumbing —
   and it doubled suite time by spawning pytest. FR-QT-004 is satisfied
   where it matters; the exemption is explicit rather than incidental.
5. **`RepairRoundCompleted` count keys are `tests_passed`/`tests_failed`/
   `tests_collected`**, not `passed`/`failed`/`collected`: the event
   already carried a *boolean* `passed` (did the suite go green) and
   reusing the name would have silently changed its type.
6. **FR-QT-005 (the no-weakening guard) is NOT implemented.** The repair
   loop's write-set is derived from failure clusters over the
   implementation phase's artifacts, so a generated test is not currently
   reachable as a repair target — the guard has nothing to guard yet. It
   becomes load-bearing only if the write-set is ever widened to `tests/`.
   Deferred to v0.1.6, stated here rather than discovered later.
7. **`anvil-instructions.md` is still duplicated** byte-for-byte at the
   repo root and in `workspace/`. Both are live in the resolution chain
   (`RUNNING.md:300-302`), so collapsing them is a behavior change, not a
   tidy-up. Left deliberately.
8. **The three tracked `.pptx` decks were left tracked**, and `.gitignore`
   was reconciled to match. Untracking them would delete deliberate
   deliverables from the repo for collaborators.

## Behavior changes to know about

- `repairContext` default moves `interfaces` → `slices`; `repairLocalization`
  defaults to `symbols`; `qaTests` defaults to `generate`. **The repair
  loop and the qa phase behave differently by default as of this release.**
  `ANVIL_REPAIR_CONTEXT=interfaces ANVIL_REPAIR_LOCALIZATION=basename
  ANVIL_QA_TESTS=plan-only` restores v0.1.4 exactly.
- `/v1/health` now returns `openhands: ok` and `mcp_discovery: not-wired`
  instead of `pending` for both.

## Still to do

- **Slice 9, the measurement (blocking for any claim about this release).**
  Commit0 tinydb median-of-3 under v0.1.4-identical conditions against the
  median 61/201 baseline; `evals/` smoke 6/6 measures #30; cachetools
  ≥ 177/215. Record gate flags per run. A null result is a reportable
  outcome — the 66% recovery figure bounds what becomes *visible* to the
  loop, not what gets fixed.
- `RUNNING.md` documentation for the three new knobs (deliberately deferred
  until the measurement says whether the defaults stand).
- v0.1.6 hand-off: the governance ring and Docker daemon validation
  together, drift report-only behind a flag; FR-QT-005; the FR-FL-005
  rewording.
