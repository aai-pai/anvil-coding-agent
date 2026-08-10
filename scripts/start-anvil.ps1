# Starts the Anvil runtime server for the VS Code @anvil extension.
#
#   Real mode (needs your OpenRouter key):
#     $env:OPENROUTER_API_KEY = "sk-or-..."
#     .\scripts\start-anvil.ps1
#
#   Offline mode (no key, placeholder output, just proves the wiring):
#     .\scripts\start-anvil.ps1 -Mode offline-llm
#
#   Custom workspace (where Anvil writes its output) / port:
#     .\scripts\start-anvil.ps1 -Workspace C:\anvil-projects\my-app -Port 8765
param(
    [string]$Workspace = "$PSScriptRoot\..\workspace",
    [ValidateSet("real", "offline-llm", "stub")]
    [string]$Mode = "real",
    [int]$Port = 8765,
    # Leave empty to use Anvil's phase-aware defaults (Gemma 4 for planning/design,
    # DeepSeek V4 for coding). Pass -Model to force a single model for every phase.
    [string]$Model = ""
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path

if ($Mode -eq "real" -and -not $env:OPENROUTER_API_KEY) {
    Write-Error "Real mode needs an API key. Run:  `$env:OPENROUTER_API_KEY = 'sk-or-...'  (or use -Mode offline-llm)"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
$env:ANVIL_EXECUTION_MODE = $Mode
# Only force a single model when -Model is given; otherwise clear ANVIL_MODEL so the
# runtime's phase-aware defaults (Gemma 4 / DeepSeek V4) drive routing (#12).
if ($Model) { $env:ANVIL_MODEL = $Model }
else { Remove-Item Env:\ANVIL_MODEL -ErrorAction SilentlyContinue }
$env:PYTHONPATH = "$repo\runtime"
Set-Location $Workspace

$modelLabel = if ($Model) { $Model } else { "phase-aware defaults (Gemma 4 / DeepSeek V4)" }
Write-Host "Anvil runtime -> http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "  mode=$Mode  model=$modelLabel  workspace=$Workspace" -ForegroundColor DarkGray
Write-Host "  (leave this window open; press Ctrl+C to stop)`n" -ForegroundColor DarkGray
python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port $Port
