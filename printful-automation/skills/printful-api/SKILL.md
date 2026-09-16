---
name: printful-api
description: >
  This skill should be used whenever Claude needs to call the Printful API for
  any reason - it holds the authentication, API-version routing (v2 first, v1
  for gaps), request helper, local config, pagination, rate-limit, error and
  spending-safety conventions shared by every other Printful skill. Load it
  when the user says "call the Printful API", "check my Printful token",
  "which Printful store am I connected to", "set up my Printful config", "set
  my shipping address", or when another printful-* skill needs to make a
  request.
license: MIT
compatibility: Requires bash, curl, python3, network access to api.printful.com, and a PRINTFUL_API_TOKEN environment variable. jq recommended.
metadata:
  version: "0.2.0"
---

# Printful API conventions

Use this skill as the foundation for every Printful request. The other
`printful-*` skills assume these rules are in effect.

## Which API version

Printful runs two API versions on the same host with the same token. **Use v2
by default**; use v1 only for the gaps v2 does not cover yet.

| Use v2 (`/v2/...`) for | Use v1 (no prefix) only for |
| --- | --- |
| Catalog browsing, prices, stock by region, size guides | Saving a design as a store (sync) product and editing or deleting it |
| Print-area specs (`mockup-styles`) and mockups (`mockup-tasks`) | Ordering a saved product by `sync_variant_id` |
| File library upload/check | Listing product templates |
| Shipping rates, orders, order items, cost estimates, confirmation | Cancelling a confirmed order (`DELETE /orders/{id}`) |
| Shipments, tracking events, invoices | Pixel print-file specs, embroidery thread detection |
| Store statistics, stores, countries, scopes | |

Full references: [references/endpoints-v2.md](references/endpoints-v2.md)
(primary) and [references/endpoints-v1.md](references/endpoints-v1.md) (gaps).

The two versions differ in ways that break things if mixed up:

- **DELETE on an order:** v1 *cancels* it; v2 *deletes* an uncharged
  draft/failed/canceled order. v2 has no cancel.
- **Creating vs confirming:** v2 always creates a draft; confirmation is a
  separate call that only succeeds once `costs.calculation_status` is `done`.
- **Envelopes:** v1 `{ code, result, paging }`; v2 `{ data, paging, _links }`.
- **Errors:** v1 `error.message`; v2 RFC 9457 `title` + `detail` (orders and
  catalog still use `error.message`).
- **Timestamps:** v1 epoch seconds; v2 ISO 8601 UTC.
- **Design positions:** v1 pixels (`files[].position`); v2 inches
  (`placements[].layers[].position`).
- **Field names:** v1 `variant_id` / `items` / file `type`; v2
  `catalog_variant_id` / `order_items` / file `role`.

## Authentication

- The token lives in `PRINTFUL_API_TOKEN`. Never ask the user to paste it into
  chat and never write it into any file.
- If it is missing, tell the user to open https://developers.printful.com,
  create a **Private token** for their store with order, product
  (sync products), file library and webhook-read access, and export it as
  `PRINTFUL_API_TOKEN`. Then run `GET /v2/oauth-scopes` to confirm the scopes.
- Store-level tokens are bound to one store. Account-level tokens also need
  `PRINTFUL_STORE_ID` (sent as `X-PF-Store-Id`). If a request complains about
  a missing store, run `GET /v2/stores`, show the list and ask which id to
  export.
- For personal merch the store should be a **Manual order platform / API**
  store (type `native`), so orders are not tied to Shopify or Etsy.

## Local config

Personal settings live **outside the plugin** in
`${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}`:

```json
{
  "currency": "AUD",
  "selling_region": "australia",
  "ship_to": {
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
  "default_shipping": "STANDARD",
  "auto_confirm_max_total": null,
  "design_hosting": {
    "provider": "r2",
    "public_base_url": "https://pub-xxxx.r2.dev",
    "bucket": "merch-designs"
  }
}
```

- Read it at the start of any order, product or design task. If it does not
  exist, offer to create it: ask for the address and preferences, write the
  file with `chmod 600`, and never commit it or copy it into the plugin.
- `ship_to` is the default recipient. Only use it when the user means
  themselves ("ship it to me", "send it home"); ask otherwise.
- `auto_confirm_max_total` is a spending cap the **user** sets by editing the
  file. Claude must never create, raise or change this value itself, even if
  asked in passing; tell the user to edit the file. `null` (the default) means
  every order needs an explicit yes.
- `design_hosting` tells the design and files skills where to put images so
  Printful can fetch them by URL.

## Making requests

Always call the API through the bundled helper `scripts/pf.sh` (relative to
this skill's directory). Resolve it to an absolute path first, because the
working directory is usually the user's project:

```bash
PF="<this skill directory>/scripts/pf.sh"
bash "$PF" GET "/v2/catalog-products?selling_region_name=australia&limit=20"
bash "$PF" POST /v2/orders @/tmp/order.json
bash "$PF" PATCH /v2/orders/123 '{"shipping":"EXPRESS"}'
bash "$PF" GET /store/products          # v1
```

- The path decides the version: `/v2/...` is v2, anything else is v1.
- Write JSON bodies to a temp file and pass `@file`.
- stdout is the response body; stderr gets a one-line error summary. Exit
  codes: `1` HTTP error, `75` still rate limited after one automatic retry,
  `77` guarded call refused, `78` token missing.
- Pipe through `jq` when available (`command -v jq`); otherwise use
  `python3 -c 'import json,sys; ...'`.
- Report the error summary to the user verbatim when a request fails; it is
  usually specific (missing field, invalid variant, address problem).

## Pagination

Both versions use `offset` + `limit` (max 100). Loop while
`offset + limit < paging.total`. Never assume one page is everything.

## Rate limits

- **v2:** leaky bucket, about 120 requests per 60 s refilling ~2 per second.
  Pace loops at no more than 2 requests per second. `pf.sh` honours
  `Retry-After` on a 429 and retries once.
- **v1:** 120/min general; sync-product writes 10/min (sleep 7 s between
  them); a 429 locks the token out for 60 s (`pf.sh` waits and retries once).
- Poll async tasks (mockups, estimates, file processing) every 5-10 s, and
  give up after about 2 minutes with a clear message.

## Identifiers

- **Catalog product id** (v2 `catalog_product_id`, v1 `product_id`): a blank,
  e.g. 71 = Bella+Canvas 3001.
- **Catalog variant id** (v2 `catalog_variant_id`, v1 `variant_id`): one
  size/colour of a blank. Orders and mockups always use variant ids.
- **Sync product / sync variant id** (v1 only): an item saved in the store.
- **Product template id**: a design saved as a template in the dashboard;
  usable in v2 orders and mockups.
- **External id**: any id path segment accepts `@your-external-id` when the
  object was created with `external_id`.

## Spending and safety rules

`pf.sh` refuses the calls below unless `PF_CONFIRM=yes` is set on that single
command. Only set it after the conditions here are met.

| Action | Call | Requirement |
| --- | --- | --- |
| Confirm (pay for) an order | `POST /v2/orders/{id}/confirmation` (or v1 `POST /orders/{id}/confirm`, `POST /orders?confirm=`, `PUT /orders/{id}?confirm=`) | Costs `done`; full summary with total shown; explicit yes in this conversation, **or** the auto-confirm rule below. |
| Cancel a confirmed order | v1 `DELETE /orders/{id}` | Show id, items, total; explicit yes. |
| Delete a draft order | `DELETE /v2/orders/{id}` | Show id and items; explicit yes. |
| Delete a product, variant or template | v1 `DELETE /store/...`, `/sync/...`, `/product-templates/...` | Show name and variant count; explicit yes. |

**Auto-confirm rule:** an order may be confirmed without asking only if
*all* of these hold: `auto_confirm_max_total` in the config is a number; the
order's `costs.total` (including GST, tax and shipping) is at or below it and
`costs.currency` equals the config `currency`; the recipient matches
`ship_to`; and the user asked in this conversation for the order to be placed.
Still show the summary afterwards.

Never chain create-and-confirm for anything else. Reads (GET), drafts, file
uploads, estimates and mockups need no confirmation once the user has
described what they want.

Payment is taken from the store's Printful billing method (Printful Wallet,
card or PayPal) set in the dashboard. The API cannot add or change payment
methods. If confirmation leaves the order `failed` because of payment, tell
the user to top up the Wallet or fix the billing method in the Printful
dashboard (Billing section), then confirm again (v2 allows
re-confirming a `failed` order).

## Quick sanity check

To verify the setup, run `GET /v2/stores` and `GET /v2/oauth-scopes`, then
report the store name, id and type, the scopes, and whether the local config
file exists. Do this first when a user says the plugin "isn't working".
