---
name: printful-report
description: >
  This skill should be used when the user wants an overview or monitoring of
  their Printful store - phrases like "Printful summary", "how did my store do
  this week", "daily Printful report", "orders needing attention", "anything
  stuck or failed", "what's out of stock", "revenue and costs this month",
  "set up a recurring Printful check", or "monitor my Printful orders".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, python3, network access, and PRINTFUL_API_TOKEN.
metadata:
  version: "0.1.0"
---

# Printful reports and monitoring

Produce on-demand summaries and recurring checks by polling the API (the
plugin does not register webhooks, which need a public server). Load the
`printful-api` skill first; helper is
`../printful-api/scripts/pf.sh`, resolved against this skill's
directory (set `PF` to that absolute path before running commands).

## Standard report

Unless the user asks for something narrower, gather all of the following for
the requested period (default: last 7 days; timestamps are epoch seconds, so
compute the cutoff portably with
`python3 -c 'import time; print(int(time.time()) - 7*86400)'` and filter on `created`):

1. **Orders** - page through `GET /orders?limit=100` until `created` is older
   than the cutoff. Count by status. Sum `costs.total` (what Printful charged)
   and `retail_costs.total` (what the customer paid, when present); margin is
   the difference. Report in the store currency.
2. **Needs attention** - orders in `failed` or `onhold`: fetch each with
   `GET /orders/{id}` and list id, recipient, and the error/hold reason. Also
   list `draft` orders older than 48 hours (probably forgotten) and `pending`
   or `inprocess` orders older than the product's usual production window
   (flag anything over 7 business days).
3. **Shipments** - orders that moved to `fulfilled` in the period with carrier
   and tracking links.
4. **Stock** - for every sync product (`GET /store/products`, then each
   `GET /store/products/{id}`), read each sync variant's catalog `variant_id`,
   call `GET /products/variant/{variant_id}` (respect the 30/min catalog
   limit; cache by variant id) and list variants that are `out_of_stock` or
   `discontinued` in the user's fulfillment region. Skip this section when the
   user only asks about orders.
5. **Top products** - count ordered items by sync product name.

## Output format

Lead with a three-line headline (orders, money, issues), then the attention
list, then the rest. Use a table for the attention list and top products. Keep
it to one screen; offer the full order table as a CSV in the working directory
if there are more than 20 orders.

## Recurring monitoring

When the user asks for a daily or weekly check, set it up as a scheduled task
using whatever scheduling tool the agent has with a standalone prompt such as:

> Load the printful-report skill and run the standard report for the last 24
> hours. If there are failed, on-hold or stale orders, list them first. Send
> the result as a message.

Suggest a time in the user's timezone (default 8:00 am local) and confirm
before creating it. If a chat tool (Slack, Teams, Discord) is available, offer to post the summary there.

## Cost lookups

For "what does X cost me", use the catalog variant `price` from
`GET /products/variant/{id}` plus a shipping estimate from
`POST /shipping/rates` to the user's typical destination. For an existing
order, read `costs` on `GET /orders/{id}`.
