# Anvil Blueprint — v0.1.2

Code-level design (Markdown only) for the v0.1.2 release. **Delta** against the
[v0.1.1 blueprint](../../v0.1.1/docs/blueprint.md); derived from
[spec.md](spec.md) and [architecture.md](architecture.md). Section numbers below
are new; unchanged modules are not restated.

## Module Structure

```
runtime/anvil_runtime/
    instructions/__init__.py          (new)
    instructions/resolver.py          (new)   #14
    agents/phases/intake_agent.py     (new)   #15
    core/phase_contracts.py           (mod)   #15
    core/development_manager.py       (mod)   #15 #16
    sdk/openhands_adapter.py          (mod)   #14 #15 #16 #18
    sdk/session_bridge.py             (mod)   #15
    artifacts/metadata.py             (mod)   #16
    artifacts/schemas.py              (mod)   #16
    api/models.py                     (mod)   #15 #17
    api/routes_runs.py                (mod)   #14 #15 #17
    app.py                            (mod)   #14 #18
    config/schema.py                  (mod)   #18
extension/src/
    chat/commandRouter.ts             (mod)   #15 #17
    chat/participant.ts               (mod)   #15 #17
    chat/responseRenderer.ts          (mod)   #15
    runtime/runtimeClient.ts          (mod)   #15 #17
```

## 1. `instructions/resolver.py` (#14)

```python
INSTRUCTIONS_FILENAME = "anvil-instructions.md"
RUN_LEVEL_REL = "domain-knowledge/anvil-instructions.md"
MAX_INSTRUCTIONS_CHARS = 16_000                      # FR-INS-003

class ResolvedInstructions(BaseModel):
    text: str | None; path: str | None; truncated: bool = False

def resolve_instructions(run_root: str, base_root: str | None = None) -> ResolvedInstructions
```

Precedence per FR-INS-001. Pure; no events (the caller emits
`InstructionsResolved`).

## 2. Phase contracts (#15)

- `PHASE_IDS = ("intake", "proposal", ...)` — 13 entries; linear DAG derivation
  is untouched (intake first ⇒ proposal depends on intake).
- `PHASE_CONTRACTS["intake"] = PhaseContract(phase_id="intake",
  agent_name="intake_agent",
  input_files=["domain-knowledge/background-information.md"],
  allowed_outputs=["domain-knowledge/background-information.md"])`
- `PhaseCompleteEvent += questions: list[str] (default []),
  assumptions: list[str] (default [])`.
- `PhaseStep += context: dict[str, object] (default {})` (carries `run_id`,
  `clarification_mode`).

`agents/phases/intake_agent.py`: `IntakeAgent(BasePhaseAgent)` with
`phase_id = "intake"`, stub `run()` → `stub_phase_result` (no questions,
FR-INT-004). Registered in `factory._AGENT_CLASSES`.

## 3. Development manager (#15, #16)

```python
RunStatus += "awaiting_clarification"
CLARIFICATION_MAX_ROUNDS = 1                          # FR-INT-009

class _RunContext:  # additions
    clarification_round: int = 0
    pending_questions: list[str] = []

class RunProgress:  # addition
    pending_questions: list[str] = []

class ClarificationDecision(BaseModel):
    run_id: str; round: int; appended: bool
```

- `step()`: after a successful dispatch of `intake`, if
  `event.questions and ctx.mode != "yolo" and ctx.clarification_round == 0` →
  `_pause_for_clarification(ctx, questions)` (status, `pending_questions`,
  `ClarificationRequired` event). Mirrors `_pause_for_gate`.
- `_clarification_mode(ctx) -> "questions" | "assumptions"`: assumptions when
  `ctx.mode == "yolo"` or `ctx.clarification_round >= CLARIFICATION_MAX_ROUNDS`.
  Passed via `phase_context` in `dispatch_phase` for the intake phase only.
- `submit_clarification(run_id, answers: list[str]) -> ClarificationDecision`:
  append `## Clarifications` Q/A block to
  `<root>/domain-knowledge/background-information.md` (questions from
  `ctx.pending_questions`, zipped with answers), invalidate intake checkpoint +
  remove from `ctx.completed`, `clarification_round += 1`, clear
  `pending_questions`, status = running, emit `ClarificationReceived`. Raises
  `ValueError` if the run is not `awaiting_clarification`.
- `_record_success`: on intake, emit `IntakeAssessed{complete, questions,
  assumptions, round}` (FR-INT-011).
- On the `completed` transition in `step()`: `_write_run_index()` →
  `docs/index.md` from a deterministic scan of `docs/*.md` frontmatter
  (FR-OKF-003); failures swallowed like failure-record writes.

## 4. LLM backend (`sdk/openhands_adapter.py`) (#14, #15, #16, #18)

```python
class LLMBackend:
    def __init__(self, provider, workspace_root=".", clock=None,
                 instructions: str | None = None,          # FR-INS-002
                 input_char_limit: int = 20_000,            # FR-CTX-001
                 event_bus: "EventBus | None" = None)       # FR-CTX-002
    INTAKE_PHASE = "intake"
```

- `run()`: three-way branch — intake / code / doc.
- `_read_inputs(step)`: per-file cap `self._input_char_limit`; on an actual cut
  emit `InputTruncated` (warning) with `{file, size, limit}`, `runId` from
  `step.context` (FR-CTX-002).
- `_instructions_block()`: `"Standing instructions (anvil-instructions.md):\n
  <text>"`, prepended in `_doc_prompt`, `_code_prompt`, `_intake_prompt`; never
  truncated (FR-INS-003).
- `_run_intake(session_id, step, model)`: prompt asks for the FR-INT-005 marker
  protocol; mode from `step.context["clarification_mode"]`. Parse with
  `_parse_intake(content) -> (complete, questions[:5], assumptions)`. In
  assumption mode with assumptions present: append
  `\n## Assumptions\n- <a>...\n` to the domain-knowledge file (its allowed
  output) and report it as the artifact. Questions mode writes nothing.
  `StepResult += questions, assumptions`.
- `_doc_prompt`: + one cross-link encouragement line (FR-OKF-004).
- `_document`: header = OKF fields (from `artifacts.schemas.okf_type_for(phase)`
  table + first-content-line description) merged over the existing lineage
  fields (FR-OKF-001).

## 5. Session bridge (#15)

`execute_phase`: build `PhaseStep(context=payload.phase_context)`; intake routes
subtask `"analysis"`; copy `result.questions/assumptions` onto the
`PhaseCompleteEvent`.

## 6. Artifacts (#16)

- `metadata.py`: `REQUIRED_METADATA_FIELDS = ("artifactId", "phase",
  "generatedAt", "type", "title")` (FR-OKF-002); `ArtifactMetadata += type,
  title, description, tags, timestamp` (optional model fields).
- `schemas.py`: `OKF_TYPES: dict[str, str]` (proposal→`Proposal`, …,
  cleanup→`Phase Summary Log`) + `okf_type_for(phase_id) -> str` (fallback:
  title-cased phase id).

## 7. API (#15, #17)

- `RunStartRequest += source_path: str | None`.
- `RunStateResponse/RunProgress += pending_questions: list[str]`.
- `ClarifyRequest(BaseModel): answers: list[str]` (non-empty).
- `routes_runs.start_run`: `task and source_path` → 400 (FR-SRC-004);
  `source_path` branch: read file (400 on error, FR-SRC-003), slug from first
  `# ` heading else stem (FR-SRC-002), resolve isolated workspace, write copy,
  copy sibling `anvil-instructions.md` if present (FR-INS-005). Both branches
  then share the existing per-run manager construction. After workspace
  resolution: `resolve_instructions(run_root, base)`; pass text to
  `build_manager`; after `start_run` emit `InstructionsResolved{path}`
  (FR-INS-004).
- `POST /v1/runs/{run_id}/clarify` → `submit_clarification` + `run_until_pause`;
  404 unknown run, 409 if not awaiting clarification.

## 8. App wiring (#14, #18)

`build_manager(workspace_root, execution_mode, config, secret_adapter,
instructions: str | None = None)`; `_build_real_manager` passes
`instructions`, `input_char_limit` (config/env), and `bus` into `LLMBackend`.
`EffectiveConfig += inputCharLimit: int = 20_000`.

## 9. Extension (#15, #17)

- `commandRouter.ts`: `build` with empty rest → `{kind: "build", description: ""}`
  (was: help); new `case "answer"` → `{kind: "answer", text}`.
- `runtimeClient.ts`: `RunStartRequest += source_path?`;
  `RunStateResponse += pending_questions?`; `clarify(runId, {answers})`.
- `participant.ts`: `TERMINAL_STATUSES += "awaiting_clarification"`; `build`
  with empty description → `source_path` from `context.workspace +
  "/domain-knowledge/background-information.md"` (error text when no
  workspace); `answer` → split on `;`, POST clarify, then re-render state.
- `responseRenderer.ts`: render pending questions when state is
  `awaiting_clarification`.

## 10. Event types added

`InstructionsResolved`, `ClarificationRequired`, `ClarificationReceived`,
`IntakeAssessed`, `InputTruncated`. All carry the active `runId` (FR-EVT-001).

## 11. Test plan mapping

| Area | Unit | Integration/E2E |
|---|---|---|
| resolver (#14) | precedence, cap | prompt contains block; event emitted |
| intake (#15) | marker parsing, mode selection, round bound | gated pause→clarify→resume; yolo assumptions; stub pass-through |
| OKF (#16) | header fields, `okf_type_for`, validator | run artifacts conform; index.md written |
| source build (#17) | slug-from-heading | isolated copy; 400s; sibling instructions copied |
| input limit (#18) | limit + event | >2,500-char file read in full |
| extension | commandRouter `answer`/empty-build parsing | runtimeClient clarify |

---

Status: Draft for collaborative review.
