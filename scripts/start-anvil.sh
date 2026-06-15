#!/usr/bin/env bash
# Starts the Anvil runtime server for the VS Code @anvil extension.
#
# Real mode (prompts for OpenRouter key if missing):
#   ./scripts/start-anvil.sh
#
# Offline mode (no key, placeholder output):
#   ./scripts/start-anvil.sh --mode offline-llm
#
# Custom workspace / port:
#   ./scripts/start-anvil.sh --workspace /tmp/my-app --port 8765
#
# Override planning/coding models:
#   ./scripts/start-anvil.sh \
#     --planning-model "google/gemma-4-26b-a4b-it" \
#     --coding-model "deepseek/deepseek-v4-flash"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKSPACE="$REPO_ROOT/workspace"
MODE="real"
PORT="8765"
MODEL="deepseek/deepseek-chat"
PLANNING_MODEL="google/gemma-4-26b-a4b-it"
CODING_MODEL="deepseek/deepseek-v4-flash"

print_usage() {
  cat <<'EOF'
Usage: scripts/start-anvil.sh [options]

Options:
  --workspace PATH        Workspace where Anvil writes output (default: ../workspace)
  --mode MODE             One of: real, offline-llm, stub (default: real)
  --port PORT             Server port (default: 8765)
  --model MODEL           Fallback model for all subtasks (default: deepseek/deepseek-chat)
  --planning-model MODEL  Planning model override (default: google/gemma-4-26b-a4b-it)
  --coding-model MODEL    Coding model override (default: deepseek/deepseek-v4-flash)
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      WORKSPACE="${2:-}"
      shift 2
      ;;
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --model)
      MODEL="${2:-}"
      shift 2
      ;;
    --planning-model)
      PLANNING_MODEL="${2:-}"
      shift 2
      ;;
    --coding-model)
      CODING_MODEL="${2:-}"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "real" && "$MODE" != "offline-llm" && "$MODE" != "stub" ]]; then
  echo "Invalid --mode '$MODE'. Expected one of: real, offline-llm, stub." >&2
  exit 2
fi

if [[ "$MODE" == "real" && -z "${OPENROUTER_API_KEY:-}" ]]; then
  read -r -s -p "OpenRouter API key: " OPENROUTER_API_KEY
  echo ""
  export OPENROUTER_API_KEY
fi

mkdir -p "$WORKSPACE"

export ANVIL_EXECUTION_MODE="$MODE"
export ANVIL_MODEL="$MODEL"
export ANVIL_PLANNING_MODEL="$PLANNING_MODEL"
export ANVIL_CODING_MODEL="$CODING_MODEL"
export PYTHONPATH="$REPO_ROOT/runtime"

cd "$WORKSPACE"

echo "Anvil runtime -> http://127.0.0.1:${PORT}"
echo "  mode=${MODE}  model=${MODEL}  planning=${PLANNING_MODEL}  coding=${CODING_MODEL}  workspace=${WORKSPACE}"
echo "  (leave this window open; press Ctrl+C to stop)"
echo ""

python -m uvicorn anvil_runtime.app:app --host 127.0.0.1 --port "$PORT"
