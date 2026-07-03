# Anvil Specification — v0.1.2

Testable requirements for the v0.1.2 feature release. This is a **delta** against
the [v0.1.1 spec](../../v0.1.1/docs/spec.md) (itself a delta on
[v0.1.0](../../v0.1.0/docs/spec.md)), which remains the baseline; only the
requirements below change. Derived from [docs/proposal.md](proposal.md).

**Stack (unchanged):** OpenRouter (direct API calls) + localhost REST runtime +
`@anvil` VS Code extension. Changes touch the runtime and (minimally, for #15/#17)
the extension.

---

## 1. Standing Instructions — `anvil-instructions.md` (#14)

A Copilot-instructions equivalent: default actions for underspecified inputs,
fallback behaviors, and conventions, available to every phase.

- **FR-INS-001**: The runtime must resolve a standing-instructions file at run
  start with precedence: `<run-workspace>/domain-knowledge/anvil-instructions.md`
  → `<base-workspace>/anvil-instructions.md` → none. First existing file wins;
  absence is not an error (behavior is then identical to v0.1.1).
- **FR-INS-002**: When resolved, the instructions content must be injected into
  **every** phase agent prompt (document, code, and intake prompts) as a clearly
  delimited block (`Standing instructions:`), distinct from phase context.
- **FR-INS-003**: The instructions block is exempt from the per-file input limit
  (§5): it must never be truncated. Oversize protection is a hard cap of 16,000
  characters at resolution time, with a warning event if exceeded.
- **FR-INS-004**: An `InstructionsResolved` event must record the resolved path
  (or `null`) on the run's event stream at run start.
- **FR-INS-005**: A file-based build (§4) must copy an `anvil-instructions.md`
  sitting next to the source file into the run workspace's `domain-knowledge/`,
  so run-level instructions travel with the request.

**Test:** precedence order honored; prompts contain the block when a file exists;
no file → prompts identical to v0.1.1; event emitted with the path.

---

## 2. Intake Phase with Bounded Clarification (#15)

A new dedicated **`intake`** phase — the 13th canonical phase — runs **before**
`proposal` and assesses the completeness of
`domain-knowledge/background-information.md` against what is needed to build.

### Phase mechanics

- **FR-INT-001**: `intake` is prepended to the canonical phase list and the
  linear DAG (`proposal` depends on `intake`). It has
  `input_files = [domain-knowledge/background-information.md]` and
  `allowed_outputs = [domain-knowledge/background-information.md]` (append-only
  usage; see FR-INT-006).
- **FR-INT-002**: `intake` runs at **every** complexity tier (it executes before
  the tier is assessed) and is never a member of any tier's excluded set.
- **FR-INT-003**: No secure-mode mandatory gate attaches to `intake`.
- **FR-INT-004**: In `stub` execution mode the intake agent reports success with
  no questions (deterministic pass-through), preserving v0.1.1 stub behavior.

### Assessment and questioning

- **FR-INT-005**: In LLM execution modes, the intake step must classify the
  background information as **complete** or emit up to **5** questions, using one
  LLM call on the planning-tier model. Output protocol (mirrors the `COMPLEXITY:`
  marker pattern): a line `INTAKE: complete` or lines `QUESTION: <text>` /
  `ASSUMPTION: <text>`.
- **FR-INT-006**: The intake step must not ask a question whose answer is
  derivable from the standing instructions (§1); the instructions are part of its
  prompt for exactly this purpose.
- **FR-INT-007** (interactive modes: `gated`, `secure`): when questions are
  emitted, the run must pause in a new **`awaiting_clarification`** status
  (sibling of `awaiting_approval`), emit a `ClarificationRequired` event carrying
  the questions, and expose them on `GET /v1/runs/{run_id}` as
  `pending_questions`.
- **FR-INT-008**: `POST /v1/runs/{run_id}/clarify` accepts
  `{"answers": ["..."]}`, appends the Q/A pairs to the run's
  `background-information.md` under a `## Clarifications` heading (a
  supervisor-owned deterministic write, exempt from phase single-writer rules
  like failure records), invalidates the intake checkpoint, and resumes the run.
  The file is the single source of truth: chat history is never load-bearing.
- **FR-INT-009** (bounded round): the clarification cycle runs **at most once**
  per run. The re-run after answers executes in *assumption mode*: any remaining
  gap is emitted as `ASSUMPTION:` lines, never a second pause.
- **FR-INT-010** (`yolo` mode): the run never pauses. Intake runs directly in
  assumption mode; emitted assumptions are appended to
  `background-information.md` under `## Assumptions` (written by the intake
  execution path within its allowed output), so downstream phases and the audit
  trail see exactly what was assumed.
- **FR-INT-011**: `IntakeAssessed` is emitted on every intake completion with
  `{complete, questions[], assumptions[], round}`.
- **FR-INT-012**: The `@anvil` extension gains an `answer <text>` command that
  posts to `/clarify` (multiple answers separated by `;`), and renders pending
  questions when a run is `awaiting_clarification`.

**Test:** complete input proceeds untouched; gated run with incomplete input
pauses with ≤5 questions; answers materialize under `## Clarifications` and the
run resumes; second round never pauses; yolo run never pauses and materializes
`## Assumptions`; stub runs are byte-identical to v0.1.1 behavior.

---

## 3. OKF-Conformant Markdown Artifacts (#16)

Adopt Google's Open Knowledge Format (spec v0.1, 2026-06-13:
markdown + YAML frontmatter; required field `type`; producers may add custom
fields) for Anvil's generated artifacts.

- **FR-OKF-001**: Every document artifact's frontmatter must carry the OKF
  fields `type`, `title`, `description`, `tags`, `timestamp` **in addition to**
  the existing lineage fields (`artifactId`, `phase`, `generatedAt`,
  `derivedFrom`, `inputHashes` where present), which OKF treats as producer
  extensions.
  - `type`: fixed per phase (e.g. `Proposal`, `Specification`, `Architecture`,
    `Blueprint`, `Development Plan`, `QA Test Plan`, …).
  - `title`: `<Type> — <run slug or project name>` derived deterministically.
  - `description`: first non-heading content line, truncated to 140 chars.
  - `tags`: `["anvil", "<phase-id>"]`.
  - `timestamp`: ISO 8601, same instant as `generatedAt`.
- **FR-OKF-002**: The artifact validator must additionally require non-empty
  `type` and `title` on artifacts whose schema requires metadata.
- **FR-OKF-003**: On run completion the supervisor must write
  `<run-workspace>/docs/index.md` — an OKF index listing each `docs/*.md`
  artifact with its `type` and `description` as a markdown link line. Generated
  deterministically (no LLM call); supervisor-owned, exempt from single-writer
  rules; regenerated (overwritten) on each completion.
- **FR-OKF-004**: Document prompts must instruct agents to reference sibling
  artifacts as relative markdown links (OKF cross-links). Encouraged, not
  validated.

**Test:** a generated artifact parses with `type`/`title` present and lineage
fields intact; validator rejects a document missing `type`; a completed run has
`docs/index.md` listing every doc artifact.

---

## 4. File-Based Build Input (#17)

- **FR-SRC-001**: `RunStartRequest` gains `source_path: str | None`. When set
  (and `task` is not), the runtime must copy the referenced markdown file into a
  **fresh isolated** `runs/<date>-<slug>/` workspace as
  `domain-knowledge/background-information.md`, then proceed exactly as a `task`
  run (FR-RUN-001..003 apply unchanged).
- **FR-SRC-002**: The slug is derived from the file's first `#` heading, else
  its file stem.
- **FR-SRC-003**: A missing/unreadable `source_path` fails with HTTP 400 and a
  clear message; nothing is created.
- **FR-SRC-004**: `task` and `source_path` are mutually exclusive; supplying
  both is HTTP 400.
- **FR-SRC-005**: `@anvil build` with **no description** resolves
  `<open folder>/domain-knowledge/background-information.md` as `source_path`
  (error message if there is no open folder or no such file); `@anvil build
  <text>` is unchanged. The task-less `start` flow (in-place, unisolated) is
  unchanged.

**Test:** file-based build creates an isolated run workspace containing a copy
of the source (and sibling instructions per FR-INS-005); missing file → 400;
both `task` and `source_path` → 400; chat-text build regression-identical.

---

## 5. Configurable Input Limit with Truncation Warnings (#18)

- **FR-CTX-001**: The per-file input character limit in the LLM backend's
  input assembly (v0.1.1 hardcoded 2,500) becomes configurable:
  `EffectiveConfig.inputCharLimit`, env override `ANVIL_INPUT_CHAR_LIMIT`,
  default **20,000** characters (~5k tokens per file).
- **FR-CTX-002**: When a file is actually truncated, an `InputTruncated`
  **warning** event must be emitted naming the file, its size, and the limit —
  truncation is never silent.
- **FR-CTX-003**: The standing-instructions block is injected outside this path
  and is never subject to this limit (see FR-INS-003).

**Test:** default limit reads a >2,500-char file in full; a file over the limit
produces an `InputTruncated` warning event; env override honored.

---

## 6. Gap Analysis (Proposal → Spec)

| Proposal item | Spec coverage |
|---|---|
| #14 standing instructions | §1 FR-INS-001…005 |
| #15 intake + bounded clarification | §2 FR-INT-001…012 |
| #16 OKF artifacts + index | §3 FR-OKF-001…004 |
| #17 file-based build | §4 FR-SRC-001…005 |
| #18 input-limit fix | §5 FR-CTX-001…003 |

Proposal items deferred to this spec now pinned: instructions file names and
precedence (§1), question cap = 5 and the `INTAKE:`/`QUESTION:`/`ASSUMPTION:`
marker protocol (§2), the `/clarify` API surface (§2), the OKF `type` taxonomy
(§3), input-limit default = 20,000 chars (§5). No gaps.

---

## 7. Acceptance Criteria

Approved when each of #14–#18 has the testable requirements above with stated
tests, all previously deferred details are pinned, and the gap analysis shows
full coverage. No open questions remain.

---

Status: Draft for collaborative review.
