# Running Anvil — Quickstart & Guide

Anvil turns a plain-English request into a working project by running it through a
governed phase pipeline. This guide covers setup, the VS Code `@anvil` flow, the REST
API, and what a run produces. (Supersedes the old `QUICKSTART.md` + `RUNNING.md`.)

## The 3 moving parts

1. **Runtime server** (Python) — Anvil's brain; runs the phases and calls OpenRouter.
2. **Extension** (TypeScript) — the `@anvil` chat participant, loaded into VS Code.
3. **VS Code Chat view** — the chat box that hosts `@anvil` (from GitHub Copilot Chat).

You need **one API key**: an **OpenRouter** key, set on the *server*. (Copilot is just
the chat window — it does no Anvil work, and its model dropdown does **not** control
`@anvil`. Anvil uses its own OpenRouter models.)

---

## One-time setup

```powershell
# 0. Allow local scripts (npm + the launcher need this) — run once
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 1. Install the Python runtime + dependencies
cd C:\path\to\openhands_based_coding_team
pip install -e runtime

# 2. Build the VS Code extension (only needed for the @anvil chat flow)
cd extension
npm install
npm run build
```

3. In VS Code, install **"GitHub Copilot Chat"** (Extensions panel) if you don't
   already have a chat box.

> Re-run `pip install -e runtime` only if `runtime/pyproject.toml` (deps/metadata)
> changes. Editing runtime `.py` code just needs a server restart, not a reinstall.

---

## Execution modes

Selected by `ANVIL_EXECUTION_MODE` (or the launcher's `-Mode`):

| Mode | Behavior | Needs key |
|---|---|---|
| `stub` | Deterministic stub agents; no files written. The unit-test pipeline. | No |
| `offline-llm` | Full pipeline (routing → execution → artifact write → validation) with an **offline** transport; writes placeholder artifacts. Proves the plumbing. | No |
| `real` | Same pipeline calling **OpenRouter** for real; phases generate genuine content. | Yes |

`scripts\start-anvil.ps1` defaults to **`real`**. The bare module
(`python -m uvicorn anvil_runtime.app:app`) defaults to **`stub`**.

---

## Use it via VS Code `@anvil`

### Step 1 — Start the server (leave the window open)

```powershell
cd C:\path\to\openhands_based_coding_team
$env:OPENROUTER_API_KEY = "sk-or-..."     # your key
.\scripts\start-anvil.ps1                  # real mode, phase-aware routing
```

Wait for `Uvicorn running on http://127.0.0.1:8765`. Verify in a browser:
<http://127.0.0.1:8765/v1/health> → `{"status":"ok",...}`.

No key? Run offline (placeholder output): `.\scripts\start-anvil.ps1 -Mode offline-llm`.

Launcher options: `-Mode real|offline-llm|stub`, `-Workspace <dir>` (where `runs/`
lives; default `...\workspace`), `-Port 8765`, `-Model <slug>` (force one model for
every phase; omit to use the phase-aware defaults below).

### Step 2 — Launch the extension

1. **File → Open Folder →** `...\openhands_based_coding_team\extension`
2. Press **F5** → a second window **"[Extension Development Host]"** opens with
   `@anvil` loaded. (Optionally open your target project folder in that window — runs
   isolate under *its* `runs/`.)

### Step 3 — Build something (plain English)

In the second window, open Chat (**Ctrl+Alt+I**) and type:

```
@anvil build a CLI tool that converts Celsius to Fahrenheit
```

A real run takes ~1–2 minutes and costs a few cents.

### `@anvil` commands

| Command | What it does |
|---|---|
| `build <description>` | Build from plain English (isolated run; asks clarifying questions once if the request is underspecified, then builds without further gates) |
| `build` | Build from the open folder's `domain-knowledge/background-information.md` (copied into an isolated run) |
| `start [mode] [profile]` | Start a run from an existing `background-information.md` (in place, unisolated) |
| `status` | Show current run state |
| `answer <a1>; <a2>; …` | Answer Anvil's clarifying questions (gated/secure runs) |
| `approve` / `deny` | Resolve a pending approval gate (gated/secure modes) |
| `rollback <phase>` | Roll back to a phase |
| `force-advance` / `stop` | Override the supervisor |
| `health` | Check the runtime is reachable |

---

## Use it via the REST API (no VS Code)

```powershell
$BASE = "http://127.0.0.1:8765"

# health
Invoke-RestMethod $BASE/v1/health

# start an autonomous build (the task is the project request)
$run = Invoke-RestMethod -Method Post $BASE/v1/runs -ContentType application/json `
  -Body '{"mode":"yolo","security_profile":"open","task":"build a CLI that converts USD to cents"}'
$run.run_id

# inspect state
Invoke-RestMethod "$BASE/v1/runs/$($run.run_id)"
```

**Secure mode** pauses at four mandatory gates (post-proposal, post-architecture,
post-blueprint, pre-deployment). Start with `"mode":"secure"`, then approve each:

```powershell
Invoke-RestMethod -Method Post "$BASE/v1/runs/$($run.run_id)/approve" `
  -ContentType application/json `
  -Body '{"gateId":"post-proposal","gateName":"Post-Proposal","approved":true,"requesterId":"me"}'
```

(Equivalent `curl` works too; SSE event stream: `GET /v1/runs/<id>/events`.)

**After a server restart**, restore a run from its checkpoint (gates, complexity
tier, and any active pause are rehydrated):

```powershell
Invoke-RestMethod -Method Post "$BASE/v1/runs/$($run.run_id)/resume"
```

The server checks its own root, then scans `runs/*` for the run id; pass
`?workspace=<path>` for a run rooted elsewhere, and `?defer=true` to restore
without advancing.

---

## Where output goes — one isolated folder per run

Every `build` run is **self-contained** under `runs/`:

```
<workspace>\runs\<date>-<slug>\
    domain-knowledge\background-information.md   <- your request, written here
    docs\   src\   tests\   logs\                <- generated, phase by phase
    .anvil\                                       <- run state / checkpoints
```

e.g. `workspace\runs\2026-06-26-build-a-cli-that-converts-usd-to-cents\`. This
isolation means a fresh prompt is never overridden by unrelated files elsewhere, and
runs never collide. `runs/` is gitignored (disposable) — copy a project out to keep it.

### Phase-aware model routing

By default phases route by tier (override per category with the env vars):

| Phase group | Default model | Env override |
|---|---|---|
| Planning / design / intake (intake, proposal, spec, architecture, blueprint, plan) | `google/gemma-4-31b-it` | `ANVIL_PLANNING_MODEL` |
| Coding (implementation, qa) | `deepseek/deepseek-v4-flash` | `ANVIL_CODING_MODEL` |
| All phases (single model) | — | `ANVIL_MODEL` |

Other env knobs: `ANVIL_INPUT_CHAR_LIMIT` — per-file character cap when phase
inputs are assembled into prompts (default 20,000; truncation emits an
`InputTruncated` warning event, never silent). Output-side completion budgets
(v0.1.3 #19): `ANVIL_INTAKE_MAX_TOKENS` (default 400), `ANVIL_DOC_MAX_TOKENS`
(default 1,500), `ANVIL_CODE_MAX_TOKENS` (default 4,000) — raise these for
large tasks; a too-small budget fails the phase with `finish_reason=length`
after retries rather than shipping a truncated artifact.
`ANVIL_CONTRACT_MAX_CHARS` (default 16,000) — hard cap on the task-contract
block (see below); an over-cap contract fails the run at intake rather than
ever being clipped. `ANVIL_TEMPERATURE` — pinned sampling temperature for
all completions (unset = provider default; useful for experiments, measured
not to reduce run-to-run variance).

### Verify what was built — the repair loop (v0.1.4)

Set `ANVIL_TEST_COMMAND` (or config `externalTestCommand`) to a command that
verifies the generated project (e.g. `python -m pytest tests -q`). After the
implementation phase, Anvil syntax-checks the generated files, runs your
command in the run workspace, and on failure repairs ONLY the implicated
files (one completion each, failure output in the prompt), re-checks the
task contract, and re-runs — up to `ANVIL_REPAIR_MAX_ROUNDS` (default 2)
rounds, bounded by `ANVIL_TEST_TIMEOUT_S` (default 600). Rounds exhausted
red → the phase fails with the test output in the failure record.

- **Opt-in**: no command → no execution, ever (pre-v0.1.4 behavior).
- **Security**: the command runs unsandboxed in the run workspace, so it is
  honored only for runs with `security_profile: open` — any other profile
  fails at intake with a clear reason rather than silently skipping
  verification.

Long implementation phases now also advance **one artifact per `/advance`**
(with `PhaseProgress` events on the SSE stream), and mid-phase progress is
checkpointed — a restart resumes from the last generated file.

### Task contracts — pin the facts that must survive (v0.1.3)

Large or interface-precise tasks can mark a **contract** section in
`background-information.md`:

```markdown
# My task

<!-- anvil:contract -->
(binding facts: file names, signatures, formats — injected VERBATIM into
 every phase prompt, never truncated, never paraphrased)
<!-- anvil:context -->
(background prose, docs, examples — summarizable; read by intake/proposal only)
```

- The contract block travels verbatim to **every** phase, so pinned names and
  signatures cannot drift in the phase-to-phase retelling. A file without
  markers behaves exactly as before (all context, nothing pinned).
- Intake clarification answers and recorded assumptions are appended *into*
  the contract block; when intake finishes, the block is **sealed**
  (`ContractSealed` event) and later writes are rejected.
- The contract may embed a fenced ```` ```contract-manifest ```` JSON block
  (`{"files": [...], "symbols": [{"qualname", "signature", "file"}]}`, paths
  relative to `src/`). After implementation, Anvil AST-checks the generated
  code against it — a missing file/symbol or changed signature fails the
  phase into the normal retry path, with the offender named.
- When the manifest (or the plan) names the output files, the implementation
  phase generates **one completion per file** — each under
  `ANVIL_CODE_MAX_TOKENS`, with per-file usage on the event stream — and if a
  target file already exists (a stub or skeleton), its current source is
  included in that file's prompt to be completed in place, not regenerated
  blind.

### Complexity gating — simple tasks stay lean

The proposal phase assesses the task's complexity and the supervisor runs only what's
needed:

- **simple** → intake → proposal → spec → architecture → blueprint → plan →
  implementation (5 canonical docs + `src/`). **No tests/packaging/deployment** —
  that's expected for a trivial tool, not a bug.
- **standard** → the above **+ qa** (tests).
- **complex** → all 13 phases.

### Intake — completeness check before anything is built

Every run starts with a small **intake** step that checks whether
`background-information.md` says enough to build from:

- **Interactive runs (`gated`/`secure` — including `@anvil build`)**: if
  information is missing, the run pauses with up to 5 questions — answer with
  `@anvil answer <a1>; <a2>; …` (or `POST /v1/runs/<id>/clarify`). Answers are
  appended to the run's `background-information.md` under `## Clarifications`,
  and intake re-checks **once** (never a second pause). A complete request
  never pauses at all.
- **Autonomous runs (`yolo`, e.g. REST with `"mode":"yolo"`)**: never pause.
  Gaps are filled from `anvil-instructions.md` defaults and recorded in the
  file under `## Assumptions`, so you can always see what was assumed.

### Standing instructions — `anvil-instructions.md`

Anvil's equivalent of `copilot-instructions.md`: defaults for underspecified
inputs, fallbacks, and conventions, injected into **every** phase prompt.
Resolution precedence: `<run>/domain-knowledge/anvil-instructions.md` →
`<workspace root>/anvil-instructions.md` → none. A file sitting next to a
`build`-from-file source travels with the run. The better this file, the fewer
questions intake asks.

Want tests on a small project? Describe it richer (e.g. "…with a CLI, validation, and
a pytest suite") so it's rated standard/complex.

### Failure records

If a phase fails (even one later recovered by retry), Anvil writes a Markdown
failure record to `<run>\docs\failure_records\FR-<NNN>-<slug>.md` with the run id,
phase, reason, and recent events.

### Audit trail

`<run>\logs\events.jsonl` (one JSON event per line, secrets redacted) and a
human-readable `<run>\logs\run-summary.log`.

### OKF artifacts

Generated markdown artifacts follow Google's **Open Knowledge Format** (OKF
v0.1): YAML frontmatter with `type`, `title`, `description`, `tags`,
`timestamp` plus Anvil's lineage fields, and a generated `docs/index.md`
listing every artifact — so other agents/tools can consume a run's docs
directly.

---

## Run the code Anvil produced

The generated project is plain source under the run's `src/`:

```powershell
cd C:\path\to\openhands_based_coding_team\workspace\runs\<date>-<slug>\src
python <entrypoint>.py <args>
```

---

## Troubleshooting

- **`@anvil` says "fetch failed"** → the server (Step 1) isn't running, or not on port 8765.
- **No second window on F5** → make sure the **`extension`** folder is the one open (not the repo root); reload after editing `launch.json`.
- **No Chat view / `@anvil` missing** → install GitHub Copilot Chat, reload.
- **npm fails with a PowerShell security error** → run the `Set-ExecutionPolicy` line above once.
- **Real mode won't start** → it needs `OPENROUTER_API_KEY`; set it, or use `-Mode offline-llm`.
- **A model error from OpenRouter** → the slug isn't available to your account; override with `ANVIL_PLANNING_MODEL` / `ANVIL_CODING_MODEL`.
- **No tests in the output** → the task was rated *simple* (see complexity gating); describe it richer to include qa.
- **Output is generic** → give a *specific* `build` description; a vague task yields a vague (but well-structured) skeleton.
