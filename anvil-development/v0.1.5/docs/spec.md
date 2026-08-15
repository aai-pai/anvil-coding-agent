# Anvil Specification — v0.1.5

Normative requirements for the [v0.1.5 proposal](proposal.md). The
[v0.1.4 specification](../../v0.1.4/docs/spec.md) remains in force; this
document covers only what changes, and states explicitly where it
supersedes a v0.1.4 requirement.

Evidence for every design choice is in
[background-information.md](../domain-knowledge/background-information.md),
re-derived from the stored v0.1.4 run artifacts on 2026-08-15.

Two v0.1.4 requirements are partially superseded here, both deliberately
and both narrowly: FR-RL-008's final sentence ("non-implicated files are
never regenerated") by FR-FL-005, and FR-IC-003's restatement of that
write-set rule by FR-FL-005 and FR-DS-003 — in each case for candidate-set
files only, and in each case leaving the rest of the requirement intact.
One v0.1.4 requirement is closed rather than changed: FR-RL-010 already
mandated pass movement on `RepairRoundCompleted`; the implementation
shipped exit code only, and §4 implements what was already required.

## 1. Fault-Aware Repair Localization (#28)

Localization splits into candidate generation (mechanical) and fault
selection (model). FR-JL-003's basename clustering is retained and feeds
the first stage rather than being replaced.

- **FR-FL-001 (symbol index)**: For each repair round, an AST index of the
  generated artifacts maps every top-level and class-level definition name
  to its file, built with the same plain `ast` extraction
  `verify/interface_map.py` already performs. Names of 3 characters or
  fewer are excluded as noise. A syntax-broken artifact contributes no
  symbols and is recorded as such — it is never silently absent.
- **FR-FL-002 (candidate generation)**: A cluster's failure text (message
  plus frame excerpt) is matched word-boundary-wise against the symbol
  index. The result is a candidate **set**, not a single file. Any file
  FR-JL-003's basename match already implicated is always a member of that
  set, so candidate generation is strictly additive.
- **FR-FL-003 (producer-first ranking)**: Candidates are ordered by
  dependency direction taken from the interface map's edges: where `A → B`
  (B references A), `A` ranks above `B`. Remaining ties break by symbol
  hit count descending, then by path, so ordering is deterministic.
  Mention frequency alone must not decide order — it is biased toward
  consumers, because assertions live at the failure site.
- **FR-FL-004 (fault selection)**: The model receives the cluster excerpt,
  the candidate signatures, and the dependency direction between
  candidates, and names the file to repair. The response must name a
  member of the candidate set; an unparseable or out-of-set response
  degrades to the FR-FL-003 ranked first candidate with a warning event.
  Selection is never a crash path.
- **FR-FL-005 (write-set — supersedes FR-RL-008's final sentence)**: The
  write-set for a cluster is its candidate set, capped at 4 files by
  FR-FL-003 order. FR-RL-008's "non-implicated files are never
  regenerated" no longer holds; its one-repair-completion-per-file-per-round
  rule is unchanged and applies to each candidate. This
  overturns v0.1.4's "write-set stays restricted to implicated files": a
  module producing wrong data for its consumers must be reachable. The cap
  keeps the write-set far narrower than the existing all-artifacts
  fallback; files outside it remain read-only.
- **FR-FL-006 (no silent drop)**: A cluster that yields no candidate emits
  an `UnlocalizedCluster` event carrying error type and failure count, and
  falls back to existing behavior. This replaces
  `sdk/openhands_adapter.py:799`'s silent discard, which dropped 43 of 67
  failures in the healthiest v0.1.4 run with no warning, no event, and no
  prompt.
- **FR-FL-007 (gate)**: `ANVIL_REPAIR_LOCALIZATION=symbols` (default) |
  `basename` (v0.1.4 behavior, for ablation). Config field
  `repairLocalization`, usual precedence.
- **FR-FL-008 (no regression)**: With the gate on `symbols`, every file
  the `basename` path would have implicated for a given report is still
  implicated. Coverage may only grow. This is the guard against replacing
  a correct narrow answer with a confident wrong one.

**Test:** symbol index excludes ≤3-character names and marks broken
artifacts; candidate set is a superset of the basename result for the
stored v0.1.4 reports; producer ranks above consumer given an `A → B`
edge, and mention count does not reorder it; out-of-set model response
degrades to first candidate with a warning; write-set capped at 4 and
files outside it unmodified; a cluster with no candidate emits
`UnlocalizedCluster` and is not dropped; `basename` restores v0.1.4
behavior byte-for-byte.

## 2. Dependency-Slice Repair Context (#29)

Escalation from FR-IC-001's signature-only map, on the condition v0.1.4's
background doc pre-registered: cross-module clusters are 89% of the
recovered failure population.

- **FR-DS-001 (slice content)**: The repair prompt carries the **bodies**
  of the candidate set's upstream dependencies — the files those
  candidates import or reference — in addition to FR-IC-001's signature
  map for everything else. Selecting `A` over `B` requires seeing what `A`
  does, not merely what it is called.
- **FR-DS-002 (slice budget)**: Slice source is dependency-ranked and
  capped by a character budget (default 12,000, separate from FR-IC-002's
  6,000-char interface cap). Files exceeding the remaining budget degrade
  to their signatures rather than being truncated mid-body, with an
  `(N files reduced to signatures)` note. The contract block is never
  displaced.
- **FR-DS-003 (write boundary — supersedes FR-IC-003 for candidates)**:
  Slice source is read-only context. Only candidate-set files (FR-FL-005)
  are writable; every other file whose body appears in the prompt must be
  unchanged after the round.
- **FR-DS-004 (gate)**: `ANVIL_REPAIR_CONTEXT=slices` (default) |
  `interfaces` (v0.1.4 behavior) | `minimal` (first-iteration prompts).
  Extends the existing v0.1.4 gate rather than adding a new one; config
  field `repairContext`, usual precedence.

**Test:** prompt contains upstream bodies for candidates and signatures
only for the rest; budget exhaustion degrades whole files to signatures
with the note, never a mid-body cut; a read-only sliced file is
byte-identical after the round; `interfaces` and `minimal` restore v0.1.4
and first-iteration behavior respectively.

## 3. Executable QA Tests (#30)

- **FR-QT-001 (routing)**: `qa` reaches the code path. `LLMBackend.run`'s
  single-phase `CODE_PHASE` check becomes a set membership test. `qa` uses
  its own prompt mode — implementation source as context, outputs under
  `tests/`, imports resolving against the real package layout — and is not
  a reuse of the implementation prompt.
- **FR-QT-002 (contract unchanged)**: `PHASE_CONTRACTS["qa"]`'s
  directory-shaped `allowed_outputs` are retained. Test filenames are not
  knowable at contract-definition time, and `_write_files` already treats
  `output_paths` as sandbox prefixes, which is the correct behavior. Only
  the routing was wrong; the contract is not to be reshaped.
- **FR-QT-003 (no markdown under `tests/`)**: On a successful `qa` phase
  no `GENERATED.md` is written under any `tests/` directory.
  `_write_files`' unparseable-manifest fallback must not target a `tests/`
  prefix; a `qa` phase that cannot produce parseable files fails and
  drives the existing retry rather than emitting a placeholder document.
- **FR-QT-004 (validation)**: `ARTIFACT_SCHEMAS["qa"]` requires that
  `pytest --collect-only` succeeds against the generated tests and
  collects a non-zero count. File existence and a `.py` extension are
  insufficient — three files containing `assert True` would satisfy them.
  Collection failure is an artifact validation failure, handled by the
  existing machinery.
- **FR-QT-005 (test authority + no-weakening guard)**: Generated tests are
  **not** authoritative for the repair loop. A repair round may revise a
  generated test only when the collected test count does not decrease,
  verified via `--collect-only` before and after. A revision that reduces
  the count is rejected and the round is treated as still red, exactly as
  FR-RL-009 treats a contract-violating repair. Reference tests supplied
  through `externalTestCommand` are never revisable.
- **FR-QT-006 (gate)**: `ANVIL_QA_TESTS=generate` (default) | `plan-only`
  (v0.1.4 behavior). Config field `qaTests`, usual precedence. Commit0
  runs use `plan-only` so their token cost and measurement surface are
  unchanged.

**Test:** `qa` routes to the code path and writes `.py` files under
`tests/`; `--collect-only` collects a non-zero count; no `GENERATED.md`
under `tests/` on success; a manifest-unparseable `qa` phase fails rather
than emitting a placeholder; a test revision reducing the collected count
is rejected and the round stays red; `plan-only` restores v0.1.4 behavior.

## 4. Repair Round Telemetry (#31)

Closes FR-RL-010, recorded as a deviation in the v0.1.4 implementation
log and deferred to this release.

- **FR-TM-001 (pass counts on the wire)**: `RepairRoundCompleted` carries
  per-round passed, failed, and collected counts, parsed from the JUnit
  report. Where no report exists the fields are absent rather than zero —
  absent means unknown, and must not be read as regression.
- **FR-TM-002 (monotonicity observable)**: The per-round series is
  recoverable from `logs/events.jsonl` alone, so v0.1.4's acceptance
  criterion "per-round pass counts monotone non-decreasing" becomes
  checkable against real run data without re-instrumenting a run.

**Test:** counts present and correct for a JUnit-reporting command; fields
absent (not zero) with no report; the round series reconstructs from the
event log alone.

## 5. Supervisor correctness (#32–#35)

- **FR-FX-001 (resume honors exclusions)**: `resume_run` computes its
  resume target as `next_phase(ctx.completed | ctx.excluded)`, matching
  `step()` and `_progress()`. A resumed `simple` or `standard` run must
  not report a target the next `step()` immediately skips.
- **FR-FX-002 (retry budgets persist)**: `RetryController.snapshot()` is
  written to `RunState.retry_counters` at checkpoint and restored on
  resume. A restart must not reset a phase's retry budget; today
  `snapshot()` has zero callers.
- **FR-FX-003 (exhausted rounds are not failure)**: A repair loop that
  exhausts its rounds without going green is reported distinctly from a
  phase failure. On a benchmark this is the loop's normal exit — the full
  suite is unreachable on tinydb by construction — and reporting it as
  failure distorts every benchmark run's outcome.
- **FR-FX-004 (honest health)**: `routes_health.py` reports real state for
  `openhands`, and reports `mcp_discovery` honestly as not wired rather
  than `"pending"`. A subsystem that is not constructed in a real run must
  not be reported as merely pending.

**Test:** resumed excluded-tier run targets a phase that is not
immediately skipped; retry counts survive a simulated restart mid-run;
exhausted-rounds status is distinguishable from phase failure in both run
status and the event log; health reflects actual wiring.

## 6. Out of scope

Governance-ring activation and Docker daemon validation (v0.1.6,
together); SWE-bench and the `patch` tier; reviving the agent layer;
renaming `openhands_adapter.py` and its classes; wrong-idea persistence
(the explicitly-different-approach prompt). Rationale in the proposal.

## 7. Acceptance

1. On the stored v0.1.4 JUnit reports, `symbols` localization attributes
   ≥60% of previously-unlocalized failures **and** implicates every file
   `basename` implicated (FR-FL-008).
2. A repair round demonstrably writes to an upstream producer the v0.1.4
   loop could not reach — the `tinydb/table.py` case, end to end.
3. No cluster is discarded without an `UnlocalizedCluster` event.
4. `RepairRoundCompleted` carries pass counts, and monotonicity is checked
   against a real run from the event log alone.
5. `qa` produces `.py` files collected by `pytest --collect-only` with a
   non-zero count, and no `GENERATED.md` under `tests/`; a count-reducing
   test revision is rejected.
6. Resumed excluded-tier run targets a non-skipped phase; retry budgets
   survive a restart.
7. Commit0 tinydb median-of-3 under conditions **identical to v0.1.4**
   (`open`/`local`, same instances), reported with its distribution
   against the median 61/201 baseline — **including if it fails to move**.
   Smoke holds 6/6; cachetools holds 177/215.
8. Every gate restores prior behavior: `basename`, `interfaces`,
   `minimal`, and `plan-only` each reproduce the documented earlier
   behavior, so the release decomposes for ablation.
