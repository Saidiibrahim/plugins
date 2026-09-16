#!/usr/bin/env bash
# pf.sh - thin wrapper around the Printful REST API (v1 and v2).
#
# Usage:
#   pf.sh GET    /v2/catalog-products/71
#   pf.sh GET    "/v2/orders?limit=20"
#   pf.sh POST   /v2/orders @/path/to/body.json
#   pf.sh PATCH  /v2/orders/123 '{"recipient":{"name":"Jane"}}'
#   pf.sh GET    /store/products              # v1 (no /v2/ prefix)
#   PF_CONFIRM=yes pf.sh POST /v2/orders/123/confirmation
#
# The API version is chosen by the path: paths starting with /v2/ are v2,
# everything else is v1.
#
# Guarded calls: requests that spend money or cannot be undone are refused
# unless PF_CONFIRM=yes is set for that single command. Set it only after the
# user has explicitly approved the specific action. Guarded calls are:
#   POST   /v2/orders/{id}/confirmation   (charges the billing method)
#   POST   /orders/{id}/confirm            (v1, charges the billing method)
#   POST   /orders?confirm=...             (v1 create-and-confirm)
#   PUT    /orders/{id}?confirm=...        (v1 update-and-confirm)
#   DELETE /orders/{id}                    (v1: CANCELS the order)
#   DELETE /v2/orders/{id}                 (v2: DELETES a draft/failed/canceled order)
#   DELETE /store/products/..., /store/variants/..., /sync/..., /product-templates/...
#
# Environment:
#   PRINTFUL_API_TOKEN   required - private token from https://developers.printful.com
#   PRINTFUL_STORE_ID    optional - required only for account-level tokens (sent as X-PF-Store-Id)
#   PRINTFUL_API_BASE    optional - defaults to https://api.printful.com
#   PF_CONFIRM           optional - "yes" to allow one guarded call
#   PF_NO_RETRY          optional - "1" to disable the single automatic retry on 429
#
# Output: the raw JSON response body on stdout. On failure a one-line summary
# of the error goes to stderr and the exit code is non-zero:
#   1  HTTP error (4xx/5xx)       64 usage error
#   75 rate limited (after retry) 77 guarded call without PF_CONFIRM=yes
#   78 PRINTFUL_API_TOKEN missing

set -euo pipefail

METHOD="$(printf '%s' "${1:-}" | tr '[:lower:]' '[:upper:]')"
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
# Normalise so the guard sees exactly what is sent: drop any #fragment,
# collapse repeated slashes, and refuse dot segments that curl would resolve.
ENDPOINT="${ENDPOINT%%#*}"
PATH_ONLY="${ENDPOINT%%\?*}"
QUERY="${ENDPOINT:${#PATH_ONLY}}"
PATH_ONLY="/$(printf '%s' "$PATH_ONLY" | tr -s '/' | sed 's#^/##')"
lower_path="$(printf '%s' "$PATH_ONLY" | tr '[:upper:]' '[:lower:]')"
if [[ "/${PATH_ONLY}/" == */./* || "/${PATH_ONLY}/" == */../* \
  || "$lower_path" == *%2e* || "$lower_path" == *%2f* || "$lower_path" == *%5c* ]]; then
  echo "Refusing ${METHOD} ${ENDPOINT}: dot segments or encoded '.', '/' or '\\' are not allowed in the path." >&2
  exit 64
fi
ENDPOINT="${PATH_ONLY}${QUERY}"

# --- guard money-spending and irreversible calls ----------------------------
lower_query="$(printf '%s' "$QUERY" | tr '[:upper:]' '[:lower:]')"
guarded=""
case "$METHOD" in
  POST)
    if [[ "$PATH_ONLY" =~ ^/v2/orders/[^/]+/confirmation/?$ ]] \
      || [[ "$PATH_ONLY" =~ ^/orders/[^/]+/confirm/?$ ]] \
      || { [[ "$PATH_ONLY" =~ ^/orders/?$ ]] && [[ "$lower_query" == *confirm* ]]; }; then
      guarded="confirms an order and charges the Printful billing method"
    fi
    ;;
  PUT)
    if [[ "$PATH_ONLY" =~ ^/orders/[^/]+/?$ ]] && [[ "$lower_query" == *confirm* ]]; then
      guarded="updates and confirms an order, charging the Printful billing method"
    fi
    ;;
  DELETE)
    if [[ "$PATH_ONLY" =~ ^/v2/orders/[^/]+/?$ ]]; then
      guarded="permanently deletes the v2 order"
    elif [[ "$PATH_ONLY" =~ ^/orders/[^/]+/?$ ]]; then
      guarded="cancels the order (v1 DELETE means cancel)"
    elif [[ "$PATH_ONLY" =~ ^/(store/products|store/variants|sync/products|sync/variant|product-templates)/ ]]; then
      guarded="permanently deletes a product, variant or template"
    fi
    ;;
esac

if [[ -n "$guarded" && "${PF_CONFIRM:-}" != "yes" ]]; then
  echo "Refusing ${METHOD} ${ENDPOINT}: this ${guarded}." >&2
  echo "Get explicit approval from the user, then re-run with PF_CONFIRM=yes for this one command." >&2
  exit 77
fi

# --- request ----------------------------------------------------------------
headers_file="$(mktemp)"
trap 'rm -f "$headers_file"' EXIT

do_request() {
  local args=(
    -sS
    -X "$METHOD"
    -D "$headers_file"
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
  curl "${args[@]}" "${BASE}${ENDPOINT}"
}

header_value() {
  # case-insensitive header lookup from the last response
  grep -i "^$1:" "$headers_file" | tail -n 1 | cut -d: -f2- | tr -d ' \r' || true
}

response="$(do_request)"
status="${response##*$'\n'}"

if [[ "$status" == "429" && "${PF_NO_RETRY:-}" != "1" ]]; then
  # v2 sends Retry-After / X-Ratelimit-Reset (seconds); v1 locks out for 60 s.
  wait="$(header_value retry-after)"
  [[ -z "$wait" ]] && wait="$(header_value x-ratelimit-reset)"
  wait="$(python3 -c 'import math,sys
try: print(min(60, max(1, math.ceil(float(sys.argv[1])))))
except Exception: print(60)' "${wait:-60}")"
  echo "Rate limited (429). Waiting ${wait}s and retrying once." >&2
  sleep "$wait"
  response="$(do_request)"
  status="${response##*$'\n'}"
fi

payload="${response%$'\n'*}"
printf '%s\n' "$payload"

if [[ "$status" == "429" ]]; then
  echo "Rate limited (429) again on ${METHOD} ${ENDPOINT}. Stop and retry later." >&2
  exit 75
fi

if [[ "$status" -lt 200 || "$status" -ge 300 ]]; then
  # Summarise the error for both envelopes:
  #   v1:            {"code":400,"result":"...","error":{"reason":"...","message":"..."}}
  #   v2 (RFC 9457): {"type":"...","status":400,"title":"...","detail":"...","invalid_params"?...}
  #   v2 legacy:     {"error":{"message":"..."}} on orders/catalog/webhook endpoints
  summary="$(printf '%s' "$payload" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print("non-JSON response"); sys.exit()
parts=[]
err=d.get("error") if isinstance(d,dict) else None
if isinstance(err,dict):
    parts.append(err.get("message") or err.get("reason") or "")
elif isinstance(err,str):
    parts.append(err)
for k in ("title","detail"):
    if isinstance(d,dict) and d.get(k): parts.append(str(d[k]))
if isinstance(d,dict) and isinstance(d.get("result"),str) and not parts:
    parts.append(d["result"])
print(" - ".join(p for p in parts if p) or "see response body")' 2>/dev/null || echo "see response body")"
  echo "HTTP ${status} from ${METHOD} ${ENDPOINT}: ${summary}" >&2
  exit 1
fi
