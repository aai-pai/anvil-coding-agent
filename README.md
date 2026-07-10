# Anvil — an OpenRouter-backed coding factory

Anvil turns a plain-English request into a working project by running it through
a governed phase pipeline (intake → proposal → spec → architecture → blueprint →
plan → implementation → …), supervised with approval gates, bounded retries,
checkpoint/resume, and a redacted audit trail.

Three moving parts:

- **`runtime/`** — the Python (FastAPI) runtime server: phase orchestration,
  LLM calls via OpenRouter, run state, and the `/v1` REST + SSE API.
- **`extension/`** — the VS Code `@anvil` chat participant (TypeScript).
- **`tests/`** — unit, integration, and e2e suites (`pytest` from the repo
  root; `npm test` inside `extension/`).

**Start here: [RUNNING.md](RUNNING.md)** — setup, the `@anvil` chat flow, the
REST API, execution modes, and what a run produces.

Design history lives under [anvil-development/](anvil-development/) (per-version
proposal / spec / architecture / blueprint / plan documents).
