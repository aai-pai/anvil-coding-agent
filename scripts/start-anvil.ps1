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
    [string]$Model = "deepseek/deepseek-chat"
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path

if ($Mode -eq "real" -and -not $env:OPENROUTER_API_KEY) {
    Write-Error "Real mode needs an API key. Run:  `$env:OPENROUTER_API_KEY = 'sk-or-...'  (or use -Mode offline-llm)"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
$env:ANVIL_EXECUTION_MODE = $Mode
$env:ANVIL_MODEL = $Model
$env:PYTHONPATH = "$repo\runtime"
Set-Location $Workspace

Write-Host "Anvil runtime -> http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "  mode=$Mode  model=$Model  workspace=$Workspace" -ForegroundColor DarkGray
Write-Host "  (leave this window open; press Ctrl+C to stop)`n" -ForegroundColor DarkGray
python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port $Port
