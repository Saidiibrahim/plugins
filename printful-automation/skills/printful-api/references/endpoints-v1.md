# Printful API v1 endpoint reference (gaps only)

All paths are relative to `https://api.printful.com` with no version prefix.
Source: https://developers.printful.com/docs/

Use v1 **only** for the jobs below, which v2 cannot do yet. Everything else
(catalog, prices, stock, mockups, files, shipping rates, orders, shipments,
statistics) is in [endpoints-v2.md](endpoints-v2.md).

| Job | Why v1 |
| --- | --- |
| Save a design as a reusable store product (sync product) | v2 has no product-management endpoints. |
| Order a saved product by `sync_variant_id` | v2 order items accept only `catalog` or `product_template` sources. |
| List product templates | v2 can *use* a template id but cannot list templates. |
| Cancel a confirmed order | v2 has no cancel endpoint; v2 `DELETE` only removes uncharged drafts. |
| Pixel-based print-file specs | `mockup-generator/printfiles` returns pixel sizes; v2 gives inches + dpi. |
| Detect embroidery thread colours from a file | `files/thread-colors`; v2 auto-detects at order time. |

## v1 conventions

- **Envelope:** `{ "code": 200, "result": ..., "paging"?: { "total", "offset", "limit" } }`.
- **Errors:** `{ "code": 400, "result": "...", "error": { "reason", "message" } }`.
- **Timestamps:** UNIX epoch seconds. **Prices:** strings, 2 decimals.
- **Pagination:** `offset` + `limit` (max 100).
- **Rate limits:** 120 requests/min general; sync-product writes 10/min
  (space writes 7 s apart); a 429 locks the token out for 60 s.
- **External ids:** any id path segment accepts `@your-external-id`.
- **Scopes:** `sync_products` (or `sync_products/read`), `orders`, `file_library`.

## Store products (sync products): writes 10 req/min

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/store/products?offset=0&limit=100&status=all` | Items: `id`, `external_id`, `name`, `variants` (count), `synced`, `thumbnail_url`, `is_ignored`. |
| GET | `/store/products/{id}` | `result.sync_product` + `result.sync_variants[]` (each has `id`, `variant_id`, `retail_price`, `files[]`, `options[]`, `availability_status`). |
| POST | `/store/products` | Create. Body below. |
| PUT | `/store/products/{id}` | Modify. Include each variant's `id` so it updates instead of duplicating. |
| DELETE | `/store/products/{id}` | Delete product and all variants. Guarded in `pf.sh`. |
| GET / PUT / DELETE | `/store/variants/{id}` | One sync variant (DELETE guarded). |
| POST | `/store/products/{id}/variants` | Add a variant. |

Create body:

```json
{
  "sync_product": {
    "name": "Koala Tee",
    "thumbnail": "https://cdn.example.com/mockups/koala-tee-front.png",
    "external_id": "koala-tee"
  },
  "sync_variants": [
    {
      "variant_id": 4012,
      "external_id": "koala-tee-m-black",
      "retail_price": "39.95",
      "sku": "KOALA-M-BLK",
      "files": [
        { "type": "front", "url": "https://cdn.example.com/designs/koala-front.png" }
      ],
      "options": []
    }
  ]
}
```

- `variant_id` here is the catalog variant id (v2 `catalog_variant_id`).
- `files[].type` is the placement (`default`/`front`, `back`, `sleeve_left`,
  `sleeve_right`, `label_inside`, `embroidery_chest_left`, ...). Valid names
  per product come from `/mockup-generator/printfiles/{product_id}`.
- `files[]` accepts a public `url` or a file-library `id`
  (`{ "type": "front", "id": 123456 }`).
- Optional `position` (pixels): `{ area_width, area_height, width, height,
  top, left, limit_to_print_area }`. Omit to auto-fit.
- `retail_price` is required by some store types; for a personal store use
  the catalog price or any placeholder the user chooses.

## Ecommerce-platform sync products (only for Shopify/Etsy/Woo stores)

`GET /sync/products`, `GET /sync/products/{id}`, `DELETE /sync/products/{id}`,
`GET/PUT/DELETE /sync/variant/{id}` (DELETEs guarded).

## Product templates

`GET /product-templates?offset=0&limit=100`, `GET /product-templates/{id}`
(`@external_id` allowed), `DELETE /product-templates/{id}` (guarded).
Templates are created in the Printful dashboard (Product templates). Order one
through v2 with `source: "product_template"`.

## Orders (v1 only for saved products and cancellation)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/orders` | Draft order for **sync variants**. Never add `?confirm=` (guarded). |
| GET | `/orders/{id}` | v1 view of the order (`costs`, `shipments[]`). |
| POST | `/orders/{id}/confirm` | Charges the billing method. Guarded. |
| DELETE | `/orders/{id}` | **Cancels** the order while `draft` or `pending` (before production). Guarded. |
| POST | `/orders/estimate-costs` | Synchronous estimate for a sync-variant body. |

Sync-variant order body:

```json
{
  "external_id": "merch-2026-0043",
  "shipping": "STANDARD",
  "recipient": {
    "name": "Jane Citizen", "address1": "12 Example St", "city": "Adelaide",
    "state_code": "SA", "country_code": "AU", "zip": "5000",
    "email": "jane@example.com", "phone": "+61400000000"
  },
  "items": [ { "sync_variant_id": 1781126754, "quantity": 1 } ]
}
```

Orders live in one system, so a v1-created draft should also be readable at
`GET /v2/orders/{id}` (which gives v2 costs and shipments). Check that the
v2 read succeeds before relying on it; if it does, confirm through the v2
flow in the `printful-order` skill, otherwise estimate with
`POST /orders/estimate-costs` and confirm with `POST /orders/{id}/confirm`.

## Mockup generator print-file specs

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/mockup-generator/printfiles/{product_id}` | `printfiles[{ printfile_id, width, height, dpi, fill_mode, can_rotate }]` in pixels, `variant_printfiles[{ variant_id, placements{ front: printfile_id } }]`, `available_placements{}`. |

Generate mockups with v2 `/v2/mockup-tasks` instead of the v1 task endpoints.

## Files

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/files/thread-colors` | Body `{ "file_url": "https://..." }`. Returns `thread_colors[]` (hex) detected for embroidery. |
| GET | `/files/{id}` | Same library as v2; either version can read it. |

## Packing slip defaults

`POST /packing-slip` with `email`, `phone`, `message`, `logo_url`,
`store_name`, `custom_order_id` sets store-wide defaults. Per-order
overrides go in v2 `customization.packing_slip`.
