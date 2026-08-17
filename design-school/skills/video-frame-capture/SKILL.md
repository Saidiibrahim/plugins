---
name: video-frame-capture
description: This skill should be used when the user wants a transcript of a video, screenshots or stills pulled from a video, before/after frames from a demo or screencast, or asks to "watch"/"take notes on" a YouTube video. It covers downloading captions and video with yt-dlp (including the HTTP 403 and DRM workarounds), locating the right moment with ffmpeg contact sheets, and extracting frame-accurate stills.
version: 1.0.0
---

# Video Frame Capture

Getting text and images out of a video reliably. The headline rule: **do this
locally with `yt-dlp` and `ffmpeg`, not through a browser.**

## Why not the browser

Every browser route fails in a way that wastes time:

- YouTube's `timedtext` caption endpoint returns **HTTP 200 with an empty body**
  under bot protection.
- The on-page transcript panel is a virtualised, tab-switching UI that needs
  several clicks and still holds only part of the text.
- MCP JavaScript results truncate near ~1.5 KB, so bulk text cannot come back
  through the browser anyway.
- `navigator.clipboard.writeText` hangs as an escape hatch.
- Worst of all, an **occluded or backgrounded browser window reports
  `document.hidden: true`** and the video element never renders — every
  screenshot is the poster image. On macOS this cannot be fixed without
  assistive-access permission for `osascript`.

Skip all of it.

## 1. Transcript

```bash
${CLAUDE_PLUGIN_ROOT}/skills/video-frame-capture/scripts/fetch-transcript.sh <URL> <OUTDIR>
```

Produces `transcript.txt` with `[mm:ss]` block markers, plus the raw `.vtt`.

Auto-caption VTT repeats each line as the rolling top line of the next cue, so
raw output is roughly twice as long as the real speech. The script dedupes,
strips shared prefixes, and merges into ~30s blocks. A 56-minute talk lands
around 70 KB — small enough that every subagent can read the whole thing.

**Auto-captions carry disfluencies and mistranscribed proper nouns.** When
quoting as evidence, reproduce them exactly rather than cleaning them up, so
claims stay checkable against the source. Note the limitation wherever the
quotes are published.

## 2. Video

Only needed if you want frames.

```bash
${CLAUDE_PLUGIN_ROOT}/skills/video-frame-capture/scripts/fetch-video.sh <URL> <OUTDIR> [MAX_HEIGHT]
```

720p is plenty for documentation stills; a one-hour talk is ~120 MB.

**Use a scratch directory as OUTDIR** (`mktemp -d`), never the user's project
root, and use a fresh one per lesson — the script only reuses an existing
download when it recorded the same URL, so a stale `video.mp4` from another
lesson is re-fetched rather than silently reused.

On first use it builds a yt-dlp with `curl_cffi` into a cached venv under
`~/.cache/design-school/` (override with `DESIGN_SCHOOL_VENV`). This leaves the
global yt-dlp untouched and is built once, not per lesson.

This wraps three real, sequential failures, so **do not hand-roll the command**:

| Attempt | Result |
|---|---|
| `yt-dlp -f "bv*+ba"` | `HTTP 403 Forbidden` — stream URL needs a JS challenge solved |
| add `--js-runtimes deno:...` | still `403` — formats also need TLS impersonation |
| add `--extractor-args player_client=ios,tv` | `This video is DRM protected` |

What works is a yt-dlp built **with `curl_cffi`** *plus* a JS runtime, and
**no pinned player client**. Homebrew's yt-dlp lacks curl_cffi, so the script
builds a scoped `uv` venv on first use and leaves the global install alone.
`deno` is commonly installed at `~/.deno/bin/deno` but absent from the PATH
yt-dlp sees, so pass it explicitly.

**Delete the video when finished** — it is the largest artifact by far and is
rarely worth keeping once frames are extracted.

## 3. Find the moment — contact sheets first

```bash
${CLAUDE_PLUGIN_ROOT}/skills/video-frame-capture/scripts/contact-sheet.sh <video.mp4> <START_SEC> [SPAN] [STEP] [COLS]
```

Then **read the resulting image** and compute each cell's time:
`time(i) = START + i * STEP`, counting left-to-right from 0.

Never guess a timestamp from the transcript alone. Someone talking about a
screen and the cut to that screen are routinely 10–30 seconds apart, so
transcript-derived guesses land on a talking head. One sheet covering four
minutes locates every usable frame at a glance.

Many ffmpeg builds have **no `drawtext` filter**, so cells cannot be labelled —
compute times from grid position instead.

Do not hand-roll this with `fps=1/STEP`. That filter samples near the *middle*
of each interval, so every cell sits ~STEP/2 later than the formula says —
verified on a counter video, where the cells read 4, 14, 24 instead of 0, 10,
20. The script extracts each cell with an individual accurate seek and then
tiles, so cell times are exact.

## 4. Extract

```bash
# one frame, frame-accurate
${CLAUDE_PLUGIN_ROOT}/skills/video-frame-capture/scripts/grab-frame.sh <video.mp4> <SECONDS> <out.jpg>

# stack two into a single before/after image
${CLAUDE_PLUGIN_ROOT}/skills/video-frame-capture/scripts/grab-frame.sh --pair <before.jpg> <after.jpg> <out.jpg>
```

`-ss T -i file` **is** frame-accurate in modern ffmpeg — `accurate_seek` is on
by default. Verified against a lossless counter video with 30s keyframe
spacing: mid-GOP targets decode exactly. It is only inaccurate with
`-noaccurate_seek` or `-c copy`. The script keeps the coarse-then-fine form
(`-ss $((T-10)) -i file -ss 10`) as belt-and-braces and because it is faster on
long files.

**So if a frame looks wrong, suspect the timestamp, not the seek** — which in
practice means the contact sheet, see the `fps` note above.

Whole seconds only: convert `[09:30]` transcript markers to `570` before
calling. The scripts reject `1:30` rather than mis-parsing it.

**Prefer composites.** For anything comparative, one `--pair` image beats two
separate stills: the reader sees the change in a single glance.

## 5. Verify before using

Extraction is cheap; being wrong is expensive. Build one verification grid of
the final set and look at it:

```bash
N=$(ls final/*.jpg | wc -l); COLS=4; ROWS=$(( (N + COLS - 1) / COLS ))
ffmpeg -pattern_type glob -i "final/*.jpg" \
  -vf "scale=440:248:force_original_aspect_ratio=decrease,pad=440:248:(ow-iw)/2:(oh-ih)/2,tile=${COLS}x${ROWS}" \
  -frames:v 1 verify.jpg
```

**Derive the grid from the file count and pad every cell — do not hardcode
`tile=4x3`.** A fixed grid silently drops frames past cell 12, and a single
differently-shaped image (any `--pair` composite) makes ffmpeg reconfigure the
filter graph mid-run and blank every remaining cell. Both exit 0 with no
warning, so the check appears to pass while showing you almost nothing.

**Count the populated cells against the file count** before trusting the grid.

On the first real run, 2 of 12 frames had landed on talking heads despite being
picked off a contact sheet. Checking the whole set in one image caught both.

## Shell gotcha

Under zsh, an empty glob **aborts the script** (`no matches found`) even with
`rm -f`. Guard cleanup with `setopt +o nomatch` or test before removing.
