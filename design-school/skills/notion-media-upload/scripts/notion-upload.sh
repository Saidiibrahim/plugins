#!/usr/bin/env bash
# POST one local file to a Notion upload slot and print its markdown source.
#
#   notion-upload.sh <UPLOAD_URL> <BEARER_TOKEN> <FILE> [MIME]
#
# This is step 2 of Notion's two-step upload. Step 1 is an MCP tool call that
# Claude makes (notion-create-file-upload), which returns upload_url and an
# authorization header. This script just pushes the bytes, because curl handles
# multipart uploads and the MCP layer does not.
#
# Prints:  file-upload://<id>   <- paste straight into page markdown as
#                                  ![Caption](file-upload://<id>)
set -euo pipefail

URL="${1:?usage: notion-upload.sh <UPLOAD_URL> <BEARER_TOKEN> <FILE> [MIME]}"
TOKEN="${2:?bearer token required}"
FILE="${3:?file path required}"
MIME="${4:-}"

[ -f "$FILE" ] || { echo "No such file: $FILE" >&2; exit 1; }

# Notion's single-part upload tops out at 20 MiB.
SIZE=$(wc -c < "$FILE" | tr -d ' ')
if [ "$SIZE" -gt 20971520 ]; then
  echo "File is ${SIZE} bytes; the single-part flow caps at 20 MiB." >&2
  exit 1
fi

if [ -z "$MIME" ]; then
  case "${FILE##*.}" in
    jpg|jpeg) MIME="image/jpeg" ;;
    png)      MIME="image/png"  ;;
    gif)      MIME="image/gif"  ;;
    webp)     MIME="image/webp" ;;
    mp4)      MIME="video/mp4"  ;;
    pdf)      MIME="application/pdf" ;;
    *)        MIME="application/octet-stream" ;;
  esac
fi

# The token goes in via --config on stdin, not argv, so it does not appear in
# `ps` for the life of the request. (Exposure is small — the slot is single-use
# and expires in ~1h — but it costs nothing to avoid.)
#
# The @path is quoted because curl treats a comma as its multi-file separator
# and a semicolon as a parameter separator; an unquoted path containing either
# fails with an opaque "Failed to open/read local data" naming no file.
RESP=$(printf 'header = "authorization: Bearer %s"\n' "$TOKEN" \
  | curl -sS --config - -X POST "$URL" \
      -F "file=@\"${FILE}\";type=${MIME}")

python3 - "$RESP" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit("Upload response was not JSON:\n" + sys.argv[1])
if d.get("status") != "uploaded":
    sys.exit("Upload did not complete:\n" + json.dumps(d, indent=2))
print(d["markdown_source"])
PY
