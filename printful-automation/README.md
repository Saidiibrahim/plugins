# Printful Automation

An [Agent Plugins](https://agent-plugins.org/specification) v1.0.0 package
for designing, buying and shipping your own custom merch through
[Printful](https://www.printful.com). Artwork comes from an image-generation
API. The plugin checks it is print-ready, hosts it, makes mockups, places and
pays for the order, and tracks the delivery.

## Recent improvements (v0.3.0)

- **Simplified design hosting setup:** Added comprehensive first-run setup
  guide for Cloudflare R2 with smoke tests. Fixed `host-design.sh` wrangler
  cache directory issues and improved reliability.
- **Better DPI handling:** Enhanced guidance in `printful-design` to ensure
  generated images meet at least 150 dpi (ideally 300 dpi) for print areas,
  preventing low-resolution failures.
- **Correct store product thumbnails:** Fixed `printful-product` to use hosted
  mockup images (not flat print files) as store product thumbnails, ensuring
  proper dashboard display.
- **Accurate dashboard URLs:** Corrected the Printful dashboard URL pattern for
  saved products to
  `/dashboard/product-templates/published/{storeId}/{syncProductId}`.
- **Pre-order validation:** Added pre-order readiness checklist in
  `printful-order` to verify recipient completeness, design URL accessibility,
  and billing method before draft creation.
- **Python venv support:** Documented virtual environment usage for Pillow
  installation on PEP 668 externally-managed systems.

## Layout

```text
printful-automation/
├── plugin.json                    # Agent Plugins manifest
├── skills/                        # Agent Skills (agentskills.io format)
│   ├── printful-api/
│   │   ├── SKILL.md               # conventions, config, version routing, safety
│   │   ├── scripts/pf.sh          # request helper (v1 + v2, guarded calls)
│   │   └── references/
│   │       ├── endpoints-v2.md    # primary API reference
│   │       └── endpoints-v1.md    # v1-only gaps
│   ├── printful-design/           # generate artwork with image APIs
│   ├── printful-files/            # print-readiness, hosting, file library
│   ├── printful-product/          # catalog, prices, stock, mockups, saved products
│   ├── printful-order/            # shipping rates, orders, payment, tracking
│   └── printful-report/           # spend, orders needing attention, deliveries
└── README.md
```

There are no client-specific files, so any client that loads Agent Plugins
skills can use the package as it is. Skills call each other's scripts through
relative paths such as `../printful-api/scripts/pf.sh`.

## How it fits together

```text
idea ─▶ printful-design ─▶ printful-files ─▶ printful-product ─▶ printful-order ─▶ printful-report
        generate art       check, fix, host   blank + mockups      pay + ship        track + spend
```

| Skill | What it does |
| --- | --- |
| `printful-api` | Shared foundation: token, local config, API version routing, `pf.sh` helper, pagination, rate limits, and the spending rules. Loaded by every other skill. |
| `printful-design` | Turns an idea into print-ready artwork using an image-generation API (whichever provider keys you have), including upscaling, background removal and public hosting. |
| `printful-files` | Checks artwork against the print area (pixels, DPI, transparency, colour mode), prepares a print file, hosts it at a public URL and validates it with Printful. |
| `printful-product` | Finds a blank that is in stock for Australia, shows prices in AUD, reads print-area specs, generates mockups and writes a reusable design spec. Can optionally save the design as a store product. |
| `printful-order` | Gets shipping options, creates a draft, waits for costs (including GST), confirms payment through the approval gate, then tracks shipments and fetches invoices. Also edits, deletes, cancels and reorders. |
| `printful-report` | Summarises spending (store statistics), orders needing attention (failed payments, holds, forgotten drafts), deliveries in transit and stock of your saved designs. Can run on a schedule. |

## Printful API v1 and v2

The plugin uses **API v2 by default** and v1 only where v2 has no
equivalent yet:

| v2 | v1 (gaps only) |
| --- | --- |
| Catalog, prices by region and currency, stock by region | Saved store (sync) products: create, update, delete |
| Print-area specs, mockup tasks | Ordering a saved product by sync variant |
| File library | Listing product templates |
| Shipping rates with delivery dates and customs flags | Cancelling a confirmed order |
| Draft orders built item by item, async cost calculation, confirmation | Pixel print-file specs, embroidery thread detection |
| Shipments with tracking events, invoices, store statistics | |

v2 is still labelled beta, but Printful supports it for production use. The
references in `skills/printful-api/references/` list the exact endpoints and
the differences that matter. The main one: `DELETE` on an order cancels it in
v1 but deletes a draft in v2.

## Setup

1. **Printful store.** Use a *Manual order platform / API* store and set a
   billing method in the Printful dashboard (Printful Wallet with
   auto-recharge, card or PayPal). The API charges this method when an order
   is confirmed; it cannot add payment details itself.
2. **Token.** At https://developers.printful.com create a **Private token**
   for that store with access to orders, products (sync products), file library
   and webhooks (read). Export it:

   ```bash
   export PRINTFUL_API_TOKEN="your-token"
   # Only for an account-level token:
   export PRINTFUL_STORE_ID="1234567"
   ```

3. **Local config.** Ask the agent to "set up my Printful config", or create
   `~/.config/printful-automation/config.json` (permissions `600`) yourself.
   The file holds your delivery address, currency (`AUD`), selling region
   (`australia`), default shipping, design hosting details and the optional
   auto-confirm spending cap. The full format is in
   `skills/printful-api/SKILL.md`. It stays outside the plugin and is never
   committed.
4. **Design generation (optional).** Export an API key for at least one image
   provider: `OPENAI_API_KEY`, `IDEOGRAM_API_KEY` or `RECRAFT_API_TOKEN`
   (supported by `generate-image.py`). `GEMINI_API_KEY`, `BFL_API_KEY`,
   `FAL_KEY` and `REPLICATE_API_TOKEN` are also documented for generation,
   upscaling and background removal. Details and verified models are in
   `skills/printful-design/references/providers.md`.
5. **Design hosting.** Printful downloads artwork from a public URL. The
   default is a public Cloudflare R2 bucket; `skills/printful-files/SKILL.md`
   covers setup and alternatives.
6. **Tools.** `bash`, `curl` and `python3` are required. `jq` is recommended,
   and Pillow is needed for the image checks.
7. Ask the agent to "check my Printful connection". It runs `GET /v2/stores`
   and `GET /v2/oauth-scopes` and checks for the config file.

Tokens and API keys are only read from the environment and never written to
files.

## Usage

- "Design a retro Adelaide sunset tee, black shirt, front print" -> `printful-design`
- "Is design.png good enough for a hoodie front?" -> `printful-files`
- "Which heavyweight tees are in stock in Australia, and what do they cost in AUD?" -> `printful-product`
- "Make mockups of this design on the Bella+Canvas 3001 in black and navy" -> `printful-product`
- "Buy one in M and ship it to me" -> `printful-order`
- "Where's my hoodie?" / "Download the invoice for order 12345" -> `printful-order`
- "How much have I spent on merch this year?" / "Check my orders every morning" -> `printful-report`

## Spending safety

- Orders are always created as drafts. Nothing is charged until the order is
  confirmed.
- Before confirming, the agent shows the items, shipping method, GST and
  total, and waits for an explicit yes.
- **Optional auto-confirm:** if you set `auto_confirm_max_total` in your config
  (for example `80`), orders you ask for can be confirmed without a second
  prompt. This only happens when the total including GST and shipping is at
  or below the cap, the currency matches, and the order goes to your saved
  address. Only you can set this value; the agent will not change it.
- `pf.sh` refuses to confirm, cancel or delete anything unless `PF_CONFIRM=yes`
  is set on that one command. This backs up the approval step.

## Australian orders

- Printful adds 10% GST to orders delivered in Australia unless your Printful
  account has an approved GST registration.
- The plugin prefers blanks in stock for the `australia` selling region. It
  warns when a shipment would leave from another country or might attract
  customs fees.
- Australian addresses need a `state_code` (`SA` for Adelaide).

## Claude Code

The marketplace entry for this repo (`../.claude-plugin/marketplace.json`)
supplies the details Claude Code shows. Claude Code finds `skills/` without a
`.claude-plugin/plugin.json`:

```bash
/plugin install printful-automation@ibby-plugins
```

## API notes

Built against Printful API v2 (`2.0.0-beta`,
https://developers.printful.com/docs/v2-beta/) and v1
(https://developers.printful.com/docs/), checked on 2026-09-16.
