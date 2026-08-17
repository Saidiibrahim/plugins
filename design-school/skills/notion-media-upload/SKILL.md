---
name: notion-media-upload
description: This skill should be used when the user wants to put local images, GIFs, screenshots, PDFs, or other files onto a Notion page — including captioned figures inside long documents. It covers Notion's two-step MCP file-upload flow, the exact markdown to reference an upload, and why browser automation is not needed for this.
version: 1.0.0
---

# Notion Media Upload

Local files can be attached to Notion pages entirely through the MCP connector
plus `curl`. **Browser automation is not required** — do not drive Chrome to
drag files into a page.

## The two-step flow

Notion issues a short-lived upload slot, then you push the bytes to it.

**Step 1 — create the slot** (MCP tool call, once per file):

```
notion-create-file-upload  { "filename": "frame-01.jpg" }
```

Returns `file_upload_id`, `upload_url`, and `upload_headers.authorization`.
The slot expires in ~1 hour and accepts exactly one file.

Omit `content_type` and let Notion infer it from the extension. A MIME type
that disagrees with the filename is stored as given, and the file then renders
as the wrong kind.

**Step 2 — push the bytes** (shell):

```bash
${CLAUDE_PLUGIN_ROOT}/skills/notion-media-upload/scripts/notion-upload.sh \
  "<upload_url>" "<bearer_token>" path/to/frame-01.jpg
```

Prints `file-upload://<id>` on success. The script verifies
`"status": "uploaded"` and fails loudly otherwise.

**Step 3 — reference it in page markdown:**

```markdown
![Caption text goes here](file-upload://3bf0327f-c65c-811b-9c26-00b2bcc7d7fc)
```

The source resolves when `create-pages` or `update-page` saves the block. After
saving, fetching the page shows a real S3 URL in place of `file-upload://` —
that is how you confirm the image actually attached.

## Doing many files efficiently

`notion-create-file-upload` is one MCP call per file, but **all of the calls can
be issued in parallel in a single message**. Collect the returned
`upload_url` and token for each, then drive every POST through the script:

```bash
while IFS='|' read -r f url tok; do
  "${CLAUDE_PLUGIN_ROOT}/skills/notion-media-upload/scripts/notion-upload.sh" "$url" "$tok" "$f"
done <<'EOF'
frame-01.jpg|<upload_url>|<token>
frame-02.jpg|<upload_url>|<token>
EOF
```

Columns are `filename|upload_url|token` — paste the returned `upload_url`
verbatim rather than rebuilding the endpoint from the id.

**Do not hand-roll curl in the loop.** Doing so loses the script's
extension→MIME mapping, its 20 MiB pre-check, and its `"status": "uploaded"`
assertion — and hardcoding `;type=image/jpeg` mislabels every PNG, GIF and PDF,
which is the exact mistake this page warns about two paragraphs above.

Eleven images take about two minutes end to end this way.

## Constraints

`upload_headers.authorization` is a **live, single-use credential**. Do not echo
it, log it, or paste it into a commit. The script passes it to curl via
`--config` on stdin so it stays out of `ps`.


- **20 MiB** per file on this single-part flow; workspace limits still apply.
- Unattached uploads expire — reference them in a page reasonably soon.
- `notion-create-attachment` with `source_url` is an alternative, but it needs a
  publicly reachable HTTPS URL with no redirects or auth, which local files do
  not have. Use the upload flow instead.

## Page-building notes

- Build long pages in several `insert_content` appends rather than one giant
  `create-pages` call — a single enormous call is fragile, and a failure loses
  everything.
- Check Notion-flavored markdown before writing a long page: read the
  `notion://docs/enhanced-markdown-spec` resource via `notion-fetch`. Images are
  `![Caption](URL)`; callouts, toggles, and columns use XML-ish tags; colored
  text is `<span color="red_bg">…</span>`.
- Put the timestamp or source reference **in the caption**, so a reader can jump
  to the original without leaving the figure.
