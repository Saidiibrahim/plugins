---
name: printful-product
description: >
  This skill should be used when the user wants to create or manage products in
  their Printful store - phrases like "create a new product on Printful",
  "add this design to a t-shirt", "generate mockups", "which Printful blanks
  can I use", "browse the Printful catalog", "find the variant id for",
  "update the price of", "list my Printful products", "delete this product",
  or "check if this variant is in stock".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, network access, and PRINTFUL_API_TOKEN.
metadata:
  version: "0.1.0"
---

# Printful products

Handle the product lifecycle: find a blank in the catalog, check print specs,
generate mockups, then create or update a sync product. Load the
`printful-api` skill first for auth, the request helper and rate limits.

Invoke the helper at `../printful-api/scripts/pf.sh`, resolved against this skill's
directory (set `PF` to that absolute path before running commands).

## 1. Find the blank

1. If the user names a product type ("hoodie", "mug", "tote"), fetch
   `GET /categories` once, match the closest category, then
   `GET /products?category_id=<id>&limit=100`.
2. If they name a brand/model (Bella+Canvas 3001, Gildan 18500, Stanley/Stella
   Creator), search the product list by `brand` and `model` fields instead.
3. Present a short table: product id, title, brand/model, techniques, number
   of variants, base price range. Keep it to the most relevant 5-10 results and
   ask the user to pick one unless they already specified it.

## 2. Pick variants and check availability

1. `GET /products/{product_id}` and read `result.variants[]`.
2. Filter by the colours and sizes the user wants. Map each to its `variant_id`.
3. Check `availability_status[]` for the region the user ships from or to
   (`region` values include `AU`, `EU`, `US`, `UK`, `CA`, `JP`, `BR`, `LV`).
   Warn about any variant that is `out_of_stock` or `discontinued` for the
   relevant region rather than silently including it.
4. If the store syncs to an external platform (Shopify, Etsy, WooCommerce),
   follow that platform's naming and SKU conventions; for a Printful-only
   store, skip this.

## 3. Get print-area specs

`GET /mockup-generator/printfiles/{product_id}` returns the print area for
each placement (`width`, `height`, `dpi`, `fill_mode`). Compare the user's
design dimensions against it and tell them if the file is too small for the
DPI (design pixels < print area pixels means upscaling and soft print). For
DTG, 150 DPI at print size is the minimum; 300 is ideal.

If the design is a local file, hand off to the `printful-files` skill to host
it or upload it to the file library first; the product endpoints only accept
URLs or file-library ids.

## 4. Generate mockups (optional but recommended)

1. `POST /mockup-generator/create-task/{product_id}` with the chosen
   `variant_ids`, `format: "png"`, and one `files[]` entry per placement. Omit
   `position` unless the user wants specific placement; Printful fits the file
   to the print area.
2. Sleep 10 seconds, then `GET /mockup-generator/task?task_key=<key>`. Repeat
   every 10 seconds until `status` is `completed` or `failed` (give up after
   2 minutes and report).
3. Show the `mockup_url` list. Offer to download them into the working
   directory because the URLs expire within about 72 hours.
4. Use one mockup URL as the product `thumbnail`.

Mockup generation has its own low rate limit; batch all variants of one product
into a single task rather than one task per variant.

## 5. Create the sync product

1. Build the body from `references/endpoints.md` in `printful-api`: one
   `sync_variants[]` entry per chosen variant with `variant_id`,
   `retail_price`, an `external_id`/`sku` pattern the user likes (propose
   `<slug>-<size>-<colour>` if they have none), and the same `files[]` for
   every variant (or per-colour files if the design differs by colour).
2. Retail price: if the user gives a margin instead of a price, compute
   `retail = ceil((base_price * (1 + margin)) * 100) / 100` from the variant's
   catalog `price` and show the calculation before creating.
3. Show a one-screen summary (name, variant count, price(s), placements) and
   ask for a go-ahead before `POST /store/products`. This write counts toward
   the 10-per-minute product limit, so space bulk creations by 7 seconds.
4. On success report the new `sync_product.id` and the dashboard link
   `https://www.printful.com/dashboard/sync-products/<id>`.

## Updating and deleting

- Price or name change: `GET /store/products/{id}`, modify only the fields the
  user asked for, `PUT /store/products/{id}` with the full `sync_product` and
  the affected `sync_variants` (include each variant's `id` so it updates
  rather than duplicates).
- Add a size/colour: `POST /store/products/{id}/variants`.
- Delete: show the product name and variant count, get explicit confirmation,
  then `DELETE /store/products/{id}`. Deletion is permanent.

## Bulk creation from a spreadsheet or list

When the user supplies a CSV or table of designs, process rows sequentially:
validate every row (design URL reachable, variant ids resolved, prices set)
before creating anything, then create with 7 second spacing and keep a running
results table (row, product id or error). Deliver the results table at the end.

## Listing

`GET /store/products?limit=100` (page through). Present id, name, variant
count, `synced` flag, and thumbnail. For a single product show each variant's
size, colour, retail price and file placements.
