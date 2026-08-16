# Anvil — VS Code chat participant

`@anvil` drives the local **Anvil coding factory** runtime from VS Code chat.

## Requirements

The Anvil runtime server must be running locally on `http://127.0.0.1:8765`:

```powershell
cd <repo>\openhands_based_coding_team
$env:OPENROUTER_API_KEY = "sk-or-..."
.\scripts\start-anvil.ps1
```

## Usage

Open Chat (Ctrl+Alt+I) and talk to `@anvil`:

- `@anvil build <description>` — build something from plain English
- `@anvil start [mode] [profile]` — start a run from the domain-knowledge file
- `@anvil status` — show the current run state
- `@anvil approve` / `@anvil deny` — resolve an approval gate
- `@anvil health` — check the runtime is reachable

See `RUNNING.md` in the repo root for the full setup guide.
