# Notion library: schema and page conventions

## Locating the library

Search for a page named **Design School**. If it does not exist, create it and
the database below, then tell the user where it went.

Existing library for this user (created 2026-08-17):

| Thing | ID |
|---|---|
| Design School page | `3bf0327f-c65c-8167-8bc4-de2ac3d2f75e` |
| Design Lessons data source | `dbb03cd1-2034-4b79-a7e5-f1c3c49a78ae` |
| Workflow page | `3bf0327f-c65c-818c-a29c-c290c76f635b` |

Verify these still resolve with `notion-fetch` before relying on them.

## Database schema

Create with `notion-create-database` if the library is new:

```sql
CREATE TABLE (
  "Lesson" TITLE,
  "Source Type" SELECT('Video':blue, 'Talk':purple, 'Article':green, 'Book':brown, 'Teardown':orange),
  "Source URL" URL,
  "Author / Speaker" RICH_TEXT,
  "Publisher" RICH_TEXT,
  "Topics" MULTI_SELECT('AI slop':red, 'Typography':blue, 'Color & contrast':purple,
                        'Layout':green, 'Content & trust':yellow, 'Agent workflow':orange,
                        'Brand':pink, 'Motion':brown),
  "Duration" RICH_TEXT,
  "Captured" DATE,
  "Status" SELECT('Draft':gray, 'Verified':green, 'Needs review':yellow),
  "Rules" NUMBER,
  "Key Takeaway" RICH_TEXT
)
```

Dates use the expanded form: `"date:Captured:start": "2026-08-17"`.

## Page conventions

**Header** — a callout with title, publisher, duration, speakers, a link to the
source, and the capture date. Then `<table_of_contents/>`.

**Strength tags** as coloured spans, not bracketed text (brackets get escaped
and render literally):

```markdown
<span color="red_bg">**HARD RULE**</span>
<span color="blue_bg">**STRONG DEFAULT**</span>
<span color="gray_bg">**TASTE CALL**</span>
```

**Evidence** as a blockquote directly beneath its rule, with the timestamp
deep-linked into the video:

```markdown
> "verbatim quote from the transcript" — [33:07](https://www.youtube.com/watch?v=ID&t=1987s)
```

Convert `mm:ss` to `&t=<seconds>s`. This is high-value: it lets a reader check
any claim in one click.

**Images** — `![Caption with what it shows and its timestamp](file-upload://<id>)`.
See the Notion Media Upload skill.

**Caveats** section gets a `⚠️` callout at the top telling the reader not to
apply the rules mechanically.

**Method appendix** — put provenance in a collapsed `<details>` toggle at the
end: how the transcript was captured, the agent counts
(`N extracted → M survived → K added by critic`), and known limitations such as
auto-caption disfluencies and unresolvable speaker attribution.

## Assembly mechanics

Build the page in roughly four calls, not one:

1. `notion-create-pages` with properties + header + first sections
2–4. `notion-update-page` with `command: "insert_content"`, `position: {"type":"end"}`

A single enormous `create-pages` call is fragile and a failure loses everything.

Transform the synthesiser's markdown before publishing — replace `**[hard rule]**`
style tags with spans, and turn `— [mm:ss]` into deep links. Doing this with a
small script beats hand-editing and avoids transcription drift.

## Verify after publishing

Fetch the page and confirm:

- no literal `file-upload://` remains (they should have resolved to S3 URLs)
- the image count matches what you uploaded
- every `## ` heading is present
- the deep-link count roughly matches the quote count
