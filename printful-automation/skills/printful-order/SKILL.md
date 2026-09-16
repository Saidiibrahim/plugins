---
name: printful-order
description: >
  This skill should be used when the user wants to buy, pay for, ship, track
  or manage Printful orders for their own custom merch - phrases like "place
  an order", "order this shirt", "buy this", "make me one", "ship it to me",
  "send it home", "pay for it", "how much will this cost", "shipping options",
  "confirm the order", "go ahead and order it", "where is my order", "track my
  order", "has it shipped", "order status", "list my orders", "which orders
  failed", "get the invoice", "download the receipt", "change the draft",
  "delete the draft", "cancel my order", or "reorder" / "order another one".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, python3, network access to api.printful.com, and PRINTFUL_API_TOKEN.
metadata:
  version: "0.2.0"
---

# Printful orders

Price, create, confirm (pay for), edit, cancel, track and invoice orders.
Load the `printful-api` skill first; its safety rules apply to everything
here. Set these absolute paths before running commands:

```bash
PF="<this skill directory>/../printful-api/scripts/pf.sh"
GATE="<this skill directory>/scripts/confirm-gate.py"
WAIT="<this skill directory>/scripts/wait-order-costs.sh"
CONFIG="${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}"
```

Use v2 for everything except ordering a saved (sync) product and cancelling a
confirmed order. Endpoint details: `../printful-api/references/endpoints-v2.md`
and `endpoints-v1.md`. Write request bodies to a temp file and pass `@file`.

## Helper scripts

| Script | Does | Exit codes |
| --- | --- | --- |
| `scripts/wait-order-costs.sh ORDER_ID [timeout_s]` | Polls `GET /v2/orders/{id}` every 5 s until `costs.calculation_status` is `done` or `failed`; prints the last order JSON. Default timeout 120 s. | `0` done, `2` failed, `124` timeout, other = `pf.sh` code |
| `scripts/confirm-gate.py [ORDER_JSON\|-] [--config PATH]` | Prints `{"ready", "auto_confirm_allowed", "reasons", "summary"}` for a v2 order (file or stdin, with or without the `data` envelope). | `0` verdict printed, `64` bad input |

`confirm-gate.py` is deterministic: `ready` needs status `draft` or `failed`
and calculation `done`; `auto_confirm_allowed` additionally needs a numeric
`auto_confirm_max_total`, `total <= cap` (decimal maths), matching currency,
status `draft` (a `failed` order always needs an explicit yes), at least one
item with quantity > 0, and a recipient equal to `ship_to` (normalised name,
address1, address2, city, state_code, country_code, zip; `ship_to` must have
name, address1, city, country_code and zip filled in). Treat its verdict as a floor: never confirm when it says
no, and never skip the conversation check it cannot do.

## 1. Place an order for custom merch (main path, v2)

1. **Read the config** (`$CONFIG`). If missing, offer to create it as the
   `printful-api` skill describes. Use its `currency` and `selling_region`.
2. **Recipient.** Use `ship_to` only when the user means themselves ("ship it
   to me", "send it home"). For anyone else ask for name, address1, city,
   state_code (required for AU, US, CA), country_code, zip, and email. Never
   guess an address.
3. **Build `order_items`.**
   - From a design spec (`<slug>.design.json`, written by `printful-product`):
     for each chosen variant in `catalog_variant_ids`, first re-check
     `GET /v2/catalog-variants/<id>/availability?selling_region_name=<config selling_region>`
     and stop to ask if it is not `in stock` for the placement techniques.
     Then build
     `{ "source": "catalog", "catalog_variant_id": <id>, "quantity": n, "name": ..., "placements": <spec placements>, "product_options": <spec product_options> }`,
     omitting `product_options` when empty.
   - Design inline: `source: "catalog"`, `catalog_variant_id`, `quantity`,
     `name`, and `placements[]` with `layers[{ type: "file", url }]` pointing
     at the public design URL. Variant, placement and technique come from the
     `printful-product` skill; the hosted URL from `printful-files`.
   - Dashboard template: `source: "product_template"`, `product_template_id`,
     `catalog_variant_id`, `quantity`.
   - Add an `external_id` to the order when the user has a reference for it.
4. **Shipping options.** `POST /v2/shipping-rates` with `recipient`,
   `order_items` (only `source: "catalog"` is accepted here: for a template
   item send its `catalog_variant_id` as a catalog item) and `currency`.
   Present a table: method (`shipping`, `shipping_method_name`), `rate` and
   currency, delivery dates (`min_delivery_date` to `max_delivery_date`),
   departure country, customs flag. **Warn** when any shipment's
   `departure_country` is not `AU` (slower, possible duties) or
   `customs_fees_possible` is true. Default to config `default_shipping` if
   offered, else the cheapest; let the user choose.
5. **Create the draft.** `POST /v2/orders` with `shipping`, `recipient`,
   `order_items` (and `external_id`, `customization` if wanted). v2 always
   creates a draft. Note `data.id`.
6. **Wait for costs.** `bash "$WAIT" <id> > /tmp/pf-order-<id>.json`.
   On exit `2`, show the order and explain why (usually a bad placement,
   an unreachable design URL, an unavailable variant or an address problem),
   fix it by editing the draft (section 6) and wait again. On `124`, say
   costs are still calculating and offer to check again shortly.
7. **Summarise.** Get full items with
   `GET /v2/orders/<id>/order-items?type=order_item` for the placements, then
   show:

   | Field | Source |
   | --- | --- |
   | Order id, external id, status | `id`, `external_id`, `status` |
   | Ship to | `recipient` name, city, state, country, zip |
   | Items | name, variant id, quantity, unit price |
   | Placements | placement, technique, design URL per item |
   | Shipping method | `shipping` plus chosen rate's delivery dates |
   | Subtotal, discount, shipping | `costs.subtotal`, `discount`, `shipping` |
   | Other fees | `digitization`, `additional_fee`, `fulfillment_fee`, `retail_delivery_fee` when non-zero |
   | GST / tax / VAT | `costs.tax`, `costs.vat` (AU deliveries include 10% GST unless GST-registered) |
   | **Total** | `costs.total` + `costs.currency` |

   Also give the dashboard link `https://www.printful.com/dashboard/default/orders`.
8. **Confirmation gate** (section 4).

## 2. Order a saved store product (v1)

v2 cannot order by `sync_variant_id`. Resolve it with `GET /store/products`
then `GET /store/products/{id}` (`sync_variants[]` by size and colour), get
shipping options as in step 4 using the variants' catalog `variant_id`, then
`POST /orders` (v1 body: `recipient`, `shipping`,
`items[{ sync_variant_id, quantity }]`). Never add `?confirm=` (guarded).

Then read the new id through v2: `bash "$WAIT" <id>`. If that succeeds, run
steps 7-8 and the v2 gate exactly as for custom merch. If the v2 read fails,
fall back to `POST /orders/estimate-costs` for the summary, require an
explicit yes (no auto-confirm on this path), and confirm with
`PF_CONFIRM=yes bash "$PF" POST /orders/<id>/confirm`, then
`GET /orders/<id>` to report the status.

## 3. Cost estimate without creating an order

For "how much would it cost":

1. `POST /v2/order-estimation-tasks` with `recipient` and `order_items`
   (same shapes as above). Note `data.id`.
2. Poll `GET /v2/order-estimation-tasks?id=<task_id>` every 5 s, up to about
   2 minutes, until `data.status` is `completed` or `failed` (show
   `failure_reasons[]`).
3. Show `costs` like the summary table. The estimate always prices
   **STANDARD** shipping: for another method, also call
   `POST /v2/shipping-rates` and present estimate total minus
   `costs.shipping` plus that method's `rate`, labelled approximate (tax may
   change with shipping). Nothing is created or charged.

## 4. Confirmation gate

Confirming charges the store's billing method and starts production.

1. Re-fetch the order immediately before the gate (never reuse an older file): `bash "$PF" GET /v2/orders/<id> > /tmp/pf-order-<id>.json`
   (or reuse the output of `$WAIT` if nothing changed since).
2. `python3 "$GATE" /tmp/pf-order-<id>.json --config "$CONFIG"`.
3. Decide:
   - `ready: false`: do not confirm. Explain `reasons` (still calculating ->
     wait; calculation failed -> fix; status not draft/failed -> already
     submitted).
   - `ready: true`, `auto_confirm_allowed: true` **and** the user asked in
     this conversation for this order to be placed ("order it", "buy it",
     "place the order"): confirm without asking, then show the summary and
     say it was auto-confirmed under the configured cap.
   - Otherwise: show the summary with the total and currency and ask
     "Confirm and pay <total> <currency> for order <id>?" Proceed only on an
     explicit yes to that question. An earlier "make me a shirt" is not a yes.
4. Confirm: `PF_CONFIRM=yes bash "$PF" POST /v2/orders/<id>/confirmation`.
   Set `PF_CONFIRM` on that one command only.
5. Re-read `GET /v2/orders/<id>` and report the new status (normally
   `pending` or `inreview`).

If the order ends up `failed` after confirming, payment usually failed: tell
the user to top up the Printful Wallet or fix the card/PayPal in the
Printful dashboard (Billing), wait for them to say it is fixed, then run the
gate again from step 1 (a `failed` order can be re-confirmed). If the error
is not about payment, show it and fix the draft instead.

Never create, raise or change `auto_confirm_max_total`; if the user wants a
cap, tell them to edit the config file themselves.

## 5. Order statuses (v2)

| Status | Meaning | What can be done |
| --- | --- | --- |
| `draft` | Created, not submitted, not charged | Edit, delete, confirm |
| `inreview` | Submitted; Printful is checking it | Wait; cancel via v1 may work |
| `pending` | Confirmed and charged, waiting for production | Cancel via v1 |
| `failed` | Submission failed (often payment or a file problem) | Fix, re-confirm, or delete |
| `canceled` | Cancelled; refunded to the billing method if charged | Delete if never charged |
| `onhold` | Needs action (approval, address, billing) in the dashboard | Resolve in dashboard |
| `inprocess` | In production | Cannot cancel; contact support |
| `partial` | Some items shipped | Track shipments |
| `fulfilled` | Everything shipped | Track, invoice, reorder |

## 6. Edit, delete or cancel

**Edit a draft** (only `draft` or `failed`):

- `PATCH /v2/orders/<id>` changes only the fields sent (`shipping`,
  `recipient`, `customization`, `external_id`). Arrays are replaced whole:
  sending `order_items` replaces all items, so avoid it for single-item
  changes.
- Items: `POST /v2/orders/<id>/order-items` (add),
  `PATCH /v2/orders/<id>/order-items/<item_id>` (quantity, placements - send
  the complete `placements` array), `DELETE .../order-items/<item_id>`
  (remove). `source` cannot be changed: delete and re-add instead.
- After any edit, costs recalculate: run `$WAIT`, show old vs new total, and
  pass the gate again before confirming.

**Delete a draft** (`draft`, `failed` or `canceled`, never charged): show id,
items and recipient, get an explicit yes, then
`PF_CONFIRM=yes bash "$PF" DELETE /v2/orders/<id>`. This removes the order;
it is not a cancel.

**Cancel a confirmed order** (`pending`, possibly `inreview` or `onhold`):
show id, items and total, get an explicit yes, then
`PF_CONFIRM=yes bash "$PF" DELETE /orders/<id>` (v1: DELETE means cancel),
then `GET /v2/orders/<id>` to report the status. If it is `inprocess` or the
API refuses, tell the user production has started and to contact Printful
support from the order page in the dashboard.

## 7. Tracking ("where is my order")

1. If no id is given, list recent orders (section 8) and match by item,
   date or recipient; ask if unclear.
2. `GET /v2/orders/<id>` for status, then `GET /v2/orders/<id>/shipments`.
3. For each shipment report: `shipment_status`, `delivery_status`, `carrier`
   and `service`, `tracking_number`, `tracking_url`, `shipped_at` /
   `delivered_at`, `estimated_delivery.from_date`-`to_date`, the items in it,
   and the latest two or three `tracking_events` (newest first, with times in
   the user's timezone). Mention `is_reshipment` when true.
4. No shipments yet: explain from the order status (e.g. `pending` = waiting
   for production).

## 8. List orders, invoices, reorder

**List:** v2 has no status filter. Page `GET /v2/orders?offset=<n>&limit=100`
while `offset + limit < paging.total` (at most 2 requests per second), filter
client-side (e.g. `status == "failed"`), and show id, external id, status,
recipient name, total + currency, `created_at`. Stop early once enough recent
matches are found if the user only wants recent ones.

**Invoice:** `GET /v2/orders/<id>/invoices` (charged orders only), then
decode `data.content` into the current working directory:

```bash
bash "$PF" GET /v2/orders/<id>/invoices | python3 -c 'import base64,json,sys
d=json.load(sys.stdin)["data"]; open(sys.argv[1],"wb").write(base64.b64decode(d["content"]))' "printful-invoice-<id>.pdf"
```

Report the file path.

**Reorder:** `GET /v2/orders/<id>` (recipient, shipping) and
`GET /v2/orders/<id>/order-items?type=order_item` (full items with
placements). For each item keep `source`, `catalog_variant_id`,
`product_template_id`, `quantity`, `name`, `placements`, `product_options`,
`orientation`; drop `id`, `type`, `price`, `currency`, `retail_currency`,
`_links` and the old `external_id`; inside each placement drop the read-only
`status` and `status_explanation`. From the recipient drop `state_name` and
`country_name`. Confirm the recipient is still right (re-check against
`ship_to` if it is the user), apply any changes they ask for (size,
quantity), then continue from step 4 of section 1 as a new draft. Store
products ordered through v1 are re-ordered through section 2.
