# Printful API v2 endpoint reference (primary)

All paths are relative to `https://api.printful.com` and start with `/v2/`.
Source: https://developers.printful.com/docs/v2-beta/ (spec version
`2.0.0-beta`; Printful states all v2 endpoints are production-ready).

Use v2 for everything below. Only fall back to v1 for the gaps listed in
[endpoints-v1.md](endpoints-v1.md).

## Conventions

- **Envelope:** `{ "data": ..., "paging"?: { "total", "offset", "limit" }, "_links": {...} }`.
- **Pagination:** `offset` + `limit` (max 100, default 20) on every list.
- **Errors:** RFC 9457 `application/problem+json`:
  `{ "type", "status", "title", "detail", "instance"? }`. Validation errors can
  add `valid_values`. Orders, catalog and webhook endpoints still return the
  older `{ "error": { "message" } }` shape; `pf.sh` summarises both.
- **Timestamps:** ISO 8601 UTC strings (`2026-09-16T06:07:08Z`), not epoch.
- **Prices:** strings with up to 2 decimals.
- **Updates:** `PATCH` only changes the fields sent. Arrays (e.g.
  `placements`) must be sent whole.
- **Rate limit:** leaky bucket, default 120 requests / 60 s (refills ~2/s).
  Headers: `X-Ratelimit-Limit`, `X-Ratelimit-Remaining`, `X-Ratelimit-Reset`
  (seconds until a token frees), `X-Ratelimit-Policy`. On 429 honour
  `Retry-After`; `pf.sh` retries once automatically.
- **IDs:** v2 names catalog ids `catalog_product_id` / `catalog_variant_id`.
  Printful's docs use the same numbers as v1 `product_id` / `variant_id`
  (e.g. 71 / 4012 for Bella+Canvas 3001) and orders share one id space, but
  confirm with a `GET` in both versions before relying on a cross-version id.

## Stores and scopes

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/v2/stores` | `[{ id, type, name }]`. |
| GET | `/v2/stores/{store_id}` | One store. |
| GET | `/v2/stores/{store_id}/statistics` | Required: `date_from`, `date_to` (`YYYY-MM-DD`, max 6-month span), `report_types` (comma list). Optional `currency`. |
| GET | `/v2/oauth-scopes` | Scopes on the current token. |
| GET | `/v2/countries` | Countries and state codes. |

`report_types`: `sales_and_costs`, `sales_and_costs_summary`, `printful_costs`,
`profit`, `total_paid_orders`, `costs_by_amount`, `costs_by_product`,
`costs_by_variant`, `average_fulfillment_type` (request it by that name; the
response key is `average_fulfillment_time`). Results come back keyed by
report type, e.g. `profit: { value, relative_difference }`,
`sales_and_costs_summary: [{ date, order_count, costs, profit }]`.

## Catalog

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/v2/catalog-products` | Filters: `category_ids`, `colors`, `placements`, `techniques`, `selling_region_name`, `destination_country`, `new`; sort: `sort_type` (`new`, `rating`, `price`, `bestseller`), `sort_direction`. |
| GET | `/v2/catalog-products/{id}` | `techniques[]`, `placements[]` (with `layers[].layer_options`, `placement_options`, `conflicting_placements`), `product_options[]`, `sizes`, `colors`. |
| GET | `/v2/catalog-products/{id}/catalog-variants` | `[{ id, catalog_product_id, name, size, color, color_code, image }]`. |
| GET | `/v2/catalog-variants/{id}` | One variant. |
| GET | `/v2/catalog-categories`, `/v2/catalog-categories/{id}`, `/v2/catalog-products/{id}/catalog-categories` | Category tree. |
| GET | `/v2/catalog-products/{id}/prices`, `/v2/catalog-variants/{id}/prices` | Optional `selling_region_name`, `currency`. Returns base price per technique, per-placement `price` / `discounted_price` (first placement is discounted), layer add-ons, `discount_tiers` by quantity. |
| GET | `/v2/catalog-products/{id}/availability`, `/v2/catalog-variants/{id}/availability` | Stock per `technique` per `selling_regions[]` (`availability`: `in stock`, `out of stock`, `not fulfillable`, `unknown`). |
| GET | `/v2/catalog-products/{id}/sizes` | Size guide; `unit=inches,cm`. |
| GET | `/v2/catalog-products/{id}/images`, `/v2/catalog-variants/{id}/images` | Blank images (many transparent, overlay on `color_code`). |
| GET | `/v2/catalog-products/{id}/shipping-countries` | Where the product can ship. |
| GET | `/v2/catalog-products/{id}/mockup-styles` | Per placement: `technique`, `print_area_width`, `print_area_height` (inches), `print_area_type`, `dpi`, `mockup_styles[{ id, category_name, view_name, restricted_to_variants }]`. |
| GET | `/v2/catalog-products/{id}/mockup-templates` | Template geometry for advanced layouts. |

`selling_region_name` values: `worldwide` (default), `north_america`,
`canada`, `europe`, `spain`, `latvia`, `uk`, `france`, `germany`,
`australia`, `japan`, `new_zealand`, `italy`, `brazil`, `southeast_asia`,
`republic_of_korea`, `all`. For deliveries in Australia use `australia`.

Techniques: `dtg`, `digital`, `cut-sew`, `uv`, `embroidery`, `sublimation`, `dtfilm`.

**Required print pixels** for a placement = `print_area_width * dpi` by
`print_area_height * dpi` (from mockup-styles). `dpi` is the minimum Printful
accepts (usually 150); aim for 300 when the source allows.

## Designs: placements and layers (shared by orders and mockups)

```json
"placements": [
  {
    "placement": "front",
    "technique": "dtg",
    "print_area_type": "simple",
    "layers": [
      {
        "type": "file",
        "url": "https://cdn.example.com/designs/koala-front.png",
        "position": { "width": 10, "height": 12, "top": 2, "left": 1 },
        "layer_options": []
      }
    ],
    "placement_options": []
  }
]
```

- Layers take a public `url` only (no file-library id).
- `position` is in **inches** (min width/height 0.3). Omit it to centre the
  design automatically.
- Embroidery thread colours: `layer_options: [{ "name": "thread_colors", "value": ["#FFFFFF", "#000000"] }]`.
  If omitted, Printful auto-detects them.
- Valid `placement` / `technique` / `layer_options` combinations come from
  `GET /v2/catalog-products/{id}`. Placements listed in each other's
  `conflicting_placements` cannot be combined.
- Extra placements add cost (see `/prices`).

## Orders

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/v2/orders` | `offset`, `limit` only (no status filter: filter client-side). |
| POST | `/v2/orders` | Always creates a **draft**. Body below. |
| GET | `/v2/orders/{order_id}` | Full order incl. `costs`, `retail_costs`, `order_items`. Accepts `@external_id`. |
| PATCH | `/v2/orders/{order_id}` | Only in `draft` or `failed`. |
| DELETE | `/v2/orders/{order_id}` | **Deletes** (not cancels) an order in `draft`, `failed` or `canceled` that has never been charged. Guarded in `pf.sh`. |
| POST | `/v2/orders/{order_id}/confirmation` | Submits for fulfillment and **charges the billing method**. Only works when `costs.calculation_status` is `done`. A `failed` order (e.g. payment failed) can be confirmed again. Guarded in `pf.sh`. |
| GET / POST | `/v2/orders/{order_id}/order-items` | List (with full `placements`; `type=order_item` skips `branding_item`s) / add an item. `GET /v2/orders/{id}` only returns item summaries without placements. |
| GET / PATCH / DELETE | `/v2/orders/{order_id}/order-items/{order_item_id}` | One item; changes only in `draft` / `failed`. |
| GET | `/v2/orders/{order_id}/shipments` | Tracking (see below). |
| GET | `/v2/orders/{order_id}/invoices` | `{ media_type: "application/pdf", content: <base64> }`. Decode to a `.pdf`. |
| POST | `/v2/order-estimation-tasks` | Async cost estimate; body = `recipient` + `order_items` (+ `retail_costs`). Returns `{ id, status: "pending" }`. |
| GET | `/v2/order-estimation-tasks?id={task_id}` | `status`: `pending` / `completed` / `failed`; `costs`, `retail_costs`, `failure_reasons[]`. Estimates use STANDARD shipping. |
| POST | `/v2/shipping-rates` | All shipping methods for recipient + items. |

There is **no v2 cancel endpoint** for confirmed orders; use v1
`DELETE /orders/{id}` (guarded) while the order is still `pending`.

Create body:

```json
{
  "external_id": "merch-2026-0042",
  "shipping": "STANDARD",
  "recipient": {
    "name": "Jane Citizen",
    "address1": "12 Example St",
    "city": "Adelaide",
    "state_code": "SA",
    "country_code": "AU",
    "zip": "5000",
    "email": "jane@example.com",
    "phone": "+61400000000"
  },
  "order_items": [
    {
      "source": "catalog",
      "catalog_variant_id": 4012,
      "quantity": 1,
      "external_id": "koala-tee-m-black",
      "name": "Koala tee (M, black)",
      "placements": [
        { "placement": "front", "technique": "dtg",
          "layers": [ { "type": "file", "url": "https://cdn.example.com/designs/koala-front.png" } ] }
      ]
    },
    {
      "source": "product_template",
      "product_template_id": 123456789,
      "catalog_variant_id": 4013,
      "quantity": 1
    }
  ],
  "customization": {
    "gift": { "subject": "For you", "message": "Enjoy!" },
    "packing_slip": { "message": "Made with love" }
  },
  "retail_costs": { "currency": "AUD" }
}
```

- `order_items[].source`: `catalog` (design inline via `placements`) or
  `product_template` (a template saved in the Printful dashboard;
  `product_template_id` accepts `@external_id`). v2 cannot order a v1 sync
  product by `sync_variant_id`: use v1 `POST /orders` for that.
- `order_items` may be empty on create; add items later with
  `POST /v2/orders/{id}/order-items` (same item shape).
- `state_code` is required for US, CA and AU.
- Optional `orientation` (`horizontal`, `vertical`, `any`) for framed posters etc.;
  optional `product_options` for things like `stitch_color`, `inside_pocket`.

Order `status` values: `draft`, `inreview`, `pending`, `failed`, `canceled`,
`onhold`, `inprocess` (no longer cancellable), `partial`, `fulfilled`.

`costs` object: `calculation_status` (`calculating`, `done`, `failed`),
`currency`, `subtotal`, `discount`, `shipping`, `digitization`,
`additional_fee`, `fulfillment_fee`, `retail_delivery_fee`, `vat`, `tax`,
`total`. For AU deliveries Printful adds 10% GST (in `tax`/`vat`) unless the
account has an approved GST registration.

### Shipping rates

```json
{
  "recipient": { "country_code": "AU", "state_code": "SA", "city": "Adelaide", "zip": "5000" },
  "order_items": [ { "source": "catalog", "catalog_variant_id": 4012, "quantity": 1 } ],
  "currency": "AUD"
}
```

Shipping-rate items accept only `source: "catalog"` (optionally with
`placements` and `product_options`). To price a product-template item, send its
`catalog_variant_id` as a catalog item.

Result `data[]`: `shipping` (id to put on the order), `shipping_method_name`,
`rate`, `currency`, `min_delivery_days`, `max_delivery_days`,
`min_delivery_date`, `max_delivery_date`, `shipments[{ departure_country,
shipment_items[], customs_fees_possible }]`. Flag any shipment with
`departure_country` other than `AU` or `customs_fees_possible: true`.

### Shipments

`data[]`: `id`, `carrier`, `service`, `shipment_status` (`pending`, `onhold`,
`canceled`, `packaged`, `shipped`, `returned`, `outstock`), `delivery_status`
(`unknown`, `pre_transit`, `in_transit`, `out_for_delivery`,
`available_for_pickup`, `delivered`, `return_to_sender`, `failure`,
`canceled`), `shipped_at`, `delivered_at`, `departure_address`,
`tracking_number`, `tracking_url`, `tracking_events[{ triggered_at,
description }]`, `estimated_delivery{ from_date, to_date }`,
`shipment_items[{ order_item_id, order_item_name, quantity }]`, `is_reshipment`.

## Files

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/v2/files` | Body: `url` (required, public), `role` (`printfile` default, `label`, `preview`), `filename`, `visible`. Same URL twice returns the original file. |
| GET | `/v2/files/{id}` | Poll until `status` is `ok` (or `failed`). Returns `width`, `height`, `dpi`, `mime_type`, `size`, `preview_url`, `thumbnail_url`. |

Uploading is optional for orders (layers take a URL directly) but is the
cheapest way to have Printful confirm it can fetch and read the file. `.ai`,
`.psd` and `.tiff` are deprecated: use PNG (transparent) or JPG.

## Mockups

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/v2/mockup-tasks` | Body below. Returns task(s) with `id`, `status: pending`. |
| GET | `/v2/mockup-tasks?id={id}` | `data[]`: `status` (`pending`, `completed`, `failed`), `catalog_variant_mockups[{ catalog_variant_id, mockups[{ placement, display_name, technique, style_id, mockup_url }] }]`, `failure_reasons[]`. |

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
          "layers": [ { "type": "file", "url": "https://cdn.example.com/designs/koala-front.png" } ] }
      ]
    }
  ]
}
```

- `products[].source` may also be `product_template` with `product_template_id`.
- Several products can go in one request; prefer that to many requests.
- Poll no faster than every 5-10 s. Mockup URLs are temporary: download any
  worth keeping.

## Webhooks (optional; needs a public HTTPS endpoint)

`GET/POST/DELETE /v2/webhooks` (default URL + expiry + signing secret) and
`GET/POST/DELETE /v2/webhooks/{eventType}` per event. Event types:
`shipment_sent`, `shipment_returned`, `shipment_out_of_stock`,
`shipment_canceled`, `shipment_put_hold`, `shipment_put_hold_approval`,
`shipment_remove_hold`, `order_created`, `order_updated`, `order_failed`,
`order_canceled`, `order_put_hold`, `order_put_hold_approval`,
`order_remove_hold`, `product_synced`, `product_updated`, `product_deleted`,
`catalog_stock_updated` (every ~5 min), `catalog_price_changed`,
`mockup_task_finished`, `approval_sheet_status_changed`. The plugin polls by
default.

## Other v2 endpoints

- `GET /v2/warehouse-products`, `/v2/warehouse-products/{id}`: Printful
  Warehousing inventory (not print-on-demand products).
- `GET /v2/approval-sheets`, `/v2/approval-sheets/{confirm_hash}/download`:
  design approval sheets for orders on hold for approval.
