# Anvil Architecture — v0.1.1

Component-level design for the v0.1.1 fix release. This is a **delta** against the
[v0.1.0 architecture](../../v0.1.0/docs/architecture.md), which remains the baseline;
only the components and interactions below change. Derived from
[docs/spec.md](spec.md). Component numbers reference the v0.1.0 architecture.

**Stack note.** v0.1.1 performs all LLM work via **direct OpenRouter API calls**; the
**OpenHands SDK Adapter (§3.7.2) is inactive/deferred** this release. Phase agents
call the OpenRouter LLM Provider (§3.7.1) and the Document Writer (new, §A.2) directly.
All changes are runtime-only.

---

## A. Component Changes

### A.1 Per-Run Workspace Resolution (#9 → Runtime API §3.1.2 + Dev Manager §3.2.1)

`workspace_root` already flows into the Development Manager, Event Bus, Checkpoint
Store, and Runtime Projection. The only change is **where it points**:

- The Runtime API `start_run` path resolves a per-run workspace
  `runs/<date>-<slug>/` (FR-RUN-001) instead of the server CWD or the open folder,
  creates it, and uses it as `workspace_root` for that run's manager.
- The prompt is written to `<run-workspace>/domain-knowledge/background-information.md`
  before dispatch (FR-RUN-002); a `start` run with no task reads the existing file
  (FR-RUN-004).

Because every downstream component is already rooted at `workspace_root`, no other
component changes — scoping all I/O to the run workspace (FR-RUN-003) falls out for
free. This is the structural fix for FR-001.

### A.2 Document Writer (#10 → replaces the v0.1.0 generation path)

The v0.1.0 document assembly (`openhands_adapter._document`) duplicated the body under
every section. v0.1.1 introduces a small **Document Writer** in the generation path
that phase agents use to format LLM output into the artifact:

- Emits the body content once (FR-DOC-001).
- Fills each required section with section-specific content or an explicit
  placeholder — never a copy of the overview (FR-DOC-002).

It depends only on the OpenRouter LLM Provider (§3.7.1) for content and is exercised
by the Artifact Validator (§3.4.3) against the section schemas.

### A.3 Complexity Gate (#11 → new, within Dev Manager §3.2.1)

A minimal per-run phase filter, not a new subsystem:

- The **proposal phase agent** emits a complexity tier
  ∈ {simple, standard, complex} in its completion metadata (FR-CX-001) — no extra
  LLM call.
- The Development Manager computes the **active phase set** from the tier
  (FR-CX-002) after the proposal phase records success, stores it on the run context,
  and constrains phase selection to it. Phases outside the set are never dispatched
  (FR-CX-003).
- The phase DAG (§4.2) remains the dependency source of truth; the active set is an
  additional filter applied in the orchestration loop (`next_phase` / `ready_phases`).
  The three tier sets are dependency-closed, so no phase runs with a missing
  prerequisite.
- A `ComplexityAssessed` event records the tier and resulting set (FR-CX-004).
  Secure-mode gates (§6.3) apply only to phases in the active set (FR-CX-005); the
  tier is config-overridable (FR-CX-006).

### A.4 OpenRouter LLM Provider Routing (#12 → §3.7.1)

The router already implements phase-aware routing; v0.1.1 fixes the wiring and slugs:

- Default per-tier slugs become real OpenRouter IDs (FR-RT-001):
  planning/design → `google/gemma-4-31b-it`; coding (implementation, qa) →
  `deepseek/deepseek-v4-flash`.
- The composition root (`app.build_manager`) must stop passing a flat subtask→model
  map that collapses every category to one model; with no override, the router's
  per-tier defaults are authoritative (FR-RT-002). Overrides via config precedence are
  unchanged (FR-RT-003).

### A.5 Run-Scoped Telemetry Emitters (#13 → §3.7.1 + Event Bus §3.5.1)

`ModelRouteSelected` and `TokenUsageReported` were emitted with `runId:""` because the
router/usage-tracker were built once at app start, before any run existed. v0.1.1
threads the active `runId` (which the Development Manager already holds) into the
routing and usage-tracking emission paths per run (FR-EVT-002), so every event type
carries a non-empty `runId` (FR-EVT-001).

---

## B. Interaction Change — Run Start with Isolation, Gating, and Routing

```mermaid
sequenceDiagram
    participant API as Runtime API
    participant DM as Dev Manager
    participant PA as Proposal Agent
    participant ORP as OpenRouter Provider
    participant EB as Event Bus

    API->>API: resolve runs/<date>-<slug>/ ; write background-information.md (#9)
    API->>DM: start_run(workspace=run-folder, run_id)
    DM->>ORP: bind active run_id (#13)
    DM->>PA: dispatch proposal
    PA->>ORP: complete(proposal) → route google/gemma-4-31b-it (#12)
    PA-->>DM: PhaseComplete{..., complexityTier}
    DM->>EB: emit ComplexityAssessed{tier, active_set} (#11)
    Note over DM: constrain phase selection to active_set; gated-out phases never dispatched
    DM->>DM: continue with active phases only
```

---

## C. Gap Analysis (Spec → Component)

| Spec | Component change |
|---|---|
| §1 FR-RUN-001…004 (#9) | A.1 Per-Run Workspace Resolution |
| §2 FR-DOC-001…002 (#10) | A.2 Document Writer |
| §3 FR-CX-001…006 (#11) | A.3 Complexity Gate |
| §4 FR-RT-001…003 (#12) | A.4 OpenRouter Provider Routing |
| §5 FR-EVT-001…002 (#13) | A.5 Run-Scoped Telemetry Emitters |
| Stack: no OpenHands | §3.7.2 inactive; A.2 + §3.7.1 are the generation path |

No gaps. All other v0.1.0 components are unchanged.

---

Status: Draft for collaborative review.
