# Anvil Proposal — v0.1.3

v0.1.3 is an evidence-driven release: every feature traces to a measured
failure from the Tier-1 eval harness (`evals/`) or the Commit0 adapter
(`benchmarks/commit0/STATUS.md`). The [v0.1.2 proposal](../../v0.1.2/docs/proposal.md)
remains in force; this document covers only what changes.

**Stack.** Unchanged: OpenRouter + the localhost REST runtime + the `@anvil`
extension. The OpenHands adapter stays parked.

**Theme.** v0.1.2 closed the loop between *what the user said* and *what
Anvil assumes*. v0.1.3 closes the loop between *what the task pins* and
*what Anvil ships*: the task's binding facts stop being lossy-retold between
phases (#20), get mechanically checked against the generated code (#21), and
large tasks become buildable (#19, #22). Deliberately **one-shot**: no
repair loop ships in this release, so every score movement is attributable
to the transport and generation fixes themselves.

## Features

### #19 — Configurable completion budgets (shipped during the cycle)

Output-side mirror of #18. The hardcoded per-step `max_tokens`
(400 intake / 1,500 doc / 4,000 code) made library-scale tasks unbuildable:
the Commit0 spec phase escalated on 3× `finish_reason=length`.

- `EffectiveConfig` fields `intakeMaxTokens` / `docMaxTokens` /
  `codeMaxTokens`; env overrides `ANVIL_INTAKE_MAX_TOKENS` /
  `ANVIL_DOC_MAX_TOKENS` / `ANVIL_CODE_MAX_TOKENS`. Precedence env > config
  > default; defaults preserve v0.1.2 values.
- A truncated completion remains a **hard step failure** (retry →
  escalation), never a silently clipped artifact.

Status: implemented (`tests/unit/runtime/test_output_budgets.py`, 272 green);
this release formalizes it in the docs/spec.

### #20 — Contract/context split in `background-information.md`

The core feature. The domain-knowledge file gains two marked sections:

```markdown
<!-- anvil:contract -->
(output contract, interface inventory, pinned names/signatures/formats,
 MUST-ALSO-DEFINE names — the facts that must survive verbatim)
<!-- anvil:context -->
(library docs, background prose, examples — summarizable material)
```

- **Contract block → injected verbatim into every phase prompt** as a
  dedicated block with a fixed binding preamble ("authoritative contract —
  never restate, never contradict, never rename"). Task-scoped analog of the
  #14 instructions block; exempt from `ANVIL_INPUT_CHAR_LIMIT`.
- **Never truncated — fail loud instead.** Hard cap
  `ANVIL_CONTRACT_MAX_CHARS` (default 16,000); an over-cap contract fails the
  run at intake with a clear reason. A clipped contract is worse than none.
- **Context block** stays a normal `input_files` member for **intake and
  proposal only** (today's behavior); it never travels further. Downstream
  phases design from proposal/spec retellings — which is fine, because
  context is summarizable by definition.
- **Append-only through intake, then sealed.** Intake clarifications
  (interactive) and assumptions (yolo) append *into the contract block* —
  an answered question is a binding fact, not prose. At
  `IntakeAssessed` the block is sealed (`ContractSealed` event); later
  writes are rejected. Resolution happens at prompt-assembly time per
  dispatch, so appends and resume work without new state.
- **Fallback:** a file with no markers behaves exactly as v0.1.2 (all
  context, nothing pinned). No migration required for existing tasks,
  `build <text>` flows, or tests.

Economics (measured on Commit0 tinydb): contract ≈ 5KB, context ≈ 30KB.
Pinning 5KB × ~9 phases replaces re-quoting the inventory through four doc
artifacts and shrinks doc outputs — fewer tokens *and* no drift. This
mechanism was validated by accident in v0.1.2: the +50-pt instructions
experiment worked precisely because injection is lossless; #20 promotes it
from per-task workaround to first-class channel.

Tests: markered file → contract block present verbatim in every phase
prompt (intake through cleanup) and context absent after proposal;
unmarkered file → v0.1.2 behavior byte-for-byte; over-cap contract fails at
intake with the documented reason; clarification answers land inside the
contract block and re-injection reflects them; writes after `ContractSealed`
are rejected; resume preserves the sealed block.

### #21 — Mechanical contract validation

With the contract in one structured place, the artifact validator can check
generated code against it deterministically — no LLM, giving the drift
checker and the secure-mode gates their first *content* check.

- The contract block may include a fenced ```contract-manifest``` JSON
  subsection: `{files: [...], symbols: [{qualname, signature, file}], ...}`.
  Optional — prose-only contracts skip mechanical checks (encouraged, not
  required; same posture as OKF cross-links in #16).
- Post-implementation, the validator AST-parses `src/` and verifies: every
  manifest file exists; every symbol exists with an unchanged signature.
  Violations emit `ArtifactValidationFailed` with the missing/changed names
  and fail the phase into the normal retry path.
- The Commit0 adapter emits the manifest automatically from its stub
  inventory (adapter change, ships alongside).

Tests: conforming src passes; a missing file, missing symbol, and changed
signature each fail with the offender named; absent manifest validates as
today; the failure enters the retry path (not a silent warning).

### #22 — Skeleton-aware, per-artifact implementation

The implementation phase today reads only `docs/plan.md` + `docs/blueprint.md`
and emits one completion — so it *reconstructs* files it has never seen and
cannot exceed one completion's budget. Two changes:

- **Read what you're completing.** When a target output file already exists
  in the workspace (stub, partial, or prior version), its current source is
  included in that file's generation prompt (subject to the #18 input cap).
  Greenfield runs, where targets don't exist, behave exactly as today.
- **Generate per artifact.** The implementation step iterates the plan's
  file list, one completion per output file (each under `codeMaxTokens`,
  each validated), instead of one completion for all of `src/`. Removes the
  single-completion ceiling structurally; per-file token usage is reported
  per artifact on the existing `TokenUsageReported` event.

Tests: an existing stub file's content appears in its generation prompt and
provided (non-stub) definitions survive into the output; a multi-file plan
yields one completion per file with per-file usage events; greenfield
behavior unchanged; a single file failing retries that file only.

## Out of scope

- **#23 — External test repair loop** (bounded `externalTestCommand` +
  feed-failures-back rounds). Deferred to v0.1.4 **for measurement
  integrity, not lack of value**: a repair loop fixes exactly the defect
  class #20 exists to prevent, so shipping both at once would make a green
  tinydb run unattributable. Sequence instead: v0.1.3 measures one-shot
  quality (#20+#22 alone), v0.1.4 adds the loop and measures *its* delta on
  top — two clean data points instead of one confounded one. The v0.1.4
  design is sketched in this proposal's history and
  `benchmarks/commit0/STATUS.md`.
- **Contract ledger** (spec/architecture appending *invented* contracts in
  greenfield, with provenance and no-contradiction rules; gates diffing
  artifacts against the ledger). The natural v0.1.4 successor to #20 once
  single-writer sealing has soaked.
- Adding `background-information.md` to later phases' `input_files` —
  superseded by #20 (it would re-send context, which is the expensive part).
- Any change to `anvil-instructions.md` semantics, content, or caps (frozen
  by team decision, 2026-07-11).
- A real OpenHands adapter; DevBench/WebGen-Bench adapters; Commit0 official
  docker/modal evaluation — benchmark-side work, tracked in
  `benchmarks/commit0/STATUS.md`.

## Acceptance criteria

Approved when it supports deriving `spec.md`, `architecture.md`,
`blueprint.md`, and `plan.md` for #19–#22. Carried into the spec phase: the
exact marker syntax and contract-block preamble text, the
`ANVIL_CONTRACT_MAX_CHARS` default and intake failure surface, the
`contract-manifest` schema, and the per-artifact iteration contract for #22
(ordering, partial-failure semantics).

Success is measured, not asserted, using the instruments that motivated the
release — and **one-shot**, with no repair loop in the pipeline, so the
numbers attribute cleanly: the `evals/` smoke suite must hold 6/6 **without**
per-task fidelity instructions (proving #20 replaces the workaround), and
the Commit0 tinydb run's pass rate over its 201 tests is the measured
baseline that v0.1.4's repair loop (#23) must then improve on its own merits.

---

Status: Draft for collaborative review.
