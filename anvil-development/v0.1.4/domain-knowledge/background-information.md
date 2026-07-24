# Anvil v0.1.4 — background information

v0.1.4 is the **verification release**: Anvil runs what it builds, repairs
what fails, and does the running inside an isolated container. It is driven
by the v0.1.3 measurement campaign (2026-07-13 → 2026-07-18) and by the
security review of what "Anvil executes workspace code" actually means
(2026-07-24). Instruments: the Tier-1 eval harness (`evals/`) and the
Commit0 adapter (`benchmarks/commit0/STATUS.md` — read it first; it carries
the full run log).

## Primary objective (set 2026-07-24)

Higher test pass rates on Commit0, achieved by a repair loop that:

1. **runs tests inside an isolated playground** — docker execution (#25)
   over an adapter-staged snapshot that scores only the repo's *original*
   tests;
2. **localizes failures structurally** — JUnit XML clustering (#26), not
   basename-grepping raw output;
3. **resubmits targeted fixes that preserve functional harmony** — the
   repair prompt carries the failure log AND the structural connections to
   the passing code (#27), so a fix never breaks what already works.

## Scope

| # | Feature | Status |
|---|---|---|
| #23 | Bounded external-test repair loop | runtime shipped (`13a94dc`) |
| #24 | Per-artifact advance granularity | runtime shipped (`13a94dc`) |
| #25 | Docker-isolated test execution | implemented ahead of docs (2026-07-24) — proposal/spec to back-fill |
| #26 | Structured failure localization (JUnit XML clustering) | this iteration — proposal → spec → … pending |
| #27 | Interface-aware repair context ("functional harmony") | this iteration — proposal → spec → … pending |
| — | Adapter: staging snapshot of original test files (qa-leak fix) | this iteration, adapter-side |

#25 was pulled into v0.1.4 (rather than deferred) because #23 without it is
gated to the `open` security profile — an execution capability that only
exists ungoverned contradicts Anvil's identity as a *governed* factory, and
the gap compounds with every release that builds on the loop.

Process note (2026-07-24): #25 was implemented straight from design
discussion, out of order. Accepted as done, but #26/#27 follow the full
pipeline: proposal → spec → architecture → blueprint → plan →
implementation, with #25's sections back-filled alongside.

### #26 — Structured failure localization

Replace `implicated_files`' basename grep with structured failure records:
the test command runs pytest with `--junitxml`, the XML is copied out of
the container (copy-out already exists in the #25 design), and failures are
mapped to files and **clustered by root cause** (same error type + same
implicated frame). One repair round then targets one *cause*, not one
file-name coincidence — the four v0.1.3 tinydb clusters accounted for ~160
of 177 red tests, so cluster-granular repair is where the measured leverage
is. Existing tool (pytest's junit output + stdlib XML parsing), no new
dependency; raw-output basename mapping stays as the fallback when the
command produces no XML (the loop must work for arbitrary
`externalTestCommand`s, not just pytest).

### #27 — Interface-aware repair context (the resubmission constraint)

Binding constraint on every repair resubmission (set 2026-07-24): the
prompt must include, alongside the failure log and the failing file's
current source, **the structural connections to the passing code — function
signatures, parameters, class attributes, and key dependency edges — so the
model retains overall functional harmony** and a targeted fix cannot drift
the interfaces the passing files rely on.

Concretely: an AST-extracted *interface map* of the generated artifacts
(qualnames + signatures + one-line docstrings + import/reference edges
touching the failing file), injected as read-only context. Signatures only
— **bodies of passing files are never included** (that is v0.1.5's
dependency-slice feature) **and passing files are never in the write-set**
(FR-RL-008 already enforces this). Existing muscle: the same `ast` pass the
#21 manifest validator and the Commit0 stub inventory already use.

## What v0.1.3 proved

1. **Transport is solved.** The contract/context split (#20) held in every
   run on both benchmarks: modules named correctly, all 50 tinydb stubs
   filled, every demanded definition present. The smoke suite holds 6/6
   *without* the per-task fidelity-instructions workaround.
2. **The remaining defect class is behavioral correctness.** The contract
   pins names, signatures, and shapes; it cannot pin what a body *does* or
   the implicit conventions between modules. Every remaining Commit0
   failure is of this class.

## The evidence driving v0.1.4

1. **One-shot variance is structural, and catastrophic failure is a real
   arm.** tinydb one-shot runs (201 tests): default temperature
   **{0, 19, 24, 60, 78} — median 24 (11.9%), import-fail 1/5** (n=5,
   2026-07-18); temperature 0 {0, 0, 40}. A handful of load-bearing
   functions decide the outcome; two temp-0 runs independently chose the
   same wrong idea for `with_typehint` and died at import.
2. **Sampler settings are not a remedy (measured).** Temperature 0 neither
   reproduces nor improves the mean. The fix is verification/repair, not
   sampler settings.
3. **The failures are cheap to detect and plausibly cheap to repair.**
   Import failure — 2 of 5 measured runs — is detectable without running a
   single test. The dominant clusters each sit in one or two functions, and
   #22's per-artifact machinery already knows how to regenerate exactly one
   file.
4. **Long synchronous advances are fragile** (#24's driver: the first
   v0.1.3 run was killed by a client timeout mid-implementation).
5. **Executing workspace code is a new capability class** (#25's driver).
   The v0.1.4 runtime as first shipped runs `externalTestCommand`
   unsandboxed on the host, so it is refused for every profile except
   `open`. The code under test is *LLM-generated* — the trust argument
   "the user typed the command" does not extend to what the command runs.

## Issue ledger — every measured defect of the campaign, and what closes it

Source: the Commit0 run log (`benchmarks/commit0/STATUS.md`) and the v0.1.2
→ v0.1.3 measurement campaign. This is the ground truth for scoping: a
feature belongs in a release only if it closes a row here.

### Closed

| Issue (where found) | Resolution | Status |
|---|---|---|
| Output token budgets hardcoded → escalation at specification, 3× `finish_reason=length` (v0.1.2 run 1) | #19 configurable completion budgets | shipped + measured |
| Contract drift in phase-to-phase retelling — v0.1.2 needed a per-task fidelity-instructions workaround | #20 contract/context split + #21 mechanical manifest validation | shipped + measured (transport solved in every run) |
| Skeleton-blindness: implementation regenerated whole files from plan docs, dropping provided code (v0.1.2 run 2) | #22 skeleton-aware per-artifact generation + adapter AST graft | shipped + measured |
| Commit0's stripper leaves dangling references invisible to stub scans (`_immutable`) | adapter "MUST ALSO DEFINE" pyflakes-lite inventory | shipped adapter-side |
| Client timeout killing long synchronous advances (first v0.1.3 run) | #24 per-artifact advance + `PhaseProgress` SSE + mid-phase checkpoint | shipped, runtime-tested |
| Graft inserted dangling defs at end-of-file → class-body NameError at import (v0.1.3 run 1) | graft fix: insert before first referencing statement | shipped adapter-side |
| Scoring resolved the INSTALLED site-packages package, not the staged repo (cachetools src-layout) | adapter fix; **structurally removed by #25** — a clean container contains only the staged code | shipped; docker closes the class |
| Behavioral-correctness failures + one-shot variance {0, 19, 24, 60, 78}, import-fail 2/5 | #23 repair loop | shipped, **measurement owed** |
| Executing workspace code = unsandboxed host execution, so #23 was `open`-profile-only | #25 docker executor | shipped this iteration |
| Failure→file localization is a basename grep over raw output | #26 JUnit XML clustering | in scope this iteration |
| Repair prompt is blind to the passing code's interfaces | #27 interface-aware repair context | in scope this iteration |
| Anvil's own qa-generated tests can leak into the benchmark score | adapter staging snapshot of original `tests/` | in scope this iteration, adapter-side |

### Still open — deferred beyond v0.1.4

Docker changes **where** code runs (safety, environment purity,
containment, profile availability), not **what the generated code does**;
#26/#27 sharpen the loop's inputs but stop at signatures. What remains:

1. **Cross-module repair context (full source slices).** The dominant
   failure clusters are cross-module (query↔middleware recursion cycle,
   database↔storage serialization, `with_typehint` inheritance) — #27's
   signature-level interface map may not be enough to see a delegation
   *cycle*; that needs the dependent **bodies** in the prompt.
   Dependency-slice via plain `ast` — **v0.1.5** (agreed 2026-07-24); the
   v0.1.4 measurement decides how much it is needed (do repaired runs
   still die on cross-module clusters?).
2. **Wrong-idea persistence.** Two independent temp-0 runs chose the same
   wrong `with_typehint` design; a repair round with the same context can
   re-choose it. Repeated failure of the same cluster needs escalating
   context or an explicitly-different-approach prompt — v0.1.5's
   escalation-ladder question, informed by the v0.1.4 measurement.
3. **Greenfield doc drift** (contract ledger) — still deferred; different
   instrument, would muddy attribution.

Existing tools over new machinery, throughout: pytest's junit XML for
localization (#26), the repo's own `ast` muscle for the interface map
(#27) and later dependency slices, the official commit0 docker evaluator
for leaderboard scoring, the existing `RetryController`/escalation
machinery for bounding — nothing here needs a new external dependency
beyond docker itself.

## #25 — Docker-isolated test execution (design decisions, 2026-07-24)

**Motivation: safety** (isolation of untrusted generated code), not
evaluator fidelity — matching Commit0's official docker evaluator is a
side benefit, not the driver.

- **Platform**: Docker Desktop / any docker CLI. Driven via `subprocess`
  (no new Python dependency), consistent with how the local runner works.
- **Executor seam**: `testExecutor: local | docker` (env
  `ANVIL_TEST_EXECUTOR`). `local` is today's subprocess runner, unchanged.
  Supporting knobs: `testImage` (default `python:3.11-slim`, env
  `ANVIL_TEST_IMAGE`) and `testSetupCommand` (run once per container, e.g.
  `pip install -e . pytest`, env `ANVIL_TEST_SETUP_COMMAND`).
- **Lifecycle**: one long-lived container per verification pass, `docker
  exec` per test round — container start and dependency install are paid
  once, repair rounds are pure exec.
- **Copy-in/copy-out, no bind mount.** Sources are `docker cp`'d in each
  round; only exit code and output come back. The container can never
  write to the host workspace — this is the load-bearing isolation
  decision (and it sidesteps Docker Desktop's slow Windows bind-mount I/O).
- **Hardening**: `--network=none` after setup (setup alone gets network,
  for pip), `--memory` / `--cpus` / `--pids-limit` caps (a runaway
  RecursionError — a measured failure cluster — becomes a contained OOM),
  `--cap-drop=ALL`, `--security-opt=no-new-privileges`. Timeout is
  enforced host-side; a timed-out container is force-removed, never
  trusted to unwind. Root inside the container is accepted for v0.1.4
  (the WSL2 VM boundary plus no mounts is the real isolation; a non-root
  user fights `pip install` for no threat-model gain).
- **Profile policy — the payoff**: `open` allows `local` or `docker`;
  `restricted`/`secure` accept the repair loop **only** with `docker`.
  Docker configured-but-unavailable fails the run at intake with a clear
  reason — never a silent skip of verification the user asked for.

## Decisions recorded from the design discussion (2026-07-24)

- **Tiger team (multi-role LLM collaboration per failure): rejected for
  now, on cost.** Anvil's differentiator is cost efficiency; no evidence
  yet that single-completion repair *with proper context* is insufficient.
  Revisit only if v0.1.5 measurement shows a reasoning-miss tier.
- **Repair context is split across two releases.** v0.1.4 (#27) gives the
  repair prompt the passing code's *interfaces* (signatures, parameters,
  dependency edges — the functional-harmony constraint); v0.1.5 escalates
  to full dependency-slice *source* if the measurement shows cross-module
  clusters still killing repaired runs. The write-set stays restricted to
  implicated files in both.
- **Codebase MCP for dependency lookup: rejected.** Anvil already has the
  AST muscle (graft, manifest validator, stub inventory); a static import
  graph + qualname cross-reference in plain `ast` code is deterministic,
  free, and testable. MCP stays the multi-language future, not the
  mechanism.
- **Scope expansion accepted with eyes open (2026-07-24, see constraints):
  #26/#27 join #23 in the score-affecting set**, so v0.1.4 is measured as
  a repair-loop *bundle* rather than one variable.

## Constraints carried into this release

- **Measurement discipline, revised (2026-07-24): bundle granularity.**
  The score-affecting set is now the whole verified repair loop — #23 +
  #26 (clustered localization) + #27 (interface context). The
  median-of-3 measurement therefore attributes the delta over the one-shot
  baseline to the *bundle*, not to any single feature — an explicit,
  accepted trade against per-feature attribution. If the delta later needs
  decomposition, #26/#27 are config-gated, so ablation runs (loop with
  basename mapping / without interface context) remain possible without
  code changes. #24 is client-facing infrastructure; **#25 changes where
  tests run, not what is generated** — with the same image and deps, local
  and docker execution are score-equivalent. The executor used is recorded
  per run.
- `anvil-instructions.md` remains frozen (team decision, 2026-07-11).
- Benchmarks remain adapter-only consumers. `externalTestCommand`, the
  docker executor, and junit localization must make sense for ordinary
  users first ("make my tests pass" is a real user ask); the Commit0
  adapter merely configures them.
- Commit0 comparisons use multi-run medians with the distribution quoted.
- Owed to close the release: the doc pipeline for #26/#27 (+#25 back-fill)
  — proposal → spec → architecture → blueprint → plan — then
  implementation; Commit0 adapter integration (staging snapshot of the
  original test files, graft-and-test entry point as the command, per-repo
  docker image); then the tinydb median-of-3 measurement against the
  one-shot baseline (median 24/201, distribution {0, 19, 24, 60, 78}) with
  cachetools ≥ 177/215 and smoke 6/6 with no command.
