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

_(filled in as slices complete)_

---

Status: Draft for collaborative review.
