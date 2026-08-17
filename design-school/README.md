# Design School

A Claude Code plugin that turns design talks and videos into **verified,
agent-readable design lessons** in Notion — reference material a coding agent
consults later when doing design work.

The output is not a summary. It is directive, checkable rules, each backed by a
verbatim quote deep-linked to the exact second of the source, tagged by
strength, and accompanied by an honest record of where the speakers hedged.

## Install

```bash
claude
/plugin marketplace add ~/Developer/plugins
/plugin install design-school@ibby-plugins
```

## Use

```
/design-lesson https://www.youtube.com/watch?v=...
```

Or just ask — the skills activate on requests like "take notes on this design
video" or "add this talk to design school".

## What's inside

| Component | Purpose |
|---|---|
| `design-lesson-from-video` skill | End-to-end pipeline and quality bar |
| `video-frame-capture` skill | Transcripts and stills via `yt-dlp` + `ffmpeg`, with the 403/DRM workarounds |
| `notion-media-upload` skill | Two-step Notion file upload; no browser needed |
| `/design-lesson` command | One-shot entry point |

The extraction workflow (in the main skill's `references/`) runs 12 agents:
five lens extractors, five adversarial fact-checkers piped straight off them, a
completeness critic, and a synthesiser.

**The adversarial pass is the point.** It catches invented quotes, wrong
timestamps, absolutes the speakers actually hedged, rules too vague to act on,
and instructions injected into an uploader-authored caption track. On the first
real run it corrected 52 of 150 rules and produced the entire "Caveats and
disputed points" section; the completeness critic then added 9 more. If Caveats
comes out empty, the pass underperformed.

## Requirements

- `yt-dlp`, `ffmpeg`, `python3` — `brew install yt-dlp ffmpeg`
- `uv` — only for the cached `curl_cffi` build used to get past YouTube's 403
- A JS runtime (`deno`, `node`, or `bun`) for yt-dlp's signature challenge
- The Notion MCP connector, authenticated

No browser is required. A browser MCP is an optional fallback for richer video
metadata in step 1, nothing else.

## Hard-won notes

Three things cost real time on the first run and are encoded in the skills:

- **The browser cannot do this.** YouTube's caption endpoint returns HTTP 200
  with an empty body, and an occluded browser window reports `document.hidden`
  and never renders video — every screenshot is the poster frame.
- **Video download needs `curl_cffi` *and* a JS runtime, with no pinned player
  client.** Each missing piece produces a different, misleading error (`403`,
  then `403` again, then "DRM protected").
- **Locate moments with a contact sheet, and build the sheet from exact seeks.**
  Speech about a screen and the cut to it are often 10–30 seconds apart, so
  transcript-derived timestamps land on a talking head. And ffmpeg's
  `fps=1/STEP` samples mid-interval, so a naive sheet is offset by ~STEP/2 —
  which reads as "the seek is inaccurate" when the seek was fine all along.
  (`-ss T -i file` *is* frame-accurate in modern ffmpeg.)

## License

MIT
