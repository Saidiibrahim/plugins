# Printful Automation

An [Agent Plugins](https://agent-plugins.org/specification) v1.0.0 package that
lets an AI agent run a Printful print-on-demand store through the Printful REST
API: browse the catalog, generate mockups, create and update products, manage
design files, place and track orders, and produce store reports.

## Layout

```text
printful-automation/
├── plugin.json                 # Agent Plugins manifest
├── skills/                     # Agent Skills (agentskills.io format)
│   ├── printful-api/
│   │   ├── SKILL.md
│   │   ├── scripts/pf.sh       # request helper used by every skill
│   │   └── references/endpoints.md
│   ├── printful-product/SKILL.md
│   ├── printful-order/SKILL.md
│   ├── printful-files/SKILL.md
│   └── printful-report/SKILL.md
└── README.md
```

There are no client-specific files, so any client that loads Agent Plugins
skills can use the package as it is. Other skills call the helper through the
relative path `../printful-api/scripts/pf.sh`, which stays inside the plugin.

## Components

| Skill | What it does |
| --- | --- |
| `printful-api` | Shared conventions: authentication, request helper (`scripts/pf.sh`), pagination, rate limits, error handling, and a full endpoint reference in `references/endpoints.md`. Loaded by every other skill. |
| `printful-product` | Find blanks in the catalog, check variant availability and print-area specs, generate mockups, create/update/delete store products, bulk-create from a spreadsheet. |
| `printful-order` | Create draft orders, get shipping options and cost estimates, confirm for fulfillment (with explicit approval), track shipments, list/filter, reorder, cancel. |
| `printful-files` | Check artwork against print specs (size, DPI, colour mode, transparency), fix simple issues, upload to the Printful file library, keep a local index. |
| `printful-report` | On-demand or scheduled summaries: orders by status, costs vs retail, orders needing attention, shipments, out-of-stock variants, top products. |

Agent Plugins v1 has two component types, skills and MCP servers. This plugin
uses only skills (there is no `mcp.json`); everything goes through direct API
calls.

## Setup

1. Go to https://developers.printful.com and create a **Private token** for
   your store. Grant the scopes `sync_products`, `orders`, `file_library` and
   `webhooks/read` (or the `/read` variants for reporting only). Set an expiry
   if you like.
2. Export the token in the environment your agent runs in:

   ```bash
   export PRINTFUL_API_TOKEN="your-token"
   # Only if you created an account-level token instead of a store-level one:
   export PRINTFUL_STORE_ID="1234567"
   ```

3. Make sure `bash`, `curl` and `python3` are available. `jq` is recommended
   for nicer output; Pillow or ImageMagick is needed for artwork checks.
4. Ask the agent "check my Printful connection" - it will call the stores
   endpoint and confirm which store the token is bound to.

The token is never written into the plugin or any file the agent creates.

## Usage

- "Create a Bella+Canvas 3001 tee with this design in black and white, S-XL,
  priced at $34.99" -> `printful-product`
- "Generate mockups for product 123456" -> `printful-product`
- "Upload design.png to my Printful library and tell me if it's print-ready" -> `printful-files`
- "Send a sample of the sunset tee (M, black) to my address" -> `printful-order`
  (creates a draft, shows the cost, asks before confirming)
- "Where is order 98765?" -> `printful-order`
- "How did the store do this week?" / "Set up a daily 8am Printful check" -> `printful-report`

## Safety

Actions that spend money or are irreversible (confirming an order, cancelling
an order, deleting a product or file) always show a summary and wait for an
explicit yes. Orders are always created as drafts first.

## Optional integrations

The skills name tool categories instead of specific products, and use
whichever tool the agent has for each one:

| Category | Examples | Used for |
| --- | --- | --- |
| Storefront | Shopify, Etsy, WooCommerce, or none | Product naming and SKU conventions |
| Cloud storage | Google Drive, Dropbox, OneDrive, S3/R2 | Hosting design files at a public URL for Printful to fetch |
| Chat | Slack, Microsoft Teams, Discord | Posting scheduled store reports |

## Claude Code

The marketplace entry for this repo (`../.claude-plugin/marketplace.json`)
supplies the details Claude Code shows. Claude Code finds `skills/` without a
`.claude-plugin/plugin.json`:

```bash
/plugin install printful-automation@ibby-plugins
```

## API notes

Built against Printful API v1 (https://developers.printful.com/docs/). API v2
is still in beta; the endpoint reference notes where v2 may be needed.
