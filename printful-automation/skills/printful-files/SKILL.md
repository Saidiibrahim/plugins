---
name: printful-files
description: >
  This skill should be used when the user wants to get design artwork into
  Printful or check whether it is print-ready - phrases like "upload this
  design to Printful", "add to my file library", "is this file good enough to
  print", "check the DPI", "what size should the print file be", "extract
  thread colours", "prepare this PNG for DTG", or "resize my artwork for the
  front print area".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, network access, PRINTFUL_API_TOKEN, and Python Pillow or ImageMagick for image checks.
metadata:
  version: "0.1.0"
---

# Printful design files

Get artwork into the Printful file library and make sure it meets print
specs. Load the `printful-api` skill first; use its helper
`../printful-api/scripts/pf.sh`, resolved against this skill's
directory (set `PF` to that absolute path before running commands).

## Constraint: files must be reachable by URL

`POST /files` accepts only a public `url`; there is no multipart upload. When
the user gives a local file:

1. Ask where they can host it if no option is known. Acceptable sources: a
   direct-download link from cloud storage (Google Drive, Dropbox, S3/R2), a file on their own website or
   CDN, or a public object-storage bucket.
2. If a cloud-storage tool is available in this session, upload the file there,
   make it link-shareable, and convert the share link to a direct-download
   form before passing it to Printful.
3. Never use a URL that requires login; Printful fetches it server-side.

## Inspect the file first

Use Python (`Pillow`) or `identify` from ImageMagick to read width, height,
mode and embedded DPI. Then compare with the target print area from
`GET /mockup-generator/printfiles/{product_id}` (see `printful-product`):

- DTG / digital: the file should be at least the print area size in pixels at
  150 DPI (e.g. 1800 x 2400 for a 12 x 16 inch front); 300 DPI is preferred.
  Report the effective DPI = pixels / inches and flag anything under 150.
- Transparency: PNG with a transparent background for garments; JPG is fine
  for all-over sublimation and posters.
- Colour: sRGB. Convert CMYK files and tell the user.
- Embroidery: flat colours, no gradients, minimum 0.05 inch line thickness,
  ideally supplied as PNG at the exact placement size; thread colours are
  limited, so run `POST /files/extract-colors` and show the detected threads.
- Max file size 200 MB; keep well under it.

Offer to fix simple problems in place: trim transparent padding, resize or
pad to the print-area ratio, convert to sRGB PNG. Save fixed copies with a
suffix (`-print.png`), never overwrite the original.

## Upload to the library

```bash
$PF POST /files '{"url":"https://.../design-print.png","type":"front","filename":"design-print.png","visible":true}'
```

- `type` is the intended placement (`default`, `front`, `back`, `sleeve_left`
  etc.). Use `default` when the same file will be used in several places.
- The response returns an `id` and `status: waiting`. Poll `GET /files/{id}`
  every 5 seconds until `status` is `ok` (or `failed`, in which case report the
  message). Show `preview_url`, `width`, `height`, `dpi`.
- Record the file `id`; the product and order skills can reference it as
  `{ "type": "front", "id": <id> }` instead of a URL.

## Organising

Printful's library has no folders via the API. Keep a local index file
(`printful-files.csv` in the working directory: id, filename, placement,
uploaded date, notes) whenever the user uploads through the plugin, and
append to it on each upload so designs can be found again later.
