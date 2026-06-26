# Anvil Proposal — v0.1.1

## 1. Executive Summary

v0.1.1 is a **targeted correctness and governance release** for Anvil. It does
not introduce new product surface area; it fixes five defects observed in real
v0.1.0 runs that undermine instruction fidelity, artifact quality, governance
clarity, model specialization, and telemetry traceability.

The release is scoped to the backlog filed against
`aai-pai/openhands_based_coding_team` and recorded in
[`domain-knowledge/background-information.md`](../domain-knowledge/background-information.md):
Issues **#9–#13**. Every issue must be resolved, documented, and regression-tested
before v0.1.1 is considered complete. All v0.1.0 architecture, contracts, and
operating modes carry forward unchanged except where a fix explicitly amends them.

## 2. Relationship to v0.1.0

v0.1.0 delivered the end-to-end supervisor-orchestrated coding factory: the
twelve-phase product pipeline, REST runtime, VS Code `@anvil` participant,
policy/hooks/skills/MCP layers, model routing, and checkpoint-resume. v0.1.1
inherits that system in full. This proposal amends only the behaviors named in
§5 and §6; the v0.1.0 proposal remains the canonical statement of overall product
intent.

## 3. Problem Statement

Five defects were observed in real runs:

- **#9 — Prompt loses to existing workspace artifacts.** A fresh-project prompt
  run inside a workspace that already contained unrelated canonical artifacts and
  domain knowledge produced Anvil's own factory artifacts instead of the requested
  project. User intent was silently overridden by pre-existing repository context.
- **#10 — Markdown artifacts duplicate full content across sections.** Generated
  documents repeat the entire body verbatim under every required-section heading
  instead of producing section-specific content.
- **#11 — Emitted artifacts appear to mismatch the canonical workflow.** The
  twelve-phase product pipeline emits auxiliary docs (`qa-test-plan.md`,
  `packaging-plan.md`, `documentation-plan.md`, `deployment-plan.md`,
  `phase-summary-log.md`) that are not present in the six-phase development
  workflow described in `.github/copilot-instructions.md`, creating an apparent
  governance mismatch.
- **#12 — Phase model routing has no effective specialization.** Every
  `ModelRouteSelected` event chose the same model for all phases, contradicting
  the phase+task hybrid routing intent documented in v0.1.0 proposal §10.
- **#13 — Telemetry events drop `runId`.** `ModelRouteSelected` and
  `TokenUsageReported` events were emitted with an empty `runId`, breaking per-run
  cost and routing traceability even though `PhaseStarted`/`PhaseCompleted` for the
  same run carried the correct ID.

## 4. Goals and Success Criteria

### 4.1 Goals

- Restore **prompt fidelity**: a user's request always determines what gets built.
- Restore **artifact quality**: generated docs contain section-specific content.
- Establish a **single authoritative artifact policy** with no ambiguity about
  which workflow produces which documents.
- Deliver **real phase-aware model specialization** matching documented intent.
- Guarantee **complete telemetry traceability**: every event carries `runId`.

### 4.2 Success Criteria

- A fresh-project prompt builds the requested project regardless of unrelated
  pre-existing repository content, because each run executes in an isolated
  per-run workspace (§6.1).
- No generated markdown artifact repeats its overview body under multiple section
  headings; required sections contain section-specific content or intentional
  structure.
- The dev-vs-product artifact split is documented and test-covered; auxiliary
  artifacts are formally blessed rather than treated as drift.
- Routing decisions differ by phase per the documented default policy, with test
  coverage asserting the per-phase model selection.
- `ModelRouteSelected` and `TokenUsageReported` events always carry the active,
  non-empty `runId`, verified across a representative run for all event types.

## 5. Scope and Non-Goals

### In Scope

- Per-run workspace isolation under `runs/` (resolves #9).
- Section-specific document generation in the OpenHands adapter (resolves #10).
- An authoritative artifact policy that documents the dev-vs-product workflow
  split (resolves #11), optionally backed by a strict canonical-only mode.
- Phase-aware default model routing (resolves #12).
- `runId` propagation to all emitted event types (resolves #13).
- Regression and routing tests for each of the above.

### Non-Goals

- No new phases, operating modes, or product surface.
- No changes to the twelve-phase contract set beyond what the fixes require.
- No model fine-tuning or new provider integrations.
- A user-facing strict canonical-only artifact mode is an **optional stretch**
  for v0.1.1 (§6.3); the governance fix does not depend on it.

## 6. Proposed Resolutions

### 6.1 Issue #9 — Per-run workspace isolation

**Root cause:** the proposal phase reads ambient repository context (existing
`docs/`, `domain-knowledge/`, surrounding structure) at higher effective priority
than the run's own prompt, so unrelated artifacts override user intent.

**Resolution — structural isolation.** Rather than tuning context weights inside a
shared workspace, each request runs in its own self-contained folder under `runs/`,
exactly as [`runs/README.md`](../../../runs/README.md) already prescribes
(`runs/<date>-<slug>/` with its own `domain-knowledge/`, `docs/`, `src/`, `tests/`,
`logs/`, `.anvil/`). The runtime:

1. Materializes (or reuses) an isolated run workspace per run.
2. Writes the run's prompt into that workspace's
   `domain-knowledge/background-information.md`.
3. Scopes all phase input/output to the run workspace, so unrelated repository
   artifacts are structurally invisible to the run.

This eliminates the conflict at the source: there is no shared workspace from
which foreign artifacts can leak. Prompt-precedence rules are documented and a
regression test covers a clean prompt in a workspace that already contains
unrelated canonical artifacts.

### 6.2 Issue #10 — Section-specific document generation

**Root cause:** `runtime/anvil_runtime/sdk/openhands_adapter.py` `_document()`
writes `## Overview` with the full content, then appends the same content again
under every entry in `required_sections`.

**Resolution.** `_document()` is corrected so the overview holds the body once and
each required section receives section-specific content or an intentional
placeholder/structure — never a verbatim copy of the overview. Regression tests
cover at least one phase with required sections and assert non-duplicated output.

### 6.3 Issue #11 — Authoritative artifact policy (dev vs product)

**Root cause:** an apparent mismatch arises from comparing two distinct workflows.
`.github/copilot-instructions.md` governs the **six-phase development workflow**
used to build Anvil itself; the runtime executes the **twelve-phase product
pipeline** used when Anvil builds a user's project. They were never meant to emit
the same artifact set.

**Resolution — document the split as the single authoritative policy.**

- **Anvil development (6 phases) → 5 docs:** `proposal.md`, `spec.md`,
  `architecture.md`, `blueprint.md`, `plan.md`. The Implementation phase produces
  `src/`, `tests/`, and the implementation log, not a `docs/` artifact.
- **Anvil usage (12 phases) → 10 docs:** the 5 canonical docs plus 5 auxiliary
  docs, one per artifact-producing phase — `qa-test-plan.md`, `packaging-plan.md`,
  `documentation-plan.md`, `deployment-plan.md`, `phase-summary-log.md`
  (factory-init scaffolds directories and implementation writes `src/`; neither
  emits a `docs/` artifact).

[`runtime/anvil_runtime/core/phase_contracts.py`](../../../runtime/anvil_runtime/core/phase_contracts.py)
is correct as written and becomes the single source of truth the policy points at;
the auxiliary artifacts are formally blessed deliverables, not drift. An optional
**strict canonical-only mode** that emits just the 5 canonical docs may be added
as a stretch item for users who want the lean chain. Tests cover the selected
policy.

### 6.4 Issue #12 — Phase-aware default model routing

**Root cause:** routing collapses to one model for all phases, contradicting the
phase+task hybrid intent in v0.1.0 proposal §10.

**Resolution.** Implement phase-aware default routing so the documented intent is
realized: reasoning-optimized defaults for the design/planning phases (proposal,
spec, architecture, blueprint, dev-plan) and a code-optimized default for the
implementation phase, with user overrides preserved via the existing configuration
precedence hierarchy. The default routing policy is documented, and tests assert
the model selected per phase.

### 6.5 Issue #13 — `runId` on all telemetry events

**Root cause:** `ModelRouteSelected` and `TokenUsageReported` are emitted from a
path that lacks the active run context, yielding an empty `runId`.

**Resolution.** Ensure the active, non-empty `runId` is threaded into every
emitted event type. Regression tests verify `runId` propagation across a
representative run for all event types, not only phase lifecycle events.

## 7. Risks and Mitigations

- **Run-isolation regressions** (existing callers assume a shared workspace):
  mitigate with end-to-end tests covering fresh-prompt runs and the existing
  resume/checkpoint paths.
- **Routing defaults increasing cost or latency** if a reasoning model is pricier:
  mitigate by keeping defaults configurable and documenting the cost profile.
- **Policy churn** if the artifact split is misread again: mitigate by anchoring
  the policy to `phase_contracts.py` as the single source of truth and testing it.

## 8. Acceptance Criteria for Proposal Completion

This proposal is approved when it is accepted as the canonical intent for v0.1.1
and supports downstream derivation of:

- `docs/spec.md` with testable requirements for issues #9–#13.
- `docs/architecture.md` updates reflecting per-run isolation, routing, and the
  artifact policy.
- `docs/blueprint.md` with implementation-ready module changes.
- `docs/plan.md` with phased slices and a per-issue test strategy.

## 9. Open Questions for Alignment

- Confirm the concrete default models for the reasoning vs code routing tiers
  (#12) — to be finalized in the spec/architecture phase.
- Confirm whether the optional strict canonical-only artifact mode (§6.3) is in
  scope for v0.1.1 or deferred.

---

Status: Draft for collaborative review.
