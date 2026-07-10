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

A task is **resolved** only if the run reached `completed` *and* all of its
held-out tests pass — the qa phase grading its own generated tests never
counts.

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

The starter `smoke` suite has 6 tasks (3 simple, 3 standard-ish). Grow this
toward 20-50 tasks across tiers for stable release-over-release numbers.

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
