---
name: printful-product
description: >
  This skill should be used when the user wants to turn a design into a
  Printful product or explore what they can print on - phrases like "put this
  design on a t-shirt", "which Printful blanks can I use", "browse the Printful
  catalog", "find a hoodie that ships from Australia", "how much is a mug in
  AUD", "is this colour in stock", "what size should the print file be",
  "generate mockups", "make a design spec for my order", "save this as a
  Printful product", "list my Printful products", "delete this product", or
  "create products from this list".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, python3, network access, and PRINTFUL_API_TOKEN. Uses the printful-files skill for hosting and checking artwork.
metadata:
  version: "0.2.0"
---

# Printful products

Take a design from "which blank?" to a reusable **design spec** that the
`printful-order` skill can order directly. Saving it as a store product is
optional. Load the `printful-api` skill first for auth, config, rate limits
and safety rules; endpoint details are in its
`references/endpoints-v2.md` (primary) and `references/endpoints-v1.md`.

Set `PF` to the absolute path of `../printful-api/scripts/pf.sh`, resolved
against this skill's directory, and call it as `bash "$PF" METHOD PATH [BODY]`.

Read the local config first. Use `selling_region` (default `australia`) as
`selling_region_name` and `currency` (default `AUD`) on every catalog call.

## Flow

1. Find the blank (catalog product).
2. Pick variants; check stock and price for the region.
3. Get print specs and valid placements.
4. Prepare and host the artwork (`printful-files` skill).
5. Generate mockups and show them.
6. Write `<slug>.design.json`.
7. Optional: save as a v1 store product.

## 1. Find the blank

- Product type ("hoodie", "mug", "tote"): `GET /v2/catalog-categories` once,
  pick the closest category ids, then list products in them.
- Brand/model ("Bella+Canvas 3001", "Gildan 18500"): list products and match
  on `name`, `brand` and `model`.

```bash
bash "$PF" GET "/v2/catalog-products?category_ids=24&selling_region_name=australia&techniques=dtg&placements=front,back&colors=Black&sort_type=bestseller&limit=50"
```

- Array filters (`category_ids`, `techniques`, `placements`, `colors`) are
  comma-separated. `sort_type` is `bestseller`, `rating`, `price` or `new`
  (`sort_direction=ascending|descending`).
- `selling_region_name` limits results to products sold in that region, which
  usually means produced closer to home (faster, no customs).
- Skip items with `is_discontinued: true`.
- Page with `offset` if `paging.total` is larger than the page.

Show 5-10 of the best matches and let the user pick unless they named one:

| id | name | brand / model | techniques | variants |
| --- | --- | --- | --- | --- |
| 71 | Unisex Staple T-Shirt | Bella+Canvas 3001 | dtg, embroidery | 180 |

## 2. Variants, stock and price

1. `GET /v2/catalog-products/{id}/catalog-variants` (page through). Filter by
   the user's colours and sizes; keep `id`, `size`, `color`, `color_code`.
2. `GET /v2/catalog-products/{id}/availability?selling_region_name=australia&techniques=dtg`
   (page through). For each chosen variant, find the technique entry and the
   region's `availability`:
   - `in stock`: fine.
   - `out of stock`: warn and suggest another colour/size or wait.
   - `not fulfillable`: cannot be made for this region; drop it or pick
     another blank.
   - `unknown`: warn and let the user decide.
   Never silently include a variant that is not `in stock`.
3. `GET /v2/catalog-variants/{variant_id}/prices?currency=AUD&selling_region_name=australia`
   for one representative variant per price level (sizes like 2XL+ often cost
   more), or `/v2/catalog-products/{id}/prices` for the whole product.
   Explain the result:
   - `variant.techniques[].price`: the blank printed with that technique.
   - `product.placements[]`: each placement has `price` and
     `discounted_price`. The **first** placement on an item is charged at
     `discounted_price`; every additional placement adds its `price`. Layers
     can add `additional_price`; some `placement_options` carry a price.
   - `discount_tiers[]`: `bulk_discount_percentage` (0.08 = 8 %) from a
     given `quantity`; rarely relevant for personal orders.
   - Present an estimate per item, e.g. "M black tee, front + back:
     about A$X before shipping and 10 % GST". These are catalog estimates;
     the `printful-order` skill gets the real total from an estimation task.

## 3. Print specs and valid placements

1. `GET /v2/catalog-products/{id}/mockup-styles?selling_region_name=australia`
   returns, per placement and technique: `print_area_width` and
   `print_area_height` (inches), `print_area_type`, `dpi`, and
   `mockup_styles[]`. Required pixels:

   | Size | Formula | 12 x 16 in front at dpi 150 |
   | --- | --- | --- |
   | Minimum | `width_in * dpi` x `height_in * dpi` | 1800 x 2400 px |
   | Ideal | `width_in * 300` x `height_in * 300` | 3600 x 4800 px |

2. `GET /v2/catalog-products/{id}` gives the rules for building placements:
   - `techniques[]` (`is_default` marks the usual one).
   - `placements[]`: valid `placement` + `technique` pairs, allowed
     `layers[].layer_options` (e.g. `thread_colors` for embroidery),
     `placement_options`, and `conflicting_placements` (placements that
     cannot be combined with this one on the same item).
   - `product_options[]` (e.g. `stitch_color`, `inside_pocket`) with the
     techniques they apply to.
   Reject any requested combination not listed there, and any pair of
   placements that conflict, before hosting files or making mockups.

3. Hand the artwork to the `printful-files` skill with the print area size and
   technique: it checks print-readiness, prepares a `-print.png` if needed,
   hosts it at a public URL, and optionally has Printful validate it.

## 4. Mockups

Choose `mockup_style_ids` from the mockup-styles response: one or two views
per placement the user cares about (e.g. a "Men's" front and a "Flat" front).
A style with non-empty `restricted_to_variants` only works for those variant
ids. Add `default_mockup_styles=true` to the mockup-styles call to hide
seasonal/lifestyle styles.

```json
{
  "format": "png",
  "mockup_width_px": 1000,
  "products": [
    {
      "source": "catalog",
      "catalog_product_id": 71,
      "catalog_variant_ids": [4012, 4017],
      "mockup_style_ids": [16652],
      "placements": [
        { "placement": "front", "technique": "dtg",
          "layers": [ { "type": "file", "url": "https://pub-xxxx.r2.dev/designs/20260916-1a2b3c4d-koala-front.png" } ] }
      ]
    }
  ]
}
```

1. Write the body to a temp file; `bash "$PF" POST /v2/mockup-tasks @body.json`.
   Put every product of a batch into one request's `products[]`; mockups are
   rate limited and count toward a daily limit (variants of the same colour
   share one mockup, so pass one size per colour).
2. Collect the task ids from `data[].id`. Wait 10 s, then
   `GET /v2/mockup-tasks?id=<id1>,<id2>` every 10 s until each `status` is
   `completed` or `failed`; stop after about 2 minutes and report.
3. On `failed`, show `failure_reasons[].detail` (and `valid_values` if
   present), fix the placements and retry once.
4. Download every `mockup_url` immediately (the URLs are temporary):
   `curl -fsSL -o "mockups/<slug>/<variant_id>-<placement>-<style_id>.png" "<url>"`.
   Show the local paths (open them if the environment allows) and ask whether
   the design looks right before going further.

## 5. Design spec (`<slug>.design.json`)

This is the hand-off to `printful-order`. Write it to the working directory
with a lowercase hyphenated slug (`koala-tee.design.json`).

```json
{
  "spec_version": 1,
  "slug": "koala-tee",
  "name": "Koala tee",
  "catalog_product_id": 71,
  "product_name": "Unisex Staple T-Shirt | Bella+Canvas 3001",
  "selling_region_name": "australia",
  "currency": "AUD",
  "variants": [
    { "catalog_variant_id": 4012, "size": "M", "color": "Black", "availability": "in stock", "unit_price_estimate": "0.00" },
    { "catalog_variant_id": 4017, "size": "L", "color": "Black", "availability": "in stock", "unit_price_estimate": "0.00" }
  ],
  "catalog_variant_ids": [4012, 4017],
  "placements": [
    {
      "placement": "front",
      "technique": "dtg",
      "layers": [
        { "type": "file", "url": "https://pub-xxxx.r2.dev/designs/20260916-1a2b3c4d-koala-front.png" }
      ]
    }
  ],
  "product_options": [],
  "artwork": [
    { "placement": "front", "local_file": "koala-front-print.png", "print_area_in": [12, 16], "effective_dpi": 300, "printful_file_id": null }
  ],
  "mockups": ["mockups/koala-tee/4012-front-16652.png"],
  "v1": { "sync_product_id": null, "sync_variant_ids": {} },
  "created_at": "2026-09-16T06:07:08Z"
}
```

Rules:

- `placements` and `product_options` use exactly the v2 order-item shape, so
  the order skill builds each item as
  `{ "source": "catalog", "catalog_variant_id": <one of catalog_variant_ids>, "quantity": n, "name": ..., "placements": <placements>, "product_options": <product_options> }`
  (omit `product_options` when empty).
- `catalog_variant_ids` lists only variants the user approved; `variants`
  carries the human-readable detail and the availability seen at creation
  time. The order skill re-checks availability before ordering.
- Layer `url`s must be public and permanent (the `printful-files` hosting
  step). Never put mockup URLs or Printful temporary URLs in `placements`.
- `position` is optional (inches). Omit it to let Printful centre the design;
  prepared print files already match the print-area aspect.
- If a spec file with that slug exists, show the differences and ask before
  overwriting; otherwise suggest a new slug.

## 6. Optional: save as a store product (v1)

A design spec is enough to order. Save a store (sync) product only when it
helps:

| Worth saving | Not needed |
| --- | --- |
| The same item will be reordered many times and the user wants it visible in the Printful dashboard | A one-off or occasional order: order from the spec |
| The user wants to order from the dashboard or a phone without Claude | The design is still changing |

Product templates: created in the Printful dashboard (Product templates), not
through the API. List them with v1 `GET /product-templates?limit=100`; use one
in v2 orders or mockups with `source: "product_template"` and
`product_template_id`.

### Create

Map the spec to the v1 body (see `endpoints-v1.md`):

- `sync_product`: `name`, `external_id` = slug, `thumbnail` = a hosted
  mockup URL (upload the chosen mockup through the `printful-files` hosting
  step first, since Printful's mockup URLs expire).
- One `sync_variants[]` per `catalog_variant_id`: `variant_id` = the catalog
  variant id, `external_id` = `<slug>-<size>-<colour>`, `retail_price` (the
  user's figure, or the estimate for a personal store), and
  `files[]` = one entry per v2 placement:
  `{ "type": "<placement>", "url": "<layer url>" }`.
- Do **not** copy v2 inch positions into v1 `position`; v1 positions are
  pixels. Omit `position` (Printful auto-fits). Only if the user needs a
  specific placement, convert using `GET /mockup-generator/printfiles/{product_id}`
  (pixels per placement) and the v2 print area in inches.
- Confirm v1 placement names with `available_placements` from that same
  printfiles call; most match v2 (`front`, `back`, `sleeve_left`,
  `embroidery_chest_left`) but some products use `default`.

Show a one-screen summary (name, variants, prices, placements), get a go-ahead,
then `bash "$PF" POST /store/products @body.json`. Record
`sync_product.id` and each `sync_variants[].id` (keyed by catalog variant id)
into the spec's `v1` block, and give the dashboard link
`https://www.printful.com/dashboard/sync-products/<id>`.

### Update, add, delete, list

- **Update**: `GET /store/products/{id}`, change only the requested fields,
  `PUT /store/products/{id}` including each variant's `id` so it updates
  instead of duplicating. Mirror file URL changes into the spec.
- **Add a variant**: `POST /store/products/{id}/variants` with the same
  `files[]`; append to the spec after checking availability.
- **Delete** (guarded): show name and variant count, get an explicit yes, then
  `PF_CONFIRM=yes bash "$PF" DELETE /store/products/{id}`. Set the spec's `v1`
  ids back to null; the design spec itself stays orderable.
- **List**: `GET /store/products?limit=100&offset=N` (page through). Show id,
  name, variant count, `synced`, thumbnail. For one product show each
  variant's size, colour, price and file placements.

## Bulk creation from a list

For a CSV or table of designs (name, artwork, product, colours, sizes,
placements):

1. **Validate everything first**, creating nothing:
   - resolve product and variant ids; check availability for the region;
   - check placements/techniques against the product and conflicts;
   - run `check-print-ready.py` on every artwork file; host files and check
     each URL returns HTTP 200;
   - pace catalog reads at no more than 2 requests per second.
   Show a table of rows with problems and let the user fix or drop them.
2. **Mockups**: one `POST /v2/mockup-tasks` with many `products[]` (split
   into a few requests for very large lists), poll, download.
3. **Specs**: write one `<slug>.design.json` per row.
4. **Store products** (only if requested): create sequentially with
   `sleep 7` between v1 writes (10 per minute). If a 429 still appears,
   `pf.sh` waits and retries once; stop the batch on a second failure.
5. Keep a running results table (row, slug, spec file, sync product id or
   error) and show it at the end.
