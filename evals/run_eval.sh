#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Meeting Summary AI — Prompt Evaluation ==="
echo ""

# Check that Ollama is reachable
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "ERROR: Ollama is not running at http://localhost:11434"
  echo "Start Ollama first: ollama serve"
  exit 1
fi

# Promptfoo requires OPENAI_API_KEY to be set even for Ollama
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"

CONFIGS=(
  "promptfooconfig.yaml"
  "promptfoo.tasks.yaml"
  "promptfoo.topics.yaml"
)

# Allow selecting a specific config: ./run_eval.sh summary | tasks | topics | all
TARGET="${1:-all}"

run_config() {
  local config="$1"
  echo "--- Running: $config ---"
  npx promptfoo eval -c "$config"
  echo ""
}

case "$TARGET" in
  summary)
    run_config "promptfooconfig.yaml"
    ;;
  tasks)
    run_config "promptfoo.tasks.yaml"
    ;;
  topics)
    run_config "promptfoo.topics.yaml"
    ;;
  all)
    for config in "${CONFIGS[@]}"; do
      run_config "$config"
    done
    ;;
  *)
    echo "Usage: $0 [summary|tasks|topics|all]"
    exit 1
    ;;
esac

echo "Opening results viewer..."
npx promptfoo view
