# Printful API v1 endpoint reference

All paths are relative to `https://api.printful.com`. Responses are wrapped in
`{ "code", "result", "paging?" }`. Source: https://developers.printful.com/docs/

## Store

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/stores` | List stores the token can access (`id`, `name`, `type`). |
| GET | `/stores/{id}` | One store. |
| POST | `/packing-slip` | Body: `email`, `phone`, `message`, `logo_url`, `store_name`, `custom_order_id`. |
| GET | `/countries` | Accepted countries and state codes. |
| GET | `/oauth/scopes` | Scopes granted to the current token. |

## Catalog (blank products) - 30 req/min

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/products?category_id=24&offset=0&limit=50` | `category_id` accepts comma-separated ids. Result items: `id`, `type`, `type_name`, `title`, `brand`, `model`, `image`, `variant_count`, `techniques[]`, `files[]` (placements), `options[]`. |
| GET | `/products/{id}` | `result.product` plus `result.variants[]` (`id`, `name`, `size`, `color`, `color_code`, `price`, `in_stock`, `availability_status[]` by region). |
| GET | `/products/variant/{id}` | One variant with its parent product. |
| GET | `/products/{id}/sizes` | Size guide (cm and inches). |
| GET | `/categories` and `/categories/{id}` | Category tree. |

## Store products (sync products) - writes 10 req/min

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/store/products?offset=0&limit=20&status=all` | List. Result items: `id`, `external_id`, `name`, `variants` (count), `synced`, `thumbnail_url`, `is_ignored`. |
| GET | `/store/products/{id}` | `result.sync_product` + `result.sync_variants[]`. |
| POST | `/store/products` | Create. Body below. |
| PUT | `/store/products/{id}` | Modify (same shape; variants listed replace/update by `id`). |
| DELETE | `/store/products/{id}` | Delete product and all variants. |
| GET | `/store/variants/{id}` | One sync variant. |
| POST | `/store/products/{id}/variants` | Add a variant. |
| PUT | `/store/variants/{id}` | Modify a variant. |
| DELETE | `/store/variants/{id}` | Delete a variant. |

Create body:

```json
{
  "sync_product": {
    "name": "Adelaide Sunset Tee",
    "thumbnail": "https://example.com/thumb.png",
    "external_id": "tee-sunset-001"
  },
  "sync_variants": [
    {
      "variant_id": 4012,
      "external_id": "tee-sunset-001-m-black",
      "retail_price": "34.99",
      "sku": "SUNSET-M-BLK",
      "files": [
        { "type": "front", "url": "https://example.com/front.png",
          "position": { "area_width": 1800, "area_height": 2400,
                        "width": 1800, "height": 1800, "top": 300, "left": 0,
                        "limit_to_print_area": true } }
      ],
      "options": [ { "id": "thread_colors", "value": "#FF0000" } ]
    }
  ]
}
```

- `files[].type` is the placement: `default` (= front for most items), `front`,
  `back`, `left`, `right`, `sleeve_left`, `sleeve_right`, `label_inside`,
  `label_outside`, `embroidery_front`, `embroidery_back`, `embroidery_left`,
  `embroidery_right`, `embroidery_chest_left`, `embroidery_chest_center`,
  `embroidery_wrist_left`, `embroidery_wrist_right`, plus product-specific ones
  returned by `/mockup-generator/printfiles/{product_id}`.
- `files[].url` must be a publicly reachable URL, or use a file-library id via
  `{ "type": "front", "id": 123456 }`.
- `position` is optional; omit it to let Printful fit the file to the print area.
- `thumbnail` is optional; use a generated mockup URL after mockups finish.

## Ecommerce-platform sync products (only when a store is connected to Shopify, Etsy etc.)

| Method | Path |
| --- | --- |
| GET | `/sync/products?status=synced&offset=0&limit=20` |
| GET | `/sync/products/{id}` |
| DELETE | `/sync/products/{id}` |
| GET | `/sync/variant/{id}` |
| PUT | `/sync/variant/{id}` |
| DELETE | `/sync/variant/{id}` |

## Product templates (account-level tokens only)

`GET /product-templates`, `GET /product-templates/{id}`, `DELETE /product-templates/{id}`.

## Orders

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/orders?status=pending&offset=0&limit=20` | `status`: `draft`, `pending`, `failed`, `canceled`, `inprocess`, `onhold`, `partial`, `fulfilled`, `archived`, or omit for all. |
| GET | `/orders/{id}` | Full order incl. `costs`, `retail_costs`, `items[]`, `shipments[]`. |
| POST | `/orders` | Create a **draft**. Add `?confirm=true` to submit immediately (only with user approval). |
| PUT | `/orders/{id}` | Update a draft (same body; omitted `items` are deleted). |
| POST | `/orders/{id}/confirm` | Submit a draft for fulfillment. **Charges the account.** |
| DELETE | `/orders/{id}` | Cancel. Only possible while `draft`, `pending`, or before production starts. |
| POST | `/orders/estimate-costs` | Same body as create; returns costs without creating anything. |

Create body:

```json
{
  "external_id": "ORD-2026-0042",
  "shipping": "STANDARD",
  "recipient": {
    "name": "Jane Citizen",
    "address1": "12 Example St",
    "address2": "",
    "city": "Adelaide",
    "state_code": "SA",
    "country_code": "AU",
    "zip": "5000",
    "email": "jane@example.com",
    "phone": "+61400000000"
  },
  "items": [
    { "sync_variant_id": 1781126754, "quantity": 1, "retail_price": "34.99" },
    { "variant_id": 4012, "quantity": 2, "retail_price": "34.99",
      "files": [ { "type": "front", "url": "https://example.com/front.png" } ] }
  ],
  "retail_costs": { "currency": "AUD", "subtotal": "104.97", "shipping": "9.95", "tax": "0.00" },
  "gift": { "subject": "Happy birthday", "message": "Enjoy!" },
  "packing_slip": { "email": "support@example.com", "message": "Thanks for your order" }
}
```

- Use `sync_variant_id` for store items (design already attached) or
  `variant_id` + `files` for one-off items.
- `state_code` is required for US, CA and AU addresses.
- `shipping` ids come from `/shipping/rates`; common values: `STANDARD`,
  `EXPRESS`, `PRINTFUL_FAST` (varies by region).

Order object highlights: `id`, `external_id`, `status`, `created`, `updated`,
`recipient`, `items[]`, `costs { currency, subtotal, discount, shipping, tax,
vat, total }`, `retail_costs`, `shipments[] { id, carrier, service,
tracking_number, tracking_url, created, ship_date, shipped_at, items[] }`.

Order status lifecycle: `draft` -> `pending` (confirmed, payment processing)
-> `inprocess` (in production) -> `partial` / `fulfilled` (shipped). Side
states: `failed` (payment or address problem - read `error` on the order),
`onhold` (needs action in the dashboard), `canceled`, `archived`.

## Shipping rates - 120 req/min

`POST /shipping/rates` body:

```json
{ "recipient": { "country_code": "AU", "state_code": "SA", "zip": "5000" },
  "items": [ { "variant_id": 4012, "quantity": 1 } ],
  "currency": "AUD" }
```

Result: `[ { "id": "STANDARD", "name": "Flat Rate (Estimated delivery: ...)", "rate": "9.95", "currency": "AUD", "minDeliveryDays": 5, "maxDeliveryDays": 10 } ]`.

## File library

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/files` | Body: `url` (required, public), `type` (placement, default `default`), `filename`, `visible` (bool), `options[]`. Returns `id`, `status` (`waiting` / `ok` / `failed`), `preview_url`, `thumbnail_url`, `width`, `height`, `dpi`. |
| GET | `/files/{id}` | Poll until `status` is `ok`. |
| POST | `/files/extract-colors` | Body: `{ "url": "..." }`. Returns the embroidery thread colours detected. |

Files must be a public URL; the API does not accept multipart uploads. For a
local file, host it first (e.g. a cloud-storage share link with direct
download, or the user's own web server). The `printful-files` skill covers this.

## Mockup generator - low rate limit; poll no sooner than every 10 s

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/mockup-generator/printfiles/{product_id}` | Print-area sizes and allowed placements per variant. |
| GET | `/mockup-generator/templates/{product_id}` | Mockup template metadata. |
| POST | `/mockup-generator/create-task/{product_id}` | Start a task. Body below. Returns `task_key`, `status: pending`. |
| GET | `/mockup-generator/task?task_key=...` | Poll. When `status` is `completed`, `result.mockups[]` holds `placement`, `variant_ids`, `mockup_url`, `extra[]`. |

Create-task body:

```json
{
  "variant_ids": [4012, 4013],
  "format": "png",
  "files": [
    { "placement": "front", "image_url": "https://example.com/front.png",
      "position": { "area_width": 1800, "area_height": 2400,
                    "width": 1800, "height": 1800, "top": 300, "left": 0 } }
  ],
  "option_groups": ["Flat"],
  "options": ["Front"],
  "product_options": [ { "id": "thread_colors", "value": "#FF0000" } ]
}
```

Mockup URLs expire after roughly 72 hours; download or re-host any the user
wants to keep as product thumbnails.

## Webhooks (read-only use in this plugin)

`GET /webhooks` returns `{ url, types[], params }`. `POST /webhooks` with
`{ "url", "types": [...] }` registers; `DELETE /webhooks` disables. Event
types: `package_shipped`, `package_returned`, `order_created`,
`order_updated`, `order_failed`, `order_canceled`, `order_put_hold`,
`order_put_hold_approval`, `order_remove_hold`, `order_refunded`,
`product_synced`, `product_updated`, `product_deleted`, `stock_updated`.
Registering requires a public HTTPS endpoint the user controls; the report
skill polls instead.

## API v2 (beta)

Same host with `/v2/` prefix; envelope is `{ "data", "_links", "paging" }`,
errors follow RFC 9457. Covers catalog, orders (itemised), shipments, files,
webhooks. Only reach for it when a v1 endpoint cannot do the job (e.g.
catalog pricing by region: `GET /v2/catalog-products/{id}/prices`).
