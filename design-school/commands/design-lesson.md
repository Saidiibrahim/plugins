---
name: design-lesson
description: Turn a design video into a verified lesson page in the Notion Design School library
argument-hint: <video-url> [notes or focus areas]
---

Create a design lesson from this source: **$ARGUMENTS**

Follow the **Design Lesson From Video** skill. In short:

1. Identify the video (title, publisher, duration, chapters).
2. Pull the transcript with `yt-dlp` — never through the browser.
3. Launch the 12-agent extraction + adversarial verification workflow in the
   background. Confirm with the user first if they have not already opted into
   multi-agent orchestration, since it spawns a dozen agents.
4. While that runs, download the video and capture 8–15 frames using contact
   sheets to locate each moment. Composite before/after pairs.
5. Publish to the Design Lessons database with deep-linked evidence and
   captioned frames.
6. Delete the downloaded video, then report the page URL.

Before publishing, spot-check 3–5 quotes against the transcript yourself, and
confirm the Caveats section is present and honest. If the user gave focus areas
in the arguments, bias the lens prompts toward them but do not drop the others.
