# Anvil Plan — v0.1.5

Ordered slices for the full v0.1.5 scope. Each slice ends with the full
suite green. Derived from [blueprint.md](blueprint.md).

Slices 1–3 are mechanical and provider-free; they can be verified against
the committed fixture before anything touches the repair loop. Nothing
score-affecting reaches the loop until slice 4.

1. **Test fixture** — commit
   `tests/unit/runtime/fixtures/junit-v0.1.4-fix-r3.xml`, trimmed from the
   real v0.1.4 report (`benchmarks/commit0/results/` is gitignored, so
   acceptance criterion 1 cannot run in CI without this). Preserve the
   assertion-failure shapes whose frames stay in test files and the
   `table.py`-implicated cluster. Blocking: slices 2 and 4 assert against
   it.

2. **Shared AST index** — `interface_map.index()` returning
   `AstIndex(symbols, edges, broken)`; `build()` gains the optional
   prebuilt index. Behavior-preserving refactor: the slice's own
   acceptance is `build(index=...) == build()` on existing cases, with no
   change to any current test's expectations.

3. **#28/#29 mechanics** — `verify/candidates.py` and `verify/slices.py`
   plus unit tests. Pure functions over `AstIndex`, no provider, no
   adapter changes yet. **FR-FL-008 is provable here**: against the
   fixture, the symbols candidate set is a superset of the basename
   result. If it is not, stop — that invariant is the release's guard
   against trading a correct narrow answer for a confident wrong one.

4. **Loop integration (#28/#29)** — adapter `localize()` rewrite,
   `_select_fault` completion, write-set union and dedupe,
   `UnlocalizedCluster` event, `_repair_prompt` slice block, config/env
   wiring for `repairLocalization` and `repairContext=slices`.
   `test_repair_loop.py` additions including the byte-for-byte `basename`
   and `interfaces` ablation checks. The silent drop at today's
   `openhands_adapter.py:799` is deleted in this slice.

5. **#31 telemetry** — `localize.try_parse_counts` + counts on
   `RepairRoundCompleted`. Small, and it lands before the measurement so
   the round series is observable while #28 is being evaluated.

6. **#30 qa code path** — `CODE_PHASES`, `_qa_targets`/`_qa_prompt`,
   `_write_files` fallback barred from `tests/`, collect-only validation,
   the FR-QT-005 no-weakening guard, `qaTests` gate. Commit0 adapter pins
   `plan-only` so the measurement surface is unchanged.

7. **Fixes #32–#35** — resume honors exclusions; retry counters persisted
   and restored; exhausted rounds distinguishable from phase failure;
   honest health. Each with its regression test.

8. **Hygiene** — `STATUS.md` header and superseded "Immediate next step";
   `benchmarks/commit0/README.md:79` vs `STATUS.md` on the offline run;
   `extension/README.md:25` dead `docs/QUICKSTART.md` link; the 12-vs-13
   phase discrepancy (`phase_contracts.py:5`, `phase_dag.py:6`,
   `runs/README.md:3`, the e2e test name); the duplicated
   `anvil-instructions.md`; tracked `.pptx` files; CI running twice per
   push on `v*` branches; required status checks on `main`.

9. **The measurement** (binding, proposal §Measurement protocol) — tinydb
   median-of-3 under conditions **identical to v0.1.4**: `open` profile,
   `local` executor, same instances, `qaTests=plan-only`. Beat median
   61/201 {47, 61, 134}; report the full distribution. Smoke suite 6/6
   (this is where #30 is measured, with `qaTests=generate`); cachetools
   ≥ 177/215. Record gate flags per run. If the delta demands
   decomposition, ablate: `ANVIL_REPAIR_LOCALIZATION=basename` (#28 off)
   and/or `ANVIL_REPAIR_CONTEXT=interfaces` (#29 off).

   **A null result is a real outcome and is reported as one.** The 66%
   recovery figure bounds what becomes *visible* to the loop, not what
   gets fixed.

10. **Close-out** — implementation log (including any spec deviation,
    stated as v0.1.4 stated FR-RL-010's), `RUNNING.md` for the three new
    knobs, `STATUS.md` run-log entries, and the v0.1.6 hand-off: the
    governance ring and Docker daemon validation, together, with drift
    report-only behind a flag.

## Ordering constraints

- Slice 1 blocks 3 and 4 (both assert against the fixture).
- Slice 2 blocks 3 (both new modules consume `AstIndex`).
- Slice 5 lands before 9 so the round series is observable during the
  measurement rather than reconstructed afterward.
- Slice 6 is independent of 2–5 and can proceed in parallel; it is inert
  on the Commit0 surface by construction (`plan-only`), so it cannot
  contaminate slice 9's number.
- Slice 9 runs only after 2–7 are green. No executor change and no
  governance wiring lands in this release, so the delta stays attributable
  to #28+#29.
