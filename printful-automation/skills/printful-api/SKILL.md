---
name: printful-api
description: >
  This skill should be used whenever Claude needs to call the Printful API for
  any reason - it holds the authentication, request, pagination, rate-limit and
  error-handling conventions shared by every other Printful skill. Load it when
  the user says "call the Printful API", "check my Printful token", "which
  Printful store am I connected to", "list my Printful stores", or when another
  printful-* skill needs to make a request.
license: MIT
compatibility: Requires bash, curl, network access to api.printful.com, and a PRINTFUL_API_TOKEN environment variable. jq recommended.
metadata:
  version: "0.1.0"
---

# Printful API conventions

Use this skill as the foundation for every Printful request. The other
`printful-*` skills assume these rules are in effect.

## Authentication

- The token lives in the environment variable `PRINTFUL_API_TOKEN`. Never ask the
  user to paste it into chat and never write it into a file inside the plugin.
- If the variable is missing, stop and tell the user how to create a private
  token: open https://developers.printful.com, choose **Private token**, pick the
  scopes needed (see below), set an optional expiry, then export the token as
  `PRINTFUL_API_TOKEN` in the environment the agent runs in.
- Private tokens are either store-level (already bound to one store) or
  account-level. Account-level tokens must also send `X-PF-Store-Id`. Support
  this with the optional `PRINTFUL_STORE_ID` variable. If a request fails with
  a message about a missing store, run `GET /stores`, show the user the list,
  and ask which store id to export.
- Scopes the plugin needs: `sync_products`, `orders`, `file_library`,
  `webhooks/read`. Read-only variants (`orders/read`, `sync_products/read`,
  `file_library/read`) are enough for reporting-only use.

## Making requests

Always call the API through the bundled helper `scripts/pf.sh` (relative to
this skill's directory) so headers, store id and status handling stay
consistent. Resolve it to an absolute path first, because the working directory
is usually the user's project:

```bash
PF="<this skill directory>/scripts/pf.sh"
bash "$PF" GET /store/products
bash "$PF" POST /orders @body.json
```

- Base URL is `https://api.printful.com`. Endpoints are v1 unless a path starts
  with `/v2/`. Prefer v1 for everything in this plugin; v2 is still beta.
- Write JSON bodies to a temp file and pass `@file` rather than inlining long
  JSON on the command line.
- Pipe output through `jq` when a subset of fields is needed. Check `jq` is
  installed first (`command -v jq`); fall back to `python3 -c 'import json,sys;...'`
  if it is not.

## Response envelope

Every v1 response is wrapped:

```json
{ "code": 200, "result": { ... } }
```

Lists add a `paging` object: `{ "total": 57, "offset": 0, "limit": 20 }`.
Errors put details under `error`: `{ "code": 400, "result": "...", "error": { "reason": "BadRequest", "message": "..." } }`.
Report the `error.message` to the user verbatim when a request fails; it is
usually specific (missing field, invalid variant id, address problem).

## Pagination

- Use `offset` and `limit` (max 100). Loop while `offset + limit < paging.total`.
- For reports that need every record, fetch in pages of 100 and aggregate; do not
  assume a single page is complete.

## Rate limits

- General limit is 120 requests per minute per token; the catalog is 30 per
  minute; creating or modifying sync products is 10 per minute; the mockup
  generator is lower still. A 429 triggers a 60 second lockout.
- When looping (bulk product creation, paging through orders), insert
  `sleep 1` between calls, and `sleep 7` between sync-product writes.
- On 429, wait 60 seconds once and retry; if it fails again, stop and report.

## Identifiers

- **Catalog product id** identifies a blank (e.g. 71 = Bella+Canvas 3001). Use it
  only for browsing, print-file specs and mockup templates.
- **Catalog variant id** identifies a specific size/colour of a blank. Orders,
  mockups and sync variants always use variant ids, never product ids.
- **Sync product / sync variant id** identifies an item the user has created in
  their store. Orders for store items use `sync_variant_id`.
- **External id**: any endpoint that takes an id also accepts `@your-external-id`
  when the object was created with `external_id`.
- Timestamps are UNIX epoch seconds; prices are strings with two decimals.

## Safety rules

- Read operations (GET) may run freely.
- Creating drafts, uploading files and generating mockups are low risk and may
  run once the user has described what they want.
- Anything that spends money or is hard to undo - confirming an order for
  fulfillment, cancelling an order, deleting a sync product or file - requires an
  explicit confirmation in the same conversation *after* showing the user what
  will happen (cost estimate, order summary, product name). Never chain a
  create-and-confirm in one step unless the user has already approved the
  specific order.

## Quick sanity check

To verify the setup, run `GET /stores` and report the store name, id and type.
This is the first thing to do when a user says the plugin "isn't working".

## Full endpoint reference

Read [references/endpoints.md](references/endpoints.md) in this skill for every endpoint the plugin uses,
with request bodies and response shapes.
