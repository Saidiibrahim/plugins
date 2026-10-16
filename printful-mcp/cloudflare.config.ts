import { bindings, defineConfig } from "cf/config";
import * as entrypoint from "./src/index.ts" with { type: "cf-worker" };

// `cf dev --mode mock` points the Worker at a local Printful stand-in for end-to-end tests.
const MOCK_PRINTFUL_URL = "http://127.0.0.1:8789";

export default defineConfig(({ mode }) => {
	const dev = mode === "development" || mode === "mock";
	return {
		worker: {
			name: "printful-mcp",
			compatibilityDate: "2026-09-25",
			// Blocks fetches to private addresses when resolving Client ID Metadata Documents.
			compatibilityFlags: dev ? [] : ["global_fetch_strictly_public"],
			entrypoint,
			env: {
				// OAuth clients, grants and tokens; Printful tokens live encrypted in grant props.
				OAUTH_KV: bindings.kv(),
				PRINTFUL_API_BASE: bindings.text(mode === "mock" ? MOCK_PRINTFUL_URL : "https://api.printful.com"),
				// Hosts the sign-in page may send a grant to; loopback apps (Claude Code) are always allowed.
				ALLOWED_REDIRECT_HOSTS: bindings.text("claude.ai,claude.com,anysphere.cursor-mcp"),
			},
		},
	};
});
