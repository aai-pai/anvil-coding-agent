# Anvil evaluation harness

A reusable Tier-1 benchmark for Anvil: it drives real Anvil runs over a suite
of greenfield tasks, grades each generated project against a **held-out**
pytest suite the agent never sees, and reports the leaderboard-shaped headline
number — **resolve rate (pass@1)** — alongside cost, latency, artifact
validity, and reliability signals mined from each run's audit trail.

Stdlib-only (plus pytest, which the repo already uses); nothing to install.

## Quickstart

```powershell
# From the repo root.

# 1. Self-test the harness plumbing (no API key; placeholder output, so 0%
#    resolve rate is expected — this proves the pipeline, not quality):
python evals/run_eval.py run --suite smoke --start-server --mode offline-llm

# 2. The real benchmark (needs your OpenRouter key; a few cents per task):
$env:OPENROUTER_API_KEY = "sk-or-..."
python evals/run_eval.py run --suite smoke --start-server --mode real --label v0.1.2 --pricing evals/pricing.json

# 2b. The v0.1.3 acceptance run: each prompt is submitted WITHOUT its
#     per-task anvil-instructions.md, so the prompts' <!-- anvil:contract -->
#     markers must carry the interface alone (#20 replaces the workaround).
#     Must hold 6/6:
python evals/run_eval.py run --suite smoke --start-server --mode real --label v0.1.3 --no-task-instructions --pricing evals/pricing.json

# 3. Compare two releases:
python evals/run_eval.py compare evals/results/<old>/results.json evals/results/<new>/results.json

# Other commands:
python evals/run_eval.py list --suite smoke          # show a suite's tasks
python evals/run_eval.py run --suite smoke --task celsius-cli ...   # subset
python evals/run_eval.py run --suite smoke --base-url http://127.0.0.1:8765  # reuse a running server
```

Results land in `evals/results/<timestamp>-<label>/` (gitignored):
`results.json` (machine-readable, feed to `compare`), `report.md` (human
summary with per-task table and failure tails), plus each task's isolated run
workspace and held-out test sandbox for debugging.

For cost estimates, copy `pricing.example.json` to `pricing.json`, fill in
blended $/1M-token rates from openrouter.ai/models, and pass `--pricing`.

## What is measured

| Metric | Source | Meaning |
|---|---|---|
| **Resolve rate (pass@1)** | held-out pytest | % of tasks where the run completed AND every held-out acceptance test passed, unattended (`yolo`), first try |
| Completion rate | run status | % of runs the pipeline finished (no escalation/timeout/pause) |
| Tokens + est. cost | `TokenUsageReported` + `ModelRouteSelected` events | per-phase tokens x the routed model's price |
| Wall-clock | harness + event timestamps | per task and per phase |
| Artifact validity | generated `docs/` | OKF frontmatter (`type`+`title`), lineage fields, `docs/index.md` presence |
| Complexity match | `ComplexityAssessed` event | assessed tier vs the task's `expected_complexity` (soft check; unassessed runs are excluded, not counted as mismatches) |
| Reliability | events + `docs/failure_records/` | escalations, artifact validation failures, input truncations, failure records |

## Scoring logic

The verdict chain, per task (code: [`runner.py`](anvil_eval/runner.py) →
[`scoring.py`](anvil_eval/scoring.py) → [`report.py`](anvil_eval/report.py)):

1. **Run the task** — the prompt is submitted as a `yolo` run and driven
   phase-by-phase until it reaches a terminal status (`completed`,
   `escalated`, `stopped`) or the per-task timeout (`runner.py`).
2. **Execute the held-out tests** — `scoring.run_held_out_tests()` copies the
   task's `held_out_tests/` into a sandbox, puts the generated `src/` on
   `sys.path`, exports `ANVIL_GENERATED_SRC`/`ANVIL_RUN_DIR`, and runs pytest.
   Pass = exit code 0, at least one test collected, zero failures/errors.
3. **Resolved** = run status `completed` **AND** step 2 passed. This is the
   only input to the headline resolve rate — the qa phase grading its own
   generated tests never counts, and a run that "finished" but produced
   broken code scores as unresolved.
4. **Secondary metrics** are mined independently: `analyze_events()` reads
   the run's `logs/events.jsonl` (tokens per phase, model routing, timings,
   complexity tier, escalations/truncations); `check_artifacts()` inspects
   the generated `docs/` (OKF frontmatter, lineage fields, `index.md`,
   failure records). `report.aggregate()` rolls everything up into the
   suite-level summary in `results.json` / `report.md`.

## The smoke suite (6 tasks)

| Task | Expected complexity | Contract (what the prompt pins) | Held-out pass criteria |
|---|---|---|---|
| `celsius-cli` | simple | `src/convert.py` with `celsius_to_fahrenheit(c)`; CLI prints the value | 3 tests: correct conversions (0→32, 100→212, −40→−40, 37→98.6); `ValueError` below −273.15; `python convert.py 100` prints `212.0` |
| `usd-cents` | simple | `src/currency.py` with `usd_to_cents()` / `cents_to_usd()`, Decimal-based | 4 tests: basic conversions; half-up rounding immune to float artifacts (1.005→101, 2.675→268); negative raises `ValueError`; `cents_to_usd(101) == "$1.01"` |
| `slugify` | simple | `src/slugger.py` with `slugify(text, max_length=None)`, exact slug rules | 4 tests: canonical slugs; collapses/strips hyphen runs; empty-string cases; `max_length` truncates without a trailing hyphen |
| `password-strength` | simple or standard | `src/password_strength.py` with `assess(pw) -> {"score", "issues"}`, 4 pinned rules | 5 tests: score 4 with empty issues; score 0 with 4 issues; exact partial scores; invariant `score + len(issues) == 4`; `TypeError` on non-string |
| `todo-cli` | standard or complex | `src/todo.py` CLI (`add`/`list`/`done`), `TODO_DB_PATH` env var, pinned JSON storage schema `{"id", "title", "done"}` | 5 tests (drive the CLI as a subprocess, assert on the JSON file): add writes the exact schema; ids increment; `list` shows titles; `done` flips the flag; unknown id → non-zero exit + stderr |
| `inventory-lib` | standard or complex | `src/inventory.py` `Inventory` class: add/remove with validation, `get_quantity`, `total_value`, `save`/`load` | 7 tests: add+query; re-add accumulates qty and updates price; add validation (`ValueError`); remove + depletion deletes the item; remove validation; `total_value` arithmetic; JSON save/load round-trip preserves state |

Expected complexity is a *soft* check against the proposal phase's
`ComplexityAssessed` tier — it feeds the complexity-match metric but never
gates resolution. Full contracts live in each task's `prompt.md`; the exact
assertions in its `held_out_tests/`.

## Suite layout / adding tasks

```
evals/suites/<suite>/<task-id>/
    task.json          # {"id", "title", "expected_complexity": [...], "tags",
                       #  optional "timeout_s", "pytest_timeout_s"}
    prompt.md          # the build request; copied verbatim into the run as
                       # background-information.md (source_path flow, #17)
    held_out_tests/    # pytest files; NEVER shown to the agent
        test_*.py
```

Task-authoring rules:

1. **Pin the interface contract in `prompt.md`** — exact file names under
   `src/`, function signatures, storage formats, CLI behavior. The held-out
   tests bind to that contract; an unpinned contract makes failures
   meaningless. (This is standard benchmark practice — SWE-bench pins via the
   repo, HumanEval via the signature.)
2. `prompt.md` needs a `#` heading — it seeds the run's slug.
3. Held-out tests reach the generated project two ways:
   - the run's `src/` is on `sys.path` (an injected conftest does this), so
     `import convert` just works;
   - `ANVIL_GENERATED_SRC` and `ANVIL_RUN_DIR` env vars point at the run for
     subprocess/file-based assertions (see `todo-cli` for the pattern).
4. Prefer asserting on pinned data formats (JSON files, return values) over
   stdout formatting; leave presentation flexible in the contract.
5. `expected_complexity` lists the tiers you'd accept from the proposal
   phase's assessment; it's scored but never gates resolution.

Grow the suite toward 20-50 tasks across tiers for stable
release-over-release numbers.

## Interpretation notes

- **Run modes:** `--mode offline-llm` validates the harness and pipeline
  wiring (placeholder artifacts, resolve rate 0 by design). Only `--mode
  real` produces meaningful quality numbers.
- **pass@1 variance:** LLM output varies run to run; on a small suite one
  flipped task moves the rate by ~17 pts. Compare releases on the same suite,
  and prefer more tasks over repeated runs.
- **Security:** held-out tests execute the *generated* code on your machine.
  That is inherent to acceptance testing; review suites before running
  untrusted prompts.
- The harness talks only to the documented REST surface
  (`POST /v1/runs?defer=true` + `/advance`), so it keeps working as runtime
  internals evolve; each task runs in a fresh isolated workspace under the
  results directory and never touches the repo's own `workspace/` or `runs/`.
