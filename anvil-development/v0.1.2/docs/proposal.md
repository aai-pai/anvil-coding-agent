# Anvil Proposal — v0.1.2

v0.1.2 is a feature release driven by four team-filed issues from real v0.1.1
usage: standing instructions, a dedicated intake/clarification step, OKF-conformant
markdown artifacts, and file-based build input — plus one enabler fix (input
truncation). The [v0.1.1 proposal](../../v0.1.1/docs/proposal.md) and its
[v0.1.0 baseline](../../v0.1.0/docs/proposal.md) remain in force; this document
covers only what changes.

**Stack.** Unchanged: OpenRouter (direct API calls) + the localhost REST runtime +
the `@anvil` VS Code extension. The OpenHands adapter stays parked.

**Theme.** The release closes the loop between *what the user said* and *what Anvil
assumes*: a run is driven by its `background-information.md` (per-run, "what to
build"), governed by `anvil-instructions.md` (workspace-level, "how to behave"),
and a dedicated intake step guarantees that gaps in the former are filled — by the
user when interactive, by the latter's documented defaults when autonomous — and
always recorded.

## Features

### #14 — Standing instructions: `anvil-instructions.md` (Issue 1)

Anvil gains a Copilot-instructions equivalent: a markdown file of default actions
for underspecified inputs, fallback behaviors, and conventions, injected into
**every** phase agent's prompt as a dedicated block (never truncated, never mixed
into phase context).

- **Resolution precedence** (mirrors the existing config precedence, no new
  mechanism): run workspace `domain-knowledge/anvil-instructions.md` →
  project workspace root → server default. First hit wins; absence is not an
  error (today's behavior is "no instructions").
- The resolved instructions path is recorded in the run's events so the audit
  trail shows which instructions governed a run.
- Consumed by the intake step (#15) as the source of gap-filling defaults.

Tests: precedence resolution; prompt contains the instructions block; a run
without any instructions file behaves exactly as v0.1.1.

### #15 — Dedicated intake step with bounded clarification (Issue 2)

A new **intake phase** runs before proposal — a dedicated, small LLM step (cheap
planning-tier model) that reads `background-information.md` +
`anvil-instructions.md` and assesses completeness. Deliberately minimal for
v0.1.2:

- **Complete** → emits a `IntakeAssessed{complete: true}` event; the run proceeds
  to proposal. No file changes.
- **Incomplete, interactive modes** → emits up to **5** questions; the run pauses
  in a new `awaiting_clarification` state (sibling of `awaiting_approval`, reusing
  the same pause/resume machinery). The extension surfaces the questions; the user
  answers via `@anvil answer <text>`. Answers are **appended to
  `background-information.md`** under a `## Clarifications` section — the file is
  the single source of truth; chat history is never load-bearing. **One round
  only** (bounded, like self-heal retries): after the answers land, intake
  re-checks once and proceeds regardless, recording any still-open gaps as
  assumptions.
- **Incomplete, yolo mode** → never pauses. Gaps are filled from
  `anvil-instructions.md` defaults and written to `background-information.md`
  under `## Assumptions`, so downstream phases and the audit trail see exactly
  what was assumed and why.

The intake phase is a core phase (runs at every complexity tier — it executes
before the tier is even assessed) and is exempt from secure-mode gates (it *is*
a gate of its own kind).

Tests: complete input passes through untouched; incomplete input pauses and
resumes on answers; answers materialize in the file; yolo run never pauses and
records assumptions; the round bound holds.

### #16 — OKF-conformant markdown artifacts (Issue 3)

Anvil's markdown artifacts adopt Google's **Open Knowledge Format** (spec v0.1,
2026-06-13). OKF requires only a `type` frontmatter field and permits custom
fields, so Anvil conforms **without dropping its lineage metadata**:

- The Document Writer emits frontmatter with the OKF standard fields —
  `type` (e.g. `Proposal`, `Spec`, `Architecture`), `title`, `description`,
  `tags`, `timestamp` — alongside the existing FR-AR-005 fields (`artifactId`,
  `phase`, `generatedAt`, `derivedFrom`, `inputHashes`), which OKF treats as
  producer extensions.
- The artifact validator additionally requires `type` and `title`.
- Each run's `docs/` gains a generated **`index.md`** (OKF progressive
  disclosure): one line per artifact with its type and description. Written by
  the supervisor deterministically — no LLM call.
- Doc prompts instruct agents to reference sibling artifacts as relative
  markdown links (OKF cross-links). Encouraged, not validated, in v0.1.2.

Tests: every generated artifact parses as OKF (frontmatter with `type`);
existing lineage validation still passes; `index.md` lists all emitted artifacts.

### #17 — Build from an existing `background-information.md` (Issue 4)

File-based intent, without losing per-run isolation (the v0.1.1 FR-001 fix):

- `POST /v1/runs` accepts a `source_path` (alternative to `task`): the referenced
  markdown file is **copied into** a fresh isolated `runs/<date>-<slug>/`
  workspace as its `domain-knowledge/background-information.md`, then the run
  proceeds normally (slug derived from the file's title/first heading).
- `@anvil build` with **no description** resolves the open folder's
  `domain-knowledge/background-information.md` and uses it as `source_path`;
  `@anvil build <text>` is unchanged.
- The task-less `start` flow (which runs **in place**, unisolated) is unchanged
  but documented as the advanced path; `build`-from-file is the recommended one.

Tests: file-based build lands in an isolated run workspace containing a copy of
the source file; missing source file is a clean 4xx / chat error; chat-text build
is unchanged.

## Fix

### #18 — Input truncation silently caps context at 2,500 characters

`LLMBackend._read_inputs` truncates every input file to 2,500 characters — a rich
background-information file (#17), appended clarifications (#15), and any large
prior-phase artifact are silently cut off.

**Fix.** Make the per-file limit configurable (config + env override) with a
generous default sized in the spec phase; when truncation does occur, emit a
warning event naming the file and the amount cut, so it is never silent. The
instructions block (#14) is injected outside this path and is never truncated.

## Out of scope

- Multi-round clarification dialogues (v0.1.2 is one bounded round).
- OKF cross-link validation, `log.md` change histories, or an OKF graph
  visualizer — frontmatter conformance and `index.md` only.
- Applying OKF to the *generated project's* own documentation (Anvil's artifacts
  only).
- A real OpenHands adapter; brownfield builds — unchanged future work.

## Acceptance criteria

Approved when it supports deriving `spec.md`, `architecture.md`, `blueprint.md`,
and `plan.md` for #14–#18. Carried into the spec phase: the exact instructions
file names and precedence order, the intake question cap and prompt/marker
format, the `awaiting_clarification` API surface, the OKF `type` taxonomy for
Anvil artifacts, and the new input-limit default.

---

Status: Draft for collaborative review.
