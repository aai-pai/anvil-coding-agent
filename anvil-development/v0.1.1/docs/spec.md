# Anvil Specification — v0.1.1

Testable requirements for the v0.1.1 fix release. This is a **delta** against the
[v0.1.0 spec](../../v0.1.0/docs/spec.md), which remains the baseline; only the
requirements below change. Derived from [docs/proposal.md](proposal.md) and grounded
in failure records FR-001 / FR-002.

**Stack (unchanged from proposal):** OpenRouter (direct API calls) + thin localhost
REST runtime + `@anvil` VS Code extension. No OpenHands yet. All v0.1.1 changes are
runtime-only.

---

## 1. Per-Run Workspace Isolation (#9)

Supersedes the v0.1.0 behavior where a run wrote into the server's working directory
(FR-001: a run inside the Anvil repo built Anvil instead of the requested project).

- **FR-RUN-001**: Every run must execute in an isolated workspace at
  `runs/<date>-<slug>/`, created if absent. `<date>` is the run-start date
  (`YYYY-MM-DD`); `<slug>` is a kebab-case fragment of the task. On collision, append
  a short uniqueness suffix.
- **FR-RUN-002**: The run's prompt (the `task` field of `POST /v1/runs`) must be
  written to `<run-workspace>/domain-knowledge/background-information.md` as the sole
  project input, before the proposal phase runs.
- **FR-RUN-003**: All phase input and output must be scoped to the run workspace. The
  runtime must not read or write repository artifacts outside it; pre-existing files
  elsewhere must be invisible to the run.
- **FR-RUN-004**: A run with no `task` (the `start` flow) reads an existing
  `background-information.md` already present in the run workspace and must not
  overwrite it.

**Test (regression for FR-001):** a fresh `task` run, executed while the repo root
contains unrelated canonical artifacts, produces the requested project and reads only
its own run workspace.

---

## 2. Section-Specific Document Generation (#10)

Supersedes the v0.1.0 document writer, which wrote the full body under `## Overview`
then repeated it under every required section (FR-002 §A; ~3× tokens).

- **FR-DOC-001**: The document writer must emit the body content exactly once.
- **FR-DOC-002**: Each required section must contain section-specific content or an
  explicit placeholder; it must never be a verbatim copy of the overview body.

**Test:** generate a document for a phase with required sections and assert no
section repeats the overview body.

---

## 3. Complexity-Gated Phase Selection (#11)

New mechanism. Replaces unconditional emission of all auxiliary docs (FR-002 §B).

- **FR-CX-001**: The proposal phase must emit a complexity tier
  ∈ {`simple`, `standard`, `complex`} as part of its completion metadata. No extra
  LLM call is made; the tier is produced within the proposal phase.
- **FR-CX-002**: The supervisor must select the run's phase set from the tier:
  - `simple` → core only: proposal, factory-init, specification, architecture,
    blueprint, dev-plan, implementation (5 canonical docs + `src/`).
  - `standard` → core + qa.
  - `complex` → all 12 phases.
- **FR-CX-003**: A phase not in the selected set must not execute and must emit no
  artifact.
- **FR-CX-004**: The tier and the resulting phase set must be recorded in the event
  stream (a `ComplexityAssessed` event) for auditability.
- **FR-CX-005**: Secure-mode mandatory checkpoints apply only to phases in the
  selected set (e.g. the Pre-Deployment-Plan gate applies only when deployment runs).
- **FR-CX-006**: The tier may be overridden through the configuration precedence
  hierarchy (v0.1.0 §2.7).

The three tier sets are dependency-closed by construction (qa depends only on
plan + `src/`, both in core), so no phase ever runs with a missing prerequisite.

**Test:** a trivial task → exactly the 5 canonical docs + `src/` (no
packaging/deployment/etc.); a complex task → the full set; the tier is present in the
event stream for both.

---

## 4. Phase-Aware Model Routing (#12)

The router already implements phase-aware defaults; v0.1.0 broke them by (a) wiring
every subtask category to one model in `app.py` and (b) using placeholder slugs.
Amends v0.1.0 FR-ML-003.

- **FR-RT-001**: Default model per tier (real OpenRouter slugs):
  - Planning/design phases (proposal, specification, architecture, blueprint,
    dev-plan) → **`google/gemma-4-31b-it`**.
  - Coding phases (implementation, qa) → **`deepseek/deepseek-v4-flash`**
    (cheapest coding-capable option; `deepseek/deepseek-v4-pro` is the documented
    override for harder tasks).
- **FR-RT-002**: Runtime wiring must not collapse all subtask categories to a single
  model. With no user override, the router's per-tier defaults (FR-RT-001) must be the
  effective selection.
- **FR-RT-003**: Defaults remain overridable via the configuration precedence
  hierarchy (carries forward v0.1.0 FR-ML-005), including the `ANVIL_PLANNING_MODEL`,
  `ANVIL_CODING_MODEL`, and `ANVIL_MODEL` environment variables.

**Test:** with no overrides, a routing decision for a planning phase selects
`google/gemma-4-31b-it` and for implementation/qa selects `deepseek/deepseek-v4-flash`.

---

## 5. `runId` on All Telemetry Events (#13)

`ModelRouteSelected` and `TokenUsageReported` were emitted with `runId:""` because the
router/usage-tracker were constructed without the per-run id (FR-002).

- **FR-EVT-001**: Every emitted event must carry the active, non-empty `runId`,
  including `ModelRouteSelected` and `TokenUsageReported` — not only phase-lifecycle
  events.
- **FR-EVT-002**: The active `runId` must be threaded into the model-routing and
  usage-tracking emission paths for each run (it is per-run, not known at app
  construction).

**Test:** over a representative run, assert every emitted event type carries a
non-empty `runId` equal to the run's id.

---

## 6. Gap Analysis (Proposal → Spec)

| Proposal item | Spec coverage |
|---|---|
| #9 per-run isolation (§6.1, §8.11) | §1 FR-RUN-001…004 |
| #10 section-specific docs (§9.2) | §2 FR-DOC-001…002 |
| #11 complexity gating (§8.12, §9.1) | §3 FR-CX-001…006 |
| #12 phase-aware routing — Gemma 4 / DeepSeek (§10) | §4 FR-RT-001…003 |
| #13 runId on all events (§8.8) | §5 FR-EVT-001…002 |
| Stack: no OpenHands | Header note |

No gaps; the proposal's deferred items (model slugs, complexity tiers) are now pinned
in §4 and §3.

---

## 7. Acceptance Criteria

Approved when each of #9–#13 has testable requirements (above) with a stated
regression test, the model slugs and complexity tiers are pinned, and the gap
analysis shows full coverage. No open questions remain.

---

Status: Draft for collaborative review.
