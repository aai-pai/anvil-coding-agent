# Anvil Architecture — v0.1.2

Component-level design for the v0.1.2 feature release. This is a **delta**
against the [v0.1.1 architecture](../../v0.1.1/docs/architecture.md) (baseline:
[v0.1.0](../../v0.1.0/docs/architecture.md)); only the components and
interactions below change. Derived from [docs/spec.md](spec.md).

**Stack note.** Unchanged: all LLM work via direct OpenRouter calls; the
OpenHands SDK Adapter stays inactive. Changes touch the runtime and, minimally,
the extension (`answer` command, file-based `build`).

---

## A. Component Changes

### A.1 Instructions Resolver (#14 → new, `anvil_runtime/instructions/`)

A small pure module `resolve_instructions(run_root, base_root)` returning
`(text | None, path | None)` with the FR-INS-001 precedence (run
`domain-knowledge/anvil-instructions.md` → base root `anvil-instructions.md` →
none), applying the 16k hard cap (FR-INS-003).

- Called on the run-start path (Runtime API §3.1.2), which knows both roots; the
  resolved **text** is threaded into the LLM Backend at per-run manager
  construction (`app.build_manager` gains an `instructions` parameter), and the
  resolved **path** is emitted as `InstructionsResolved` on the run's event bus
  (FR-INS-004).
- The LLM Backend (§3.7.1) injects the text as a delimited `Standing
  instructions:` block into its document, code, and intake prompts (FR-INS-002),
  outside the `_read_inputs` truncation path (FR-INS-003/FR-CTX-003).

### A.2 Intake Phase (#15 → Phase Contracts §4.2 + Dev Manager §3.2.1 + LLM Backend §3.7.1)

`intake` becomes the 13th canonical phase, first in the linear DAG
(`proposal` now depends on `intake`). Three cooperating changes:

1. **Contracts/agents.** New `PhaseContract` (inputs: the domain-knowledge file;
   allowed output: the same file) + `IntakeAgent` stub (deterministic success, no
   questions — FR-INT-004). `PhaseCompleteEvent` gains `questions: list[str]` and
   `assumptions: list[str]`; `PhaseStep`/`PhaseInvocationPayload` context now
   carries `clarification_mode ∈ {questions, assumptions}` so the backend knows
   which protocol to run.
2. **LLM Backend intake path.** A `_run_intake` branch (alongside `_run_doc` /
   `_run_code`): one planning-tier call emitting `INTAKE: complete` /
   `QUESTION:` / `ASSUMPTION:` marker lines (FR-INT-005), with the standing
   instructions in-prompt so derivable questions are not asked (FR-INT-006). In
   assumption mode it appends `## Assumptions` to the domain-knowledge file
   (within the phase's allowed output, FR-INT-010).
3. **Supervisor pause/resume.** The Dev Manager's `step()` gains a
   clarification pause (mirroring `_pause_for_gate`): after a successful intake
   dispatch in an interactive mode with questions present and round 1, status →
   **`awaiting_clarification`**, `pending_questions` set, `ClarificationRequired`
   emitted (FR-INT-007). A new `submit_clarification(run_id, answers)` appends
   `## Clarifications` Q/A to the file (supervisor-owned write, like failure
   records), invalidates the intake checkpoint, bumps the round counter, and
   sets the run running (FR-INT-008/009). Yolo mode selects assumption mode from
   the start and never pauses (FR-INT-010).

New API surface: `POST /v1/runs/{run_id}/clarify`; `RunStateResponse` gains
`pending_questions`. Extension: `answer <text>` command posts to `/clarify`;
`awaiting_clarification` joins the participant's terminal-status set so the
progress loop stops and renders the questions.

Complexity gating (§A.3 of v0.1.1) is untouched: `intake` is in no tier's
excluded set (FR-INT-002); the tier is still assessed by `proposal`, which now
simply runs second.

### A.3 OKF Artifact Headers + Run Index (#16 → Document Writer §A.2 + Artifact Validator §3.4.3 + Dev Manager §3.2.1)

- The Document Writer's `_document` header gains the OKF fields (`type`,
  `title`, `description`, `tags`, `timestamp`) alongside the existing lineage
  fields (FR-OKF-001); a per-phase `type` table lives beside the artifact
  schemas.
- `REQUIRED_METADATA_FIELDS` gains `type` and `title` (FR-OKF-002); the
  validator behavior is otherwise unchanged.
- The Dev Manager writes `docs/index.md` at the run-completed transition in
  `step()` — a deterministic scan of `docs/*.md` frontmatter (FR-OKF-003),
  supervisor-owned like failure records.
- Doc prompts add one line encouraging relative markdown cross-links
  (FR-OKF-004).

### A.4 File-Based Build (#17 → Runtime API §3.1.2 + Extension §3.2)

`start_run` grows a third intake branch: `source_path` (mutually exclusive with
`task`, FR-SRC-004) → read the file (400 on failure, FR-SRC-003), resolve an
isolated `runs/<date>-<slug>/` workspace (slug from first heading, FR-SRC-002),
copy the file in as `background-information.md`, and copy a sibling
`anvil-instructions.md` when present (FR-INS-005). Everything downstream is the
existing `task`-run path. Extension: `build` with no description sends
`source_path = <open folder>/domain-knowledge/background-information.md`.

### A.5 Input Limit + Truncation Events (#18 → LLM Backend §3.7.1)

`LLMBackend` gains `input_char_limit` (config `inputCharLimit` / env
`ANVIL_INPUT_CHAR_LIMIT` / default 20,000 — FR-CTX-001) and an optional event
bus; `_read_inputs` emits `InputTruncated` warnings naming file, size, and limit
when it actually cuts (FR-CTX-002). Run id for the event comes from the step
context (already threaded per FR-EVT-002).

---

## B. Interaction Change — Run Start with Intake Clarification

```mermaid
sequenceDiagram
    participant EXT as @anvil Extension
    participant API as Runtime API
    participant DM as Dev Manager
    participant IA as Intake (LLM Backend)
    participant EB as Event Bus

    EXT->>API: POST /v1/runs {source_path | task}
    API->>API: resolve runs/<date>-<slug>/ ; copy/write background-information.md (#17)
    API->>API: resolve anvil-instructions.md (#14) -> InstructionsResolved
    API->>DM: start_run + run_until_pause
    DM->>IA: dispatch intake (mode: questions | assumptions)
    IA-->>DM: PhaseComplete{questions[] | assumptions[]}
    alt questions, interactive, round 1
        DM->>EB: ClarificationRequired{questions}
        DM->>DM: status = awaiting_clarification
        EXT->>API: POST /v1/runs/{id}/clarify {answers}
        API->>DM: submit_clarification -> append ## Clarifications, invalidate intake, round=2
        DM->>IA: re-dispatch intake (mode: assumptions)
        IA-->>DM: PhaseComplete{assumptions[]}
    else complete or yolo
        Note over DM: assumptions (if any) appended to background-information.md
    end
    DM->>DM: proceed: proposal -> ... -> completion
    DM->>DM: on RunCompleted: write docs/index.md (#16)
```

---

## C. Component Inventory Delta

| Component | Change |
|---|---|
| `instructions/` (new) | resolver, FR-INS-001..003 |
| `core/phase_contracts.py` | +`intake` phase, +`questions`/`assumptions` on completion event |
| `core/phase_dag.py` | unchanged code; linear default now starts at `intake` |
| `core/development_manager.py` | clarification pause/resume, round counter, `docs/index.md` writer |
| `agents/phases/intake_agent.py` (new) | stub agent |
| `sdk/openhands_adapter.py` | `_run_intake`, instructions block, configurable input limit, OKF header |
| `sdk/session_bridge.py` | thread `clarification_mode`, `questions`/`assumptions` through |
| `artifacts/metadata.py` / `schemas.py` | OKF required fields; per-phase `type` table |
| `api/models.py` / `routes_runs.py` | `source_path`, `/clarify`, `pending_questions` |
| `app.py` | `build_manager(..., instructions)` wiring |
| `config/schema.py` | `inputCharLimit` |
| extension `commandRouter.ts` / `participant.ts` / `runtimeClient.ts` | `answer` command, no-arg `build`, `awaiting_clarification` terminal status |

All other v0.1.1 components are unchanged.

---

Status: Draft for collaborative review.
