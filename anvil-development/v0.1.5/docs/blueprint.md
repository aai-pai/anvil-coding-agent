# Anvil Blueprint — v0.1.5 (delta)

File-level construction plan for the v0.1.5 spec. Delta against the
v0.1.4 blueprint; only new and touched files described. Derived from
[architecture.md](architecture.md).

The `verify/` provider-free boundary is load-bearing throughout: every new
module here is mechanical and unit-testable with no provider. The single
new LLM call (fault selection) lands in `sdk/openhands_adapter.py`, where
every other completion already lives.

## New files

### `runtime/anvil_runtime/verify/candidates.py` (#28)

- `MAX_CANDIDATES = 4` (FR-FL-005 cap), `MIN_SYMBOL_CHARS = 4` (FR-FL-001
  excludes names of 3 characters or fewer as noise).
- `build(cluster, index, basename_file) -> list[str]` — the ranked
  candidate set for one cluster:
  - seed with `basename_file` when the cluster has one (FR-FL-002: the
    basename result is *always* a member, so generation is strictly
    additive and FR-FL-008 holds by construction rather than by test);
  - match the cluster's text (message + excerpt of each record)
    word-boundary-wise against `index.symbols`, accumulating per-file hit
    counts;
  - order producer-first from `index.edges` — where `A → B` (B references
    A), `A` precedes `B`; ties by hit count desc, then by path
    (FR-FL-003, deterministic);
  - truncate to `MAX_CANDIDATES`, preserving the seed.
- Returns `[]` when nothing matches — the FR-FL-006 signal. Never raises.
- Pure functions over an `AstIndex`; no filesystem access, no provider.

### `runtime/anvil_runtime/verify/slices.py` (#29)

- `SLICE_MAX_CHARS = 12_000` (FR-DS-002, separate from
  `INTERFACE_MAP_MAX_CHARS`).
- `build(root, candidates, index, cap=SLICE_MAX_CHARS) -> str` — bodies of
  the candidates' upstream dependencies (files the candidates
  import/reference), dependency-ranked. A file that will not fit in the
  remaining budget degrades to its signature block rather than being cut
  mid-body; the block ends with `({n} files reduced to signatures)` when
  any did. Candidates themselves are not sliced — their source is already
  in the repair prompt.
- Syntax-broken dependency → its signature line only, matching #27's
  `(currently broken)` handling. Returns `""` when there are no upstream
  dependencies, so `_repair_prompt` composition is unconditional.

## Modified files

### `runtime/anvil_runtime/verify/interface_map.py`

The shared AST pass (architecture §"One AST pass per round").

- `AstIndex` (pydantic): `symbols` (`name -> rel`, first definer wins),
  `edges` (`rel -> set[rel]` it references), `broken` (`set[rel]`).
- `index(root, artifacts) -> AstIndex` — one `ast.parse` per artifact,
  reusing the existing `_names_used` and `_top_level_defs` rather than
  re-implementing extraction. Class-level definitions are indexed as well
  as top-level (FR-FL-001).
- `build(root, artifacts, failing_rel, cap, index=None)` — gains an
  optional prebuilt index so the round performs one walk, not three.
  Default `None` preserves the current signature and behavior exactly.

### `runtime/anvil_runtime/verify/localize.py` (#31)

- `FailureCounts` (pydantic): `passed`, `failed`, `collected`.
- `try_parse_counts(path) -> FailureCounts | None` — from the JUnit root's
  `tests`/`failures`/`errors`/`skipped` attributes. `None` when the report
  is missing or unparseable; **never zero-as-unknown** (FR-TM-001: absent
  means unknown and must not read as regression).

### `runtime/anvil_runtime/sdk/openhands_adapter.py`

- `CODE_PHASES = {"implementation", "qa"}`; `run()`'s
  `step.phase == self.CODE_PHASE` becomes membership (FR-QT-001).
  `CODE_PHASE` retained as the implementation constant.
- `localize()` rewritten: per cluster, `candidates.build(...)`; empty →
  `UnlocalizedCluster` event + existing fallback (FR-FL-006, replacing the
  silent `if entry.file and ...` drop at today's line 799); single → that
  file, no completion (architecture §#28 step 4); multiple →
  `_select_fault`. Selected files dedupe across clusters into one
  write-set entry carrying both cluster excerpts (FR-RL-008's
  one-completion-per-file rule preserved).
- `_select_fault(step, model, cluster, candidates, index) -> str` — one
  completion: cluster excerpt + candidate signatures + dependency
  direction; response constrained to the candidate set. Out-of-set,
  unparseable, or provider failure → `candidates[0]` + a warning event.
  Uses the step's already-routed `model`; introduces no routing path
  (architecture §"Token budget").
- `_repair_prompt` composes contract → slices (#29) → interface map (#27)
  → cluster excerpt (#26). `repairContext == "interfaces"` skips the slice
  call so v0.1.4 prompts reproduce byte-for-byte; `minimal` unchanged.
- `_qa_targets(step)` — test targets from `docs/qa-test-plan.md` plus the
  `src/` inventory, *not* the contract manifest (which pins `src/`).
  `_qa_prompt` is its own mode, not a reuse of the implementation prompt.
- `_write_files` fallback is barred from `tests/` prefixes (FR-QT-003): a
  qa phase with an unparseable manifest fails into the existing retry
  rather than writing `GENERATED.md` under `tests/`.
- `RepairRoundCompleted` gains `passed`/`failed`/`collected` when known
  (FR-TM-001).
- Test-revision guard (FR-QT-005): collected count before/after a round
  that touched `tests/`; a decrease marks the round red, the same path
  FR-RL-009 uses for a contract-violating repair.

### `runtime/anvil_runtime/artifacts/schemas.py` + `validator.py` (#30)

- `ARTIFACT_SCHEMAS["qa"]` gains a collect-only requirement.
- `validator.py` gains a `qa` branch beside the existing
  `if phase_id == "implementation"` special case at line 79: run
  `pytest --collect-only` against the generated tests; zero collected or a
  collection error is an `ArtifactValidationFailed`, driving the existing
  retry. Subprocess invocation is injectable so unit tests need no pytest
  subprocess.

### `runtime/anvil_runtime/core/development_manager.py` (#32/#33/#34)

- `resume_run`: `next_phase(ctx.completed | ctx.excluded)` (FR-FX-001),
  matching `step()` and `_progress()`.
- Checkpoint write includes `self._retries.snapshot(run_id)`; `resume_run`
  restores it (FR-FX-002).
- Exhausted repair rounds surface distinctly from phase failure
  (FR-FX-003) in both run status and the event log.

### `runtime/anvil_runtime/core/retry_controller.py` (#33)

- `restore(run_id, counters)` — the read side of `snapshot()`, which today
  has zero callers.

### `runtime/anvil_runtime/api/routes_health.py` (#35)

- `build_checks()` reports real state for `openhands` and reports
  `mcp_discovery` honestly as not wired, replacing the hardcoded
  `"pending"` and its stale "Slice 5 flips these" comment.

### `runtime/anvil_runtime/config/schema.py` / `app.py`

- `repairLocalization` (`symbols` | `basename`), `repairContext` gains
  `slices` as default, `qaTests` (`generate` | `plan-only`);
  `SLICE_MAX_CHARS`. Env wiring `ANVIL_REPAIR_LOCALIZATION`,
  `ANVIL_REPAIR_CONTEXT`, `ANVIL_QA_TESTS` with the usual
  env > config > default precedence.

### `benchmarks/commit0/commit0_adapter/`

- Runs pin `qaTests=plan-only` so the Commit0 measurement surface and
  token cost are unchanged from v0.1.4 (proposal §Measurement).

## Test fixtures (blocking, not incidental)

`benchmarks/commit0/results/` is gitignored — `git check-ignore` confirms
the v0.1.4 JUnit reports are untracked. Spec acceptance criterion 1 and
FR-FL-008's regression test both reference "the stored v0.1.4 reports",
so they cannot run in CI as things stand.

**A trimmed copy of one real report is committed as a fixture** under
`tests/unit/runtime/fixtures/junit-v0.1.4-fix-r3.xml`, preserving the
failure shapes that matter (assertion failures whose frames stay in test
files; the `table.py`-implicated cluster) with test bodies reduced. This
is the first committed fixture in the repo, and the directory is new.

## Tests

- `tests/unit/runtime/test_candidates.py` — basename result always a
  member; producer ranks above consumer given an `A → B` edge, and hit
  count does not reorder it; `MIN_SYMBOL_CHARS` excludes short names;
  cap at 4 preserves the seed; empty set for no match; determinism on
  repeated calls.
- `tests/unit/runtime/test_slices.py` — upstream bodies present,
  non-upstream absent; budget degrades whole files to signatures with the
  note, never a mid-body cut; broken dependency → signature only; empty
  string with no upstream.
- `tests/unit/runtime/test_interface_map.py` additions — `index()`
  symbols/edges/broken; `build(index=...)` equals `build()` without it
  (the refactor is behavior-preserving).
- `tests/unit/runtime/test_localize.py` additions — `try_parse_counts`
  from a real root; `None` (not zero) for missing/malformed.
- `test_repair_loop.py` additions — FR-FL-008 against the committed
  fixture (symbols ⊇ basename); `UnlocalizedCluster` emitted, not
  dropped; single-candidate cluster issues no selection completion;
  out-of-set selection degrades to `candidates[0]` with a warning;
  write-set capped and files outside it byte-identical; `basename` and
  `interfaces` each restore v0.1.4 behavior byte-for-byte;
  `RepairRoundCompleted` counts.
- `tests/unit/runtime/test_qa_tests.py` (new) — qa routes to the code
  path; targets from the plan not the manifest; no `GENERATED.md` under
  `tests/`; collect-only validation fails on zero collected; a
  count-reducing revision marks the round red; `plan-only` restores
  v0.1.4 behavior.
- Existing suites — resume honors exclusions; retry counters survive a
  simulated restart; exhausted rounds distinguishable from failure;
  health reflects wiring.
