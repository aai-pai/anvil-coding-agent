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

## Still to do in this cycle (plan.md slices 4–7)

- **Commit0 adapter integration** (spec §3): staging-time snapshot of the
  original test files; an adapter-owned `graft_and_test.py` entry point
  (carrying `{junit_xml}`) as the `ANVIL_TEST_COMMAND`; drop the
  long-advance timeout workaround; optional per-repo docker image.
- **Real-docker smoke** (manual, once): offline-llm run with
  `ANVIL_TEST_EXECUTOR=docker` to validate the CLI assumptions the fakes
  encode.
- **The measurement** (bundle: #23+#26+#27): tinydb median-of-3 with the
  loop vs the one-shot baseline (median 24/201, distribution
  {0, 19, 24, 60, 78}, import-fail 1/5); cachetools must hold ≥ 177/215;
  smoke suite 6/6 with no command; executor + ablation flags recorded per
  run.
