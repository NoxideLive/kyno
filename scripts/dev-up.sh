#!/usr/bin/env bash
# Start local Docker dev stack detached (vite + optional phi).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/dev-init.sh" --no-hint

echo ""
echo "Docker stack running detached."
echo "  Stop:  ./scripts/dev-down.sh"
echo "  Logs:  docker compose --env-file .env.local logs -f vite"
echo ""
echo "Start Convex separately: npx convex dev --env-file .env.local"
