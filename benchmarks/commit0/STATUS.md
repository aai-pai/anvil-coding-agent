# Commit0 × Anvil — status, findings, and future work

*Last updated: 2026-07-11. This document is the handoff record of the Commit0
testing/fixing arc: what was built, what each run found, what was fixed, and
what comes next. Read alongside [README.md](README.md) (usage) and
[evals/README.md](../../evals/README.md) (the Tier-1 harness this builds on).*

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

Pattern across all three: **Anvil's code generation was never the problem** —
failures were budget plumbing, contract transport, and skeleton-blindness.

## Immediate next step (blocked on OPENROUTER_API_KEY)

One fresh real run now that the inventory demands `_immutable` and graft
preserves the skeleton:

```powershell
$env:OPENROUTER_API_KEY = "sk-or-..."
python benchmarks/commit0/run_commit0.py run --repo tinydb --start-server --mode real --label v0.1.3-graft --baseline
```

Realistic outcomes: the package imports and we get the **first real pass
rate** over 201 tests; or a next-layer import error appears (triage via the
`output_tail` in results.json + `logs/events.jsonl` in the staged repo).
The honest-adapter budget is now spent — whatever this scores, remaining
gaps are core work.

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
