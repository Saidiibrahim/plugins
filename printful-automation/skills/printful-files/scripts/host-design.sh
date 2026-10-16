#!/usr/bin/env bash
# Upload a local design to the configured public host and print its public URL.
#
# Usage: host-design.sh FILE [--key KEY] [--dry-run] [--no-verify]
#
# Reads design_hosting from ${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}:
#   { "provider": "r2", "public_base_url": "https://pub-xxxx.r2.dev", "bucket": "merch-designs" }
#
# provider "r2":
#   - If aws CLI is installed and R2_ACCOUNT_ID, AWS_ACCESS_KEY_ID and
#     AWS_SECRET_ACCESS_KEY are set, uploads through the S3-compatible API.
#   - Otherwise uses `wrangler r2 object put --remote` (needs `wrangler login`
#     or CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID).
# any other provider: prints what to upload and exits 3 (upload it yourself,
#   then use public_base_url/KEY).
#
# Default key: designs/<YYYYMMDD>-<sha256 first 8>-<sanitised filename>
# The hash makes a changed file get a new URL (Printful and CDNs cache by URL).
#
# stdout: the public URL. Exit: 0 ok, 1 upload/verify failed, 2 usage/config,
# 3 manual upload needed.
set -euo pipefail

die() { echo "host-design: $*" >&2; exit "${2:-2}"; }

FILE="" KEY="" DRY=0 VERIFY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --key) KEY="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --no-verify) VERIFY=0; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) [ -z "$FILE" ] || die "only one file at a time"; FILE="$1"; shift ;;
  esac
done
[ -n "$FILE" ] || die "usage: host-design.sh FILE [--key KEY] [--dry-run] [--no-verify]"
[ -f "$FILE" ] || die "no such file: $FILE"

CONFIG="${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}"
[ -f "$CONFIG" ] || die "config not found at $CONFIG (see printful-api skill, Local config)"

read_cfg() {
  python3 - "$CONFIG" "$1" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
v = (cfg.get("design_hosting") or {}).get(sys.argv[2], "")
print(v if v is not None else "")
PY
}
PROVIDER="$(read_cfg provider)"
BASE="$(read_cfg public_base_url)"
BUCKET="$(read_cfg bucket)"
BASE="${BASE%/}"
[ -n "$BASE" ] || die "design_hosting.public_base_url is not set in $CONFIG"
case "$BASE" in https://*) ;; *) die "public_base_url must be https" ;; esac

# Set safe cache directory for wrangler to avoid /node_modules/.cache/wrangler write errors
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$XDG_CACHE_HOME/wrangler" 2>/dev/null || true

NAME="$(basename "$FILE")"
if [ -z "$KEY" ]; then
  SAFE="$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/-+/-/g; s/-\./\./g; s/^-//')"
  if command -v sha256sum >/dev/null 2>&1; then HASH="$(sha256sum "$FILE" | cut -c1-8)"
  else HASH="$(shasum -a 256 "$FILE" | cut -c1-8)"; fi
  KEY="designs/$(date +%Y%m%d)-${HASH}-${SAFE}"
fi
KEY="${KEY#/}"

case "$NAME" in
  *.png|*.PNG) CTYPE="image/png" ;;
  *.jpg|*.jpeg|*.JPG|*.JPEG) CTYPE="image/jpeg" ;;
  *) CTYPE="application/octet-stream" ;;
esac

URL="$BASE/$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$KEY")"

if [ "$PROVIDER" != "r2" ]; then
  echo "host-design: provider '$PROVIDER' has no automatic upload." >&2
  echo "Upload $FILE so it is publicly reachable at: $URL" >&2
  echo "$URL"
  exit 3
fi
[ -n "$BUCKET" ] || die "design_hosting.bucket is not set in $CONFIG"

if command -v aws >/dev/null 2>&1 && [ -n "${R2_ACCOUNT_ID:-}" ] \
   && [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
  CMD=(aws s3 cp "$FILE" "s3://$BUCKET/$KEY" --content-type "$CTYPE"
       --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com" --region auto)
elif [ -x "./node_modules/.bin/wrangler" ]; then
  CMD=(./node_modules/.bin/wrangler r2 object put "$BUCKET/$KEY" --file "$FILE" --content-type "$CTYPE" --remote)
elif command -v wrangler >/dev/null 2>&1; then
  CMD=(wrangler r2 object put "$BUCKET/$KEY" --file "$FILE" --content-type "$CTYPE" --remote)
elif command -v npx >/dev/null 2>&1; then
  CMD=(npx --yes wrangler r2 object put "$BUCKET/$KEY" --file "$FILE" --content-type "$CTYPE" --remote)
else
  die "neither aws CLI (with R2 credentials) nor wrangler is available"
fi

if [ "$DRY" = 1 ]; then
  printf 'would run:' >&2; printf ' %q' "${CMD[@]}" >&2; echo >&2
  echo "$URL"
  exit 0
fi

"${CMD[@]}" >&2 || die "upload failed" 1

if [ "$VERIFY" = 1 ]; then
  STATUS="$(curl -s -o /dev/null -w '%{http_code}' -I "$URL" || true)"
  [ "$STATUS" = "200" ] || die "uploaded, but $URL returned HTTP $STATUS (is public access enabled on the bucket?)" 1
fi
echo "$URL"
