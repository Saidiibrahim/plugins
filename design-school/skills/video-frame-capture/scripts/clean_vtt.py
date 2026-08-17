#!/usr/bin/env python3
"""Turn an auto-generated VTT into a clean, timestamped transcript.

    clean_vtt.py <input.vtt> <output.txt> [block_seconds]

Auto-captions repeat each line as the rolling top line of the next cue, so a
naive dump is roughly 2x too long and unreadable. This does three passes:

  1. drop cues identical to the previous cue
  2. strip the prefix a cue shares with its predecessor (the rolling repeat)
  3. merge what's left into ~30s blocks, each prefixed with [mm:ss]

The [mm:ss] markers are what downstream agents cite as evidence, so they must
line up with the real video. Block start times are exact cue starts.
"""
import html
import re
import sys

CUE = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3}) --> ")
TAG = re.compile(r"<[^>]+>")


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    cues, i = [], 0
    while i < len(lines):
        m = CUE.match(lines[i])
        if not m:
            i += 1
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() and not CUE.match(lines[i]):
            txt = TAG.sub("", lines[i]).strip()
            if txt:
                buf.append(txt)
            i += 1
        if buf:
            cues.append((t, " ".join(buf)))
    return cues


def dedupe(cues):
    out, prev = [], None
    for t, txt in cues:
        if txt == prev:
            continue
        prev = txt
        out.append((t, txt))

    final, prev = [], ""
    for t, txt in out:
        if prev and txt.startswith(prev):
            txt = txt[len(prev):].strip()
        if not txt:
            continue
        final.append((t, txt))
        prev = txt
    return final


def blocks(cues, span):
    out, cur = [], None
    for t, txt in cues:
        if cur is None or t - cur[0] >= span:
            cur = [t, [txt]]
            out.append(cur)
        else:
            cur[1].append(txt)
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    span = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    cues = dedupe(parse(src))
    if not cues:
        sys.exit("No cues parsed — is this a valid VTT?")
    body = "\n\n".join(
        f"[{b[0] // 60:02d}:{b[0] % 60:02d}] " + " ".join(b[1]) for b in blocks(cues, span)
    )
    body = html.unescape(body).replace(">> ", "\n— ").replace(">>", "—")
    open(dst, "w", encoding="utf-8").write(body)
    last = cues[-1][0]
    print(
        f"{len(cues)} cues -> {len(blocks(cues, span))} blocks, "
        f"{len(body)} chars, ends {last // 60:02d}:{last % 60:02d}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
