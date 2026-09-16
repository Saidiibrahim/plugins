---
name: printful-report
description: >
  This skill should be used when the user wants an overview or monitoring of
  their Printful orders and spending - phrases like "Printful summary", "how
  much have I spent on Printful", "what did my merch cost this month", "where
  is my order", "has my merch shipped", "tracking for my Printful order",
  "orders needing attention", "anything stuck or failed", "is my design still
  in stock", "daily Printful report", "set up a recurring Printful check", or
  "monitor my Printful orders".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, python3, network access, and PRINTFUL_API_TOKEN.
metadata:
  version: "0.2.0"
---

# Printful reports and monitoring

Summarise the user's own merch orders: what they spent, what needs action,
where their parcels are, and whether the blanks behind their designs are still
in stock. This is a personal account, so lead with orders and spending; show
retail and profit figures only when the orders actually carry retail prices.

Load the `printful-api` skill first (auth, config, pacing, safety rules). Set
`PF` to the absolute path of `../printful-api/scripts/pf.sh` and `SUMMARY` to
`scripts/orders-summary.py`, both resolved against this skill's directory.
Read the local config for `currency`, `selling_region` and `ship_to`.

Everything here is read-only. If the user then wants to fix something
(re-confirm, delete a draft, cancel), follow the guarded-call rules in
`printful-api`; never set `PF_CONFIRM=yes` from a report run.

## Standard report

Unless the user asks for something narrower, gather sections 1-4 for the
period (default: last 7 days; "this month" = 1st of the month to today). Add
section 5 when the user asks about stock or when saved designs exist and the
report is a recurring one.

### 1. Orders overview

`GET /v2/orders` has no status or date filter. Page it and filter locally:

```bash
: > /tmp/pf-orders.json
offset=0
while :; do
  if ! bash "$PF" GET "/v2/orders?limit=100&offset=$offset" > /tmp/pf-page.json; then
    echo "WARNING: order listing stopped at offset $offset; the report is incomplete" >&2
    break
  fi
  cat /tmp/pf-page.json >> /tmp/pf-orders.json
  read -r total oldest < <(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["paging"]["total"], min((o["created_at"] for o in d["data"]), default=""))' /tmp/pf-page.json)
  offset=$((offset + 100))
  [[ $offset -ge $total || "$oldest" < "$CUTOFF" ]] && break
  sleep 0.5
done
python3 "$SUMMARY" --since "$CUTOFF" /tmp/pf-orders.json
```

- `CUTOFF` is an ISO 8601 UTC timestamp, e.g.
  `python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))'`.
  String comparison works because v2 timestamps are all `YYYY-MM-DDTHH:MM:SSZ`.
- The v2 spec does not document the sort order. Printful returns newest first
  in practice, so stopping at the first page older than the cutoff is normally
  safe; if `paging.total` is 300 or less, just read every page.
- Always fetch at least the first page even for a short period: attention
  items (failed, on hold) can be older than the period.

`orders-summary.py` (stdlib only, offline) de-duplicates the pages and prints:
counts by status for the period, **spend per `costs.currency`** (sum of
`costs.total` for orders not in `draft`, `failed` or `canceled`), retail value
when `retail_costs.total` is above zero, the attention list, and the order ids
whose shipments to fetch. Useful flags: `--days N` or `--since ISO`, `--now
ISO`, `--draft-hours 48`, `--stale-business-days 7`, `--json`, `--csv PATH`.

Never add amounts in different currencies together; list them separately.

### 2. Needs attention

The script flags these; enrich each with `GET /v2/orders/{id}` when the user
wants detail. v2 orders carry no failure or hold reason field, so say so and
point to the dashboard order page (`https://www.printful.com/dashboard/default/orders`)
when the cause is not obvious.

| Condition | Likely cause | What to tell the user |
| --- | --- | --- |
| `failed` | Payment declined or Wallet empty; sometimes an address or file problem | Top up the Printful Wallet or fix the billing method in the dashboard (Billing), then re-confirm the order (v2 allows re-confirming a `failed` order; guarded). For address or file problems, `PATCH` the order first. |
| `onhold` | Printful found a problem in fulfillment (design, address, stock) | Check `GET /v2/approval-sheets?order_id={id}`; a sheet with `status: waiting_for_action` needs the user to approve or request changes in the dashboard. Otherwise check Printful messages. |
| `inreview` | Printful is reviewing the order | Usually clears by itself; it is still cancellable. Flag only if it lasts more than 2 business days. |
| `draft` older than 48 h | Forgotten order | Drafts are never charged. Offer to review and confirm it, or delete it (guarded). |
| `pending` / `inprocess` with no update for more than ~7 business days | Slow production or a stuck order | Check its shipments (section 3); if nothing is packaged, suggest contacting Printful support. |

### 3. Deliveries

For each shipment candidate from the script (recent non-draft, non-failed,
non-canceled orders, plus anything still `pending`, `inprocess` or
`partial`), call `GET /v2/orders/{id}/shipments`, pacing at 2 requests per
second or slower. Build one table row per shipment:

| Order | Shipment status | Delivery status | Carrier / service | Tracking | Est. delivery | Latest event |
| --- | --- | --- | --- | --- | --- | --- |

- Tracking: `tracking_url` as a link, else `tracking_number`.
- Est. delivery: `estimated_delivery.from_date` to `to_date`.
- Latest event: the `tracking_events[]` entry with the newest `triggered_at`,
  shown as date plus `description`.
- **Highlight** shipments to the user's own address (order `recipient.zip`
  and `country_code` equal config `ship_to`) whose `delivery_status` is
  `in_transit`, `out_for_delivery` or `available_for_pickup` ("on its way to
  you"), and anything with `delivery_status` `return_to_sender` or `failure`,
  or `shipment_status` `returned`, `outstock` or `onhold` (list those under
  Needs attention too).
- Skip shipments `delivered` more than 7 days before the period start.
- `is_reshipment: true` means a replacement parcel; say so.

### 4. Spending (store statistics)

For "how much have I spent", prefer Printful's own totals over summing orders:

1. Store id: `PRINTFUL_STORE_ID` if set, else `GET /v2/stores` (one store:
   use it; several: ask).
2. `GET /v2/stores/{store_id}/statistics?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&report_types=printful_costs,total_paid_orders,costs_by_amount&currency=<config currency>`

The response is `data: { store_id, currency, <report_type>: ... }`. Shapes:

| Report type | Shape | Use it for |
| --- | --- | --- |
| `printful_costs` | `{ value, relative_difference }` | **Headline spend**: total paid to Printful for fulfillment and shipping. |
| `total_paid_orders` | `{ value (integer), relative_difference }` | Number of paid orders. |
| `costs_by_amount` | `[{ date, product_amount, digitization, branding, vat, sales_tax, shipping, discount, total }]` | **Spend breakdown** (products vs shipping vs GST/tax vs discounts). |
| `costs_by_product` | `[{ product_id, product_name, fulfillment, sales, quantity }]` | What the money went on, by blank. `fulfillment` excludes shipping. |
| `costs_by_variant` | `[{ variant_id, variant_name, product_id, fulfillment, sales, quantity }]` | Same by size/colour. |
| `sales_and_costs_summary` | `[{ date, order_count, costs, profit }]` | Spend over time (a small chart or table). |
| `sales_and_costs` | `[{ date, sales, fulfillment, profit, sales_discount, fulfillment_discount, sales_shipping, fulfillment_shipping }]` | Only when the user sells and has retail prices. |
| `profit` | `{ value, relative_difference }` | Only with retail prices; without them it is just negative costs, so skip it. |
| `average_fulfillment_type` (request name) | `{ value, relative_difference }` under `average_fulfillment_time` | Average time Printful took to fulfil. |

- In date-grouped arrays the **first element has `date: "Total"`** for the
  whole period; later elements are per day (`Y-m-d`) or per month (`Y-m`).
- `relative_difference` compares with the previous period of equal length
  (`-1` = 100% decrease, `1` = 100% increase; may be null).
- Amounts are strings; parse them as decimals.
- The period may not exceed 6 months. For longer ranges, split into
  consecutive chunks of at most 6 months (e.g. calendar quarters), request
  each (pause 0.5 s between), then sum `printful_costs.value`,
  `total_paid_orders.value` and the `Total` rows of `costs_by_amount`; merge
  `costs_by_product` by `product_id` summing `fulfillment`, `sales` and
  `quantity`. Do not sum `relative_difference`.
- If statistics are unavailable (error, missing scope), fall back to the
  per-currency spend from section 1 and say which source was used. The two can
  differ slightly: statistics count paid orders in the period, the order sum
  uses `created_at`.
- AU deliveries include 10% GST unless the account is GST-registered; show it
  from `costs_by_amount.vat` / `sales_tax` when non-zero.

### 5. Stock watch

Check the blanks behind designs the user cares about, in their
`selling_region` (default `australia`).

1. Collect catalog variant ids:
   - Saved design specs in the working directory (written by
     `printful-product`):
     `find . -maxdepth 4 -name '*.design.json'`, then read
     `catalog_product_id`, `catalog_variant_ids[]` and the techniques in
     `placements[].technique` from each.
   - Optionally saved store products (v1): `GET /store/products?limit=100`
     (page), then `GET /store/products/{id}` and take each
     `sync_variants[].variant_id`. v1 `variant_id` should be the same number as v2
     `catalog_variant_id`; if a lookup 404s, report it rather than guessing.
2. De-duplicate, then for each id:
   `GET /v2/catalog-variants/{id}/availability?selling_region_name=<region>`
   (add `&techniques=<comma list>` from the spec's placement techniques). Cache results
   for the run, pace at 2 requests per second or slower, and above 100 ids warn
   that the run will take about a minute per 120.
3. Read `data.techniques[].selling_regions[]` entries whose `name` is the
   region. Report every variant whose `availability` is not `in stock`:
   - `out of stock`: supplier is out; Printful can still fulfil (may be slower
     or ship from another region). Suggest waiting or an alternate colour.
   - `not fulfillable`: cannot be made in that region with that technique;
     ordering would ship from overseas or fail. Suggest another blank.
   - `unknown`: say it could not be determined.
4. Present design file, product, variant name (from `GET
   /v2/catalog-variants/{id}` only for flagged ids), technique, status. If
   everything is in stock, one line saying so is enough.

## Output format

1. **Headline** (three lines max): orders in the period and by status; spend
   per currency (statistics figure, with change versus previous period when
   available); number of issues and parcels on their way.
2. **Needs attention** table: order, status, issue, age, total, next step.
   Omit the section when empty ("Nothing needs attention").
3. **Deliveries** table (section 3), highlighted rows first.
4. **Spend**: total, then the breakdown from `costs_by_amount` (products,
   shipping, tax/GST, discounts), then top items from `costs_by_product`.
   Retail and profit lines only when retail prices exist.
5. **Stock watch** (when run).

Keep it to one screen. When there are more than 20 orders or shipments,
summarise and offer the full list as a CSV in the working directory
(`orders-summary.py --csv printful-orders-YYYY-MM-DD.csv`, or build the
shipments CSV the same way).

## Recurring monitoring

When the user asks for a daily or weekly check, set it up as a scheduled task
using whatever scheduling tool the agent has, with a standalone prompt such as:

> Load the printful-report skill and run the standard report for the last 24
> hours, including deliveries and a stock watch for saved designs. List
> failed, on-hold or stale orders and delivery problems first. Do not confirm,
> cancel or delete anything. Send the result as a message.

Suggest a time in the user's timezone (default 8:00 am local) and confirm the
schedule, period and prompt before creating it. If a chat tool (Slack, Teams,
Discord) is available, offer to post the summary there. The scheduled run
needs `PRINTFUL_API_TOKEN` in its environment; mention that if the scheduler
runs remotely.

**Alternative: webhooks.** Printful v2 can push events instead of being polled
(`POST /v2/webhooks`, then per-event `POST /v2/webhooks/{eventType}`), e.g.
`shipment_sent`, `shipment_returned`, `shipment_put_hold`, `order_failed`,
`order_put_hold`, `order_canceled`, `catalog_stock_updated`. This needs a
public HTTPS endpoint that the user runs and that verifies the signing secret,
so only offer it when they already have one; polling is the default.

## Cost lookups

For "what would X cost me", use `GET /v2/catalog-variants/{id}/prices?selling_region_name=<region>&currency=<currency>`
plus `POST /v2/shipping-rates` to the config `ship_to`, or an
`order-estimation-tasks` estimate for an exact total with GST (see the
`printful-order` skill). For an existing order, read `costs` on
`GET /v2/orders/{id}`, and fetch the invoice PDF with
`GET /v2/orders/{id}/invoices` (base64 `content`) if the user wants a receipt.
