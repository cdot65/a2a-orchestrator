#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env if present
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

pids=()
cleanup() {
  echo "Stopping agents..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait
}
trap cleanup INT TERM EXIT

echo "Starting recipe-url on :${RECIPE_URL_PORT:-8001}"
uv run python -m a2a_orchestrator.recipe_url &
pids+=($!)

echo "Starting recipe-gen on :${RECIPE_GEN_PORT:-8002}"
uv run python -m a2a_orchestrator.recipe_gen &
pids+=($!)

echo "Starting shell on :${SHELL_PORT:-8003} (requires Docker)"
uv run python -m a2a_orchestrator.shell &
pids+=($!)

# Give specialists ~1s to open ports before orchestrator runs discovery
sleep 1

echo "Starting orchestrator on :${ORCHESTRATOR_PORT:-8000}"
uv run python -m a2a_orchestrator.orchestrator &
pids+=($!)

echo
echo "All agents launched. Ctrl-C to stop."
wait
