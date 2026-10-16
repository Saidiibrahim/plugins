// The connector's sign-in page. The user pastes a Printful private token here,
// not into chat. It's checked against Printful, then stored only inside the
// OAuth grant's props, which the provider library encrypts with a key that
// only the holder of the issued token can unwrap.

import {
	AuthorizationError,
	type AuthRequest,
	CimdFetchError,
	type ConsentDescription,
	type OAuthHelpers,
} from "@cloudflare/workers-oauth-provider";
import { printfulFetch } from "./printful.ts";

export const SCOPE = "printful";

export interface Props {
	token: string;
	storeId?: string;
	storeName: string;
}

interface AuthorizeEnv {
	OAUTH_PROVIDER: OAuthHelpers;
	PRINTFUL_API_BASE: string;
	ALLOWED_REDIRECT_HOSTS: string;
}

const escape = (value: string) => value.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);

const html = (body: string, headers = new Headers(), status = 200) => {
	headers.set("Content-Type", "text/html; charset=utf-8");
	headers.set("Cache-Control", "no-store");
	return new Response(body, { status, headers });
};

const errorPage = (message: string, status = 400) =>
	html(page("Can't connect to Printful", `<p class="error">${escape(message)}</p>`), new Headers(), status);

function page(title: string, content: string): string {
	return `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${escape(title)}</title>
<style>
	:root { color-scheme: light dark; --fg: #1f1d1a; --muted: #6b665e; --bg: #faf9f6; --card: #fff; --line: #e4e0d8; --accent: #c2410c; --error: #b91c1c; }
	@media (prefers-color-scheme: dark) { :root { --fg: #ece9e3; --muted: #a39e94; --bg: #1a1917; --card: #24221f; --line: #3a3732; --accent: #fb923c; --error: #f87171; } }
	* { box-sizing: border-box; }
	body { margin: 0; padding: 32px 16px; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }
	main { max-width: 480px; margin: 0 auto; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 24px; }
	h1 { font-size: 1.25rem; margin: 0 0 12px; }
	p { margin: 0 0 12px; }
	.muted { color: var(--muted); font-size: 0.9rem; }
	.warn { border-left: 3px solid var(--accent); padding-left: 12px; }
	.error { color: var(--error); font-weight: 600; }
	label { display: block; font-weight: 600; margin: 16px 0 4px; }
	input { width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); color: var(--fg); font: inherit; }
	.actions { display: flex; gap: 8px; margin-top: 20px; }
	button { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); font: inherit; cursor: pointer; }
	button[value=approve] { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
	a { color: var(--accent); }
</style>
<main>
<h1>${escape(title)}</h1>
${content}
</main>
</html>`;
}

function consentPage(details: ConsentDescription, handle: string, query: string, error?: string): string {
	const name = escape(details.clientName);
	const origin = details.clientDomain
		? `Published by <strong>${escape(details.clientDomain)}</strong>.`
		: "This app registered itself, so its name isn't verified.";
	return page(
		"Connect Printful",
		`<p><strong>${name}</strong> wants to use your Printful store through this connector. ${origin}</p>
<p>Access goes to <strong>${escape(details.redirectHost)}</strong>.</p>
${details.redirectIsLoopback ? '<p class="warn">This sends access to an app on your computer. Continue only if you just started connecting from it.</p>' : ""}
<p class="muted">With this access the app can read your catalog, files and orders and create drafts. Confirming (paying for) or cancelling an order uses a separate tool your Claude client asks you to approve.</p>
${error ? `<p class="error">${escape(error)}</p>` : ""}
<form method="post" autocomplete="off">
	<input type="hidden" name="handle" value="${escape(handle)}">
	<input type="hidden" name="q" value="${escape(query)}">
	<label for="token">Printful private token</label>
	<input id="token" name="token" type="password" required spellcheck="false" autocomplete="off">
	<p class="muted">Create one at <a href="https://developers.printful.com/tokens" target="_blank" rel="noopener noreferrer">developers.printful.com</a> with access to orders, products, file library and webhooks (read). It's stored encrypted inside this connection and never shown again. Revoke it at Printful to cut access.</p>
	<label for="store_id">Store ID <span class="muted">(only for account-level tokens)</span></label>
	<input id="store_id" name="store_id" inputmode="numeric" pattern="[0-9]*" spellcheck="false">
	<div class="actions">
		<button name="decision" value="deny" formnovalidate>Deny</button>
		<button name="decision" value="approve">Connect</button>
	</div>
</form>`,
	);
}

/** Redirects may only go to Claude's own callbacks (or a local app), so a stranger can't phish a grant. */
function redirectAllowed(details: ConsentDescription, allowedHosts: string): boolean {
	const allowed = allowedHosts
		.split(",")
		.map((host) => host.trim().toLowerCase())
		.filter(Boolean);
	return details.redirectIsLoopback || allowed.includes(details.redirectHost.toLowerCase());
}

/** Checks the token against Printful and works out which store it acts for. */
async function verifyToken(
	env: AuthorizeEnv,
	token: string,
	storeId: string,
): Promise<{ props: Props; storeKey: string } | { error: string }> {
	if (storeId && !/^\d+$/.test(storeId)) return { error: "The store ID is a number." };
	const response = await printfulFetch(env.PRINTFUL_API_BASE, { token }, "GET", "/v2/stores");
	if (response.status === 401 || response.status === 403) {
		return { error: "Printful didn't accept that token. Check it's a private token that hasn't expired." };
	}
	if (response.status < 200 || response.status >= 300) {
		return { error: `Printful returned HTTP ${response.status}. Try again in a minute.` };
	}
	const stores = (JSON.parse(response.body) as { data?: { id: number; name: string }[] }).data ?? [];
	const store = storeId ? stores.find((candidate) => String(candidate.id) === storeId) : stores[0];
	if (!store) return { error: `This token has no access to store ${storeId}.` };
	if (!storeId && stores.length > 1) {
		const list = stores.map((candidate) => `${candidate.name} (${candidate.id})`).join(", ");
		return { error: `This token can reach several stores. Enter the store ID to use: ${list}.` };
	}
	return { props: { token, storeId: storeId || undefined, storeName: store.name }, storeKey: String(store.id) };
}

export async function handleAuthorize(request: Request, env: AuthorizeEnv): Promise<Response> {
	const oauth = env.OAUTH_PROVIDER;
	try {
		if (request.method === "GET") {
			const authRequest = await oauth.parseAuthRequest(request);
			const details = await oauth.describeConsent(authRequest);
			if (!redirectAllowed(details, env.ALLOWED_REDIRECT_HOSTS)) {
				return errorPage(`This connector only signs in to Claude. ${details.redirectHost} isn't allowed.`, 403);
			}
			const consent = await oauth.beginConsent(authRequest);
			return html(consentPage(details, consent.handle, new URL(request.url).search.slice(1)), consent.headers);
		}

		if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

		const form = await request.formData();
		const handle = String(form.get("handle") ?? "");
		if (form.get("decision") !== "approve") {
			const denied = await oauth.denyConsent(request, handle);
			return new Response(null, { status: 302, headers: denied.headers });
		}

		const token = String(form.get("token") ?? "").trim();
		const storeId = String(form.get("store_id") ?? "").trim();
		const verified = token ? await verifyToken(env, token, storeId) : { error: "Paste your Printful token." };
		if ("error" in verified) {
			// The handle is still unused, so show the same form again with the error.
			const query = String(form.get("q") ?? "");
			const original = await oauth.parseAuthRequest(new Request(new URL(`/authorize?${query}`, request.url)));
			const details = await oauth.describeConsent(original);
			return html(consentPage(details, handle, query, verified.error), new Headers(), 400);
		}

		const approved = await oauth.approveConsent(request, handle, { scope: [SCOPE] });
		const authRequest: AuthRequest = approved.request;
		const { redirectTo } = await oauth.completeAuthorization({
			request: authRequest,
			userId: `printful-store-${verified.storeKey}`,
			metadata: { storeName: verified.props.storeName },
			scope: [SCOPE],
			props: verified.props,
		});
		approved.headers.set("Location", redirectTo);
		return new Response(null, { status: 302, headers: approved.headers });
	} catch (error) {
		if (error instanceof AuthorizationError && error.redirectTo) {
			return Response.redirect(error.redirectTo, 302);
		}
		if (error instanceof AuthorizationError) return errorPage(error.description);
		if (error instanceof CimdFetchError) return errorPage("This app could not be verified.");
		throw error;
	}
}
