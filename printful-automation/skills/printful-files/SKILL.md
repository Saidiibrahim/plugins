---
name: printful-files
description: >
  This skill should be used when the user wants to get design artwork ready
  for Printful or somewhere Printful can fetch it - phrases like "is this file
  good enough to print", "check the DPI", "what size should the print file
  be", "prepare this PNG for DTG", "resize my artwork for the front print
  area", "host this design", "upload this design to R2", "upload to my
  Printful file library", "extract thread colours", or "find the design I
  uploaded last week".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, python3 with Pillow for image checks, network access, and PRINTFUL_API_TOKEN. Cloudflare R2 hosting needs wrangler or the aws CLI.
metadata:
  version: "0.2.0"
---

# Printful design files

Make artwork print-ready, host it at a public URL, and optionally have
Printful validate it. Load the `printful-api` skill first. Set `PF` to the
absolute path of `../printful-api/scripts/pf.sh` and `FILES` to this skill's
`scripts/` directory, both resolved against this skill's directory.

Flow: **check -> prepare (if needed) -> check again -> host -> validate with
Printful (optional) -> record in the index.**

The print area size, dpi and technique come from the `printful-product`
skill (`GET /v2/catalog-products/{id}/mockup-styles`). Ask for them or run
that lookup if unknown.

## 1. Check print-readiness

```bash
python3 "$FILES/check-print-ready.py" koala.png --width-in 12 --height-in 16 --dpi 150 --technique dtg
```

Needs Pillow. If it exits with "Pillow is not installed", offer
`python3 -m pip install --user Pillow` (or a virtualenv); do not install
without asking.

Output is JSON: `width_px`, `height_px`, `mode`, `has_alpha`,
`transparent_fraction`, `effective_dpi` and `limiting_axis` (dpi when the
artwork is fitted into the print area), `required_px.min/ideal`, `aspect`
mismatch, `content` (transparent padding and the dpi after trimming),
`colours` (embroidery only), `verdict` (`ok`, `warn`, `fail`), `reasons`,
`notes`. Exit code 1 means `fail`.

Rules it applies:

| Check | Rule |
| --- | --- |
| Resolution | Below `--dpi` (150, Printful's usual minimum) fails; below 300 warns. |
| Aspect | More than 2 % off the print-area ratio warns (the design will not fill the area). |
| Colour | CMYK, high bit depth, or a non-sRGB ICC profile warns. |
| Transparency | For `dtg`, `dtfilm`, `embroidery`, `uv`: no alpha or no transparent pixels warns (the background prints as a box). For `sublimation`, `cut-sew`, `digital`: transparent areas are noted (they show the base material). |
| Format / size | Not PNG or JPG warns; over 200 MB fails. |
| Embroidery | Quantised colour count over 15 or top-15 colours covering under 90 % warns (gradients, photos, shadows); soft edges warn. Keep lines >= 0.05 in and text >= 0.25 in. |

Explain the verdict in plain words. A `fail` must be fixed (a larger source
or re-generation at higher resolution) before ordering. Upscaling does not
add detail: a file prepared with `--allow-upscale` passes the pixel check but
can still print soft; say so.

## 2. Prepare a print file

```bash
python3 "$FILES/prepare-print-file.py" koala.png --width-in 12 --height-in 16 --dpi 300
```

- Applies EXIF rotation, converts to 8-bit sRGB PNG with alpha (uses the
  embedded ICC profile when present), trims fully transparent padding, fits
  the artwork without distortion, and centres it on a transparent canvas with
  the print-area aspect ratio.
- Canvas is `width_in * dpi` x `height_in * dpi`. If the artwork is smaller,
  it is **not** upscaled unless `--allow-upscale`; the canvas is built at the
  artwork's own resolution instead and the JSON reports that `dpi` and
  `below_150_dpi`.
- `--valign top` puts the artwork at the top of the area (usual for shirt
  fronts). `--background '#FFFFFF'` fills instead of transparent (for
  sublimation or posters). `--no-trim` keeps padding.
- Never overwrites the original. Default output `<name>-print.png` beside it;
  refuses to replace an existing output without `--force`.

Run the check again on the output and show both verdicts.

## 3. Host at a public URL

Printful downloads files server-side from a URL. The URL must be public HTTPS
with no login, cookies or expiring signature, and should stay up at least
until the order ships (keep it permanently if the design will be reordered).
Never use chat attachments, Google Drive/Dropbox preview pages, or presigned
URLs.

Read `design_hosting` from the config (`provider`, `public_base_url`,
`bucket`), then:

```bash
URL="$(bash "$FILES/host-design.sh" koala-print.png)"   # add --dry-run to preview
```

The script uses key `designs/<YYYYMMDD>-<sha256 8>-<name>` (a changed file
gets a new URL, which avoids stale caches), uploads, checks the URL returns
HTTP 200 and prints it. Exit 3 means the provider has no automatic upload:
the user uploads the file and the script has printed the URL to expect.

### Cloudflare R2 (default)

One-time setup (the user does this; never put credentials in files):

1. Create a bucket (e.g. `merch-designs`) in the Cloudflare dashboard or with
   `wrangler r2 bucket create merch-designs`.
2. Make it public, either:
   - **Public development URL**: dashboard R2 > bucket > Settings > Public
     Development URL > Enable, or `wrangler r2 bucket dev-url enable merch-designs`.
     Gives `https://pub-<hash>.r2.dev`. Cloudflare rate-limits r2.dev and
     intends it for non-production use; fine for occasional personal orders.
   - **Custom domain** (recommended for regular use): dashboard R2 > bucket >
     Settings > Custom Domains, or
     `wrangler r2 bucket domain add merch-designs --domain designs.example.com --zone-id <zone>`.
     The domain must be a zone on the same Cloudflare account.
3. Put that base URL in `design_hosting.public_base_url`.

Upload routes the script picks from:

| Route | Needs | Command |
| --- | --- | --- |
| S3-compatible API (used if all env vars are set and `aws` is installed) | `R2_ACCOUNT_ID`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` from an R2 API token (R2 > Manage API tokens, Object Read & Write on the bucket) | `aws s3 cp FILE s3://BUCKET/KEY --endpoint-url https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com --region auto --content-type image/png` |
| Wrangler | `wrangler login` once, or `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | `wrangler r2 object put BUCKET/KEY --file FILE --content-type image/png --remote` |

Always pass `--remote` to wrangler so the object goes to the real bucket, not
local dev storage. Uploading to a bucket without public access succeeds but
the URL check fails: point the user at step 2.

### Any other public host

Set `provider` to something else (e.g. `"manual"`) and `public_base_url` to
the folder URL. Upload by whatever means the host offers (own website, S3
static bucket, GitHub Pages, a CDN), then confirm with
`curl -sI <url>` that the status is 200 and `content-type` is `image/png` or
`image/jpeg` before using it.

## 4. Validate with Printful (optional)

v2 order items and mockups take the URL directly, so uploading to the file
library is not required. Do it to catch fetch or format problems before
spending money, or when the user wants the file in their Printful library.

```bash
bash "$PF" POST /v2/files '{"url":"https://pub-xxxx.r2.dev/designs/20260916-1a2b3c4d-koala-print.png","role":"printfile","filename":"koala-print.png","visible":true}'
```

- Returns `data.id` with `status: waiting`. Poll `GET /v2/files/{id}` every
  5 s until `ok` or `failed` (stop after about 2 minutes).
- On `ok`, report `width`, `height`, `dpi`, `mime_type`, `size` and
  `preview_url`; compare `width`/`height` with the local check.
- On `failed`, the URL is usually not public or not a real image: re-run the
  `curl -sI` check.
- Posting the same URL again returns the original file record.
- The file id is not needed in v2 orders (layers use the URL). v1 store
  products can use `{ "type": "front", "id": <id> }` instead of a URL.

### Embroidery thread colours

```bash
bash "$PF" POST /files/thread-colors '{"file_url":"https://.../logo-print.png"}'
```

v1 only. Show the detected `thread_colors` hex values. To pin them, add
`{ "name": "thread_colors", "value": ["#FFFFFF", "#000000"] }` to the
layer's `layer_options` in the design spec; otherwise Printful detects them
at order time. More detected colours than the design really has means the
artwork needs flattening.

## 5. Local index (`printful-files.csv`)

Printful's library has no folders, so keep an index in the working directory.
Append one row every time a file is hosted or uploaded; create the file with a
header if missing.

| Column | Value |
| --- | --- |
| `id` | Printful file id, or empty if only hosted |
| `filename` | local file name that was hosted |
| `url` | public URL |
| `placement` | intended placement (`front`, `back`, `embroidery_chest_left`, ...) |
| `uploaded_at` | ISO 8601 UTC |
| `notes` | product/slug, print size and dpi, verdict |

```bash
python3 - "$ROW_ID" "$FILENAME" "$URL" "$PLACEMENT" "$NOTES" <<'PY'
import csv, datetime, os, sys
path = "printful-files.csv"
new = not os.path.exists(path)
with open(path, "a", newline="") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["id", "filename", "url", "placement", "uploaded_at", "notes"])
    fid, name, url, placement, notes = sys.argv[1:6]
    w.writerow([fid, name, url, placement,
                datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), notes])
PY
```

When the user asks for an earlier design, search this file first (by name,
placement or notes) before listing anything from Printful.
