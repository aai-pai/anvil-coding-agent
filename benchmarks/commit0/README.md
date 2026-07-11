# Commit0 adapter for Anvil

Runs Anvil on [Commit0](https://commit-0.github.io) tasks: real Python
libraries whose function bodies were stripped to `pass` (signatures and
docstrings intact), graded by each library's own unit-test suite. This is
Anvil's nearest public benchmark — spec in, working library out — and this
adapter is deliberately **adapter-only**: no Anvil core changes, so scores
reflect Anvil as users get it.

## Quickstart

```powershell
# From the repo root.

# Plumbing self-test (no key; placeholder output scores ~0 by design):
python benchmarks/commit0/run_commit0.py run --repo tinydb --start-server --mode offline-llm

# Real run:
$env:OPENROUTER_API_KEY = "sk-or-..."
python benchmarks/commit0/run_commit0.py run --repo tinydb --start-server --mode real --label v0.1.2 --baseline

# Several repos, against an already-running server:
python benchmarks/commit0/run_commit0.py run --repo tinydb --repo cachetools --base-url http://127.0.0.1:8765
```

Results land in `benchmarks/commit0/results/<stamp>-<label>/` (gitignored):
`results.json` + `report.md`, plus each repo's staged workspace (Anvil's docs,
the merged package, junit XML) for debugging.

## Pipeline (one repo)

1. **fetch** — clone the stubbed skeleton: `github.com/commit-0/<repo>`,
   branch `commit0_combined` (cached under `skeletons/`).
2. **prepare** — stage a disposable copy and generate:
   - `domain-knowledge/background-information.md` — the task, with an
     AST-extracted **stub inventory** (every unimplemented function's module
     path, signature, docstring line) as the pinned contract;
   - `domain-knowledge/anvil-instructions.md` — fill-the-skeleton fidelity
     rules (the mechanism that took the smoke suite 50% → 100%).
3. **run** — task-less in-place Anvil run (`POST /v1/runs` with `workspace`
   only), driven phase-by-phase in yolo mode.
4. **apply** — merge Anvil's generated `src/*.py` onto the package: exact
   relative path first, else unique basename; files that don't parse as
   Python are skipped. Unmatched output is *reported, not guessed* — a low
   applied-count is a real finding about contract adherence.
5. **score** — run the repo's own pytest suite (current environment, staged
   repo first on `sys.path`). Reports pass rate, plus `collection_error`
   when the package can't even be imported (the skeleton's natural state).

Verified end-to-end: offline run completes all 13 phases on the tinydb
skeleton; injecting the reference implementation through steps 4–5 yields
10/10 modules applied and 201/201 tests passing.

## What to expect, honestly

- The stub skeleton usually **fails at import** (stubs break module-level
  code), so the baseline is 0% with `collection_error` — implementing enough
  to import is part of the task.
- First real Anvil scores will be **low**. Anvil's implementation phase
  generates from its own plan docs; producing complete, correctly named
  modules for a ~50-stub library in one shot is exactly the capability gap
  this benchmark is meant to expose. Expected failure modes to triage:
  missing modules (unmatched/apply=0), partial files, hallucinated structure.
  Those findings should become Anvil core features (skeleton-aware
  implementation mode, external-test repair loop), shipped as normal
  releases and regression-guarded by `evals/`.
- The **local score is a dev-loop proxy**: it runs tests in your Python
  environment, so repos needing heavy dependencies may not score locally
  (`STARTER_REPOS` in `repos.py` lists light ones; it is *not* the official
  split). Leaderboard submissions must use the official evaluator
  (`pip install commit0`; `commit0 setup / test / evaluate` with its
  docker/modal backends) against the official splits from the
  `wentingzhao/commit0_combined` dataset.
- Generated code is executed by the test run — same caveat as `evals/`.

## Files

```
benchmarks/commit0/
    run_commit0.py            launcher (wires evals/anvil_eval + this package)
    commit0_adapter/
        repos.py              skeleton fetch + package-dir detection
        stubs.py              AST stub inventory + markdown rendering
        prepare.py            workspace staging + task/instructions generation
        cli.py                orchestration, results.json / report.md
        apply.py              generated-src -> package merge policy
        score.py              local pytest scoring
    skeletons/                cached clones (gitignored)
    results/                  run outputs (gitignored)
```
