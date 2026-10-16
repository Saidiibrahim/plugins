#!/usr/bin/env bash
# End-to-end test: runs the Worker locally (cf dev --mode mock) against a
# Printful stand-in and walks the whole OAuth sign-in and MCP tool flow.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOG="$(mktemp)"
DEV_LOG="$(mktemp)"

# The mock's client secret, for "Sign in with Printful". Never touches a .dev.vars you already have.
if [[ ! -e "$ROOT/.dev.vars" ]]; then
  printf 'PRINTFUL_CLIENT_SECRET=mock-secret\n' >"$ROOT/.dev.vars"
  CREATED_DEV_VARS=1
fi

python3 -I "$HERE/mock_printful.py" "$LOG" &
MOCK_PID=$!
(cd "$ROOT" && exec npx cf dev --mode mock >"$DEV_LOG" 2>&1) &
DEV_PID=$!
cleanup() {
  kill "$MOCK_PID" "$DEV_PID" 2>/dev/null || true
  rm -f "$LOG" "$DEV_LOG"
  [[ -n "${CREATED_DEV_VARS:-}" ]] && rm -f "$ROOT/.dev.vars"
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -sf -o /dev/null http://localhost:5173/ && break
  sleep 1
done

python3 -I "$HERE/e2e.py" http://localhost:5173 "$LOG"
