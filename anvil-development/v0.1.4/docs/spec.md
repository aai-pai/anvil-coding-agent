# Anvil Specification — v0.1.4

Testable requirements for the v0.1.4 release. This is a **delta** against the
[v0.1.3 spec](../../v0.1.3/docs/spec.md), which remains the baseline; only
the requirements below change. Derived from [docs/proposal.md](proposal.md).

**Stack (unchanged):** OpenRouter + localhost REST runtime + `@anvil`
extension. All changes are runtime-side plus Commit0-adapter consumer
changes. **Opt-in release:** with no `externalTestCommand` configured, every
run behaves exactly as v0.1.3.

---

## 1. Bounded External-Test Repair Loop (#23)

Anvil's first verification-by-execution capability: run a user-supplied test
command against what the implementation phase produced, feed failures back
into bounded per-artifact repair.

### Configuration

- **FR-RL-001**: `EffectiveConfig` gains `externalTestCommand: str | None`
  (default `None`), `repairMaxRounds: int` (default 2), and
  `testTimeoutS: int` (default 600). Env overrides `ANVIL_TEST_COMMAND` /
  `ANVIL_REPAIR_MAX_ROUNDS` / `ANVIL_TEST_TIMEOUT_S`; precedence env >
  config field > default (the #18/#19 pattern).
- **FR-RL-002 (opt-in)**: With no command configured the pipeline is
  v0.1.3 byte-for-byte — no execution, no new events, identical prompts.
  A command is never inferred or discovered.

### Security posture

- **FR-RL-003**: A configured command is honored only under security
  profile `open`. Under `restricted`/`strict` the run **fails at intake**
  with a reason naming the profile and the command — fail loud, never
  silently skip verification the user asked for.
- **FR-RL-004**: The command runs with cwd = the run workspace, bounded by
  `testTimeoutS`; stdout/stderr are captured (tail recorded on events and
  failure records). Execution is not sandboxed in v0.1.4 — a documented
  limitation carried in RUNNING.md, not a silent claim.

### Round zero — mechanical smoke

- **FR-RL-005**: Before the first command run, every generated `.py`
  artifact is compile-checked (`compile()`); a syntax-broken artifact
  enters repair immediately without spending a command run. (True
  import-time failures surface through the command itself and map back via
  FR-RL-007.)

### The loop

- **FR-RL-006**: After the implementation step's generation (and passing
  #21 validation), the supervisor-visible flow is: run command → exit 0 →
  `ExternalTestsPassed`, phase completes. Non-zero → `ExternalTestsFailed`
  (exit code + output tail) → repair round, at most `repairMaxRounds`
  times. Rounds exhausted with red tests → the implementation step fails
  into the normal retry/escalation path with the last output tail in the
  failure reason.
- **FR-RL-007 (failure→file mapping)**: Implicated files are generated
  targets whose basename or workspace-relative path appears in the command
  output. If none match, all targets are implicated (bounded by the target
  list). Mapping is deterministic and recorded on the round's event.
- **FR-RL-008 (per-artifact repair)**: Each implicated file gets ONE repair
  completion per round (under `codeMaxTokens`, pinned temperature
  honored), whose prompt carries: the file's current source, the failure
  output tail, the contract block, and an explicit fix-in-place
  instruction. Non-implicated files are never regenerated.
- **FR-RL-009**: After each repair round the #21 mechanical validation
  re-runs; a repair that un-pins a manifest symbol fails the round as if
  tests were still red (the contract outranks the tests).
- **FR-RL-010 (events)**: Each round emits `RepairRoundStarted`
  (round, implicated files) and `RepairRoundCompleted` (round, exit code,
  pass movement where parseable). Per-file repair usage rides the existing
  per-artifact `TokenUsageReported`.
- **FR-RL-011 (no-list fallback)**: When the implementation ran in v0.1.2
  single-completion mode (no derivable file list), repair regenerates via
  one whole-`src/` completion carrying the failure tail — the loop still
  functions, only less surgically.

**Test:** no command → v0.1.3 behavior byte-for-byte (prompts and events);
green command → `ExternalTestsPassed`, no repair; red-then-green → one
repair round touching only implicated files; permanently red → rounds
bounded, step fails with tail, enters retry path; syntax-broken artifact
repaired at round zero; restricted profile + command → intake failure naming
both; #21 violation introduced by a repair fails the round; repair prompts
carry source + failure tail + contract.

## 2. Per-Artifact Advance Granularity (#24)

- **FR-AG-001**: During per-artifact implementation (and each repair
  round), the backend emits `PhaseProgress` events (`artifact`,
  `index`, `count`, `stage`: "generate" | "repair" | "test") on the run's
  event stream, so SSE clients observe progress inside a long phase.
- **FR-AG-002**: One `/advance` on a deferred run performs at most one
  unit of implementation work — one artifact generation, one command run,
  or one repair round — persisting phase-internal progress so the next
  `/advance` (or a resume after restart) continues where it left off.
  `run_until_pause` semantics are unchanged (it loops `step`).
- **FR-AG-003**: Phase-internal progress is checkpointed; a mid-phase
  restart resumes from the last completed artifact, never regenerating
  completed ones (their content is on disk and checksummed).
- **FR-AG-004**: Single-artifact runs, stub mode, and doc phases are
  byte-for-byte unchanged.

**Test:** a 3-file implementation needs 3 advances, each returning progress;
kill/resume mid-phase regenerates only the remaining files; SSE stream
carries `PhaseProgress`; smoke-suite behavior unchanged.

## 3. Commit0 adapter (consumer changes, ship alongside)

- Snapshot the repo's original test files at staging; the configured
  command and local scoring both use the snapshot (Anvil's qa-generated
  tests can never enter the repair signal or the score).
- Configure the spawned server with `ANVIL_TEST_COMMAND` pointing at an
  adapter-owned graft-and-test entry point (graft generated `src/` onto a
  scratch package copy, run the snapshot suite) so the repair signal tests
  exactly what scoring tests.
- Drop the long-advance timeout workaround once FR-AG-002 lands.

## 4. Out of scope

Sandboxed execution; contract ledger; sampling-default changes; instruction
semantics (frozen); OpenHands/DevBench/WebGen adapters; official Commit0
evaluation.

## 5. Acceptance

Per the proposal: tinydb median-of-3 with the loop vs the n=5 one-shot
baseline (must beat the median AND delete the import-fail arm); cachetools
must not regress from 177/215; smoke suite 6/6 with no command configured;
per-round pass counts monotone non-decreasing.
