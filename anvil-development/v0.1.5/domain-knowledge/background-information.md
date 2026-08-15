# Anvil v0.1.5 — background information

Input document for the v0.1.5 proposal. Records the evidence, the design
discussion, and the decisions — including two that overturn constraints
recorded in v0.1.4. Written before the proposal, per the doc pipeline
(background-information → proposal → spec → architecture → code); v0.1.3
skipped the middle and #25 was back-filled, and neither is repeated here.

Everything numeric below was re-derived from the v0.1.4 run artifacts on
2026-08-15 by running Anvil's own `verify/localize.py` against the stored
JUnit reports. Nothing is quoted from memory.

## Primary objective (set 2026-08-15)

v0.1.4 made the repair loop real and measured it: tinydb median 61/201
(30.3%) against the v0.1.3 one-shot baseline median 24 (11.9%), with the
import-failure arm deleted (floor 47 vs 0). The loop works.

v0.1.5's objective is to make the loop **repair the right file**. The
measurement below shows the loop is not limited by its ability to fix
code — it is limited by its ability to identify *which* code is wrong.

## What the v0.1.4 measurement actually showed

Re-running `try_parse_report` + `cluster` over the final-round JUnit report
of each valid v0.1.4 run (`v0.1.4-fix-r1/r2/r3`, tinydb):

| run | failures | localized | unlocalized (`file=None`) |
|---|---|---|---|
| fix-r1 | 140 | 113 | 27 (19%) |
| fix-r2 | 154 | 144 | 10 (6%) |
| fix-r3 | 67 | 24 | **43 (64%)** |

Two findings, in order of importance.

### 1. The blind spot concentrates where the ceiling is

The unlocalized fraction is not stable — 6%, 19%, 64%. It is **highest in
the run with the fewest failures**. That follows from the mechanism:
`_implicated_target` (`verify/localize.py:64`) matches source *basenames*
against traceback text, so it resolves failures whose frames enter library
code. While generated code is badly broken those dominate — crashes name
files. Once the code mostly works, what remains are assertion mismatches
that fail *inside the test function*, so every frame is in `tests/` and no
source basename ever appears.

Crashes name files. Assertions name symbols. The localizer only reads the
first kind, so it goes dark precisely on the last mile — the part that
separates 61/201 from a better number.

A representative dropped failure, `fix-r3`:

```
tests.test_tables.test_query_cache_with_mutable_callable[memory]
E  + where <bound method QueryInstance.is_cacheable of Query()> = Query().is_cacheable
E  +   where Query() = <bound method Query.map of Query()>(<function ...lambda...>)
E  +     where Query() = where('val')
```

Unmistakably about `tinydb/queries.py` — it names `QueryInstance.is_cacheable`,
`Query.map`, `where()`. The literal string `queries.py` never appears, so the
cluster carries `file=None`.

An unlocalized cluster is then **silently discarded**:
`sdk/openhands_adapter.py:799` reads `if entry.file and entry.file not in
excerpts`. No warning, no event, no prompt. Note the asymmetry: if *every*
cluster is unlocalized the code falls through to `list(artifacts)` and
repairs everything, but *partial* localization drops the blind clusters
entirely. In `fix-r3` that discarded 43 of 67 failures.

### 2. Symptom-based localization targets the failure site, not the fault

This is the finding that changed the design, and it invalidates the first
fix considered (see "Rejected" below).

Symbol matching was prototyped against the same reports: parse each source
file's top-level defs/classes, look for those names in the failure text,
attribute by hit count. Coverage is good — 53 of the 80 unlocalized
failures (66%) become attributable, 28 of 43 in `fix-r3`. Attribution
quality is not:

| file | in candidate set | selected by hit count |
|---|---|---|
| `tinydb/queries.py` | 28 | 12 |
| `tinydb/database.py` | 25 | 16 |
| **`tinydb/table.py`** | **20** | **0** |
| `tinydb/utils.py` | 1 | 0 |

89% of recovered failures implicate more than one module (21 of 28
implicate three). `table.py` is a candidate in 20 of 28 failures and is
selected **zero** times — consistently outvoted by the modules that consume
it. If `table.py` produces wrong data that `database.py` and `queries.py`
operate on, every repair goes to the consumer and the producer is never
touched.

`utils.py` appears once. v0.1.3's temperature-0 experiment found two
independent runs choosing the same wrong `with_typehint` — which lives in
`utils.py`. Low-level helpers are systematically invisible to
symptom-based localization because their names do not appear in
high-level assertion messages; the more load-bearing a function is, the
less likely it is to be named at the failure site.

The existing basename matcher shares this flaw: it keeps the *deepest*
traceback line naming a target, and the deepest frame is the raise site.
Symbol matching does not introduce the problem — it inherits it, and by
replacing "no answer" with a confident wrong answer it can narrow the
write-set onto the consumer and foreclose the fix. Coverage without
selection is not obviously an improvement.

### The v0.1.4 escalation trigger has fired

v0.1.4's background doc (`:204-207`) pre-registered the condition:

> v0.1.5 escalates to full dependency-slice *source* if the measurement
> shows cross-module clusters still killing repaired runs.

It does, with numbers. Cross-module clusters are 89% of the recovered
population. The escalation is not a new idea; it is the planned branch.

## Decisions recorded from the design discussion (2026-08-15)

- **Fault selection is a reasoning task, not a lookup.** Deciding that `A`
  returned a wrong value that `B` asserted on cannot be derived from name
  frequency. Localization splits into two stages: mechanical **candidate
  generation** (what symbol matching is good at) and **fault selection**
  (given to the model, with dependency direction and slice source as
  evidence).
- **Write-set constraint overturned.** v0.1.4's background doc states "the
  write-set stays restricted to implicated files in both." That constraint
  is why `table.py` cannot be fixed. The write-set becomes the *candidate
  set* — typically three files — which is still far narrower than the
  existing all-artifacts fallback. Overturned deliberately, on the
  `20 candidates / 0 selections` evidence, not dropped quietly.
- **Ranking is producer-first, not mention-first.** Mention frequency is
  biased toward consumers because that is where assertions live. Where
  `interface_map.py`'s dependency edges show `A → B`, `A` ranks above `B` —
  the inverse of the prototype's ordering.
- **Codebase MCP: rejected again**, and the v0.1.4 rationale stands
  unchanged (deterministic, free, testable; Anvil already has the AST
  muscle). The new evidence does not move it, because what is missing is
  data-flow inference rather than retrieval — an index would return a
  better-organized version of a graph `interface_map.py` already builds.
  Two additional reasons now recorded: an eval harness needs localization
  reproducible, and a server adds a daemon, network, and version skew to
  the exact component whose output is being attributed; and `MCPManager`
  is never constructed in a real run (unwired ring, see below), so no MCP
  is available without doing v0.1.6's work first. **Revisit when the
  `patch` tier is scoped** — localizing in a 100k-line repo you did not
  write is a retrieval problem, and that is where it earns its cost.
- **Governance ring deferred to v0.1.6.** `drift/`, `hooks/`,
  `config/projection.py`, `SpecialistRegistry`, `MCPManager`, `skills/`
  are built, unit-tested, documented, and never constructed by
  `_build_real_manager`. Real, but it produces no number: bundling it with
  a scored release makes the delta unattributable, and drift can only move
  a Commit0 score neutrally or downward. It ships as its own release with
  "the path is provably entered" as the acceptance criterion.
- **Drift lands report-only when it lands.** No `drift_context_provider`
  implementation exists anywhere — only the constructor parameter and
  `DriftContext` hand-built in tests. Wiring it means writing a new
  extractor over LLM-written markdown, and `_post_phase_checks` *fails the
  phase* on major/critical drift. A name-matching miss would turn working
  runs into failures. It arrives behind a flag, emitting events without
  failing phases, until the extractor has an accuracy measurement.
- **Docker validation does not gate this release.** Every measurement to
  date runs `open`/`local` (`evals/anvil_eval/config.py:31`). Code
  execution already works; Docker changes *where* it runs, which matters
  for the restricted-profile safety story but is independent of
  localization. It goes with the ring in v0.1.6, where the acceptance
  criterion is a real daemon.
- **Generated tests are not authoritative for the repair loop.** An
  LLM-written test can be wrong, and treating it as ground truth lets the
  loop damage a correct implementation to satisfy a bad assertion —
  producing no score gain against Commit0's hidden reference tests, and
  possibly a loss. Repair may revise a test only under the guard below.
- **The no-weakening guard.** If a test is revised, the collected test
  count must not decrease. This blocks the degenerate "delete the failing
  assertion" strategy more robustly than a prose rule, and is mechanically
  checkable via `pytest --collect-only`.

## Rejected

- **Test-file → module path mapping.** The first fix considered. The
  worked example above fails it: the failure is in `tests/test_tables.py`
  but the fault is in `queries.py`. Path-shaped heuristics encode the
  wrong assumption; symbol-shaped ones at least see the right names.
- **Symbol matching with argmax selection.** Rejected on the
  `table.py 20/0` evidence. Retained as candidate generation only.
- **Contract ledger / greenfield doc drift.** Still deferred, unchanged
  from v0.1.4 — different instrument, would muddy attribution.

## Issue ledger

### Closed by this release

- **#28** — unlocalized clusters silently dropped
  (`openhands_adapter.py:799`); failure-site rather than fault-site
  attribution; producer modules unwritable.
- **#29** — signature-only repair context insufficient for cross-module
  clusters (v0.1.4's pre-registered escalation).
- **#30** — `qa` emits three identical `GENERATED.md` files and no
  executable tests; `ARTIFACT_SCHEMAS["qa"]` cannot detect it.
- **#31** — `RepairRoundCompleted` carries exit code only, so v0.1.4's
  "per-round pass counts monotone non-decreasing" was never checkable
  (FR-RL-010, deviation recorded in the v0.1.4 implementation log).
- **#32–#35** — supervisor correctness: resume ignores tier exclusions;
  retry counters never persisted; "rounds exhausted" reported as failure
  when it is the loop's normal benchmark exit; health endpoint reports
  shipped subsystems as `"pending"`.

### Still open — deferred beyond v0.1.5

1. **Governance ring activation + Docker daemon validation** — v0.1.6,
   as one release, per the decisions above.
2. **Wrong-idea persistence.** Two temp-0 runs chose the same wrong
   `with_typehint`. #29's slice source gives a repair round more to work
   with, but a round that re-reads the same context can re-choose the same
   design. An explicitly-different-approach prompt on repeated cluster
   failure remains open; #28's escalation ladder is the partial answer.
3. **The agent layer is vestigial.** All 13 `agents/phases/*.py` are stubs
   and `BridgeExecutor` never calls `agent.run()` — it reads
   `agent.phase_id` and delegates to `SessionBridge`. A real architectural
   question, deliberately not this release's.
4. **SWE-bench / the `patch` tier.** Roughly half its difficulty is
   localization in a large existing repo, which the 13-phase greenfield
   waterfall has no phase for. Needs its own proposal; the v0.1.4 repair
   loop and #28's fault selection are the reusable assets.

## Constraints carried into this release

- **Measurement discipline: two surfaces, one variable each.** #28+#29 are
  the score-affecting bundle and are measured on Commit0 tinydb under
  conditions **identical to v0.1.4** (`open`/`local`, same instances,
  median-of-3, distribution quoted). #30 is inert on Commit0 —
  `graft_and_test.py` runs the snapshotted original tests — so it is
  measured on the `evals/` smoke suite instead. No executor change, no
  governance wiring, nothing else score-affecting lands in the same
  release. This is the v0.1.3 discipline, held.
- **Config-gated for ablation**, as #26/#27 were: `#28` and `#29` each
  switchable off, so the bundle can be decomposed after the fact.
- **Localizing is not repairing.** The 66% recovery figure is the ceiling
  on what becomes *visible*, not a prediction of score. The honest claim
  for the release is that more failures enter repair; how many are fixed
  is the thing being measured.
- **Evidence caveats, stated up front.** The three reports are
  final-state, one per run — per-round distributions were not
  reconstructed. One repo (tinydb); cachetools at 177/215 may look
  nothing like this. Symbol matching can mis-attribute, so #28 must be
  shown not to degrade currently-working localization, which is what the
  ablation gate is for.
- **Existing tools over new machinery**, unchanged: pytest's JUnit XML,
  the repo's own `ast` muscle, the existing `RetryController` and
  escalation machinery. No new external dependency.
