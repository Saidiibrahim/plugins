---
name: printful-design
description: >
  This skill should be used when the user wants to turn an idea into
  print-ready merch artwork with an AI image-generation API (OpenAI GPT Image,
  Ideogram, Recraft, Gemini, FLUX) and host it for Printful - phrases like
  "design a t-shirt", "generate merch art", "make a design for a hoodie",
  "create an image for a mug", "AI design for Printful", "turn this idea into
  a print", "make me a logo for a shirt", or "generate a few design options".
license: MIT
compatibility: Requires python3, curl, network access, at least one image API key (OPENAI_API_KEY, IDEOGRAM_API_KEY, RECRAFT_API_TOKEN, GEMINI_API_KEY, BFL_API_KEY or FAL_KEY), the printful-api, printful-product, printful-files and printful-order skills from the same plugin, and Pillow for the print-file checks.
metadata:
  version: "0.2.0"
---

# Printful design generation

Take an idea from brief to a print-ready PNG (or SVG) at a public URL, then
hand off to `printful-product` for mockups and `printful-order` to buy it.
This is personal merch, not a shop: optimise for one great file, not volume.

Resolve paths against this skill's directory first:

```bash
SKILL="<this skill directory>"
GEN="$SKILL/scripts/generate-image.py"
FILES="$SKILL/../printful-files/scripts"
PF="$SKILL/../printful-api/scripts/pf.sh"
```

Provider facts (model ids, sizes, transparency, URL expiry, upscalers,
background removal) are in [references/providers.md](references/providers.md),
verified 2026-09-16. Read it before calling a provider by hand.

## 1. Brief

Collect, in one short exchange (skip what the user already said):

| Item | Why it matters |
| --- | --- |
| Product (tee, hoodie, mug, tote, poster...) and placement (front, back, left chest, sleeve, wrap) | Decides print area and aspect ratio |
| Technique (DTG, DTF, embroidery, sublimation, UV) | Decides palette and detail limits |
| Garment or product colour(s) | Design must contrast with it |
| Style (flat vector, retro badge, line art, watercolour, photo) | Drives provider choice and prompt |
| Exact text, if any | Spell-check it with the user before generating |

Then get the print area **before generating** (load `printful-product` and
`printful-api` for the helper):

```bash
bash "$PF" GET "/v2/catalog-products/<id>/mockup-styles" \
  | python3 -c 'import json,sys
for p in json.load(sys.stdin)["data"]:
    print(p["placement"], p["technique"], p["print_area_width"], "x", p["print_area_height"], "in @", p["dpi"], "dpi")'
```

Record `W_IN`, `H_IN` and the minimum `DPI` for the chosen placement and
technique. Calculate the **minimum** required pixels:
`MIN_PX = W_IN * DPI` x `H_IN * DPI` (e.g. 12 x 16 in @ 150 dpi = 1800 x
2400 px). Calculate the **ideal** target pixels: `IDEAL_PX = W_IN * 300` x
`H_IN * 300` (e.g. 3600 x 4800 px). Use `W_IN:H_IN` as the generation aspect
ratio. For designs that should not fill the area (left chest, small centre
logo), decide the intended printed size with the user and use that instead.

**DPI guidance for generation:**
- Always aim to generate at a size that meets at least the 150 dpi minimum
  (MIN_PX), preferably closer to 300 dpi (IDEAL_PX), within the provider's
  capabilities.
- For OpenAI: the automatic size selection in `generate-image.py` may produce
  images below 150 dpi for large print areas. Calculate the target pixels
  first and use `--size WxH` explicitly when the print area is large
  (e.g. `--size 3600x4800` for 12x16 in @ 300 dpi, or at minimum
  `--size 1800x2400` for 12x16 in @ 150 dpi). OpenAI supports up to 3840 px
  on the long edge.
- For Ideogram transparent: use `--resolution 4K` or `8K` when the print area
  requires it to meet 150 dpi.
- For Recraft: choose the aspect ratio; Recraft generates at high resolution
  by default.
- If the first generation fails print-check due to low DPI, calculate the
  required size and regenerate once at the correct dimensions rather than
  discovering after multiple attempts.

## 2. Write the prompt for print

Build the prompt from the brief; show it to the user before spending money.

- **Isolated subject** on a plain or transparent background: "a single
  centred illustration of ..., isolated, no background scene, no frame, no
  mockup, not on a t-shirt".
- **No photographic backgrounds**, drop shadows, vignettes or borders; they
  print as a visible rectangle.
- **Flat, limited palette** for DTG/DTF (4-8 solid colours, bold outlines,
  screen-print or vector style). Gradients and soft glows print poorly and
  fade on dark garments.
- **Contrast with the garment:** name the garment colour ("designed to print
  on a black shirt, use light and saturated colours, avoid black and dark
  navy elements").
- **Avoid tiny details:** no hairlines, fine text, or detail smaller than
  about 1/16 inch at print size.
- **Text:** quote it exactly ("the text reads \"ADELAIDE\" in bold condensed
  capitals"), keep it short, and check every candidate letter by letter.
- **Embroidery:** 3-6 flat thread colours, bold solid shapes, no gradients,
  no photo realism, no text under about 0.25 inch tall, thick outlines.
- **Sublimation / all-over / posters:** full-bleed backgrounds are fine;
  request an opaque image at the full area ratio instead of transparency.

## 3. Choose a provider

Detect which keys exist without printing them:

```bash
for v in OPENAI_API_KEY IDEOGRAM_API_KEY RECRAFT_API_TOKEN GEMINI_API_KEY BFL_API_KEY FAL_KEY REPLICATE_API_TOKEN; do
  [ -n "$(printenv "$v")" ] && echo "$v set"; done
```

Pick the first available match:

| Design need | Preferred | Fallbacks |
| --- | --- | --- |
| Text-heavy (slogan, typography, badge with words) | `ideogram` (transparent endpoint) | `openai`; BFL `flux-2-flex` by hand |
| Logo, icon, flat vector, embroidery-friendly | `recraft --vector` (SVG) | `ideogram`, `openai` with a flat-style prompt |
| Illustration needing a transparent PNG directly | `openai --transparent` or `ideogram --transparent` | any + background removal |
| Painterly or photoreal art (mugs, posters, sublimation) | `openai` | Gemini `gemini-3.1-flash-image` or FLUX.2 by hand (see providers.md) |

- `generate-image.py` supports `openai`, `ideogram` and `recraft`. For Gemini,
  BFL or fal, build the `curl` call from providers.md, save the images into
  the same `designs/<slug>/` folder, and write the `prompt.json` sidecar in
  the same shape.
- If no key is set, ask which provider the user wants, point them to that
  provider's API key page, and ask them to `export` the variable in their
  shell. Never ask them to paste a key into chat, never write keys to files.
- Do not use Imagen (`imagen-*`); it was shut down on 2026-08-17.

## 4. Generate candidates

Use a short slug for the idea and generate 2-4 candidates. Always run a
`--dry-run` first on a new provider or prompt shape and check the request.

```bash
python3 "$GEN" --provider ideogram --prompt "$PROMPT" --aspect "$W_IN:$H_IN" \
  --n 3 --transparent --out-dir "designs/koala-surfer" --dry-run
python3 "$GEN" --provider ideogram --prompt "$PROMPT" --aspect "$W_IN:$H_IN" \
  --n 3 --transparent --out-dir "designs/koala-surfer"
```

- Options: `--size WxH` (openai/recraft), `--quality` (openai quality, or
  Ideogram `TURBO|DEFAULT|QUALITY`), `--resolution 1K|2K|4K|8K` (Ideogram
  transparent, default 4K), `--vector` (recraft SVG), `--model`, `--seed`.
- Output: `designs/<slug>/candidate-NN.png|svg` plus `prompt.json`
  (appends one record per run: provider, model, prompt, request bodies,
  seed, returned seeds, revised prompts, UTC timestamp, files, notes).
- Exit codes: `0` ok, `1` API or network error (show the message), `2` usage,
  `3` key missing.
- Show every candidate to the user (read the image files) and ask which one
  to take forward or what to change. Refine the prompt rather than
  re-rolling blindly.

## 5. Costs and limits

- Image APIs charge per image (and per upscale or background removal). State
  the provider, model and image count before each paid run.
- **Ask before generating more than 4 images in one go** or before upscaling
  or background-removing more than 2 files. The script refuses `--n` above 4
  unless `--allow-more` is passed; only pass it after the user agrees.
- **Never loop generations unattended** (no retry-until-good loops, no
  scheduled runs). One run, show results, wait for the user.

## 6. Post-process to print-ready

Work on a copy of the chosen candidate; keep originals.

1. **Vector (SVG):** skip upscaling. Rasterise at the exact target pixels
   (e.g. `rsvg-convert -w PX -h PX` or Inkscape if installed), transparent
   background.
2. **Background removal** if the background is not already transparent
   (check the alpha channel with `check-print-ready.py`). Options in
   providers.md: fal `fal-ai/bria/background/remove` (preferred) or Recraft
   `removeBackground` (accepts a data URL, so no hosting needed). These need
   the image by URL: host a temporary copy first (step 7) or use Recraft with
   a `data:image/png;base64,...` URL.
3. **Upscale** when pixels are below target: fal `fal-ai/topaz/upscale/image`
   with `model: "CGI"` (art) or `"Text Refine"` (text), `output_format: "png"`,
   `face_enhancement: false`, `upscale_factor` = ceil(target / current), max 4;
   or Recraft `crispUpscale`. Aim for 300 dpi; 150 dpi is the floor. Re-check
   that upscaling did not warp text.
4. **Check and prepare** with the printful-files scripts:

   ```bash
   python3 "$FILES/check-print-ready.py" designs/koala-surfer/final.png \
     --width-in "$W_IN" --height-in "$H_IN" --dpi 150 --technique dtg
   python3 "$FILES/prepare-print-file.py" designs/koala-surfer/final.png \
     --width-in "$W_IN" --height-in "$H_IN" --dpi 300 \
     --out designs/koala-surfer/final-print.png
   ```

   Fix anything `check-print-ready.py` flags before hosting. Download
   provider URLs straight away; Ideogram, BFL (10 min), fal and Replicate
   links expire.

## 7. Host publicly

Read `design_hosting` from
`${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}` and
follow the `printful-files` skill for the upload (Cloudflare R2 by default;
`bash "$FILES/host-design.sh" FILE` uploads it and prints the
public URL). Use a content-hashed key so a changed file gets a new URL.

Then verify the URL is public **without credentials**:

```bash
curl -sI "$URL" | awk 'NR==1 || tolower($1)=="content-type:"'
```

Continue only on `200` with `content-type: image/png` (or `image/jpeg`).
Anything else (403, 404, `text/html`, a redirect to a login page) means
Printful cannot fetch it: fix the bucket's public access or the key.

## 8. Hand off

- **Mockups and placement:** load `printful-product` and create a mockup task
  with the hosted URL in `placements[].layers[]` (position in inches), show
  the mockups, and adjust size or position if needed.
- **Buy it:** load `printful-order`. A v2 order item can carry the design
  inline (`source: "catalog"` plus placements with the URL), so saving a
  product is optional. All spending rules in `printful-api` apply.
- Add the final URL and chosen candidate to `designs/<slug>/prompt.json`
  under the latest record's `notes` so the design can be reordered later.

## Rights and content rules

Before generating, refuse or redirect prompts that ask for:

- Trademarked logos, brand names, sports team or band marks.
- Copyrighted characters (Disney, Pokemon, Marvel, anime), or "in the style
  of" a living artist's specific work.
- A real person's likeness (celebrities, public figures) or private people
  without consent.
- Copied artwork, album covers, film posters or photos found online.

Explain that Printful reviews designs for intellectual-property problems and
may reject, hold or cancel such orders, and that "personal use" does not
change that. Offer an original alternative (e.g. "a koala surfer mascot"
instead of a licensed character). Ideogram's optional
`enable_copyright_detection` can be turned on as an extra check.
