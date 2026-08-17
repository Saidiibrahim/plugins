#!/usr/bin/env bash
# Download a video for local frame extraction, working around YouTube's gate.
#
#   fetch-video.sh <URL> [OUTDIR] [MAX_HEIGHT]
#
# Prints the path to the downloaded mp4 on stdout.
#
# THE PROBLEM THIS SOLVES (all three failures are real and sequential):
#   1. plain `yt-dlp -f ...`                     -> HTTP 403 Forbidden
#      YouTube requires solving a JS challenge to decipher the stream URL.
#   2. adding only `--js-runtimes deno:...`      -> still HTTP 403
#      The chosen formats also require TLS impersonation.
#   3. forcing `--extractor-args player_client=ios,tv`
#                                                -> "This video is DRM protected"
#      Do NOT pin a player client; let yt-dlp choose once curl_cffi is present.
#
# The fix is a yt-dlp built with curl_cffi (TLS impersonation) PLUS a JS
# runtime. Homebrew's yt-dlp ships without curl_cffi, so this script builds a
# cached venv on first use and leaves the user's global install untouched.
set -euo pipefail

URL="${1:?usage: fetch-video.sh <URL> [OUTDIR] [MAX_HEIGHT]}"
OUTDIR="${2:-.}"
MAXH="${3:-720}"
mkdir -p "$OUTDIR"
OUT="$OUTDIR/video.mp4"
URLFILE="$OUTDIR/video.url"

# --- cache: only reuse when the existing file came from THIS url ---
# Keying on the filename alone silently hands back the previous lesson's video,
# and every frame published from it is then wrong evidence for the new lesson.
if [ -f "$OUT" ]; then
  if [ -f "$URLFILE" ] && [ "$(cat "$URLFILE")" = "$URL" ]; then
    echo "$OUT"; exit 0
  fi
  echo "note: $OUT exists but is from a different (or unrecorded) URL; re-downloading" >&2
  rm -f "$OUT"
fi

command -v ffmpeg >/dev/null || { echo "ffmpeg not found. brew install ffmpeg" >&2; exit 1; }

# --- locate a JS runtime (deno is often installed but not on yt-dlp's PATH) ---
JS_ARGS=()
for cand in "$(command -v deno || true)" "$HOME/.deno/bin/deno" \
            "$(command -v node || true)" "$(command -v bun || true)"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then
    JS_ARGS=(--js-runtimes "$(basename "$cand"):$cand")
    break
  fi
done
# NOTE: bash 3.2 (macOS stock) treats "${arr[@]}" on an EMPTY array as an
# unbound variable under `set -u`, so every expansion below uses the
# "${arr[@]+...}" guard. Without it this script dies here instead of trying.
[ ${#JS_ARGS[@]} -gt 0 ] || echo "warn: no JS runtime found; download may 403" >&2

# --- pick a yt-dlp that has curl_cffi ---
SYS_PY=()
if command -v yt-dlp >/dev/null; then
  # A console-script shebang may be multi-token (`#!/usr/bin/env python3`),
  # so read it as an argv array rather than a single executable path.
  IFS=' ' read -r -a SYS_PY < <(head -1 "$(command -v yt-dlp)" | sed 's|^#!||')
fi
have_cffi() {
  [ ${#SYS_PY[@]} -gt 0 ] || return 1
  "${SYS_PY[@]+"${SYS_PY[@]}"}" -c 'import curl_cffi' 2>/dev/null
}

if have_cffi; then
  YTDLP="$(command -v yt-dlp)"
else
  # Cache the venv outside OUTDIR: OUTDIR is per-lesson scratch, and building a
  # fresh CPython + 18 packages for every lesson is pure waste. Putting it in
  # OUTDIR also collides with any existing .venv, which `uv venv` refuses.
  VENV="${DESIGN_SCHOOL_VENV:-${XDG_CACHE_HOME:-$HOME/.cache}/design-school/ytdlp-venv}"
  if [ ! -x "$VENV/bin/yt-dlp" ]; then
    command -v uv >/dev/null || { echo "uv not found (needed for the curl_cffi build). https://docs.astral.sh/uv/" >&2; exit 1; }
    echo "Building a cached yt-dlp with curl_cffi in $VENV (first run only) ..." >&2
    mkdir -p "$(dirname "$VENV")"
    uv venv "$VENV" --python 3.12 >&2
    uv pip install --python "$VENV/bin/python" "yt-dlp[default,curl-cffi]" >&2
  fi
  YTDLP="$VENV/bin/yt-dlp"
fi

"$YTDLP" "${JS_ARGS[@]+"${JS_ARGS[@]}"}" \
  -f "bv*[height<=$MAXH]+ba/b[height<=$MAXH]" \
  --merge-output-format mp4 -o "$OUT" "$URL" >&2

[ -f "$OUT" ] || { echo "Download failed — see yt-dlp output above." >&2; exit 1; }
printf '%s' "$URL" > "$URLFILE"
echo "$OUT"
