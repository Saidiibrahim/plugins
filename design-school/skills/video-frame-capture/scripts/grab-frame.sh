#!/usr/bin/env bash
# Extract ONE frame accurately, or stack two frames into a before/after image.
#
#   grab-frame.sh <video.mp4> <SECONDS> <out.jpg>
#   grab-frame.sh --pair <before.jpg> <after.jpg> <out.jpg> [WIDTH]
#
# SEEK NOTE: `-ss T -i file` IS frame-accurate in modern ffmpeg, because
# `accurate_seek` is on by default — verified against a lossless counter video
# with 30s keyframe spacing, where mid-GOP targets decoded exactly. It is only
# inaccurate with `-noaccurate_seek` or `-c copy`.
#
# This script still uses the coarse-then-fine form below as belt-and-braces
# (it is also faster than a plain output seek on long files):
#
#     ffmpeg -ss $((T-10)) -i file -ss 10 -frames:v 1 out.jpg
#
# If a frame looks wrong, suspect the TIMESTAMP, not the seek. See the skill's
# note on `fps=1/STEP` contact sheets landing mid-interval.
set -euo pipefail

if [ "${1:-}" = "--pair" ]; then
  BEFORE="${2:?before.jpg}"; AFTER="${3:?after.jpg}"; OUT="${4:?out.jpg}"; W="${5:-1600}"
  ffmpeg -v error -i "$BEFORE" -i "$AFTER" \
    -filter_complex "[0][1]hstack=2,scale=$W:-1" -frames:v 1 "$OUT" -y
  echo "$OUT"; exit 0
fi

VIDEO="${1:?usage: grab-frame.sh <video.mp4> <SECONDS> <out.jpg>}"
T="${2:?seconds required}"
OUT="${3:?output path required}"

# Whole seconds only. "1:30" and zero-padded "09" both break the arithmetic
# below with a raw bash error; convert mm:ss to seconds before calling.
case "$T" in ''|*[!0-9]*)
  echo "SECONDS must be whole seconds, not '$T' (convert mm:ss first)" >&2; exit 1 ;;
esac
T=$((10#$T))

PRE=$(( T > 10 ? T - 10 : 0 ))
OFF=$(( T - PRE ))

ffmpeg -v error -ss "$PRE" -i "$VIDEO" -ss "$OFF" -frames:v 1 -q:v 3 "$OUT" -y
echo "$OUT"
