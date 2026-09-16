#!/usr/bin/env bash
# pf.sh - thin wrapper around the Printful REST API (v1).
#
# Usage:
#   pf.sh GET    /store/products
#   pf.sh GET    "/orders?status=pending&limit=20"
#   pf.sh POST   /orders '{"recipient":{...},"items":[...]}'
#   pf.sh POST   /orders @/path/to/body.json
#   pf.sh PUT    /store/products/123 '{...}'
#   pf.sh DELETE /orders/123
#
# Environment:
#   PRINTFUL_API_TOKEN   required - private token from https://developers.printful.com
#   PRINTFUL_STORE_ID    optional - required only for account-level tokens (sent as X-PF-Store-Id)
#   PRINTFUL_API_BASE    optional - defaults to https://api.printful.com
#
# Output: the raw JSON response body on stdout. Exit code is non-zero when the
# HTTP status is not 2xx, so callers can detect failures without parsing.

set -euo pipefail

METHOD="${1:-}"
ENDPOINT="${2:-}"
BODY="${3:-}"

if [[ -z "$METHOD" || -z "$ENDPOINT" ]]; then
  echo "usage: pf.sh METHOD /endpoint [json-body | @file]" >&2
  exit 64
fi

if [[ -z "${PRINTFUL_API_TOKEN:-}" ]]; then
  echo "PRINTFUL_API_TOKEN is not set. Create a private token at https://developers.printful.com and export it." >&2
  exit 78
fi

BASE="${PRINTFUL_API_BASE:-https://api.printful.com}"
ENDPOINT="${ENDPOINT#/}"

args=(
  -sS
  -X "$METHOD"
  -H "Authorization: Bearer ${PRINTFUL_API_TOKEN}"
  -H "Content-Type: application/json"
  -H "Accept: application/json"
  -w $'\n%{http_code}'
)

if [[ -n "${PRINTFUL_STORE_ID:-}" ]]; then
  args+=(-H "X-PF-Store-Id: ${PRINTFUL_STORE_ID}")
fi

if [[ -n "$BODY" ]]; then
  # curl reads the body from a file when it starts with @
  args+=(--data-binary "$BODY")
fi

response="$(curl "${args[@]}" "${BASE}/${ENDPOINT}")"
status="${response##*$'\n'}"
payload="${response%$'\n'*}"

printf '%s\n' "$payload"

if [[ "$status" == "429" ]]; then
  echo "Rate limited (429). Wait 60 seconds before retrying." >&2
  exit 75
fi

if [[ "$status" -lt 200 || "$status" -ge 300 ]]; then
  echo "HTTP ${status} from ${METHOD} /${ENDPOINT}" >&2
  exit 1
fi
