# Image-generation providers for merch

Everything here was checked against the provider's own documentation on
**2026-09-16** (Context7 docs index first, then the live docs page, OpenAPI
spec or `llms.txt` named in each section). Model ids and parameters change
often: if a call fails with an unknown model or field, re-check the source
link before guessing. Items marked **unverified** were not stated in the docs
consulted.

`generate-image.py` implements the three providers marked **(script)**. The
others are documented so Claude can call them by hand with `curl` when the
user only has that key.

## Summary

| Provider | Env var | Best for | Transparent PNG | Vector / SVG | Returned as |
| --- | --- | --- | --- | --- | --- |
| OpenAI GPT Image **(script)** | `OPENAI_API_KEY` | General illustration, following long prompts | Yes (`background: transparent`) | No | base64 in JSON |
| Ideogram **(script)** | `IDEOGRAM_API_KEY` (plugin convention) | Text-heavy designs, typography, logos | Yes (dedicated endpoint, up to 8K tier) | No | Expiring URL |
| Recraft **(script)** | `RECRAFT_API_TOKEN` | Vector/flat illustration, logos, SVG | Not natively; use its `removeBackground` | Yes (`*_vector` models) | URL (~24 h) or base64 |
| Google Gemini (Nano Banana) | `GEMINI_API_KEY` | Photoreal or painterly art, edits with references | Not documented (treat as no) | No | base64 in JSON |
| Black Forest Labs FLUX.2 | `BFL_API_KEY` | Painterly/photoreal art; `flex` for typography | No (png/jpeg/webp only, no alpha option) | No | Signed URL, 10 min |
| FLUX.2 via fal.ai | `FAL_KEY` | Same models, one key for upscale + bg removal too | No | No | fal media URL |

## OpenAI GPT Image

Verified on 2026-09-16 from https://developers.openai.com/api/docs/guides/image-generation
(live `.md` page) and the API reference `images.generate` (Context7
`/websites/developers_openai_api`).

- **Models:** `gpt-image-2.5-flare` (fast, high-quality everyday generation)
  and `gpt-image-2.5-sunburst` (best editing precision) are the current
  recommended models. Earlier: `gpt-image-2`, `gpt-image-2-2026-04-21`,
  `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`. Note: the API
  reference default for `model` is still `dall-e-2`, so always send `model`.
- **Endpoint:** `POST https://api.openai.com/v1/images/generations`, JSON,
  header `Authorization: Bearer $OPENAI_API_KEY`.
- **Body:** `model`, `prompt` (up to 32000 chars), `n` (1-10), `size`,
  `quality` (`low`, `medium`, `high`, `xhigh`, `max`, `auto`; `xhigh`/`max`
  only on the 2.5 models), `background` (`transparent`, `opaque`, `auto`),
  `output_format` (`png`, `jpeg`, `webp`), `output_compression`,
  `moderation` (`low`, `auto`).
- **Sizes:** `1024x1024`, `1536x1024`, `1024x1536`, `auto`, or custom
  `WIDTHxHEIGHT`: both edges multiples of 16, aspect between 1:3 and 3:1,
  max edge 3840, total pixels 655,360-8,294,400. Sizes above `2560x1440` are
  "experimental".
- **Transparency:** `background: "transparent"` with `output_format` `png` or
  `webp` (both 2.5 models).
- **Vector:** no.
- **Text:** "significantly improved" but docs list precise text placement
  and clarity as a limitation. Fine for a short word or two; check spelling.
- **Response:** `data[].b64_json` (GPT image models do not support
  `response_format: url`). Nothing expires; decode and save.
- **Cost:** token-priced ($30 per 1M image output tokens for the 2.5
  models); higher quality and larger sizes cost more.

## Ideogram

Verified on 2026-09-16 from the OpenAPI spec at https://api.ideogram.ai/openapi.json
and https://developer.ideogram.ai/api-reference (Context7
`/websites/developer_ideogram_ai`).

- **Auth:** header `Api-Key: <key>`. The docs do not name an environment
  variable; this plugin uses `IDEOGRAM_API_KEY`.
- **Endpoints used by the script** (both accept `application/json` or
  `multipart/form-data`, synchronous):
  - `POST https://api.ideogram.ai/v1/ideogram-v4/generate-transparent` -
    Ideogram 4.0, PNG with alpha. Fields: `text_prompt` (or `json_prompt`),
    `seed`, `aspect_ratio` (`AUTO`, `1x4`, `1x3`, `1x2`, `9x16`, `10x16`,
    `2x3`, `3x4`, `4x5`, `1x1`, `5x4`, `4x3`, `3x2`, `16x10`, `16x9`, `2x1`,
    `3x1`, `4x1`), `output_resolution` (`1K`, `2K`, `4K`, `8K`; a total-pixel
    budget equal to that square), `rendering_speed` (`TURBO`, `DEFAULT`,
    `QUALITY`).
  - `POST https://api.ideogram.ai/v1/ideogram-v4/generate` - Ideogram 4.0,
    opaque. Fields: `text_prompt`, `seed`, `resolution` (38 fixed values,
    largest `2048x2048`, `1728x2304`, `1664x2496`, `1440x2880`, ...),
    `rendering_speed` (`FLASH` listed but "coming soon" for V4).
  - Neither V4 endpoint has a `num_images` field, so the script makes one
    call per image.
- **Also available:** `/v1/ideogram-v45/generate` (Ideogram 4.5),
  `/v1/ideogram-v3/generate` and `/v1/ideogram-v3/generate-transparent`
  (with `num_images`, `negative_prompt`, `style_type` `AUTO|GENERAL|REALISTIC|DESIGN|FICTION`,
  `style_preset` incl. `FLAT_VECTOR`, `FLAT_ART`, `HALFTONE_PRINT`,
  `WOODBLOCK_PRINT`, `upscale_factor` `X1|X2|X4` on transparent), plus
  `generate-design`, `layerize-design`, `upscale`.
- **Vector:** no.
- **Text:** Ideogram's positioning and docs emphasise best-in-class text
  rendering; first choice for slogans and typographic designs.
- **Response:** `{ created, data: [{ url, prompt, resolution, is_image_safe, seed }] }`.
  "Image links are available for a limited period of time" - download
  immediately. `url` is empty when `is_image_safe` is false (422 when the
  prompt fails safety).
- **Copyright:** optional `enable_copyright_detection` (Hive likeness and logo
  checks).

## Recraft

Verified on 2026-09-16 from https://www.recraft.ai/docs/api-reference/endpoints
and https://www.recraft.ai/docs/api-reference/appendix (live `.md` pages;
Context7 `/websites/recraft_ai`).

- **Auth:** `Authorization: Bearer $RECRAFT_API_TOKEN` (the docs' examples use
  that variable name). Base URL `https://external.api.recraft.ai/v1`.
- **Endpoint:** `POST /v1/images/generations` (any model), or
  `/v1/images/generations/raster` and `/v1/images/generations/vector` to
  enforce output type. JSON body.
- **Body:** `prompt`, `n` (1-6), `model` (default `recraftv4_1`), `size`
  (`WxH` or `w:h`), `style` / `style_id` (styles apply to V2/V3 and V4 Styles
  models only), `negative_prompt` (V2/V3 only), `random_seed`,
  `response_format` (`url` default, or `b64_json`), `controls`
  (`colors` array of `{rgb:[r,g,b]}` up to 10, `background_color`,
  `artistic_level`, `no_text`).
- **Models:** `recraftv4_1`, `recraftv4_1_vector`, `recraftv4_1_pro`,
  `recraftv4_1_pro_vector`, `recraftv4_1_utility(_vector)`,
  `recraftv4_1_utility_pro(_vector)`, `recraftv4(_vector)`,
  `recraftv4_pro(_vector)`, `recraftv4_styles(_pro)(_vector)`,
  `recraftv3(_vector)`, `recraftv2(_vector)`. **Models ending in `_vector`
  return SVG.**
- **Sizes (V4 / V4.1 / V4.1 Utility / V4 Styles):** `1:1` 1024x1024, `2:1`,
  `1:2`, `3:2` 1280x832, `2:3` 832x1280, `4:3`, `3:4` 896x1216, `5:4`, `4:5`
  896x1152, `6:10`, `14:10`, `10:14`, `16:9`, `9:16`. Pro tier doubles these
  (e.g. `1:1` 2048x2048, `3:4` 1792x2432). Vector models accept the same
  aspect ratios (resolution-independent).
- **Transparency:** no transparent option on generation was found
  (**unverified** that one exists). Use `POST /v1/images/removeBackground`
  (raster in, transparent raster out; SVG in, SVG out).
- **Response:** `{ data: [{ url }], credits }` or `b64_json`. Generated
  images are "stored for approx. 24 hours".
- **Tools (all accept `file` multipart or `image_url` JSON, `response_format`):**
  `removeBackground`; `crispUpscale` (PNG/JPG/WEBP, max 10 MB, 16 MP, 4096 px
  edge); `creativeUpscale` (min 256 px); `vectorize` (raster to SVG).

## Google Gemini image models (Nano Banana)

Verified on 2026-09-16 from https://ai.google.dev/gemini-api/docs/image-generation
and https://ai.google.dev/gemini-api/docs/imagen (live pages; Context7
`/websites/ai_google_dev_gemini-api`).

- **Models:** `gemini-3.1-flash-image` (Nano Banana 2, general workhorse, up
  to 4K), `gemini-3-pro-image` (Nano Banana Pro), `gemini-3.1-flash-lite-image`
  (1K only), `gemini-2.5-flash-image` (legacy).
- **Imagen is gone:** Imagen models (`imagen-4.0-generate-001` etc., endpoint
  `models/{model}:predict`) were deprecated and shut down on **August 17,
  2026**. Do not use them.
- **Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/interactions`,
  header `x-goog-api-key: $GEMINI_API_KEY`. Body: `model`, `input` (prompt),
  `response_format: { type: "image", mime_type, aspect_ratio, image_size }`.
  (`generateContent` still exists; media returns as `inlineData` base64.)
- **Aspect ratios:** `1:1`, `3:2`, `2:3`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`,
  `16:9`, `21:9`. **Sizes:** `512px` (3.1 Flash only), `1K`, `2K`, `4K`
  (uppercase K).
- **Transparency:** not documented; treat as unsupported and remove the
  background afterwards.
- **Vector:** no.
- **Text:** docs claim "advanced text rendering"; recommend generating the
  text first, then asking for the image with that text.
- **Response:** `steps[].content[]` items `{ type: "image", data: <base64>, mime_type }`.
  All images carry a SynthID watermark (invisible).

## Black Forest Labs FLUX (direct)

Verified on 2026-09-16 from https://api.bfl.ai/openapi.json,
https://docs.bfl.ai/flux_2/flux2_text_to_image and https://docs.bfl.ai/llms.txt
(Context7 `/websites/bfl_ai`).

- **Auth:** header `x-key: $BFL_API_KEY`. Base `https://api.bfl.ai`.
- **Endpoints:** `POST /v1/flux-2-pro` (recommended default),
  `/v1/flux-2-max`, `/v1/flux-2-flex` ("specialized for typography and text
  rendering, and for preserving small details"; has `guidance` 1.5-10 and
  `steps` 1-50), `/v1/flux-2-pro-preview`, `/v1/flux-2-klein-9b`,
  `/v1/flux-2-klein-4b`, `/v1/flux-1.1-pro`, `/v1/flux-1.1-pro-ultra`
  (`aspect_ratio` 21:9 to 9:21), Kontext pro/max.
- **Body (FLUX.2):** `prompt`, `width`, `height` (min 64; max and multiple
  constraints **unverified** for text-to-image; outpainting tool caps at
  4 MP), `seed`, `safety_tolerance` 0-5, `output_format` `jpeg` (default),
  `png`, `webp`, `disable_pup` (pro/max) or `prompt_upsampling` (flex).
- **Async:** the POST returns `{ id, polling_url }`; poll `polling_url`
  (or `GET /v1/get_result?id=`) until `status` is `Ready`; the image is
  `result.sample`. **Signed URLs expire after 10 minutes.**
- **Transparency / vector:** neither.
- **Cost:** credits, 1 credit = US$0.01.

## FLUX and tools via fal.ai

Verified on 2026-09-16 from https://fal.ai/docs/documentation/model-apis/inference/queue
and per-model `https://fal.ai/models/<id>/llms.txt` (Context7 `/websites/fal_ai`,
`/websites/fal_ai_models`).

- **Auth:** `Authorization: Key $FAL_KEY`.
- **Calling:** synchronous `POST https://fal.run/<model-id>` or queued
  `POST https://queue.fal.run/<model-id>` which returns `request_id`,
  `status_url`, `response_url`; poll status until `COMPLETED`, then GET
  `response_url`.
- **Generation:** `fal-ai/flux-2-pro` (`prompt`, `image_size` preset or
  object, default `landscape_4_3`; `seed`; `output_format` `jpeg|png`;
  US$0.03 first MP + US$0.015 per extra MP), `fal-ai/flux-2-flex`. fal also
  hosts `fal-ai/ideogram/v3` and `fal-ai/recraft/v4/text-to-image` (schemas
  not checked).
- **Output:** `images[].url` on fal media storage; URL lifetime
  **unverified** - download straight away.

## Upscaling (post-process)

| Option | Call | Verified inputs | Notes |
| --- | --- | --- | --- |
| **fal Topaz** (recommended) | `POST https://fal.run/fal-ai/topaz/upscale/image`, `Authorization: Key $FAL_KEY` | `image_url` (required), `model` (`Standard V2` default, `High Fidelity V2`, `CGI` for art/graphics, `Text Refine` keeps text and shapes crisp, ...), `upscale_factor` 1-4 (default 2), `output_format` `jpeg` (default) or `png`, `face_enhancement` (default true) | Returns `image.url`. US$0.08 up to 24 MP output. Use `CGI` or `Text Refine`, `output_format: png`, `face_enhancement: false` for merch art. |
| **Recraft crisp upscale** | `POST https://external.api.recraft.ai/v1/images/crispUpscale`, Bearer `RECRAFT_API_TOKEN` | `file` (multipart) or `image_url` (JSON), `response_format` | Input max 4096 px edge, 16 MP, 10 MB. Output factor **unverified**. |
| Replicate `recraft-ai/recraft-crisp-upscale` | `POST https://api.replicate.com/v1/models/recraft-ai/recraft-crisp-upscale/predictions`, `Authorization: Bearer $REPLICATE_API_TOKEN`, `Prefer: wait` | `input.image` (URL) | Output is a URI (example was `.webp`; convert to PNG). |
| Replicate `nightmareai/real-esrgan` | `POST https://api.replicate.com/v1/models/nightmareai/real-esrgan/predictions` | `input.image`, `input.scale` (e.g. 2, 4), `input.face_enhance` | Classic, cheap; softer on flat art. |
| Ideogram upscale | `/upscale` endpoint and `upscale_factor` on V3 transparent | see Ideogram spec | Only if already using Ideogram. |
| Vector art | none needed | - | Rasterise the SVG at the exact print pixel size instead of upscaling. |

Replicate sync mode (`Prefer: wait`, up to 60 s) returns the finished
prediction with `output`; otherwise poll the prediction. Replicate output URL
lifetime is **unverified** - download immediately.

## Background removal (post-process)

| Option | Call | Verified inputs | Output |
| --- | --- | --- | --- |
| **fal Bria RMBG 2.0** (recommended) | `POST https://fal.run/fal-ai/bria/background/remove`, `Authorization: Key $FAL_KEY` | `image_url`, `sync_mode` | `image.url` PNG. US$0.018 per image; trained on licensed data. |
| fal rembg | `POST https://fal.run/fal-ai/imageutils/rembg` | `image_url` | `image.url` |
| **Recraft removeBackground** | `POST https://external.api.recraft.ai/v1/images/removeBackground` | `file` or `image_url`, `response_format` | Transparent raster; SVG in gives SVG out. Max 4096 px edge. |
| Replicate `bria/remove-background` | `POST https://api.replicate.com/v1/models/bria/remove-background/predictions` | `input.image` or `input.image_url`, `preserve_alpha` | URI |

All of these take a **URL** (or data URL for Recraft), so either host the
candidate first or, for Recraft, send a `data:image/png;base64,...` URL.

## Items not verified

- Recraft transparent generation parameter (none found).
- Gemini transparent output (not documented).
- BFL FLUX.2 maximum width/height and required multiple.
- fal and Replicate output URL lifetimes.
- Recraft crisp upscale scale factor.
- Ideogram environment variable name (docs use a literal header value).
