# printful-mcp

A remote MCP server on Cloudflare Workers that gives the
[`printful-automation`](../printful-automation) plugin access to the Printful
API from Claude chat. Claude chat runs skills in a sandbox with no
`PRINTFUL_API_TOKEN`, so the token lives here instead.

## How the token is kept

1. Claude connects to `/mcp`, gets a `401`, and starts OAuth (dynamic client
   registration or a Client ID Metadata Document, with PKCE).
2. The Worker's own sign-in page at `/authorize` asks for a Printful private
   token, and an optional store ID for account-level tokens. The token goes
   into this page, never into the conversation.
3. The Worker checks the token with `GET /v2/stores`. A rejected token shows
   the form again and isn't echoed back.
4. The token is stored only in the OAuth grant's `props`, which
   [`@cloudflare/workers-oauth-provider`](https://github.com/cloudflare/workers-oauth-provider)
   encrypts with a key that only the holder of the issued token can unwrap.
   `OAUTH_KV` holds hashes and ciphertext, plus the store name as grant
   metadata.

The sign-in page only sends grants to `ALLOWED_REDIRECT_HOSTS` (Claude's
callbacks and Cursor's) or to a loopback app such as Claude Code. That stops
someone else's client from collecting a grant through a phished link. There's
no shared secret: anyone can connect, but only with their own Printful token.

Revoke the token in Printful to cut access everywhere. Grants expire after 90
days without use, and after a year at most.

## Tools

| Tool | Does | Annotations |
| --- | --- | --- |
| `printful_get` | `GET` any v1 or v2 path | read-only |
| `printful_request` | `POST`/`PUT`/`PATCH`/`DELETE` that doesn't spend money or delete for good | not destructive |
| `printful_guarded_request` | Only the calls `pf.sh` guards: confirming (paying for) an order, cancelling or deleting one, deleting a saved product, variant or template | destructive |

The guard is a port of `printful-api/scripts/pf.sh`: the same path
normalisation, the same guarded calls, and one retry on a short `429`.
Guarded calls have their own destructive tool, so in Claude's connector
settings you can let the read and write tools run freely and keep
`printful_guarded_request` on approval.

## Develop

```bash
npm install
npm test            # guard and error-summary unit tests
npm run test:e2e    # cf dev --mode mock + a Printful stand-in: OAuth, consent, tokens, every tool
npm run typecheck
cf dev              # http://localhost:5173
```

`cloudflare.config.ts` defines the Worker. `--mode mock` points
`PRINTFUL_API_BASE` at `http://127.0.0.1:8789`, where `test/e2e/mock_printful.py`
listens.

## Deploy

```bash
cf deploy
```

The first deploy creates the `OAUTH_KV` namespace and prints the
`workers.dev` URL. The connector URL is that URL plus `/mcp`. It's referenced
by `printful-automation/mcp.json` and by the `mcpServers` entry in
`.claude-plugin/marketplace.json`. The Worker takes its OAuth issuer and
resource from the address each request arrives on, so a custom domain works
without config changes. Tokens issued on one address don't work on another.
