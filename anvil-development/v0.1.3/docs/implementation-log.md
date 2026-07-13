# Anvil v0.1.3 — Implementation Log

What shipped, where it lives, and how it was verified. Requirements:
[spec.md](spec.md); rationale: [proposal.md](proposal.md) and
`domain-knowledge/background-information.md`.

## Code map

### New: the task-contract channel (`runtime/anvil_runtime/contract/`)

- `resolver.py` — marker constants (`<!-- anvil:contract -->` /
  `<!-- anvil:context -->`), the fixed binding preamble, `split_contract`
  (FR-CT-001/002), `resolve_contract` (per-dispatch resolution, FR-CT-006),
  and `append_block` (append into the contract section when markered, v0.1.2
  append-at-end byte-for-byte when not; FR-CT-008).
- `manifest.py` — `parse_contract_manifest` (fenced `contract-manifest`
  JSON, loud on malformed input; FR-MV-001/004) and `validate_manifest`
  (AST existence + whitespace-insensitive signature checks; FR-MV-002).

### Changed

- `config/schema.py` — `DEFAULT_CONTRACT_MAX_CHARS = 16_000`,
  `EffectiveConfig.contractMaxChars` (FR-CT-007).
- `app.py` — `ANVIL_CONTRACT_MAX_CHARS` env > config > default, threaded into
  the backend (FR-CT-007).
- `sdk/openhands_adapter.py` (`LLMBackend`) —
  - `_contract_block()` injected into the intake, doc, and code prompts
    (FR-CT-003), never truncated (FR-CT-004);
  - `_read_inputs` substitutes the context-only part of a markered
    domain-knowledge file (FR-CT-005);
  - intake fails pre-completion on an over-cap contract (FR-CT-007);
  - `_append_assumptions` appends into the contract block (FR-CT-008);
  - `_run_code` split: `_code_targets` (manifest → plan-mention → none;
    FR-PA-001), `_run_code_per_file` (one completion per file, per-file
    bounded retry, per-artifact `TokenUsageReported`, fence stripping;
    FR-PA-003/004/005), `_file_prompt` + `_existing_source` (skeleton-aware
    complete-in-place; FR-PA-002), `_run_code_single` (v0.1.2 path,
    unchanged).
- `core/phase_contracts.py` — `RunState.contract_sealed` (FR-CT-009/010).
- `core/development_manager.py` — `_seal_contract` after the final intake
  completion (emits `ContractSealed`, checkpoints the flag);
  `submit_clarification` rejects post-seal writes; `_append_clarifications`
  appends into the contract block; resume rehydrates the seal
  (FR-CT-008/009/010).
- `artifacts/validator.py` — `_validate_contract_manifest` on the
  implementation phase; violations are `kind="contract"` issues that flow
  into the existing `ArtifactValidationFailed` → retry path (FR-MV-002/003).

### Commit0 adapter (consumer-side, ships alongside)

- `stubs.py` — `render_manifest` (stub inventory → `contract-manifest` JSON;
  FR-MV-005).
- `prepare.py` — the task file is now markered (contract: task rules + stub
  inventory + manifest; context: readme + doc excerpts), and every module
  needing work is pre-staged under `src/` so #22 reads exactly the stub it is
  completing and `apply` maps by exact relative path.
- `cli.py` — spawned servers get `ANVIL_CONTRACT_MAX_CHARS=48000` headroom
  (library-scale inventories exceed the 16k default, which fails intake
  loudly by design).

## Verification

- **Unit**: 43 new tests — `test_contract_split.py`,
  `test_contract_injection.py`, `test_contract_seal.py`,
  `test_contract_validation.py`, `test_per_artifact_implementation.py`
  (each spec **Test:** paragraph has a corresponding case). Full suite:
  **343 passed** (was 300; zero regressions).
- **E2E (offline-llm, via the API)**: a markered prose-contract run completes
  all 13 phases and emits `ContractSealed`; a manifest-bearing run escalates
  at implementation with 3 `ArtifactValidationFailed` (initial + 2 retries) —
  the mechanical check correctly refuses placeholder output. The latter is
  the *expected* offline behavior for manifest tasks from this release on.
- **Adapter handshake (offline)**: synthetic skeleton → `stage_workspace` →
  Anvil-side `resolve_contract`/`parse_contract_manifest` round-trips; the
  pre-staged stubs validate clean; a broken signature is named
  (`changed signature: add in core.py — pinned 'def add(a, b) -> int',
  found 'def add(a)'`).

## Measurement still owed (needs `OPENROUTER_API_KEY`)

Per the acceptance criteria — not run in this cycle:

1. `evals/` smoke suite in real mode **without** per-task fidelity
   instructions → must hold 6/6.
2. Commit0 tinydb real run (`v0.1.3` label) → pass rate over 201 tests is
   the one-shot baseline v0.1.4's repair loop (#23) must beat.
