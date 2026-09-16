---
name: printful-order
description: >
  This skill should be used when the user wants to place, check, or manage
  Printful orders - phrases like "create an order", "send a sample to",
  "place a draft order", "how much will this order cost", "shipping options
  to", "confirm order", "what's the status of order", "track my order",
  "where is the shipment", "cancel order", "list pending orders", "which
  orders failed", or "reorder".
license: MIT
compatibility: Requires the printful-api skill from the same plugin, bash, curl, network access, and PRINTFUL_API_TOKEN.
metadata:
  version: "0.1.0"
---

# Printful orders

Create drafts, estimate costs, confirm for fulfillment, track shipments and
cancel. Load the `printful-api` skill first; use its helper script
`../printful-api/scripts/pf.sh`, resolved against this skill's
directory (set `PF` to that absolute path before running commands).

## Money rule

Confirming an order charges the user's Printful billing method and starts
production. Cancelling may be impossible once production begins. Therefore:

- Always create orders as **drafts** (never `?confirm=true`).
- Show the cost estimate and full order summary, then ask "Confirm this order
  for fulfillment?" and only call `POST /orders/{id}/confirm` after an explicit
  yes in the current conversation.
- Before `DELETE /orders/{id}`, show the order id, recipient and total, and get
  an explicit yes.

## Creating an order

1. Collect what is needed: recipient (name, address1, city, state code for
   US/CA/AU, country code, zip, email), items (either store items by
   sync variant, or catalog variant + design file), and quantities. If the user
   says "send me a sample", use their own address if they provide it; do not
   guess an address.
2. Resolve items:
   - Store item: `GET /store/products` -> find product -> read
     `sync_variants[]` -> pick `sync_variant_id` by size/colour.
   - One-off item: catalog `variant_id` plus `files[]` (see
     `printful-product` and `printful-files`).
3. Validate the country/state with `GET /countries` if unsure of a code.
4. Get shipping options: `POST /shipping/rates` with the recipient and items.
   Present each option (`id`, `name`, `rate`, delivery window) and let the user
   choose, defaulting to the cheapest.
5. Estimate: `POST /orders/estimate-costs` with the full body (including the
   chosen `shipping`). Show subtotal, shipping, tax, total in the returned
   currency, and the retail figures if the user supplied `retail_costs`.
6. Create the draft: `POST /orders`. Report the order id and dashboard link
   `https://www.printful.com/dashboard/default/orders/<id>`.
7. Ask whether to confirm now. If yes -> `POST /orders/{id}/confirm`, then
   `GET /orders/{id}` and report the new status (`pending`).

Include an `external_id` whenever the user has their own order reference so
they can later use `@<external_id>` in place of the Printful id.

## Checking status and tracking

- `GET /orders/{id}` (or `@external_id`). Report `status`, `created`,
  `updated`, and for each `shipments[]` entry the carrier, service, tracking
  number and `tracking_url`.
- Explain statuses plainly: `draft` = not submitted; `pending` = confirmed,
  awaiting production; `inprocess` = printing; `partial` = some items shipped;
  `fulfilled` = all shipped; `failed` = look at the order's error and fix
  (usually address or payment); `onhold` = needs action in the dashboard.
- For "where is my order" without an id, list `GET /orders?limit=20` and ask
  which one, or match on recipient name.

## Listing and filtering

`GET /orders?status=<status>&limit=100`, paging with `offset`. Present a table:
id, external id, status, recipient name, country, total, created date (convert
epoch to the user's timezone). For "failed orders", also fetch each order to
surface the error message.

## Updating a draft

Only drafts can be edited. `GET /orders/{id}`, apply the requested change to
the body, `PUT /orders/{id}` (send the full `items` array: items left out
are deleted). Re-run the estimate and show the delta.

## Reorder

Fetch the original order, strip `id`, `status`, `costs`, `shipments`, keep
`recipient` and `items` (using `sync_variant_id` or `variant_id`), create a new
draft, and follow the creation flow from step 4.

## Cancelling

`DELETE /orders/{id}` after confirmation. If the API refuses because the order
is already in production, tell the user to contact Printful support from the
dashboard order page.
