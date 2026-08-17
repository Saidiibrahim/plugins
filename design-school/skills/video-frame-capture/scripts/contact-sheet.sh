#!/usr/bin/env bash
# Build a contact sheet so you can SEE which second holds the shot you want.
#
#   contact-sheet.sh <video.mp4> <START_SEC> [SPAN_SEC] [STEP_SEC] [COLS] [OUT]
#
# Defaults: SPAN=240 STEP=10 COLS=4  -> a 4x6 grid covering four minutes.
#
# ALWAYS do this before extracting frames. Someone talking about a screen and
# the cut to that screen are routinely 10-30s apart, so timestamps guessed from
# the transcript land on a talking head. One sheet finds every usable frame.
#
# Read the grid left-to-right, top-to-bottom. Cell times are EXACT:
#     time_of_cell(i) = START + i * STEP        (i starts at 0)
#
# Implementation note: this extracts each cell as an individually seeked frame
# and then tiles them, rather than using ffmpeg's `fps=1/STEP` filter. The fps
# filter samples near the MIDDLE of each interval, which offsets every cell by
# ~STEP/2 and makes the formula above wrong — a good way to pick the wrong
# frame. Exactness matters more here than the extra second of runtime.
#
# Many ffmpeg builds (incl. Homebrew's default) have NO drawtext filter, so
# cells cannot be labelled. Compute times from position using the formula.
set -euo pipefail

VIDEO="${1:?usage: contact-sheet.sh <video.mp4> <START_SEC> [SPAN] [STEP] [COLS] [OUT]}"
START="${2:?start second required}"
SPAN="${3:-240}"
STEP="${4:-10}"
COLS="${5:-4}"
OUT="${6:-sheet_${START}.jpg}"

# Validate up front. A zero-padded START (e.g. "09" copied from an [09:30]
# transcript marker) is parsed as octal and blows up in the arithmetic below,
# and STEP=0 divides by zero — both previously surfaced as the misleading
# "No frames extracted" message.
for pair in "START:$START" "SPAN:$SPAN" "STEP:$STEP" "COLS:$COLS"; do
  name="${pair%%:*}"; val="${pair#*:}"
  case "$val" in ''|*[!0-9]*)
    echo "$name must be whole seconds/count with no colons or signs (got '$val')" >&2
    exit 1 ;;
  esac
done
START=$((10#$START)); SPAN=$((10#$SPAN)); STEP=$((10#$STEP)); COLS=$((10#$COLS))
[ "$STEP" -gt 0 ] || { echo "STEP must be greater than 0" >&2; exit 1; }
[ "$COLS" -gt 0 ] || { echo "COLS must be greater than 0" >&2; exit 1; }

N=$(( SPAN / STEP ))
[ "$N" -gt 0 ] || { echo "SPAN ($SPAN) must be >= STEP ($STEP)" >&2; exit 1; }
ROWS=$(( (N + COLS - 1) / COLS ))

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

i=0
while [ "$i" -lt "$N" ]; do
  T=$(( START + i * STEP ))
  PRE=$(( T > 10 ? T - 10 : 0 ))
  OFF=$(( T - PRE ))
  ffmpeg -v error -ss "$PRE" -i "$VIDEO" -ss "$OFF" -frames:v 1 \
    -vf "scale=384:-1" "$TMP/$(printf '%04d' "$i").jpg" -y 2>/dev/null || true
  i=$(( i + 1 ))
done

COUNT=$(find "$TMP" -name '*.jpg' | wc -l | tr -d ' ')
[ "$COUNT" -gt 0 ] || { echo "No frames extracted — is START beyond the video length?" >&2; exit 1; }

ffmpeg -v error -pattern_type glob -i "$TMP/*.jpg" \
  -vf "tile=${COLS}x${ROWS}" -frames:v 1 "$OUT" -y

echo "$OUT"
echo "grid ${COLS}x${ROWS}, ${COUNT} cells; cell i (0-based, L->R) = $START + i*$STEP sec" >&2
