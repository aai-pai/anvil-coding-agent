# Anvil v0.1.4 — Implementation Log

What has shipped so far, where it lives, and how it was verified.
Requirements: [spec.md](spec.md); rationale: [proposal.md](proposal.md).

## Code map

### #23 — Bounded external-test repair loop (FR-RL-001..011) — DONE

- `config/schema.py` — `externalTestCommand` (default None = loop absent),
  `repairMaxRounds` (2), `testTimeoutS` (600); `app.py` wires
  `ANVIL_TEST_COMMAND` / `ANVIL_REPAIR_MAX_ROUNDS` / `ANVIL_TEST_TIMEOUT_S`
  (env > config > default).
- New `runtime/anvil_runtime/verify/runner.py` — `run_external_tests`
  (shell command in the run workspace, bounded, output captured),
  `compile_smoke` (round-zero syntax check), `implicated_files`
  (deterministic failure→file mapping by basename/relative path).
- `sdk/openhands_adapter.py` — `_verify_and_repair` (smoke → run → map →
  per-file repair → #21 re-validation → re-run, bounded; exhausted rounds
  fail the step with the last output tail); `_repair_prompt` (current
  source + failure excerpt + contract block, fix-in-place); events
  `ExternalTestsPassed/Failed`, `RepairRoundStarted/Completed`. Intake
  refuses a configured command for non-`open` runs (FR-RL-003) using the
  **run's** profile, threaded per dispatch (`phase_context.security_profile`
  — the manager-level config profile is only a fallback; caught by e2e).

### #25 — Docker-isolated test execution (FR-DX-001..002) — DONE

Scope pulled into v0.1.4 on 2026-07-24 (safety-motivated; design decisions
recorded in [background-information.md](../domain-knowledge/background-information.md)).

- `config/schema.py` — `testExecutor` (`local`|`docker`, default `local`),
  `testImage` (default `python:3.11-slim`), `testSetupCommand`; `app.py`
  wires `ANVIL_TEST_EXECUTOR` / `ANVIL_TEST_IMAGE` /
  `ANVIL_TEST_SETUP_COMMAND` (env > config > default).
- New `runtime/anvil_runtime/verify/docker_executor.py` — `DockerExecutor`
  (one hardened long-lived container per verification pass, `exec` per
  round), `docker_probe`, `DockerError`. Isolation: copy-in/copy-out (no
  bind mount — the container can never write to the host workspace);
  network only during setup, disconnect is fail-closed; `--memory`/
  `--cpus`/`--pids-limit`/`--cap-drop=ALL`/`no-new-privileges`; host-side
  timeout force-removes the container. Driven via the docker CLI through
  an injectable `exec_fn` seam (no new dependency).
- `sdk/openhands_adapter.py` — intake policy (FR-DX-002): `docker` +
  unusable daemon fails at intake with the probe's reason; `local` under a
  non-`open` profile still refused, message now names the docker
  alternative. `_verify_and_repair` binds a `run_tests` closure over the
  chosen executor; `DockerError` fails the step with its own reason (never
  conflated with a red test run); container cleanup in `finally`;
  `DockerExecutorSelected` event.

### #26 — Structured failure localization (FR-JL-001..005) — DONE

- New `runtime/anvil_runtime/verify/localize.py` — `{junit_xml}` token
  substitution (canonical report `.anvil/junit-report.xml`),
  `try_parse_report` (stdlib etree; missing/malformed → None, never
  raises), clustering by (error type, implicated file) size-desc,
  `cluster_excerpt` (≤3 representative failures per cause).
- `sdk/openhands_adapter.py` — `_verify_and_repair` substitutes the token
  once per pass, deletes any stale report before every run
  (`run_tests_fresh`), localizes red runs via clusters (implication order
  = largest cause first; per-file prompts get the cluster summary instead
  of the raw tail), `RepairRoundStarted` carries the cluster summary,
  degraded paths (`JunitReportMissing` warning → basename fallback).
- `verify/docker_executor.py` — `run(..., copy_out_rel=...)`: best-effort
  copy-out of the report, the only copy-out beyond exit code and output.
- No token in the command → first-iteration behavior byte-for-byte (the
  ablation lever; no config field).

### #27 — Interface-aware repair context (FR-IC-001..004) — DONE

- New `runtime/anvil_runtime/verify/interface_map.py` — one `ast` pass per
  sibling artifact: signatures (incl. defaults/annotations), class
  attributes, one-line docstrings; connection ranking (imports of the
  failing file first, importers second, rest last); cap (6,000 chars)
  drops whole least-connected files with an omission note; syntax-broken
  sibling listed as `(currently broken)`. Bodies never emitted.
- `sdk/openhands_adapter.py` — `_repair_prompt` injects the map + the
  functional-harmony instruction between contract and failure excerpt;
  gate `repairContext: interfaces|minimal` (`ANVIL_REPAIR_CONTEXT`),
  `minimal` skips the block for ablation. Applies to compile-smoke
  repairs too. Write-set unchanged (FR-RL-008).

### Repair-prompt persistence (post-measurement addition, 2026-07-25) — DONE

- `_persist_repair_prompt` in `sdk/openhands_adapter.py`: every repair
  completion's prompt is written verbatim to
  `logs/repair-prompts/NNN-<file>.md` before the LLM call. Rationale:
  repair prompts are assembled per file per round from moving parts
  (junit clusters, sibling interface map, current source) and were
  memory-only — unreproducible after the run. Observability only; no
  prompt content change (measurement unaffected). Suite: **397**.

### #24 — Per-artifact advance granularity (FR-AG-001..004) — DONE

- `PhaseProgress` events per artifact/repair stage (backend, FR-AG-001).
- `PhaseCompleteEvent.phase_complete` / `StepResult.phase_complete` — a
  successful unit of an in-progress phase; `RunState.phase_progress` — the
  mid-phase checkpoint (FR-AG-003).
- `core/development_manager.py` — implementation dispatches in unit mode
  (`completed_artifacts` threaded per dispatch); `_record_unit` checkpoints
  each unit + emits `PhaseUnitCompleted`; completion/rollback clear
  progress; resume rehydrates it. `PhaseStarted` announces once per phase,
  not per unit.
- `sdk/openhands_adapter.py` — `_run_code_unit`: next ungenerated artifact,
  or (all present) the verification/repair pass as the final unit;
  `_generate_one` shared with whole-phase #22 generation. Single-shot mode
  (no derivable file list) still completes in one advance (FR-AG-004).

## Verification

- **392-test suite green** — 19 new for #23/#24 since v0.1.3's 343
  (`test_repair_loop.py` 10, `test_advance_granularity.py` 4,
  `test_temperature.py` 5 from the variance experiment) + 14 for #25
  (`test_docker_executor.py` 9 — the CLI call sequence *is* the security
  posture; `test_repair_loop.py` 5 more — profile unlock, probe refusal,
  loop integration, infra-failure cleanup) + 16 for #26/#27
  (`test_localize.py` 7, `test_interface_map.py` 5, `test_repair_loop.py`
  4 more — cluster-driven implication with stdout that never names the
  file, `minimal` ablation gate, missing-report degradation, docker
  report copy-out); zero regressions. All #25 tests fake the docker CLI
  seam; no test needs a docker daemon.
- **E2E (offline, via the API)**: markered run completes and seals;
  manifest-violating run still escalates (#21 intact); green-command run
  completes with `ExternalTestsPassed`; restricted-profile run with a
  command escalates at intake with the reason in the failure record.

### Commit0 adapter integration (spec §3) — DONE (plan slice 4)

- `prepare.py` — staging now snapshots the repo's original test files
  (`commit0-meta.json`: package rel/name + test list, test-pattern files
  only) and keeps a pristine package copy (`.commit0-pristine/`). The
  pristine copy is load-bearing: the graft fills only STUB bodies, so
  repairs can never propagate through an already-grafted package.
- New `graft_and_test.py` — the repair-signal entry point Anvil runs as
  `externalTestCommand` (cwd = run workspace): restore the staged package
  from pristine → `apply_generated` in place → run the snapshot tests
  with score.py's proven invocation shape → write the `{junit_xml}`
  report #26 reads → exit with pytest's code. The repair signal tests
  exactly what scoring tests. **Real-run lesson (2026-07-24)**: the first
  version grafted onto a scratch package and relied on sys.path ordering;
  in the real tinydb run pytest's conftest loading resolved the STAGE
  skeleton anyway (dangling `_immutable` NameError → pytest exit 4, no
  junit report, loop repaired blind — runs r1/r2 at 22:30/23:00 invalid).
  Fixed to in-place restore+graft; validated against the failed run's
  stage: 201 collected, real failure tracebacks.
- `score.py` — `test_files` param: scoring runs only the snapshot (qa-leak
  fix); no snapshot → old whole-dir behavior.
- `apply.py` — `exclude_dir` param (scratch grafting for src-layouts).
- `cli.py` — spawned servers get `ANVIL_TEST_COMMAND` (entry point +
  token) and `ANVIL_TEST_TIMEOUT_S`; `--no-repair` flag for one-shot /
  ablation runs; the whole-run-budget advance-timeout workaround is
  replaced by a principled per-unit bound
  (`(rounds+1) × test_timeout + slack` — the verify/repair unit is the
  longest single advance); both score calls use the snapshot.
- Tests: `tests/unit/benchmarks/test_commit0_repair_integration.py` (4,
  real pytest subprocesses over a miniature skeleton repo) — snapshot
  meta + pristine written; qa-generated test never enters the score;
  green graft-and-test leaves the skeleton untouched; **a repair
  propagates through the pristine re-graft** (the in-place graft would
  have silently pinned the first wrong body forever). Suite: **396**.

## The measurement (plan slice 6) — DONE 2026-07-25

All acceptance criteria met (local executor, `open` profile,
`ANVIL_REPAIR_CONTEXT=interfaces`, `{junit_xml}` active):

1. **tinydb median-of-3: {47, 61, 134} of 201 — median 61 (30.3%)** vs
   the v0.1.3 one-shot baseline median 24 (11.9%), distribution
   {0, 19, 24, 60, 78}. Median beaten 2.5×; **import-fail arm deleted**
   (floor 47 vs 0). Junit signal healthy in every round
   (`JunitReportMissing` 0 across all runs). Cost 386–460k tokens/run
   (~2.7× one-shot), 32–44 min wall.
2. **cachetools 177/215 (82.3%)** — holds the v0.1.3 bar exactly (64k
   tokens).
3. **Smoke suite 6/6 (100%), no command configured** — avg 18k
   tokens/task; the opt-in default leaves v0.1.3 behavior intact.

Spec deviation noted: FR-RL-010's "pass movement where parseable" is not
on `RepairRoundCompleted` (exit code only); pass movement is derivable
from the per-round cluster counts instead. Carried to v0.1.5 as a
refinement, not a blocker.

First-batch lesson (2026-07-24, runs `v0.1.4-r1/r2` INVALID): the v1
scratch-package entry point let pytest resolve the stage skeleton via
conftest loading — exit 4, no report, loop repaired blind. Fixed to
in-place restore+graft (see adapter section); the failure and fix are in
STATUS.md's run log.

## Still to do in this cycle

- **Real-docker smoke** (manual, once): offline-llm run with
  `ANVIL_TEST_EXECUTOR=docker` to validate the CLI assumptions the fakes
  encode. Blocked 2026-07-24: no docker CLI on the dev machine — needs
  Docker Desktop installed; the measurement did not depend on it.
