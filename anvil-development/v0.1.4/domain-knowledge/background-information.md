# Anvil v0.1.4 — background information

v0.1.4 is driven by the v0.1.3 measurement campaign (2026-07-13 → 2026-07-18):
the first release whose features were fully measured before the next was
proposed. Instruments: the Tier-1 eval harness (`evals/`) and the Commit0
adapter (`benchmarks/commit0/STATUS.md` — read it first; it carries the full
run log).

## What v0.1.3 proved

1. **Transport is solved.** The contract/context split (#20) held in every
   run on both benchmarks: modules named correctly, all 50 tinydb stubs
   filled, every demanded definition present (including `_immutable`, the
   dangling reference no earlier run would write). The smoke suite holds
   6/6 *without* the per-task fidelity-instructions workaround — cheaper
   (−30% tokens) and faster (−50% wall) than the workaround it replaced.
2. **The remaining defect class is behavioral correctness.** The contract
   pins names, signatures, and shapes; it cannot pin what a body *does* or
   the implicit conventions between modules. Every remaining Commit0
   failure is of this class.

## The evidence driving v0.1.4

1. **One-shot variance is structural, and catastrophic failure is a real
   arm.** tinydb one-shot runs (201 tests): default temperature
   **{0, 19, 24, 60, 78} — median 24 (11.9%), import-fail 1/5** (n=5,
   2026-07-18); temperature 0 {0, 0, 40}. The swing
   is not model "inconsistency": a handful of load-bearing functions decide
   the outcome. Two temp-0 runs independently chose the same wrong idea for
   `with_typehint` (decorator factory instead of subclass) and died at
   import — one function, zero score, twice. Run 1's four root causes
   accounted for ~160 of 177 red tests.
2. **Sampler settings are not a remedy (measured).** Temperature 0 neither
   reproduces (5/7 generated files still differ per run — provider routing
   + batched inference) nor improves the mean (0/0/40 vs 24/78). The
   `ANVIL_TEMPERATURE` knob exists for experiments; the default stays
   provider-default. Team decision 2026-07-18: no case for it as a
   measurement lever.
3. **The failures are cheap to detect and plausibly cheap to repair.**
   Import failure — 2 of 5 measured runs — is detectable without running a
   single test. The dominant clusters (TinyDB-as-dict-key, recursion cycle,
   str-vs-file-handle, `with_typehint`) each sit in one or two functions,
   and #22's per-artifact machinery already knows how to regenerate exactly
   one file. Commit0 ships the library's own test suite precisely so agents
   can run it and repair; Anvil still never executes anything it builds.
4. **Long synchronous advances are fragile.** #22 made one `/advance` a
   many-completion call (~70s/module on tinydb); the first v0.1.3 run was
   killed by a client timeout mid-implementation. The adapter works around
   it with a long timeout; repair rounds will make single advances longer
   still.
5. **cachetools generalization (82.3%, 177/215)** — low-coupling repos
   score high one-shot; the src-layout harness bugs it exposed are fixed
   adapter-side.

## The through-line

v0.1.3 closed the loop between *what the task pins* and *what Anvil ships*.
v0.1.4 closes the loop between *what Anvil ships* and *what actually runs*:
verification by execution (#23), with the supervisor able to report progress
at the granularity the work now has (#24). This was deliberately deferred
from v0.1.3 for measurement integrity; the one-shot baseline it must beat is
now measured, with run-to-run variance quantified — the repair loop's
success criterion includes *collapsing that variance*, not just raising the
mean.

## Constraints carried into this release

- One-variable measurement discipline: #23 is the only score-affecting
  feature; #24 is client-facing infrastructure with no effect on generated
  content. The contract ledger stays deferred (again) — it targets
  greenfield doc drift, a different instrument, and would muddy attribution.
- `anvil-instructions.md` remains frozen (team decision, 2026-07-11).
- Benchmarks remain adapter-only consumers. `externalTestCommand` must make
  sense for ordinary users first ("make my tests pass" is a real user ask);
  the Commit0 adapter merely configures it.
- Commit0 comparisons use multi-run medians with the distribution quoted;
  single runs are too noisy to compare releases on (measured, evidence #1).
- Anvil executing workspace code is a **new capability class** — v0.1.4's
  security posture for it must be explicit (see proposal).
