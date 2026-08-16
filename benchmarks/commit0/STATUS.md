# Commit0 × Anvil — status, findings, and future work

*Last updated: 2026-08-15. This document is the handoff record of the Commit0
testing/fixing arc: what was built, what each run found, what was fixed, and
what comes next. Read alongside [README.md](README.md) (usage) and
[evals/README.md](../../evals/README.md) (the Tier-1 harness this builds on).*

> **2026-07-24 — v0.1.4 runtime + adapter integration complete (396 tests).**
> The verified repair loop is a bundle: #23 (bounded repair loop), #25
> (docker-isolated execution — safety-motivated; `local` remains the
> measurement default), #26 (junit clustering — repair by root cause), #27
> (interface-aware repair prompts — passing files' signatures travel with
> every resubmission). Adapter side (spec §3, all landed): staging snapshots
> the original test files (qa-generated tests can never enter the repair
> signal or the score), `graft_and_test.py` is the repair-signal entry
> point (pristine re-graft per round — an in-place graft would pin the
> first wrong body forever), and the long-advance timeout workaround is
> replaced by a per-unit bound. One-shot/ablation lever: `--no-repair`.
> **The v0.1.4 measurement (tinydb median-of-3 vs baseline median 24/201)
> is the next real-key step**; docs in
> [anvil-development/v0.1.4/docs/](../../anvil-development/v0.1.4/docs/).

> **2026-07-25 — v0.1.4 MEASURED. tinydb median-of-3 with the repair loop:
> {47, 61, 134} of 201 — median 61 (30.3%) vs one-shot baseline median 24
> (11.9%). Import-fail arm deleted (floor 47 vs baseline floor 0; the
> worst repaired run beats 3 of 5 baseline runs). cachetools holds at
> 177/215 (82.3%). Smoke suite 6/6 with no command (avg 18k tokens/task —
> opt-in default intact). Cost: ~420k tokens/run vs 154k one-shot (~2.7×)
> for 2.5× the median.** All acceptance criteria met. Details in the run
> log below.

> **2026-07-12 — v0.1.3 implemented.** #20 (contract/context split), #21
> (mechanical contract validation), and #22 (skeleton-aware per-artifact
> implementation) are now in Anvil core (343 tests green; see the
> [implementation log](../../anvil-development/v0.1.3/docs/implementation-log.md)).
> Adapter side: the staged task file is contract-markered, emits a
> `contract-manifest`, and pre-stages work modules under `src/`; spawned
> servers get `ANVIL_CONTRACT_MAX_CHARS=48000`. Two behavior changes to know:
> the **offline plumbing run now escalates at implementation** (the #21
> validator correctly refuses placeholder output against the manifest — that
> escalation *is* the plumbing proof), and the real-run command below should
> use label `v0.1.3`. The measurement itself is still blocked on
> `OPENROUTER_API_KEY`.

## Positioning (agreed strategy)

Commit0 is **the gym, not the podium**: three real runs each exposed a real
Anvil defect, but the benchmark grades none of Anvil's differentiators
(intake, complexity gating, governed docs) and structurally rewards the
agentic edit-run-repair loop Anvil doesn't have yet. The benchmark portfolio:

| Tier | Benchmark | Role |
|---|---|---|
| Regression gate | `evals/` smoke suite (6 tasks, 28 held-out tests) | run per release, compare resolve rate |
| Capability driver | **Commit0, small repos** (this adapter) | forces skeleton-awareness + test-repair (#2) |
| Identity showcase | DevBench / WebGen-Bench (future) | grades request→project + design docs — Anvil's actual story |
| Endgame | SWE-bench Verified (future) | the leaderboard; needs #2 matured into the OpenHands adapter |

## What was built

`benchmarks/commit0/` — adapter-only (policy: **no benchmark forks of Anvil**;
anything the benchmark needs that Anvil lacks becomes a versioned core
feature, never a special branch). Pipeline per repo:

1. **fetch** — clone stubbed skeleton (`github.com/commit-0/<repo>` branch
   `commit0_combined`; bodies are `pass`, signatures/docstrings intact).
2. **prepare** — stage a workspace: AST **stub inventory** (+ per-module
   "MUST ALSO DEFINE" dangling references) + `docs/*.rst` spec excerpts into
   `background-information.md`; fidelity `anvil-instructions.md` alongside
   (that file's content is frozen by team decision — do not edit it).
3. **run** — stock in-place Anvil run over REST (`AnvilClient.start_run_in_place`).
4. **apply** — **AST graft** (`graft.py`): skeleton file kept as shipped; only
   stub bodies transplanted from same-qualname generated functions; missing
   methods inserted into existing classes; missing imports added. Replaced
   the v1 whole-file copy, which destroyed skeleton-provided code.
5. **score** — repo's own pytest suite locally; `collection_error`
   distinguishes "can't import" from "ran and failed". Official numbers need
   the real `commit0` evaluator (docker/modal) — local is the dev loop.

Loop verified end-to-end: reference implementation pushed through
apply+score = **201/201 tests** on tinydb; untouched skeleton = import-fail
(that's the true baseline — skeletons don't even import).

## Run log and findings (all on tinydb)

| Run (results dir label) | Outcome | Finding → fix |
|---|---|---|
| `v0.1.2` (2026-07-11 02:13) | **escalated** at specification, 3× `finish_reason=length` | Output token budgets were hardcoded (400/1500/4000). → **#19, shipped in core**: config fields + `ANVIL_INTAKE/DOC/CODE_MAX_TOKENS` env overrides (mirrors #18); adapter spawns servers with doc 6000 / code 16000 / input 80k. 272 tests green. |
| `v0.1.2` rerun with #19 (02:46) | **completed 9 phases**, 8 modules generated, 7 named correctly, 48/50 stub bodies present — but import-fail | Implementation regenerates whole files from plan docs (never reads skeleton) → dropped provided code (`QueryLike`, `FrozenDict`, `LRUCache`, `MemoryStorage`, `__all__`). → adapter **graft v2** (AST body transplant); rescoring the same run's saved output: 48 bodies grafted cleanly. |
| graft rescore (offline, same output) | import-fail, one level deeper | Commit0's stripper sometimes deletes a whole definition leaving a dangling reference (`__setitem__ = _immutable`, `def _immutable` gone) — invisible to stub scans, so Anvil was never asked to write it. → inventory now emits **"MUST ALSO DEFINE"** via a pyflakes-lite pass (verified: flags `_immutable`). |
| `v0.1.3` first attempt (2026-07-13 00:22) | client-side **timeout mid-implementation** (5 modules generated at ~70s each, run healthy) | #22 made one `/advance` a many-completion call; the adapter's 600s per-advance client timeout killed it. → adapter gives an advance the full per-repo budget (`--timeout`). |
| **`v0.1.3` (2026-07-18 18:35)** | **completed 9 phases** (intake→qa), 7/7 modules generated per-artifact, **50/50 stub bodies grafted, 0 unmatched**, model defined `_immutable` as demanded, 153,848 tokens — but still import-fail | Graft bug, not a generation failure: missing module-level defs were inserted at **end-of-file**, and `__setitem__ = _immutable` executes in a *class body* at import time → NameError before the def. → graft fix: insert a dangling def **before its first referencing top-level statement**. Offline rescore of the same output: **package imports; 24/201 tests pass (11.9%)** — Anvil's first real Commit0 number. |

| `v0.1.3-validation` tinydb (2026-07-18 21:12) | **imports end-to-end, 78/201 (38.8%)** — first run to produce a pass rate with no rescore step | Confirms the graft fix in the loop. Also calibrates one-shot variance: two independent v0.1.3 runs scored 24/201 and 78/201 — same pipeline, different generations. |
| `v0.1.3-validation` cachetools (2026-07-18 21:12) | reported 0/2 "import-fail" — but the harness had scored the INSTALLED site-packages cachetools, not the staged repo | cachetools is a **src-layout** repo (`src/cachetools/`): `score.py` put only the stage root on `PYTHONPATH`, so `import cachetools` resolved to anaconda's 5.3.3; `apply.py` also swept the in-src package as "generated" and grafted it onto itself. → both fixed (importable root = package parent dir; package-internal files excluded from apply). Offline rescore of the same output: **177/215 (82.3%)** — all 10 stubs in 2 modules generated and grafted cleanly; failures are one `func.py` decorator-attribute cluster (~37) + one `typedmethodkey` assertion. |

| `v0.1.4-r1`/`-r2` (2026-07-24 22:30/23:00) | **INVALID as measurements** — 18/201 and 0/0; every repair-signal run died with pytest exit 4, no junit report, loop repaired blind | Harness bug, not Anvil: `graft_and_test.py` v1 grafted onto a scratch package and relied on sys.path ordering; pytest's conftest loading resolved the STAGE skeleton anyway (dangling `_immutable` NameError at collection). → entry point rewritten to restore-from-pristine + graft **in place**, using score.py's proven invocation; validated offline against the dead run's stage (201 collected). |
| **`v0.1.4-fix-r1..r3` (2026-07-24/25) — THE v0.1.4 MEASUREMENT** | **{47, 61, 134} of 201 — median 61 (30.3%)** vs baseline median 24 (11.9%); zero import-fails; junit signal healthy every round (`JunitReportMissing` 0); repairs targeted utils/operations/storages per cluster | The repair loop does what it was built for: the catastrophic arm is gone (floor 47 vs 0) and the median is 2.5× the baseline. Cost 386–460k tokens (~2.7× one-shot). All runs end `escalated` — green requires the full 201-test suite, unreachable by design here; the score is the final repaired state. Two v0.1.5 leads: (1) the largest cluster every round is `file: null` (68–75 assertion failures whose tracebacks stay in test files — a test-file→module mapping heuristic would put them in play); (2) "rounds exhausted red" is the loop's *normal successful* exit on a benchmark, but reads as failure in run status. |
| `v0.1.4-cachetools` (2026-07-25) | **177/215 (82.3%)** — holds the v0.1.3 bar exactly; 64k tokens | High-baseline case does not regress with the loop in play. |

**Smoke suite `v0.1.4-smoke` (2026-07-25): 6/6 resolved (100%), avg 18,073
tokens/task, no `externalTestCommand` configured** — the opt-in default
leaves non-benchmark behavior intact (FR-RL-002 held in production).

**Temperature experiment (2026-07-18, 3× tinydb at `ANVIL_TEMPERATURE=0`,
labels `v0.1.3-temp0-r1..r3`):** scores 0 (import-fail), 0 (import-fail),
40/201 — pinning temperature 0 does **not** make runs converge and does not
help the mean. Generated modules still differ per run (5/7 files unique MD5s
across the three runs — OpenRouter/DeepSeek is not deterministic at temp 0:
provider routing + batched inference). The revealing part: r1 and r2
independently picked the *same wrong implementation idea* for the same
load-bearing function (`with_typehint` built as a decorator factory instead
of returning a `baseclass` subclass), and that single function killed both
runs at import (`class TinyDB(TableBase)` → TypeError). Full 5-run one-shot
picture on tinydb: **0, 0, 24, 40, 78 of 201** — a few make-or-break
functions dominate the outcome, catastrophic import failure is a real arm of
the distribution (2/5), and the fix is verification/repair (#23: even a
bare import-smoke check would have caught r1/r2), not sampler settings. The
`ANVIL_TEMPERATURE` knob stays (useful for controlled experiments) but is
not a measurement-variance remedy.

**v0.1.3 one-shot BASELINE (n=5, default temperature, 2026-07-18; labels
`v0.1.3`, `v0.1.3-validation`, `v0.1.3-default-r3..r5`): tinydb
{0, 19, 24, 60, 78} of 201 — median 24 (11.9%), import-fail 1/5.
cachetools 177/215 (82.3%).** This is the distribution v0.1.4's repair loop
(#23) must beat on the median AND tighten (delete the import-fail arm). Contract
transport did its job in every run — modules named correctly, every stub
filled, every demanded definition present. The remaining failures are
implementation-*correctness* defects, i.e. exactly the class #23's repair
loop (v0.1.4) exists to fix — and the tinydb variance itself is an argument
for #23, which converts "unlucky generation" into "one more repair round".
Dominant clusters from the first tinydb run's junit (`graftfix-junit.xml`):

- 73× `TypeError: keys must be str… not TinyDB` (table registry / storage
  serialization in `database.py` — one bug, 60 of these are fixture errors)
- 60× `RecursionError` (query/middleware delegation cycle)
- 16× `'str' object has no attribute 'read'` (storage file-handle handling)
- 10× `LRUCache` attribute contract (`.lru` / `.length`)

Four root causes likely account for ~160 of the 177 red tests — a strong
setup for measuring #23's delta.

Pattern across all three: **Anvil's code generation was never the problem** —
failures were budget plumbing, contract transport, and skeleton-blindness.

## Immediate next step

**v0.1.4's measurement is complete** (2026-07-25): median 61/201 (30.3%)
over the 24/201 baseline, distribution {47, 61, 134}, import-fail arm
deleted. See the run log above.

Next is **v0.1.5's**: the #28 fault-aware localization + #29 dependency-slice
bundle, measured against the median 61 baseline under *identical* conditions
(`open` profile, `local` executor, same instances, `qaTests=plan-only` so the
new qa test generation cannot touch this surface). Ablation levers:
`ANVIL_REPAIR_LOCALIZATION=basename` and `ANVIL_REPAIR_CONTEXT=interfaces`.

The motivating finding, re-derived from the stored v0.1.4 reports: the loop
was blind to the largest cluster in every round because assertion failures
name symbols rather than files, and `tinydb/table.py` — implicated in 20 of
28 recovered failures — was never once selected by hit count. A null result
is a reportable outcome; recovery bounds what becomes *visible*, not what
gets fixed.

## Future work

> **Now formalized:** the v0.1.3 proposal
> ([anvil-development/v0.1.3/docs/proposal.md](../../anvil-development/v0.1.3/docs/proposal.md))
> covers #19 (budgets, shipped), #20 (contract/context split — pinned
> contract block injected into every phase), #21 (mechanical contract
> validation), #22 (skeleton-aware per-artifact implementation). #23 (the
> bounded external-test repair loop) is **deliberately deferred to v0.1.4**:
> it fixes the defect class #20 prevents, so shipping both at once would
> make a green tinydb run unattributable — v0.1.3 is measured one-shot, and
> the repair loop is then measured as its own delta. The items below are
> the raw findings that fed the proposal.

### #2 — the core features Commit0 exists to force (v0.1.3+)
- **Skeleton-aware implementation mode**: the implementation phase must read
  the actual files it is filling (today its only inputs are `docs/plan.md` +
  `docs/blueprint.md` — see `PHASE_CONTRACTS` in
  `runtime/anvil_runtime/core/phase_contracts.py`), and emit completed
  versions instead of reconstructions. Likely per-module chunked generation
  (one completion per module) rather than one shot — also fixes the output-
  budget ceiling structurally.
- **External-test repair loop**: run a designated test suite, feed failures
  back, bounded retries (Anvil already has retry/self-heal machinery to hang
  this on). This is what Commit0's visible tests are *for*, and it's the
  same muscle SWE-bench requires.
- Considered and deliberately deferred: adding
  `domain-knowledge/background-information.md` to later phases'
  `input_files` (closes the contract-drift topology generally); a one-line
  `PHASE_CONTRACTS` change but affects every run's prompt sizes — treat as an
  explicit v0.1.3 design decision.

### Adapter/harness backlog (small)
- The per-artifact implementation phase (#22) makes one `/advance` a
  many-completion call (~70s/module observed on tinydb). The adapter now
  gives an advance the full per-repo budget (fixed 2026-07-13 after the
  first v0.1.3 run timed out mid-implementation at the client's old 600s
  cap); the *runtime-side* fix — advancing per artifact or reporting
  progress over SSE so clients keep a short timeout — is a v0.1.4 candidate.
- Scoring should run only the repo's *original* test files (snapshot the
  `tests/` list at staging) so Anvil's own qa-generated tests can't leak into
  the score.
- 2–3 more small repos (`STARTER_REPOS`: simpy, cachetools, voluptuous,
  wcwidth — NOT the official split) once tinydb produces a number.
- A/B lever already in place: `doc_chars` is recorded per run, so
  docstrings-only vs docstrings+docs is a one-line experiment in
  `prepare.py`.
- For leaderboard submission: official `commit0` evaluator (docker/modal) +
  official HF splits (`wentingzhao/commit0_combined`).

### Key files
```
benchmarks/commit0/commit0_adapter/   repos / stubs / prepare / cli / apply / graft / score
evals/anvil_eval/                     harness this reuses (client, server, events scoring)
runtime/.../sdk/openhands_adapter.py  #19 budgets (LLMBackend), doc/code prompts
runtime/.../core/phase_contracts.py   per-phase input_files (the drift topology)
tests/unit/runtime/test_output_budgets.py   #19 coverage
```
