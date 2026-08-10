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

- **FR-RL-003** (revised by FR-DX-002): With the `local` executor a
  configured command is honored only under security profile `open`. Under
  `restricted`/`strict` the run **fails at intake** with a reason naming
  the profile, the command, and the `docker` alternative — fail loud,
  never silently skip verification the user asked for.
- **FR-RL-004**: The command runs with cwd = the run workspace (`local`)
  or the container workdir (`docker`), bounded by `testTimeoutS`;
  stdout/stderr are captured (tail recorded on events and failure
  records). `local` execution is not sandboxed — a documented limitation
  carried in RUNNING.md, not a silent claim; isolation is FR-DX.

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

## 1b. Docker-Isolated Test Execution (#25) — implemented 2026-07-24, back-filled

- **FR-DX-001 (executor seam)**: `EffectiveConfig` gains `testExecutor:
  "local" | "docker"` (default `local`), `testImage: str` (default
  `python:3.11-slim`), `testSetupCommand: str | None` (default `None`).
  Env overrides `ANVIL_TEST_EXECUTOR` / `ANVIL_TEST_IMAGE` /
  `ANVIL_TEST_SETUP_COMMAND`, usual precedence. `local` is the v0.1.4
  first-iteration runner, byte-for-byte.
- **FR-DX-002 (profile policy)**: `docker` is accepted under every
  profile and is the ONLY executor accepted under `restricted`/`strict`.
  With executor `docker` and a configured command, intake probes the
  daemon; unusable docker fails the run at intake with the probe's reason.
- **FR-DX-003 (isolation)**: one hardened container per verification pass
  (`--memory`/`--cpus`/`--pids-limit` caps, `--cap-drop=ALL`,
  `no-new-privileges`), `exec` per round. Sources reach the container by
  copy-in; only exit code, output, and the FR-JL-002 report come back. No
  bind mounts. Network exists only while `testSetupCommand` runs; the
  post-setup disconnect is fail-closed.
- **FR-DX-004 (timeout)**: enforced host-side; a timed-out container is
  force-removed and the round reports `timed_out`; a later round starts a
  fresh container.
- **FR-DX-005 (failure taxonomy)**: docker infrastructure failure raises
  its own error and fails the step with a `docker test executor failed`
  reason — never conflated with a red test run. Container cleanup runs on
  every exit path.
- **FR-DX-006 (testability)**: the docker CLI is driven through an
  injectable seam; the unit suite fakes it and asserts the exact call
  sequence (the sequence IS the security posture). No test requires a
  daemon.

**Test:** hardening flags + `--network none` without setup; setup gets
network then fail-closed disconnect; copy-in per round, container started
once; timeout → rm + fresh container; infra failure raises; probe refusal
at intake; restricted profile + docker proceeds; env wiring reaches the
backend.

## 1c. Structured Failure Localization (#26)

- **FR-JL-001 (token contract)**: When `externalTestCommand` contains the
  literal token `{junit_xml}`, Anvil substitutes the canonical report path
  (`.anvil/junit-report.xml`, workspace-relative) before execution. No
  token → no report handling; FR-RL-007 basename mapping applies
  unchanged (this is also the #26 ablation lever).
- **FR-JL-002 (report retrieval)**: After each run the report is read from
  the workspace; the docker executor copies it out of the container (the
  only copy-out beyond exit code and output). A missing or unparseable
  report degrades to FR-RL-007 with a warning event — never a crash, the
  command may have died before writing it.
- **FR-JL-003 (clustering)**: Parsed failures become records (test id,
  error type, message, implicated frame = deepest traceback frame whose
  file matches a generated artifact). Records cluster by **(error type,
  implicated file)**; clusters order by size, descending. Implicated
  files = the clusters' files (largest cause first); files with no
  cluster are not implicated.
- **FR-JL-004 (cause-focused prompts)**: A repaired file's prompt carries
  its cluster's summary — failure count, error type, and up to 3
  representative failures (test id + message + frame excerpt) — instead
  of the raw output tail. The raw tail remains the fallback when no
  cluster maps to the file.
- **FR-JL-005 (events)**: `RepairRoundStarted` gains the cluster summary
  (per cluster: error type, file, count) so the audit trail shows *what
  cause* each round attacked.

**Test:** token substituted in the executed command; report parsed →
clusters keyed by (error type, file); largest cluster repaired first;
repair prompt carries cluster summary, not raw tail; missing report falls
back to basename mapping with a warning; no token → byte-for-byte
first-iteration behavior; docker copies the report out.

## 1d. Interface-Aware Repair Context (#27)

- **FR-IC-001 (interface map)**: For each repair completion, an
  AST-extracted map of the OTHER generated `.py` artifacts is injected as
  read-only context: per file, its top-level and class-level qualnames
  with signatures and one-line docstrings; per class, its assigned
  attributes. Syntax-broken files are listed as `(currently broken)`
  without content.
- **FR-IC-002 (connection ranking + cap)**: Files are ordered by
  connection to the failing file — files it imports/references first, then
  files importing/referencing it, then the rest — and the block is capped
  (default 6,000 chars) by dropping whole files from the tail of that
  order, with a `(N files omitted)` note. The contract block is never
  displaced.
- **FR-IC-003 (harmony instruction)**: The repair prompt states that the
  listed interfaces are the passing code's contracts: the fix must keep
  every interface the failing file exposes to them intact unless a failure
  demands otherwise. Write-set unchanged (FR-RL-008: non-implicated files
  are never regenerated).
- **FR-IC-004 (gate)**: `ANVIL_REPAIR_CONTEXT=interfaces` (default) |
  `minimal` (first-iteration prompts, for ablation). Config field
  `repairContext`, usual precedence.

**Test:** repair prompt contains other files' signatures but never their
bodies; connection ranking puts imported-by-failing-file first; cap drops
least-connected files with the omission note; `minimal` restores
first-iteration prompts byte-for-byte; broken sibling listed without
content.

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
  exactly what scoring tests. The entry point carries the `{junit_xml}`
  token so FR-JL localization is active on the benchmark.
- Optionally prebuild a per-repo docker image (skeleton deps + pytest) and
  set `ANVIL_TEST_EXECUTOR=docker` so repair rounds are pure exec.
- Drop the long-advance timeout workaround once FR-AG-002 lands.

## 4. Out of scope

Contract ledger; full dependency-slice repair context and the escalation
ladder (v0.1.5); tiger-team multi-role repair; sampling-default changes;
instruction semantics (frozen); OpenHands/DevBench/WebGen adapters;
official Commit0 evaluation.

## 5. Acceptance

Per the proposal: tinydb median-of-3 with the loop vs the n=5 one-shot
baseline (must beat the median AND delete the import-fail arm); cachetools
must not regress from 177/215; smoke suite 6/6 with no command configured;
per-round pass counts monotone non-decreasing.
