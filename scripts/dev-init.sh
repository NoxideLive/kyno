#!/usr/bin/env bash
# Bootstrap local dev: Docker (vite + phi-gateway when GPU available).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SHOW_HINT=true
COMPOSE_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-hint) SHOW_HINT=false ;;
    *) COMPOSE_ARGS+=("$arg") ;;
  esac
done

if [[ ! -f .env.local ]]; then
  if [[ -f .env.example ]]; then
    echo "Creating .env.local from .env.example — fill in secrets before continuing."
    cp .env.example .env.local
  else
    echo "ERROR: .env.local missing and no .env.example to copy" >&2
    exit 1
  fi
  echo "Edit .env.local, then re-run: ./scripts/dev-init.sh"
  exit 1
fi

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

SERVICES=()
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  echo "GPU detected — starting vite + phi-gateway."
else
  echo "No GPU — starting vite only."
  SERVICES=(vite)
fi

echo "Starting Docker services..."
docker compose --env-file .env.local up --build -d "${SERVICES[@]}" "${COMPOSE_ARGS[@]}"

echo ""
echo "Docker up."
if $SHOW_HINT; then
  echo ""
  echo "Detached stack: ./scripts/dev-up.sh"
  echo ""
  echo "One-time if needed: npx convex login"
  echo "Convex (separate terminal): npx convex dev --env-file .env.local"
  echo ""
  echo "  App:    http://localhost:5173"
  echo "  Phi:    http://localhost:8090/health (when phi-gateway is running)"
fi
