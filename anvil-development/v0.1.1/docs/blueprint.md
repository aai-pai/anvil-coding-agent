# Anvil Blueprint — v0.1.1

Implementation-ready code changes for the v0.1.1 fix release (Markdown only; no
source edits yet). **Delta** against the [v0.1.0 blueprint](../../v0.1.0/docs/blueprint.md);
derived from [docs/architecture.md](architecture.md) and [docs/spec.md](spec.md).
Every change is runtime-only and intentionally minimal (Simplicity First).

---

## 1. Data Contract Additions

Two optional fields carry the complexity tier up from the proposal phase. Both
default to `None`, so stub-mode and all other phases are unchanged.

- `sdk/openhands_adapter.py` → `StepResult`: add `complexity_tier: str | None = None`.
- `core/phase_contracts.py` → `PhaseCompleteEvent`: add `complexity_tier: str | None = None`.

---

## 2. #9 — Per-Run Workspace Isolation

**`api/routes_runs.py` → `start_run`.** Resolve an isolated per-run workspace instead
of writing into the server CWD / open folder.

- New helper (small, e.g. `api/run_workspace.py` or inline):
  ```
  def resolve_run_workspace(base: str, task: str | None, now: datetime) -> str:
      # returns f"{base}/runs/{now:%Y-%m-%d}-{slug(task)}", created, unique on collision
  def slug(task: str | None) -> str:
      # kebab-case first ~5 words of task; fallback "run"; truncate to ~40 chars
  ```
- In `start_run`: compute `workspace_root = resolve_run_workspace(base, request.task, now)`
  where `base = request.workspace or state.workspace_root`. Build the run's manager
  rooted there via `build_manager(...)` and register the handle (FR-RUN-001).
- The existing prompt write (lines 78–83) is unchanged in logic but now lands in the
  isolated workspace's `domain-knowledge/background-information.md` (FR-RUN-002). A run
  with no `task` does not write and reads the existing file (FR-RUN-004).
- FR-RUN-003 needs no further change: `DevelopmentManager`, `EventBus`,
  `CheckpointStore`, and `LLMBackend` are already rooted at `workspace_root`.

---

## 3. #10 — Section-Specific Document Generation

**`sdk/openhands_adapter.py` → `LLMBackend._document`** (lines 314–329). The
`_doc_prompt` already instructs the model to include the required section headings, so
the generated `content` already contains them. Stop re-appending the full body.

Replace the section loop:
```
# before: body = [title, "", "## Overview", content, ""]; for s in sections: append(s); append(content)
# after:
body = [f"# {step.phase.replace('-', ' ').title()}", "", content.strip(), ""]
for section in self._required_sections(step.phase):
    if not _has_heading(content, section):          # only add what the model omitted
        body.append(f"## {section}")
        body.append(f"_See above._")                # explicit placeholder, never a copy
        body.append("")
return front + "\n".join(body) + "\n"
```
- Add `_has_heading(content, section) -> bool` (case-insensitive match of `## <section>`).
- Result: body written once (FR-DOC-001); required sections present, section-specific
  or an explicit placeholder, never a verbatim copy (FR-DOC-002). Realizes
  architecture A.2 by fixing the existing document writer in place rather than adding a
  new module.

---

## 4. #11 — Complexity-Gated Phase Selection

### 4.1 Proposal phase emits the tier (no extra LLM call)

**`sdk/openhands_adapter.py` → `LLMBackend`.**
- `_doc_prompt`: when `step.phase == "proposal"`, append:
  `"On the final line output exactly: COMPLEXITY: <simple|standard|complex>."`
- `_run_doc`: after completion, if proposal, parse the tier from `response.content`
  (`_extract_tier(content) -> (cleaned, str | None)`) and set `StepResult.complexity_tier`;
  strip the COMPLEXITY line from the written body. **Absent/unparseable → `None`,
  which gates nothing** (fail-open; keeps stub/offline runs at all 12 phases).

**`sdk/session_bridge.py` → `execute_phase`.** Copy `result.complexity_tier` onto the
returned `PhaseCompleteEvent` (FR-CX-001).

### 4.2 Supervisor selects the active phase set

**`core/development_manager.py`.**
- `_RunContext`: add `excluded: set[str] = set()`.
- New module-level helper:
  ```
  _GATED_BY_TIER = {
      "simple":   {"qa", "packaging", "documentation", "deployment", "cleanup"},
      "standard": {"packaging", "documentation", "deployment", "cleanup"},
      "complex":  set(),
  }
  def excluded_for_tier(tier: str | None) -> set[str]:
      return _GATED_BY_TIER.get(tier or "standard", set())
  ```
- In `_record_success`, when `phase_id == "proposal"`: apply config override if present
  (`self._config` tier field, FR-CX-006) else `event.complexity_tier`; set
  `ctx.excluded = excluded_for_tier(tier)`; emit `ComplexityAssessed`
  (`data={"tier", "active": [...], "excluded": [...]}`) (FR-CX-004).
- In `step`, feed the exclusions to the DAG so gated phases are never selected:
  ```
  next_phase = self._dag.next_phase(ctx.completed | ctx.excluded)
  ```
  Excluded phases are never dispatched, recorded, or checkpointed (FR-CX-002/003). For
  the linear DAG this makes the run complete after the last active phase.
- FR-CX-005 falls out: `step` never reaches a gated-out phase, so its pre/post gate
  (e.g. `pre-deployment`) never fires. No gate-map change needed.

The three tier sets are dependency-closed (qa depends on plan + `src/`, both core), so
no phase runs with a missing prerequisite. `PhaseDAG` is unchanged.

---

## 5. #12 — Phase-Aware Model Routing

**`llm/model_router.py`.** Update the default slugs (lines 30–31):
```
DEFAULT_PLANNING_MODEL = "google/gemma-4-31b-it"
DEFAULT_CODING_MODEL   = "deepseek/deepseek-v4-flash"
```
(`_CODING_PHASES = {"implementation", "qa"}` and the precedence logic stay as-is —
FR-RT-001.)

**`app.py` → `_build_real_manager`.** Stop collapsing routing. Build `subtask_models`
only from explicitly-set env overrides; otherwise pass nothing so the router's
per-tier defaults apply (FR-RT-002):
```
overrides = {}
if os.environ.get("ANVIL_PLANNING_MODEL"): overrides.update(planning=..., analysis=..., review=...)
if os.environ.get("ANVIL_CODING_MODEL"):   overrides.update(coding=..., debugging=...)
if os.environ.get("ANVIL_MODEL"):          overrides = {c: ANVIL_MODEL for c in SUBTASK_CATEGORIES}
ModelRouter(subtask_models=overrides or None, event_bus=bus, ...)
```
Overrides via config precedence remain intact (FR-RT-003).

---

## 6. #13 — `runId` on All Telemetry Events

The run_id already reaches `SessionBridge` via `payload.phase_context["run_id"]`; pass
it to the emitters.

- **`llm/model_router.py` → `select`**: add `run_id: str | None = None`; use it in the
  `_emit` (fall back to `self._run_id`).
- **`llm/usage_tracker.py` → `record`**: add `run_id: str | None = None`; use it in
  `_emit` (fall back to `self._run_id`).
- **`sdk/session_bridge.py` → `execute_phase`**: read
  `run_id = payload.phase_context.get("run_id", "")` and pass it to
  `self._router.select(phase, subtask, run_id=run_id)` and
  `self._usage.record(phase, result.usage, run_id=run_id)`.

Result: `ModelRouteSelected` and `TokenUsageReported` carry the active non-empty
`runId` (FR-EVT-001/002). DevelopmentManager events already carry it.

---

## 7. Feature — Failure-Record (FR) Writer

**New module `core/failure_record.py`** with a pure renderer + writer:
```
def render_fr(seq: int, packet: EscalationPacket, mode: str, exec_mode: str,
              now: datetime) -> str:
    # returns the FR-001/002 Markdown: metadata block + Summary / Observed Evidence /
    # Root Cause (placeholder) / Impact / Recommendations (packet.available_actions) /
    # Verification Plan (placeholder). Deterministic; no LLM. (FR-REC-002/003)

def write_fr(workspace_root: str, packet: EscalationPacket, mode: str,
             exec_mode: str, now: datetime) -> str:
    # seq = count(docs/failure_records/FR-*.md) + 1; slug from phase + reason;
    # writes docs/failure_records/FR-<NNN>-<slug>.md ; returns the path. (FR-REC-001)
```

**`core/development_manager.py` → `_handle_failure`.** It is the single chokepoint for
every failure (pre-retry and at escalation). After `record_failure`, build the packet
(reuse `self._escalation.build_packet`) and call `write_fr(self._root, packet, ctx.mode,
exec_mode, self._clock())` for **every** failure, not only escalations (FR-REC-001).
`exec_mode` is read from the existing execution-mode context (env/app state). The write
must not alter phase status or single-writer ownership (FR-REC-005).

The escalation path (retries exhausted) is unchanged except that the FR file already
exists for that final failure.

---

## 8. Files Touched

| File | Fixes / feature |
|---|---|
| `api/routes_runs.py` (+ small workspace helper) | #9 |
| `sdk/openhands_adapter.py` | #10, #11 (tier emit + `StepResult` field) |
| `sdk/session_bridge.py` | #11 (tier propagate), #13 (run_id) |
| `core/development_manager.py` | #11 (gating), FR writer hook in `_handle_failure` |
| `core/phase_contracts.py` | #11 (`PhaseCompleteEvent` field) |
| `core/failure_record.py` (new) | FR writer |
| `llm/model_router.py` | #12 (slugs), #13 (run_id param) |
| `llm/usage_tracker.py` | #13 (run_id param) |
| `app.py` | #12 (wiring) |

`PhaseDAG`, `ArtifactValidator`, schemas, and the VS Code extension are unchanged.

---

## 9. Testing Map (per spec)

| FR | Test |
|---|---|
| FR-RUN-001…004 | `tests/e2e/.../test_per_run_isolation`: fresh `task` run with unrelated artifacts at repo root → builds requested project under `runs/<date>-<slug>/`, reads only that workspace |
| FR-DOC-001…002 | `tests/unit/runtime/test_document_writer`: a phase with required sections → no section repeats the overview body |
| FR-CX-001…006 | `tests/unit/runtime/test_complexity_gate` (tier→excluded set) + `tests/integration/.../test_gated_phase_selection`: simple → 5 docs + src; complex → full set; `ComplexityAssessed` emitted |
| FR-RT-001…003 | extend `tests/unit/runtime/test_model_router`: no override → planning=`google/gemma-4-31b-it`, impl/qa=`deepseek/deepseek-v4-flash` |
| FR-EVT-001…002 | `tests/unit/runtime/test_usage_tracker` + `test_model_router`: emitted events carry non-empty `runId`; integration asserts all event types in a run share the run id |
| FR-REC-001…005 | `tests/unit/runtime/test_failure_record` (render/seq/slug) + `tests/integration/.../test_failure_record_written`: an induced failure writes a conforming `docs/failure_records/FR-001-*.md`; a second failure writes `FR-002` |

---

## 10. Gap Analysis (Architecture → Blueprint)

| Architecture | Blueprint |
|---|---|
| A.1 per-run workspace | §2 |
| A.2 document writer | §3 |
| A.3 complexity gate | §1, §4 |
| A.4 routing | §5 |
| A.5 run-scoped emitters | §6 |
| A.6 failure-record writer | §7 |

No gaps. A.2 is realized by fixing the existing `_document` writer in place (minimal
change) rather than extracting a new module.

---

Status: Draft for collaborative review.
