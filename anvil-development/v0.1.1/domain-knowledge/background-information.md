# background-information.md — v0.1.1

v0.1.1 is a fix release for five defects found while testing v0.1.0 against the live
OpenRouter pipeline (Issues #9–#13 on `aai-pai/openhands_based_coding_team`). The
errors are documented in failure records **FR-001** and **FR-002** (branch
`test_anvil_v0.1.0_ssainis`). This file records the problems and the agreed
direction; the formal plan is in [`docs/proposal.md`](../docs/proposal.md).

## Architecture context

- v0.1.1 has three parts: **OpenRouter** (direct API calls), a **thin localhost REST
  runtime**, and the **`@anvil` VS Code extension**.
- It does **not use OpenHands yet** — the v0.1.0 "OpenHands adapter" was only a shim
  over the OpenRouter provider. A real adapter is future work.
- All five fixes are **runtime-only**; the extension is unchanged.

## Errors faced and agreed direction

### #9 — Prompt overridden by existing workspace artifacts (FR-001)

A fresh prompt run inside the Anvil repo built Anvil itself instead of the requested
project; pre-existing `docs/` and `domain-knowledge/` outweighed the prompt.

→ Each run executes in its own isolated `runs/<date>-<slug>/` workspace, with the
prompt as the sole input there. Unrelated artifacts are invisible.

### #10 — Markdown repeats the full body under every heading (FR-002 §A)

`_document()` wrote the body once under `## Overview`, then appended it again under
each required section — roughly 3× the tokens.

→ Generate the body once; each section gets section-specific content or a
placeholder, never a copy.

### #11 — Auxiliary docs emitted even when unneeded (FR-002 §B)

qa / packaging / documentation / deployment / cleanup docs were always emitted, even
for a trivial CLI.

→ **Complexity-gated phase selection.** Core phases always run (proposal → spec →
architecture → blueprint → plan → implementation = 5 docs + `src/`); auxiliary phases
run only when task complexity warrants. Trivial task → 5 docs; complex → up to 10.

### #12 — Every phase used one model (FR-002 §C)

All routing collapsed to `deepseek/deepseek-chat` because planning and coding shared
a single default.

→ Phase-aware defaults: **Gemma 4** for planning/design phases, **DeepSeek** for
implementation.

### #13 — Telemetry events missing `runId` (FR-002)

`ModelRouteSelected` and `TokenUsageReported` were emitted with `runId:""`.

→ Thread the active `runId` into every event.
