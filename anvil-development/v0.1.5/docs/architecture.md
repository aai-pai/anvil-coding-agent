# Anvil Architecture — v0.1.5 (delta)

How the v0.1.5 spec's requirements land in the existing runtime. Delta
against the v0.1.4 architecture; only touched components described.
Derived from [spec.md](spec.md).

## The boundary question (decided first, because it constrains everything)

v0.1.4's architecture states the rule plainly:

> All four verify modules stay **mechanical — no LLM involvement**; the
> only LLM calls remain `LLMBackend`'s repair completions. That boundary
> is the architecture: localization and context assembly are
> deterministic and unit-testable with no provider.

FR-FL-004 introduces a model call *into localization*. Taken naively that
breaks the rule and makes `verify/` untestable without a provider.

**Decision: the boundary holds, and the split runs through the middle of
#28.** Candidate generation and ranking (FR-FL-001/002/003) are
mechanical and live in `verify/`. Fault *selection* (FR-FL-004) is a
completion and therefore lives in `LLMBackend`, exactly where every other
completion lives. `verify/` hands up a ranked candidate set; the sdk layer
decides. No provider ever enters `verify/`, and selection stays unit-
testable through the existing fake-provider seam.

This is why FR-FL-003's ranking is normative rather than advisory: the
ranked first candidate is the deterministic answer the system falls back
to whenever selection is unavailable, degraded, or gated off.

## Component map

```
runtime/anvil_runtime/
  verify/
    runner.py            #23  local executor, compile smoke, basename mapping (shipped)
    docker_executor.py   #25  DockerExecutor, docker_probe, DockerError (shipped)
    localize.py          #26  junit parsing + clustering (shipped) — #31 adds counts
    interface_map.py     #27  AST interfaces + connection ranking (shipped)
    candidates.py        #28  NEW — symbol index, candidate sets, producer-first rank
    slices.py            #29  NEW — dependency-ranked body slices under a budget
  sdk/openhands_adapter.py    LLMBackend: loop orchestration, fault SELECTION, prompts
  artifacts/schemas.py        #30  qa schema gains a collect-only assertion
  artifacts/validator.py      #30  qa validation path
  core/development_manager.py #32/#33/#34  resume, retry persistence, exhausted status
  core/retry_controller.py    #33  snapshot wired to checkpoint
  api/routes_health.py        #35  honest subsystem state
  config/schema.py            knobs: repairLocalization, repairContext=slices, qaTests
  app.py                      env wiring (env > config > default, throughout)
```

`candidates.py` and `slices.py` are mechanical, provider-free, and
unit-tested against the stored v0.1.4 JUnit reports as fixtures.

## One AST pass per round, three consumers

`interface_map.py` already walks every artifact per round. #28 needs a
symbol→file index and #29 needs dependency edges — both derivable from the
same walk, and both required to agree with the interface map or ranking
and context will disagree about the same code.

So the walk is performed once per round and yields three products:

```
ast pass (per round) ──┬──▶ interface map   (#27, signatures)
                       ├──▶ symbol index    (#28, name → file)
                       └──▶ dependency edges (#28 ranking, #29 slice order)
```

Per **round**, not per pass: a round-1 repair adds or removes definitions
that round 2's index must see. `interface_map._names_used` and
`_top_level_defs` already compute most of this; #28/#29 consume them
rather than re-implementing the extraction.

## #28 — localization flow (revised)

1. `localize.cluster(records)` as shipped — clusters keyed
   (error type, implicated file), size-descending. Unchanged.
2. For each cluster, `candidates.build(cluster, symbol_index, edges)`
   returns a ranked candidate set: basename result first (always a member,
   FR-FL-002), then symbol matches, ordered producer-first (FR-FL-003),
   capped at 4 (FR-FL-005).
3. **Empty candidate set** → `UnlocalizedCluster` event and the existing
   fallback (FR-FL-006). The silent `if entry.file and ...` drop at
   `openhands_adapter.py:799` is deleted, not amended.
4. **Single candidate** → no selection call. Unambiguous is the common
   cheap case and must not pay for a completion.
5. **Multiple candidates** → `LLMBackend._select_fault` issues one
   completion per cluster: cluster excerpt + candidate signatures +
   dependency direction, response constrained to the candidate set. Out of
   set, unparseable, or failed → ranked first candidate + warning event.
   Never a crash path.
6. Write-set := union of the selected files across clusters. A file
   selected by two clusters gets **one** repair completion carrying both
   cluster excerpts — FR-RL-008's one-completion-per-file-per-round rule
   is preserved by deduplicating before repair, exactly as v0.1.4's
   `excerpts` dict does today.

## #29 — context flow

`slices.build(root, candidates, edges, budget)` emits the bodies of the
candidate set's upstream dependencies, dependency-ranked, degrading whole
files to signatures at the budget edge rather than truncating mid-body.
`_repair_prompt` composes:

```
contract block (never displaced)
  → dependency slices   (#29, ≤12k chars, upstream bodies)
  → interface map       (#27, ≤6k chars, everything else, signatures)
  → cluster excerpt     (#26)
```

The two caps are separate so `repairContext=interfaces` restores v0.1.4's
prompt byte-for-byte by skipping the slice call entirely — the ablation
contract stays at the prompt level and testable by string equality, as
v0.1.4 established.

## Token budget (the cost this release adds)

v0.1.4 measured 386–460k tokens per Commit0 run. v0.1.5 adds two things
and both are bounded on purpose:

- **Selection completions**: one per *ambiguous* cluster per round, not
  per file. Small prompt (excerpt + signatures), one-token-ish answer.
  Skipped entirely for single-candidate clusters (3 of 28 recovered
  failures in `fix-r3` were unambiguous).

  Selection uses **the phase's already-routed model** — the coding model —
  and introduces no new routing path. Routing it to the cheaper planning
  model is tempting and deliberately not done here: `LLMBackend` receives
  one routed `model` per step by construction (`CompletionRequest` is
  documented as "bound to a routed model"), and the routing decision is
  `SessionBridge`'s, made through `ModelRouter.select`, which is where
  policy enforcement and the `ModelRouteSelected` event live. Letting
  `LLMBackend` choose its own model would open a policy hole to save a
  small number of small completions. If the measurement says the cost
  matters, the correct mechanism is for `SessionBridge` to route a second
  model through `ModelRouter.select` and thread it onto `PhaseStep` —
  a v0.1.6 change, not an inline shortcut.
- **Slice source**: +12k chars on repair prompts that have upstream
  candidates.

Expected envelope is ~10% over v0.1.4, well inside the existing
`(rounds+1)*test_timeout+300` advance budget. If the measurement shows
otherwise, the per-round selection-call count is the knob to cap first —
it degrades to FR-FL-003 ranking, which is the defined fallback anyway.

## #30 — qa code path

`LLMBackend.run`'s `step.phase == self.CODE_PHASE` becomes membership in
`CODE_PHASES = {"implementation", "qa"}`. `qa` then needs its own target
derivation: `_code_targets` reads the contract manifest, which pins
`src/`, not tests. For `qa` the targets come from `docs/qa-test-plan.md`
plus the implemented `src/` inventory, and outputs land under the `tests/`
prefixes `_write_files` already sandboxes (FR-QT-002 — the contract is not
reshaped).

Validation moves from "the plan document exists" to "the tests collect":
`ARTIFACT_SCHEMAS["qa"]` gains a collect-only assertion run by
`artifacts/validator.py`, which already has an implementation-only
special case (`validator.py:79`) and gains a qa one alongside it.
`_write_files`' unparseable-manifest fallback is barred from `tests/`
prefixes, so a qa phase that cannot produce parseable files fails into
the existing retry instead of emitting a placeholder.

## Failure taxonomy (extended)

Additions to v0.1.4's list:

- cluster with no candidate → `UnlocalizedCluster`, fallback, continue
- selection response out-of-set/unparseable → warning, ranked first
  candidate, continue
- selection completion fails or times out → same degradation; a provider
  problem must not lose a round
- slice extraction error on a dependency → that file degrades to its
  signature, as #27 already does for a broken sibling
- qa tests fail to collect → artifact validation failure → existing retry
- test revision reducing collected count → round stays red (FR-QT-005),
  the same treatment FR-RL-009 gives a contract-violating repair

## Checkpoint/resume

Unchanged, and for the same reason as v0.1.4: #28/#29 are stateless within
a round and #24's `phase_progress` already carries the verify/repair unit
boundary. A resume mid-loop re-runs the current round from the test run,
which rebuilds the AST pass, the candidates, and the slices from disk —
idempotent.

#33 is the one checkpoint change in this release, and it is orthogonal to
the loop: `RetryController.snapshot()` is written into
`RunState.retry_counters` at checkpoint and restored on resume, closing
the gap where a restart silently reset every phase's retry budget.
