#!/usr/bin/env bash
# Stop detached local Docker dev stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env.local ]]; then
  docker compose --env-file .env.local down "$@" 2>/dev/null || \
    docker compose down "$@" 2>/dev/null || true
else
  docker compose down "$@" 2>/dev/null || true
fi

echo "Docker dev stack stopped."
