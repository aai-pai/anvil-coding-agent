# background-information.md

## v0.1.1 Backlog — Issues to Address

The following issues were filed against the `aai-pai/openhands_based_coding_team` repository and must all be resolved in the v0.1.1 release of Anvil.

---

### Issue #9 — Prompt loses to existing workspace artifacts and domain knowledge

**Summary:** A run submitted with a user prompt (e.g. `build a cli tool that converts dollars to cents`) completed all phases but produced Anvil factory artifacts instead of the requested project. The user prompt was effectively overridden by pre-existing workspace artifacts and domain knowledge.

**Suspected root cause:**
- The proposal-phase context overweights existing `docs/` artifacts, `domain-knowledge/`, and surrounding repository structure.
- The `prompt` field is forwarded but at lower priority than existing canonical project artifacts.
- Continuation-workflow assumptions leak into fresh-project runs.

**Acceptance criteria:**
- A fresh-project prompt can override unrelated pre-existing repository context, **or** the runtime explicitly rejects such runs instead of silently building the wrong project.
- Prompt precedence rules are documented and test-covered.
- Regression test: clean prompt in a workspace that already contains unrelated canonical artifacts.

---

### Issue #10 — Generated markdown artifacts duplicate full content across sections

**Summary:** Generated documents (e.g. `proposal.md`, `spec.md`, `architecture.md`, `plan.md`) repeat the same full body content under multiple section headings instead of producing section-specific content.

**Suspected root cause:** `runtime/anvil_runtime/sdk/openhands_adapter.py` in `_document()` writes `## Overview` with the full `content` and then appends the same content again for each entry in `required_sections`.

**Acceptance criteria:**
- Generated markdown documents do not repeat the full body under every section heading.
- Required sections contain section-specific content or an intentional placeholder/structure (not a verbatim copy of the overview).
- Regression tests cover at least one phase with required sections and assert non-duplicated output.

---

### Issue #11 — Align emitted runtime artifacts with canonical workflow (or add a strict canonical mode)

**Summary:** The runtime emits additional docs artifacts beyond the canonical workflow defined in `.github/copilot-instructions.md`, creating a governance mismatch.

**Non-canonical artifacts currently emitted:**
- `docs/qa-test-plan.md`
- `docs/packaging-plan.md`
- `docs/documentation-plan.md`
- `docs/deployment-plan.md`
- `docs/phase-summary-log.md`

**Canonical workflow artifacts:**
- `docs/proposal.md`, `docs/spec.md`, `docs/architecture.md`, `docs/blueprint.md`, `docs/plan.md`, then implementation

**Root cause:** Non-canonical outputs are hardcoded in `runtime/anvil_runtime/core/phase_contracts.py` and reinforced in `runtime/anvil_runtime/artifacts/schemas.py`.

**Acceptance criteria:**
- A single authoritative artifact policy is defined and documented.
- Either runtime contracts are updated to match the canonical workflow, **or** documentation is updated to include the expanded set, **or** a strict mode is added that emits only canonical artifacts.
- Tests cover the selected policy.

---

### Issue #12 — Phase model routing lacks clear specialization defaults

**Summary:** In a real run, every `ModelRouteSelected` event selected the same model (`deepseek/deepseek-chat`) for all phases including planning and coding, suggesting there is no effective phase-aware default routing policy.

**Problem:** Without differentiated defaults, planning and coding phases cannot specialize (e.g. use a reasoning-optimized model for planning, a code-optimized model for implementation) unless the user manually configures environment-variable overrides.

**Acceptance criteria:**
- Default routing behavior is explicitly documented.
- The runtime either implements phase-aware default routing **or** intentionally uses a single default model with that policy clearly surfaced.
- Test coverage exists for routing decisions by phase.

---

### Issue #13 — Model and token telemetry events must always include `runId`

**Summary:** `ModelRouteSelected` and `TokenUsageReported` events were observed with an empty `runId`, while `PhaseStarted` and `PhaseCompleted` events for the same run contained the correct run ID. This breaks per-run cost and routing traceability.

**Evidence:** Observed for run `8173533c7e3246c4a06ffe9aa09255cd` in `logs/events.jsonl`. Referenced in `docs/failure_records/FR-002-artifact-duplication-noncanonical-artifacts-and-model-routing.md`.

**Acceptance criteria:**
- `ModelRouteSelected` events always carry the active, non-empty `runId`.
- `TokenUsageReported` events always carry the active, non-empty `runId`.
- Regression tests verify `runId` propagation for all emitted event types across a representative run.
