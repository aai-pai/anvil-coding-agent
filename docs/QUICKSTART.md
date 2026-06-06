# Anvil Quickstart — using `@anvil` in VS Code

Anvil has **3 moving parts**:

1. **Runtime server** (Python) — Anvil's brain; does the phase work via OpenRouter.
2. **Extension** (TypeScript) — the `@anvil` chat participant, loaded into VS Code.
3. **VS Code Chat view** — the chat box that hosts `@anvil` (from GitHub Copilot Chat).

You only need **one API key**: an **OpenRouter** key, set on the *server*. (Copilot is just the chat window; it does no Anvil work. The model dropdown in the chat does **not** control `@anvil`.)

---

## One-time setup

```powershell
# 0. Allow local scripts (npm + the launcher need this)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 1. Install the Python runtime + dependencies
cd C:\Users\pcuser\openhands_based_coding_team
pip install -e runtime

# 2. Build the VS Code extension
cd extension
npm install
npm run build
```

3. In VS Code, install **"GitHub Copilot Chat"** (Extensions panel) if you don't
   already have a chat box.

---

## Every time you want to use Anvil

### Step 1 — Start the server (leave the window open)

```powershell
cd C:\Users\pcuser\openhands_based_coding_team
$env:OPENROUTER_API_KEY = "sk-or-..."     # your key
.\scripts\start-anvil.ps1
```

Verify: open <http://127.0.0.1:8765/v1/health> → `{"status":"ok",...}`.

No key? Use placeholder output instead: `.\scripts\start-anvil.ps1 -Mode offline-llm`.

### Step 2 — Launch the extension

1. **File → Open Folder →** `...\openhands_based_coding_team\extension`
2. Press **F5** → a second window **"[Extension Development Host]"** opens with `@anvil` loaded.

### Step 3 — Build something (plain English)

In the second window, open Chat (**Ctrl+Alt+I**) and type:

```
@anvil build a CLI tool that converts Celsius to Fahrenheit
```

The runtime writes your request to `domain-knowledge/background-information.md`,
then runs all 12 phases with the model and writes the result into the server's
**workspace** folder (default: `...\openhands_based_coding_team\workspace\`).
A real run takes ~1–2 minutes and costs a few cents.

---

## Commands `@anvil` understands

| Command | What it does |
|---|---|
| `build <description>` | Build something from plain English (autonomous) |
| `start [mode] [profile]` | Start a run from the existing domain-knowledge file |
| `status` | Show current run state |
| `approve` / `deny` | Resolve a pending approval gate (gated/secure modes) |
| `rollback <phase>` | Roll back to a phase |
| `force-advance` / `stop` | Override the supervisor |
| `health` | Check the runtime is reachable |

## Troubleshooting

- **`@anvil` says "fetch failed"** → the server (Step 1) isn't running, or not on port 8765.
- **No second window on F5** → make sure the **`extension`** folder is the one open
  (not the repo root); reload the window after editing `launch.json`.
- **No Chat view / `@anvil` missing** → install GitHub Copilot Chat, reload.
- **npm fails with a PowerShell security error** → run the `Set-ExecutionPolicy`
  line above once.
- **Output is generic** → give a *specific* `build` description; a vague task
  produces a vague (but well-structured) skeleton.
