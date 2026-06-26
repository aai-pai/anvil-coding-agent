# Anvil Implementation Plan — v0.1.1

Phased, sliced plan for the v0.1.1 fix release. **Delta** against the
[v0.1.0 plan](../../v0.1.0/docs/plan.md); derived from [docs/blueprint.md](blueprint.md),
[docs/architecture.md](architecture.md), and [docs/spec.md](spec.md). All work is
runtime-only.

## Conventions for every slice

- No drift: implement exactly the blueprint change; nothing speculative (Simplicity First).
- Run the **full test suite** (`pytest`) at the end of each slice; fix and retry up to
  5 times before escalating.
- Drift check vs blueprint/architecture/spec, then commit `[IMPL-Sn] …` and update the
  implementation log + mark the slice ✅ with its commit hash.
- Existing v0.1.0 tests must stay green throughout.

Slices are ordered to minimize churn on shared files
(`session_bridge.py` → S1 then S4; `development_manager.py` → S4 then S5).

---

## Slice 1 — Telemetry & routing (#12, #13)

**Objective.** Real per-tier model defaults and a non-empty `runId` on every event.

**Changes** (blueprint §5, §6): `llm/model_router.py` (real slugs + `run_id` param on
`select`), `llm/usage_tracker.py` (`run_id` param on `record`), `sdk/session_bridge.py`
(read `run_id` from `payload.phase_context`, pass to `select`/`record`), `app.py`
(`_build_real_manager` builds overrides only from explicit env vars).

**Tests.**
- Unit: `test_model_router` — no override → planning=`google/gemma-4-31b-it`,
  impl/qa=`deepseek/deepseek-v4-flash`; emitted `ModelRouteSelected` has the passed
  `runId`. `test_usage_tracker` — `record` emits `TokenUsageReported` with the `runId`.
- Integration: a run asserts all event types share one non-empty `runId`.

**Done when** FR-RT-001…003 and FR-EVT-001…002 tests pass; suite green.

---

## Slice 2 — Section-specific documents (#10)

**Objective.** No duplicated body across section headings.

**Changes** (blueprint §3): `sdk/openhands_adapter.py` `LLMBackend._document` — write
body once; add only missing required headings as explicit placeholders; add
`_has_heading`.

**Tests.**
- Unit: `test_document_writer` — a phase with required sections → body appears once;
  no section repeats the overview; missing sections become placeholders.

**Done when** FR-DOC-001…002 tests pass; suite green.

---

## Slice 3 — Per-run workspace isolation (#9)

**Objective.** Every run builds in an isolated `runs/<date>-<slug>/`.

**Changes** (blueprint §2): `api/routes_runs.py` `start_run` resolves a per-run
workspace; new helper (`slug`, `resolve_run_workspace`); prompt written into the run
workspace; manager built rooted there.

**Tests.**
- Unit: helper — slug derivation, collision suffix, date path.
- E2E: `test_per_run_isolation` — a fresh `task` run while the repo root holds
  unrelated canonical artifacts → builds the requested project under
  `runs/<date>-<slug>/`, reading only that workspace (regression for FR-001).

**Done when** FR-RUN-001…004 tests pass; suite green.

---

## Slice 4 — Complexity-gated phase selection (#11)

**Objective.** Auxiliary phases run only when the task warrants.

**Changes** (blueprint §1, §4): `core/phase_contracts.py` (`PhaseCompleteEvent.complexity_tier`);
`sdk/openhands_adapter.py` (`StepResult.complexity_tier`, proposal prompt emits
`COMPLEXITY:`, parse + strip); `sdk/session_bridge.py` (propagate tier);
`core/development_manager.py` (`excluded_for_tier`, set `ctx.excluded` after proposal,
emit `ComplexityAssessed`, feed `next_phase(completed | excluded)`).

**Tests.**
- Unit: `test_complexity_gate` — tier → excluded set; `_parse_tier` defaulting.
- Integration: `test_gated_phase_selection` — simple → 5 canonical docs + `src/` only;
  complex → full set; `ComplexityAssessed` emitted; gated `pre-deployment` gate never
  fires for a simple run.

**Done when** FR-CX-001…006 tests pass; suite green.

---

## Slice 5 — Failure-record (FR) reporting (feature)

**Objective.** Every phase failure writes an FR-001/002-style record.

**Changes** (blueprint §7): new `core/failure_record.py` (`render_fr`, `write_fr`);
`core/development_manager.py` `_handle_failure` calls `write_fr` on every failure.

**Tests.**
- Unit: `test_failure_record` — render matches the FR layout; sequence numbering;
  slug; placeholders for unknown fields; non-empty `runId`.
- Integration: `test_failure_record_written` — an induced failure writes a conforming
  `docs/failure_records/FR-001-*.md`; a second failure writes `FR-002`; phase status
  and single-writer ownership unaffected.

**Done when** FR-REC-001…005 tests pass; suite green.

---

## Final review

After S5: full-codebase drift check vs spec/architecture/blueprint, run the complete
suite (unit + integration + e2e) green, confirm a representative real/offline run
produces the expected artifacts + events, then final commit.

## Gap Analysis (Blueprint → Plan)

| Blueprint | Slice |
|---|---|
| §2 #9 per-run workspace | S3 |
| §3 #10 document writer | S2 |
| §1, §4 #11 complexity gate | S4 |
| §5 #12 routing | S1 |
| §6 #13 runId | S1 |
| §7 FR writer | S5 |

No gaps; every blueprint change maps to a slice with unit/integration/e2e coverage.

---

Status: Draft for collaborative review.
