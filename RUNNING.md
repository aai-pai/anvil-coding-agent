# Running Anvil

Post-v0.1.0 integration. The runtime can drive a project end-to-end over its REST
API. Phase execution runs through a pluggable executor selected by the
`ANVIL_EXECUTION_MODE` environment variable.

## Execution modes

| `ANVIL_EXECUTION_MODE` | Behavior | Needs API key |
|---|---|---|
| `stub` (default) | Deterministic stub agents; no files written. The v0.1.0 test pipeline. | No |
| `offline-llm` | Full real pipeline (routing → execution → artifact write → validation) with an **offline** LLM transport; writes placeholder artifacts. Proves the plumbing. | No |
| `real` | Same pipeline calling **OpenRouter** for real; phases generate genuine artifact content. | Yes |

## Prerequisites

```bash
pip install -e runtime            # installs fastapi, httpx, uvicorn, pydantic, pyyaml
```

## Start the runtime server

The server writes artifacts under its current working directory, so run it from
the workspace you want Anvil to build in:

```bash
# Offline smoke (no key) — proves the pipeline produces validated artifacts:
cd /path/to/your/workspace
ANVIL_EXECUTION_MODE=offline-llm \
  PYTHONPATH=/path/to/repo/runtime \
  python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port 8765
```

```bash
# Real run — generates real content via OpenRouter:
export OPENROUTER_API_KEY=sk-or-...        # never logged; redacted from the audit trail
cd /path/to/your/workspace
ANVIL_EXECUTION_MODE=real \
  PYTHONPATH=/path/to/repo/runtime \
  python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port 8765
```

Model routing defaults in this repo:

- `ANVIL_PLANNING_MODEL=google/gemma-4-26b-a4b-it` (planning/analysis/review)
- `ANVIL_CODING_MODEL=deepseek/deepseek-v4-flash` (coding/debugging)

Override models explicitly (Linux/macOS):

```bash
export ANVIL_PLANNING_MODEL=google/gemma-4-26b-a4b-it
export ANVIL_CODING_MODEL=deepseek/deepseek-v4-flash
```

### Complexity gate (optional planning docs)

The doc-only planning phases (`packaging`, `documentation`, `deployment`) only
run when the task is complex enough to warrant them. In `real`/`offline-llm`
mode an LLM classifies the run once (from the proposal + spec) as
`simple` / `standard` / `complex` and skips the phases the tier doesn't enable
(`ComplexityClassified` and `PhaseSkipped` events record the decision). `qa` and
`cleanup` always run. Force a tier (skips the classification call) with:

```bash
export ANVIL_COMPLEXITY=simple      # simple | standard | complex | full
```

`full` keeps every phase (the pre-gate behavior).

On Windows PowerShell, set env vars first:

```powershell
$env:ANVIL_EXECUTION_MODE = "real"
$env:OPENROUTER_API_KEY = "sk-or-..."
$env:ANVIL_PLANNING_MODEL = "google/gemma-4-26b-a4b-it"
$env:ANVIL_CODING_MODEL = "deepseek/deepseek-v4-flash"
$env:PYTHONPATH = "C:\path\to\repo\runtime"
python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port 8765
```

The endpoint (`127.0.0.1:8765`) matches the VS Code extension's `API_BASE_URL`.

## Drive a run over the API

```bash
BASE=http://127.0.0.1:8765

# Start a fully-autonomous run:
curl -s -X POST $BASE/v1/runs \
  -H 'content-type: application/json' \
  -d '{"mode":"yolo","security_profile":"open"}'

# Inspect state (status, current phase, completed phases, pending gate):
curl -s $BASE/v1/runs/<run_id>

# Stream the audit/event trail (SSE):
curl -s $BASE/v1/runs/<run_id>/events

# Fetch a produced artifact's path + checksum:
curl -s $BASE/v1/artifacts/architecture
```

For **secure** mode (`{"mode":"secure", ...}`) the run pauses at the four
mandatory gates (post-proposal, post-architecture, post-blueprint,
pre-deployment); approve each to continue:

```bash
curl -s -X POST $BASE/v1/runs/<run_id>/approve \
  -H 'content-type: application/json' \
  -d '{"gateId":"post-proposal","gateName":"Post-Proposal","approved":true,"requesterId":"me"}'
```

## What a run produces

Each phase writes its canonical artifact under `docs/` (and `src/`, `tests/` for
the coding phases) with an FR-AR-005 metadata header, and the supervisor
validates each artifact before advancing (FR-SV-009). The full audit trail is in
`logs/events.jsonl` (secrets redacted) and a human-readable summary in
`logs/run-summary.log`.

## VS Code extension

```bash
cd extension && npm install && npm run build   # produces dist/extension.js
```

Launch the extension host (F5 in VS Code) with the runtime server running; the
`@anvil` chat participant talks to `127.0.0.1:8765`.
