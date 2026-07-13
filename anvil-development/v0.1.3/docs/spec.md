# Anvil Specification — v0.1.3

Testable requirements for the v0.1.3 release. This is a **delta** against the
[v0.1.2 spec](../../v0.1.2/docs/spec.md), which remains the baseline; only the
requirements below change. Derived from [docs/proposal.md](proposal.md); every
requirement traces to a measured failure in `evals/` or
`benchmarks/commit0/STATUS.md`.

**Stack (unchanged):** OpenRouter + localhost REST runtime + `@anvil` extension.
All changes are runtime-side (plus the Commit0 adapter, which is a consumer,
not part of Anvil). **One-shot release:** no repair loop (#23 is v0.1.4), so
score movement attributes to the transport/generation fixes alone.

---

## 1. Configurable Completion Budgets (#19) — shipped during the cycle

Formalized here; implemented and tested during the Commit0 investigation
(`tests/unit/runtime/test_output_budgets.py`).

- **FR-BGT-001**: `EffectiveConfig` gains `intakeMaxTokens` / `docMaxTokens` /
  `codeMaxTokens` (defaults 400 / 1,500 / 4,000 — the v0.1.2 hardcoded
  values), applied per step category as the completion `max_tokens`.
- **FR-BGT-002**: Env overrides `ANVIL_INTAKE_MAX_TOKENS` /
  `ANVIL_DOC_MAX_TOKENS` / `ANVIL_CODE_MAX_TOKENS`; precedence env > config
  field > default (mirrors #18).
- **FR-BGT-003**: A completion with `finish_reason=length` (or empty content)
  is a **hard step failure** entering the normal retry/escalation path — never
  a silently clipped artifact.

---

## 2. Contract/Context Split (#20) — the core feature

`domain-knowledge/background-information.md` may mark a **contract** section
(binding facts that must survive verbatim) and a **context** section
(summarizable material). Fixes the measured contract drift: 3/6 smoke
failures where the spec phase paraphrased pinned names away.

### Markers and split

- **FR-CT-001**: Marker syntax is exactly `<!-- anvil:contract -->` (opens the
  contract section) and `<!-- anvil:context -->` (returns to context), each on
  its own line. Text before the first marker is context. Marker lines belong
  to neither section.
- **FR-CT-002 (fallback)**: A file with no contract marker behaves exactly as
  v0.1.2 — all context, nothing pinned, byte-for-byte identical prompts and
  appends. No migration for existing tasks, `build <text>` flows, or tests.

### Injection

- **FR-CT-003**: The contract block is injected **verbatim into every phase
  prompt** (intake through cleanup) as a dedicated block prefixed with the
  fixed binding preamble: *"Authoritative task contract — the facts below are
  binding and pinned. Never restate, never contradict, never rename: use
  every file name, symbol name, signature, and format exactly as written
  below."*
- **FR-CT-004**: The contract block is exempt from `ANVIL_INPUT_CHAR_LIMIT`
  and is **never truncated**.
- **FR-CT-005**: The context part remains a normal (truncatable)
  `input_files` member for **intake and proposal only** (today's topology);
  it never travels further. On a markered file the input read substitutes the
  context-only portion so the contract is not duplicated in those prompts.
- **FR-CT-006**: Resolution happens at prompt-assembly time per dispatch (no
  cached copy), so intake appends and resume need no extra transport state.

### Cap — fail loud, never clip

- **FR-CT-007**: Hard cap `contractMaxChars` (default **16,000**; env override
  `ANVIL_CONTRACT_MAX_CHARS`, precedence as FR-BGT-002). A contract over the
  cap **fails the run at intake** — before any completion is spent — with a
  reason naming the cap, the actual length, and the remedy (shrink the block
  or raise the cap). A clipped contract is worse than none.

### Append-only through intake, then sealed

- **FR-CT-008**: Intake clarification answers (interactive) and recorded
  assumptions (yolo) are appended **into the contract block** — an answered
  question is a binding fact, not prose. On an unmarkered file the v0.1.2
  append-at-end format is preserved byte-for-byte.
- **FR-CT-009**: When intake completes without pausing (its final round), a
  markered contract is **sealed**: a `ContractSealed` event is emitted and the
  sealed flag is checkpointed. Later contract writes (e.g. a stray
  `/clarify`) are rejected with an error naming the seal.
- **FR-CT-010**: Resume rehydrates the seal from the checkpoint; a restarted
  run cannot mutate binding facts mid-pipeline.

**Test:** markered file → contract present verbatim (with preamble) in every
phase prompt and context absent after proposal; unmarkered file → v0.1.2
prompts byte-for-byte; over-cap contract fails at intake with the documented
reason and zero completions spent; clarification answers and assumptions land
inside the contract block and re-injection reflects them; writes after
`ContractSealed` are rejected; resume preserves the seal.

---

## 3. Mechanical Contract Validation (#21)

With the contract in one structured place, generated code is checked against
it deterministically — no LLM. First *content* check for the drift checker
and secure-mode gates.

- **FR-MV-001**: The contract block may include a fenced
  ```` ```contract-manifest ```` JSON subsection:
  `{"files": [<src-relative paths>], "symbols": [{"qualname", "signature",
  "file"}]}`. `signature` is optional per symbol (existence-only check when
  absent). The manifest itself is optional — a prose-only contract skips
  mechanical checks (encouraged, not required; same posture as OKF
  cross-links, #16).
- **FR-MV-002**: Post-implementation, the artifact validator AST-parses
  `src/` and verifies: every manifest file exists; every symbol exists with
  an unchanged signature (whitespace-insensitive comparison of the
  `def name(args) -> ret` form).
- **FR-MV-003**: Violations emit `ArtifactValidationFailed` naming each
  missing/changed offender and **fail the phase into the normal retry path**
  — never a silent warning.
- **FR-MV-004**: A malformed manifest fence (bad JSON / wrong schema) fails
  validation loudly rather than silently skipping the check.
- **FR-MV-005**: The Commit0 adapter emits the manifest automatically from its
  stub inventory (adapter change, ships alongside).

**Test:** conforming src passes; a missing file, missing symbol, and changed
signature each fail with the offender named; absent manifest validates as
today; malformed manifest fails loudly; the failure enters the retry path.

---

## 4. Skeleton-Aware, Per-Artifact Implementation (#22)

Fixes skeleton blindness (Commit0 tinydb: 48/50 stubs regenerated blind,
provided code dropped, import broken) and removes the single-completion
ceiling structurally.

- **FR-PA-001 (target list)**: The implementation step derives its output-file
  list in priority order: (1) the contract manifest's `files` (authoritative
  when present); (2) file paths the plan/blueprint name explicitly under an
  allowed output prefix (e.g. `src/*.py`), first-mention order, capped at 40;
  (3) none → the v0.1.2 single-completion behavior, exactly.
- **FR-PA-002 (read what you're completing)**: When a target file already
  exists in the workspace (stub, partial, or prior version), its current
  source is included in **that file's** generation prompt with an explicit
  complete-in-place instruction, subject to the #18 input cap (truncation
  emits `InputTruncated`, never silent). Greenfield targets get no such block.
- **FR-PA-003 (generate per artifact)**: One completion per target file, each
  under `codeMaxTokens`, written to its sandboxed path (stray fences/markers
  stripped). Ordering follows the target list.
- **FR-PA-004 (per-file usage)**: Each file's token usage is reported on the
  existing `TokenUsageReported` event, tagged with the artifact path; the
  phase aggregate is still reported by the usage tracker.
- **FR-PA-005 (partial-failure semantics)**: A failed completion for one file
  is retried **for that file only** (bounded, 2 attempts) without
  regenerating files already produced; a file that exhausts its attempts
  fails the step with the file named, entering the normal phase retry path.

**Test:** an existing stub's content appears in its generation prompt and only
there; a manifest/multi-file plan yields one completion per file with per-file
usage events; a plan naming no files keeps the single-completion path; a
single file failing retries that file only; fences are stripped.

---

## 5. Out of Scope (unchanged from the proposal)

#23 external-test repair loop (v0.1.4, measurement integrity); contract
ledger; adding the domain-knowledge file to later phases' inputs (superseded
by #20); any change to `anvil-instructions.md` semantics (frozen,
2026-07-11); OpenHands/DevBench/WebGen adapters and official Commit0
evaluation.

---

## 6. Acceptance

Measured one-shot on the instruments that motivated the release: the `evals/`
smoke suite must hold 6/6 **without** per-task fidelity instructions (proving
#20 replaces the workaround), and the Commit0 tinydb run's pass rate over its
201 tests becomes the baseline v0.1.4's repair loop must improve on its own
merits.
