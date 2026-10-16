import assert from "node:assert/strict";
import { test } from "node:test";
import { authorizeUrl, signInAvailable } from "../src/printful-oauth.ts";

const env = { PRINTFUL_OAUTH_BASE: "https://www.printful.com", PRINTFUL_CLIENT_ID: "app-1040801" };

test("Printful sign-in is offered only once the client secret is set", () => {
	assert.equal(signInAvailable(env), false);
	assert.equal(signInAvailable({ ...env, PRINTFUL_CLIENT_SECRET: "" }), false);
	assert.equal(signInAvailable({ ...env, PRINTFUL_CLIENT_SECRET: "s" }), true);
});

test("the authorize URL carries the client, state and this Worker's callback", () => {
	const url = new URL(authorizeUrl(env, "https://printful-mcp.example.workers.dev", "a&b=c"));
	assert.equal(url.origin + url.pathname, "https://www.printful.com/oauth/authorize");
	assert.equal(url.searchParams.get("client_id"), "app-1040801");
	assert.equal(url.searchParams.get("state"), "a&b=c");
	assert.equal(url.searchParams.get("redirect_url"), "https://printful-mcp.example.workers.dev/printful/callback");
});
