#!/usr/bin/env bash
# wait-order-costs.sh - poll a v2 order until its costs are calculated.
#
# Usage: wait-order-costs.sh ORDER_ID [timeout_seconds]
#   ORDER_ID          Printful order id, or @external_id
#   timeout_seconds   default 120
#
# Calls GET /v2/orders/{id} through ../../printful-api/scripts/pf.sh every
# PF_POLL_INTERVAL seconds (default 5) until costs.calculation_status is
# "done" or "failed". Prints the last order JSON on stdout.
#
# Exit codes:
#   0    calculation_status is done
#   2    calculation_status is failed (read the order for the reason)
#   124  timed out while still calculating
#   64   usage error
#   other  pf.sh exit code (1 HTTP error, 75 rate limited, 78 token missing)

set -euo pipefail

ORDER_ID="${1:-}"
TIMEOUT="${2:-120}"
INTERVAL="${PF_POLL_INTERVAL:-5}"

if [[ -z "$ORDER_ID" || ! "$TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "usage: wait-order-costs.sh ORDER_ID [timeout_seconds]" >&2
  exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PF="${SCRIPT_DIR}/../../printful-api/scripts/pf.sh"
if [[ ! -f "$PF" ]]; then
  echo "pf.sh not found at $PF" >&2
  exit 64
fi

deadline=$(( $(date +%s) + TIMEOUT ))
order_json=""

while :; do
  set +e
  order_json="$(bash "$PF" GET "/v2/orders/${ORDER_ID}")"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    [[ -n "$order_json" ]] && printf '%s\n' "$order_json"
    exit "$rc"
  fi

  calc="$(printf '%s' "$order_json" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    o=d.get("data", d) if isinstance(d, dict) else {}
    print(((o or {}).get("costs") or {}).get("calculation_status") or "unknown")
except Exception:
    print("unparseable")')"

  case "$calc" in
    done)
      printf '%s\n' "$order_json"
      exit 0
      ;;
    failed)
      printf '%s\n' "$order_json"
      echo "Order ${ORDER_ID}: cost calculation failed. Check the order items, placements and recipient." >&2
      exit 2
      ;;
  esac

  now=$(date +%s)
  if (( now + INTERVAL > deadline )); then
    printf '%s\n' "$order_json"
    echo "Order ${ORDER_ID}: costs still '${calc}' after ${TIMEOUT}s. Try again later." >&2
    exit 124
  fi
  echo "Order ${ORDER_ID}: calculation_status=${calc}, waiting ${INTERVAL}s" >&2
  sleep "$INTERVAL"
done
