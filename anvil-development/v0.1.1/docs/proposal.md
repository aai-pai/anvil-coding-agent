# Anvil Proposal — v0.1.1

v0.1.1 is a fix release: five defects found in real v0.1.0 testing (Issues #9–#13,
grounded in failure records FR-001 and FR-002) plus one small feature —
complexity-gated phase selection. The [v0.1.0 proposal](../../v0.1.0/docs/proposal.md)
remains the baseline; this document covers only what changes.

**Stack.** OpenRouter (direct API calls) + a thin localhost REST runtime + the
`@anvil` VS Code extension. v0.1.1 does **not use OpenHands yet** — the v0.1.0
"OpenHands adapter" was only a shim over the OpenRouter provider and is set aside
until a real adapter is built in a later release.

## Fixes

### #9 — Prompt overridden by existing workspace artifacts

A fresh prompt run inside the Anvil repo built Anvil itself instead of the requested
project (FR-001): pre-existing `docs/` and `domain-knowledge/` outweighed the prompt.

**Fix.** Each run executes in its own `runs/<date>-<slug>/` workspace (per
[`runs/README.md`](../../../runs/README.md)). The prompt is written to that folder's
`domain-knowledge/background-information.md` and all phase I/O is scoped there, so
unrelated artifacts are invisible. Regression test: a clean prompt in a workspace
that already contains unrelated artifacts.

### #10 — Markdown repeats the full body under every heading

`_document()` wrote the full content under `## Overview`, then appended it again
under each required section (FR-002 §A) — roughly 3× the tokens.

**Fix.** Generate the body once; each required section gets section-specific content
or a placeholder, never a copy. Regression test asserts no duplicated blocks.

### #11 — Auxiliary docs emitted even when unneeded → complexity gating

The pipeline always emitted qa / packaging / documentation / deployment / cleanup
docs, even for a trivial CLI (FR-002 §B).

**Fix (the one new feature).** Complexity-gated phase selection:

- **Core phases always run:** proposal, spec, architecture, blueprint, plan,
  implementation → the 5 canonical docs + `src/`.
- **Auxiliary phases run only when task complexity warrants:** qa, packaging,
  documentation, deployment, cleanup. When skipped, the phase does not run and emits
  nothing.

A trivial task emits 5 docs; a complex one up to 10. A secure-mode checkpoint
applies only to a phase that actually runs. The exact complexity signals and
thresholds are pinned in the spec phase. Tests: trivial task → minimal set, complex
task → full set.

### #12 — Every phase used one model

All routing went to `deepseek/deepseek-chat` because planning and coding both fell
back to a single default (FR-002 §C; confirmed in `app.py`).

**Fix.** Phase-aware defaults — **Gemma 4** for the planning/design phases,
**DeepSeek** for implementation. Exact OpenRouter slugs are pinned in the spec
phase. Test asserts the model selected per phase.

### #13 — Telemetry events missing `runId`

`ModelRouteSelected` and `TokenUsageReported` were emitted with `runId:""` (FR-002).

**Fix.** Thread the active `runId` into every event. Test asserts a non-empty
`runId` on all event types.

## Out of scope

- A manual strict/canonical artifact mode — complexity gating handles #11
  automatically.
- A real OpenHands adapter — future release.
- Brownfield/incremental builds (Anvil editing an existing codebase) — future
  release.

## Acceptance criteria

Approved when it supports deriving `spec.md`, `architecture.md`, `blueprint.md`, and
`plan.md` for #9–#13 and the complexity gate. Carried into the spec phase: the
complexity tiers/thresholds and the exact Gemma 4 / DeepSeek OpenRouter slugs.

---

Status: Draft for collaborative review.
