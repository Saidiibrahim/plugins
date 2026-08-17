#!/usr/bin/env bash
# Download auto-captions for a video and emit a clean, timestamped transcript.
#
#   fetch-transcript.sh <URL> [OUTDIR]
#
# Writes <OUTDIR>/transcript.txt  — blocks prefixed with [mm:ss]
#        <OUTDIR>/video.en*.vtt   — raw captions, kept for verification
#
# Why not the browser: YouTube's timedtext endpoint returns HTTP 200 with an
# EMPTY body under bot protection, and the on-page transcript panel is a
# virtualised, tab-switching UI. yt-dlp is faster and deterministic.
set -euo pipefail

URL="${1:?usage: fetch-transcript.sh <URL> [OUTDIR]}"
OUTDIR="${2:-.}"
mkdir -p "$OUTDIR"

command -v yt-dlp >/dev/null || { echo "yt-dlp not found. brew install yt-dlp" >&2; exit 1; }

yt-dlp --skip-download --write-auto-subs --write-subs \
  --sub-langs "en.*" --sub-format vtt \
  -o "$OUTDIR/video.%(ext)s" "$URL" >&2

# `--sub-langs "en.*"` also matches regional tags (en-US, en-GB) and machine
# translations (en-de = "English from German"). Prefer the real tracks, and do
# NOT use `ls` with several arguments — it sorts them rather than honouring the
# order given, which would pick en-de over en-orig.
shopt -s nullglob
VTT=""
for cand in "$OUTDIR"/video.en.vtt "$OUTDIR"/video.en-orig.vtt "$OUTDIR"/video.en*.vtt; do
  [ -f "$cand" ] && { VTT="$cand"; break; }
done
if [ -z "$VTT" ]; then
  echo "No English captions were produced for this video. $OUTDIR contains:" >&2
  ls -1 "$OUTDIR" >&2 || true
  exit 2
fi

python3 "$(dirname "$0")/clean_vtt.py" "$VTT" "$OUTDIR/transcript.txt"
echo "$OUTDIR/transcript.txt"
