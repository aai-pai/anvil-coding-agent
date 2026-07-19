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

- **362-test suite green** — 19 new since v0.1.3's 343
  (`test_repair_loop.py` 10, `test_advance_granularity.py` 4,
  `test_temperature.py` 5 from the variance experiment); zero regressions.
- **E2E (offline, via the API)**: markered run completes and seals;
  manifest-violating run still escalates (#21 intact); green-command run
  completes with `ExternalTestsPassed`; restricted-profile run with a
  command escalates at intake with the reason in the failure record.

## Still to do in this cycle

- **Commit0 adapter #23 integration** (spec §3): staging-time snapshot of
  the original test files; an adapter-owned graft-and-test entry point as
  the `ANVIL_TEST_COMMAND`; drop the long-advance timeout workaround.
- **The measurement**: tinydb median-of-3 with the loop vs the one-shot
  baseline (median 24/201, distribution {0, 19, 24, 60, 78}, import-fail
  1/5); cachetools must hold ≥ 177/215; smoke suite 6/6 with no command.
