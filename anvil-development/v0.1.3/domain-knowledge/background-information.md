# Anvil v0.1.3 — background information

v0.1.3 is driven by measured evidence, not filed issues: the Tier-1 eval
harness (`evals/`, 2026-07-10) and the Commit0 benchmark adapter
(`benchmarks/commit0/`, 2026-07-10/11) produced the first hard numbers on
Anvil and a precise defect list. Full run log: `benchmarks/commit0/STATUS.md`.

## The evidence

1. **Contract drift (smoke suite, real mode).** v0.1.2 resolved 3/6 tasks.
   All three failures lost the request's *interface contract* (file names,
   signatures, return shapes) between the request and the implementation —
   traced to the spec phase paraphrasing it away (`"issues"`: 2 mentions in
   the request, 0 in spec.md, `bool` instead of the pinned dict in code).
   Per-task standing instructions ("quote contracts verbatim") lifted the
   score to 6/6 (+50 pts) — proving delivery-by-injection works, but paying
   for it by re-quoting the contract through every doc artifact.

2. **Output truncation (Commit0 tinydb, run `v0.1.2` 02:13).** The spec phase
   escalated after 3× `finish_reason=length`: completion budgets were
   hardcoded (400/1500/4000). Fixed during the cycle as **#19** (config +
   env overrides, mirroring #18's input-side fix); formalized in this
   release.

3. **Skeleton blindness (Commit0 tinydb, run 02:46).** With #19 the run
   completed and generated 48/50 stub implementations under exactly the
   right names — but regenerated whole modules from `plan.md`/`blueprint.md`
   (its only inputs), dropping everything the skeleton already provided
   (`QueryLike`, `FrozenDict`, `LRUCache`, `MemoryStorage`) and breaking
   import. The implementation phase never reads the files it is completing,
   and a single completion per phase cannot hold a library.

4. **No external verification.** Commit0 ships the library's own test suite
   precisely so agents can run it and repair; Anvil has no
   run-tests-and-fix loop, so every defect above survived to scoring.

## The through-line

#18 fixed *input* truncation; #19 fixed *output* truncation; the remaining
failures are **transport** (the task's binding facts don't survive the
phase-to-phase retelling) and **verification** (nothing checks generated
code against the task or its tests). v0.1.3 fixes transport (#20, #22) and
adds *contract* verification (#21, mechanical). *Test* verification — the
repair loop (#23) — is deliberately deferred to v0.1.4: it would fix the
same defect class #20 prevents, making a green run unattributable. v0.1.3
is measured one-shot; the repair loop is then measured as its own delta.

## Constraints carried into this release

- `anvil-instructions.md` stays a behavioral-policy channel; its content and
  role are frozen (team decision, 2026-07-11). Task-scoped facts need their
  own channel — they must not colonize the instructions file.
- Benchmarks remain adapter-only consumers: no Anvil forks, no
  benchmark-special modes. Features below must make sense for ordinary
  users first (fill-in-my-skeleton and make-my-tests-pass are real user
  asks, not benchmark hacks).
