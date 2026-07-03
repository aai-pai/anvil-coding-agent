# Anvil Implementation Plan — v0.1.2

Phased implementation plan for v0.1.2. **Delta** scope; derived from
[blueprint.md](blueprint.md). Each slice: no drift from blueprint/architecture/
spec; unit + integration/e2e tests; full suite green before commit
(`[IMPL-S<n>]` commits). Baseline entering implementation: 243 tests passing.

## Implementation Slices

### Slice 1 — Input limit + truncation events (#18) `FR-CTX-001..003`
`config/schema.py` (`inputCharLimit`), `openhands_adapter.LLMBackend`
(`input_char_limit`, `event_bus`, `InputTruncated`), `app.py` wiring
(config/env). Tests: `test_document_writer.py` additions (limit honored,
event emitted, env override).

### Slice 2 — Instructions resolver + prompt injection (#14) `FR-INS-001..004`
New `instructions/resolver.py`; `LLMBackend(instructions=...)` +
`_instructions_block()` in all prompts; `build_manager(instructions=...)`;
`routes_runs` resolution + `InstructionsResolved` event. Tests: new
`test_instructions_resolver.py`; prompt-content assertions; route event test.
(FR-INS-005 lands with Slice 3.)

### Slice 3 — File-based build (#17) `FR-SRC-001..005` + `FR-INS-005`
`RunStartRequest.source_path`; `routes_runs.start_run` source branch (400s,
slug-from-heading, copy, sibling instructions copy). Extension: empty `build`,
`source_path` in client. Tests: `test_run_workspace.py`/route tests; e2e
`per_run_isolation` addition; `test_command_router.ts`.

### Slice 4 — Intake phase + bounded clarification (#15) `FR-INT-001..012`
Contracts (+`intake`, event fields, `PhaseStep.context`), `IntakeAgent`,
factory, `_run_intake` + marker parsing, session-bridge threading, manager
pause/resume + `/clarify` route + models, extension `answer` command +
renderer + terminal status. Tests: unit (parsing, mode, round bound; existing
suites updated for 13 phases), integration (gated pause→clarify→resume; yolo
assumptions; stub pass-through), extension unit tests.

### Slice 5 — OKF artifacts + run index (#16) `FR-OKF-001..004`
`schemas.OKF_TYPES`, `_document` OKF header, `metadata` required fields,
`_doc_prompt` cross-link line, manager `_write_run_index`. Tests:
`test_document_writer.py`, `test_artifact_validator.py`, e2e full-run index
assertion.

### Slice 6 — Final review
Full pytest + `npm test` (vitest) green; drift check against blueprint;
RUNNING.md updates (new commands, files, env vars); implementation log below.

## Slice → Requirement Traceability

| Slice | Requirements |
|---|---|
| 1 | FR-CTX-001..003 |
| 2 | FR-INS-001..004 |
| 3 | FR-SRC-001..005, FR-INS-005 |
| 4 | FR-INT-001..012 |
| 5 | FR-OKF-001..004 |

## Implementation Log

Baseline entering implementation: 243 tests. Final: **272 passed** (Python).

- **Slice 1 ✅ COMPLETED** — `[IMPL-S1]`. `inputCharLimit` config + `ANVIL_INPUT_CHAR_LIMIT`
  env; `LLMBackend(input_char_limit, event_bus)`; `InputTruncated` warning; also
  landed `PhaseStep.context` early (needed for run-id on backend events). +3 tests.
- **Slice 2 ✅ COMPLETED** — `[IMPL-S2]`. New `instructions/resolver.py`
  (run > base precedence, 16k cap); `_instructions_block()` in doc/code prompts;
  `build_manager(instructions=…)`; `InstructionsResolved` emitted from the
  run-start route. +9 tests.
- **Slice 3 ✅ COMPLETED** — `[IMPL-S3]`. `RunStartRequest.source_path` (400 on
  missing / on `task`+`source_path`); slug from first heading; sibling
  `anvil-instructions.md` copied (FR-INS-005). Extension: bare `build` →
  `source_path`. +3 tests.
- **Slice 4 ✅ COMPLETED** — `[IMPL-S4]`. `intake` as 13th canonical phase (first
  in DAG); marker protocol `INTAKE:`/`QUESTION:`/`ASSUMPTION:` in
  `LLMBackend._run_intake`; `awaiting_clarification` + `submit_clarification`
  + `POST /clarify`; single-round bound; yolo assumption mode appends
  `## Assumptions`. Extension: `answer` command, terminal status, question
  rendering. 20 pre-existing tests updated for 13 phases; +10 new tests.
- **Slice 5 ✅ COMPLETED** — `[IMPL-S5]` (committed by JC). OKF header fields in
  `_document`; `OKF_TYPES`/`okf_type_for`; validator requires `type`/`title`;
  supervisor writes `docs/index.md` on completion; cross-link prompt line.
  +4 tests; 3 fixtures updated.
- **Slice 6 ✅ COMPLETED** — final review. Offline-llm e2e sanity (source_path →
  13 phases → OKF index + all new events verified live); RUNNING.md updated.
  Shipped a starter `workspace/anvil-instructions.md` (the server-level default
  the FR-INS-001 resolver consults; runtime file, deliberately not part of the
  version-scoped dev docs) and gitignored `workspace/runs/`. Extension verified
  on Node v24.18.0 (36 vitest tests, clean tsc) and repackaged as
  `anvil-extension-0.1.2.vsix`.
- **Amendment (post-review, JC request)** — `@anvil build` now starts runs in
  **gated** mode instead of yolo, so the intake step can hold its one
  clarifying round from chat before building; gated mode adds no approval
  gates of its own, so a complete request still builds straight through
  unattended. FR-INT-010 (yolo never pauses) is unchanged — `build` simply no
  longer uses yolo. REST callers keep full mode control. Extension re-tested
  and repackaged.
  **Issue encountered:** Node.js is not installed on this development machine, so
  `npm test` (vitest) and `npm run build` (tsc) for the extension could not be
  run; TS changes (commandRouter/participant/runtimeClient/responseRenderer +
  test updates) reviewed but **must be built/tested on a Node-equipped machine
  before shipping the .vsix**.

---

Status: Draft for collaborative review.
