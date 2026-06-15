# FR-002: Artifact Duplication, Non-Canonical Artifact Emission, and Single-Model Routing

**Date:** 2026-06-15  
**Run ID:** `8173533c7e3246c4a06ffe9aa09255cd`  
**Execution Mode:** `real` (OpenRouter)  
**Status:** Partially closed

---

## Summary

The dollars-to-cents run produced working code, but three quality/governance issues were observed:

1. Generated Markdown artifacts repeat the same content across multiple sections.
2. Runtime emits additional non-canonical docs artifacts (`qa-test-plan.md`, `packaging-plan.md`, `documentation-plan.md`, `deployment-plan.md`, `phase-summary-log.md`) that are not part of the repository's canonical phase artifact list.

This record documents evidence from both generated artifacts and runtime code.

---

## Observed Evidence

### A) Repeated text in artifacts

Observed in generated docs for this run:
- `docs/proposal.md`: the same full proposal content appears under `## Overview`, then repeated under `## Problem Statement`, then repeated again under `## Scope`.
- `docs/spec.md`: the same full specification content appears under `## Overview`, then repeated under `## Requirements`.
- Similar pattern appears in `docs/architecture.md` and `docs/plan.md`.

This is deterministic and reproducible.

### B) Non-canonical artifacts emitted

Files created in `docs/` include:
- `docs/qa-test-plan.md`
- `docs/packaging-plan.md`
- `docs/documentation-plan.md`
- `docs/deployment-plan.md`
- `docs/phase-summary-log.md`

These are produced in addition to canonical docs (`proposal/spec/architecture/blueprint/plan`).

### C) All model routing to DeepSeek chat

From `logs/events.jsonl` for run `8173533c7e3246c4a06ffe9aa09255cd`:
- Every `ModelRouteSelected` event shows model `deepseek/deepseek-chat`.
- This includes planning phases and coding phases (`implementation`, `qa`).
- `TokenUsageReported` events were emitted for all 12 phases (aggregate observed total tokens across phases: 16057).

---

## Code-Level Root Cause Analysis

### Issue 1: Why artifact text is repeated

Root cause is in document assembly logic:
- File: `runtime/anvil_runtime/sdk/openhands_adapter.py`
- `_document()` builds body as:
  - `## Overview` with full `content`
  - then loops over required sections and appends each section with the same full `content` again

Relevant lines:
- `body = [ ..., "## Overview", content, ... ]`
- `for section in self._required_sections(step.phase): ... body.append(content)`

This guarantees repeated full content whenever `required_sections` is non-empty.

### Issue 2: Why non-canonical artifacts are created

Non-canonical outputs are explicitly hardcoded in phase contracts and schemas.

1) Phase contracts define outputs:
- File: `runtime/anvil_runtime/core/phase_contracts.py`
- `qa` phase allowed output includes `docs/qa-test-plan.md`
- `packaging` phase output is `docs/packaging-plan.md`
- `documentation` phase output is `docs/documentation-plan.md`
- `deployment` phase output is `docs/deployment-plan.md`
- `cleanup` phase output is `docs/phase-summary-log.md`

2) Artifact schemas reinforce these outputs:
- File: `runtime/anvil_runtime/artifacts/schemas.py`
- Schemas exist for `qa`, `packaging`, `documentation`, `deployment`, `cleanup` with those same paths.

This is therefore expected behavior in current runtime design, not model improvisation.

3) Canonical workflow mismatch:
- File: `.github/copilot-instructions.md`
- Canonical listed artifacts/phases center on:
  - `docs/proposal.md`
  - `docs/spec.md`
  - `docs/architecture.md`
  - `docs/blueprint.md`
  - `docs/plan.md`
  - then implementation

The runtime's 12-phase contract is broader than the instruction file's canonical list.

## Additional Observation

`ModelRouteSelected` and `TokenUsageReported` events in the log tail show `runId:""` (empty) while `PhaseStarted/PhaseCompleted` include the real run ID. This may reduce traceability for model/token analytics and should be validated as a separate instrumentation bug.

---

## Impact

- Lower artifact quality due to duplicated narrative blocks.
- Confusion about expected outputs vs canonical workflow docs.
- Reduced control over model specialization (planning vs coding) unless env vars are set explicitly.
- Potential observability gap if model/token events are not associated with run IDs.

---

## Recommendations

1. **Fix duplication in `_document()`**
   - Keep `## Overview` as summary.
   - For required sections, either:
     - ask LLM for sectioned output and map sections, or
     - insert placeholders/checklist headings instead of re-inserting full body.

2. **Align runtime artifact contract with canonical workflow**
   - Option A: Update `.github/copilot-instructions.md` to explicitly include QA/packaging/documentation/deployment/cleanup artifacts.
   - Option B: Add a strict mode where only canonical five docs are emitted.

3. **Fix event run ID propagation**
   - Ensure `ModelRouteSelected` and `TokenUsageReported` carry the active run ID.

---

## Verification Plan

- Re-run the same prompt after fixes and confirm:
  - No repeated full-body blocks in `proposal/spec/architecture/blueprint/plan`.
  - Artifact set matches intended policy (strict canonical or expanded by design).
  - `ModelRouteSelected` shows planning phases on planning model and coding phases on coding model.
  - All event types include the same non-empty `runId`.
