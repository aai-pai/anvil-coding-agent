# Anvil Proposal — v0.1.4

v0.1.4 is the verification release: Anvil starts *executing* what it builds.
Every feature traces to the v0.1.3 measurement campaign
(`benchmarks/commit0/STATUS.md`; evidence summarized in
[background-information.md](../domain-knowledge/background-information.md)).
The [v0.1.3 proposal](../../v0.1.3/docs/proposal.md) remains in force; this
document covers only what changes.

**Stack.** Unchanged: OpenRouter + the localhost REST runtime + the `@anvil`
extension. The OpenHands adapter stays parked.

**Theme.** v0.1.3 closed the loop between *what the task pins* and *what
Anvil ships* — and measured that the remaining defect class is behavioral:
code that names everything correctly and then does the wrong thing, with a
handful of load-bearing functions deciding whole-run outcomes (tinydb
one-shot: 0–78 of 201 across five runs). v0.1.4 closes the loop between
*what Anvil ships* and *what actually runs*: a bounded, opt-in
run-tests-and-repair loop (#23), with supervisor progress reported at the
granularity the work now has (#24). Success is a higher *and tighter*
distribution — the repair loop must collapse the one-shot variance, not just
raise the mean.

## Features

### #23 — Bounded external-test repair loop (the core feature)

Anvil today never executes anything it builds; every v0.1.3 failure survived
to scoring untouched. #23 adds verification by execution, strictly opt-in.

**Configuration.**

- `EffectiveConfig` fields `externalTestCommand` (string, default none) and
  `repairMaxRounds` (int, default 2); env overrides `ANVIL_TEST_COMMAND` /
  `ANVIL_REPAIR_MAX_ROUNDS`, precedence env > config > default (the #18/#19
  pattern).
- **Absent `externalTestCommand`, behavior is v0.1.3 byte-for-byte.** No
  command is ever inferred, discovered, or defaulted — execution happens
  only when the user (or an adapter acting as an ordinary user) explicitly
  supplies one.

**Round zero — import smoke check (mechanical, free).** Before any test
run: byte-compile / import the generated artifacts (for Python targets,
`compile()` + import of the manifest files with the workspace on the path).
Two of five measured tinydb runs died at import on a single function
(`with_typehint`); this catches that class without spending a completion or
running user code beyond module import. Failures feed the same repair path
as test failures.

**The loop.** After the implementation phase completes (post-#21
validation), when a command is configured:

1. Run `externalTestCommand` in the run workspace (bounded by a new
   `ANVIL_TEST_TIMEOUT_S`; captured output, exit code recorded).
2. Green (exit 0) → emit `ExternalTestsPassed`, proceed. Red → emit
   `ExternalTestsFailed` (counts + tail) and, if rounds remain, enter
   repair; if rounds are exhausted, the phase fails into the normal
   escalation path with the last test tail in the failure record.
3. **Repair is per-artifact** (reuses #22's machinery): parse the failure
   output, map implicated files (traceback paths ∩ generated targets;
   unmappable failures implicate the full target list), and regenerate
   *only* those files — each prompt carrying the file's current source, the
   relevant failure excerpt, and the standing contract block. One completion
   per implicated file per round, under `codeMaxTokens`.
4. Re-run #21 mechanical validation after each round (a repair must not
   un-pin a signature), then loop.
- Events per round: `RepairRoundStarted` / `RepairRoundCompleted` with
  round number, implicated files, and pass-count movement — the audit trail
  must show *what the loop bought*, per round.

**Security posture (new capability class — executing workspace code).**

- The repair loop runs only under security profile `open`; under
  `restricted`/`strict` a configured `externalTestCommand` is refused at
  intake with a clear reason (fail loud, not silently skip). Secure-mode
  runs additionally surface the exact command at the post-blueprint gate.
- The command runs with cwd = run workspace. v0.1.4 does not sandbox it
  (documented limitation — same trust level as the user running the command
  themselves; the benchmarks already execute this code at scoring time).
  Sandboxing is future work, not silently claimed.

**Commit0 adapter (consumer change, ships alongside).** The adapter
configures `externalTestCommand` = the repo's pytest invocation pinned to a
**staging-time snapshot of the original test files**, so Anvil's own
qa-generated tests can never enter the repair signal or the score (closes
the existing backlog item). Local scoring keeps using the same snapshot.

Tests: no command configured → v0.1.3 behavior byte-for-byte (prompt-level
and event-level); import smoke failure enters repair; a failing run repairs
only implicated files (others' content untouched); rounds are bounded and
each emits its events; exhausted rounds escalate with the last tail;
restricted profile refuses the command at intake; #21 re-validates after
each round; resume mid-loop restores the round counter.

### #24 — Per-artifact advance granularity

#22 made one `/advance` a many-completion call; the first real v0.1.3 run
was killed by a client-side timeout mid-implementation, and #23's repair
rounds extend the same call further. Clients should not need
benchmark-sized timeouts to survive normal progress.

- The supervisor's `step()` boundary within the implementation phase (and
  #23 repair rounds) becomes resumable mid-phase: each `/advance` performs
  at most one artifact generation (or one repair round), persisting
  per-phase progress in the checkpoint, so `run_until_pause` still works
  and a driving client sees progress per call.
- `PhaseProgress` events (artifact index/count) stream over the existing
  SSE surface either way, so even long calls are observable.
- The eval harness and Commit0 adapter drop their long-timeout workaround
  once this lands (adapter change rides along).

Tests: a multi-file implementation advances one artifact per `/advance` with
state persisted between calls; kill/resume mid-phase regenerates only
remaining artifacts; SSE carries per-artifact progress; single-artifact and
stub runs are unchanged.

## Measurement protocol (new, binding for this release)

Single Commit0 runs are too noisy to compare releases on (measured: tinydb
one-shot 0–78/201 across five runs). v0.1.4 comparisons use **the median of
3 runs with the full distribution quoted**. The eval smoke suite stays the
per-release regression gate (single run; its variance is not the bottleneck).

## Out of scope

- **Contract ledger** (spec/architecture appending invented contracts with
  provenance) — deferred again; it targets greenfield doc drift, a
  different instrument than #23's, and would muddy attribution.
- Sandboxed test execution (documented as a limitation of #23, not built).
- Any change to the sampling default — measured in the temperature
  experiment (2026-07-18): temp 0 neither reproduces nor improves the mean.
  `ANVIL_TEMPERATURE` stays an experiment knob.
- Any change to `anvil-instructions.md` semantics (frozen, 2026-07-11).
- OpenHands adapter; DevBench/WebGen-Bench adapters; official Commit0
  docker/modal evaluation.

## Acceptance criteria

Approved when it supports deriving `spec.md`, `architecture.md`,
`blueprint.md`, and `plan.md` for #23/#24. Carried into the spec phase: the
exact repair-round contract (failure→file mapping rules, round bounding,
event names and payloads), the import-smoke mechanics, the security-profile
refusal surface, and #24's mid-phase checkpoint schema.

Success is measured against the v0.1.3 baselines:

1. **Commit0 tinydb, 3 runs with the repair loop** (median + distribution)
   vs the v0.1.3 one-shot baseline: **median 24/201 (11.9%), distribution
   {0, 19, 24, 60, 78} of 201, import-fail 1/5** (n=5, default temperature,
   2026-07-18). The loop must beat the baseline median AND show a
   tighter distribution (no import-fail outcomes — round zero exists
   precisely to delete that arm).
2. **cachetools with the loop** vs 177/215 one-shot (82.3%) — the
   high-baseline case must also improve, or at minimum not regress.
3. **Smoke suite 6/6, no repair loop configured** — proving the opt-in
   default leaves v0.1.3 behavior intact.
4. Per-round telemetry shows monotone non-decreasing pass counts on the
   runs above (the loop never makes a run worse; #21 re-validation guards
   the contract).

---

Status: Draft for collaborative review. Baseline measured (n=5,
2026-07-18): tinydb one-shot median 24/201, distribution {0, 19, 24, 60, 78}.
