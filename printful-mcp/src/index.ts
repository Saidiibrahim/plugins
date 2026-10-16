import {
	insufficientScope,
	OAuthError,
	type OAuthResourceContext,
	OAuthProvider,
	type TokenExchangeCallbackOptions,
	type TokenExchangeCallbackResult,
} from "@cloudflare/workers-oauth-provider";
import { createMcpHandler } from "agents/mcp/server";
import { handleAuthorize, handlePrintfulCallback, type Props, SCOPE } from "./authorize.ts";
import { callbackPath, PrintfulGrantRevoked, refreshTokens } from "./printful-oauth.ts";
import { createServer } from "./tools.ts";

const DAY = 24 * 60 * 60;
/** Refresh Printful's access token when it has less than this long left. */
const REFRESH_MARGIN_SECONDS = 5 * 60;

const mcpHandler = {
	fetch(request: Request, env: Env, ctx: ExecutionContext) {
		const { props, auth } = ctx as unknown as OAuthResourceContext<Props>;
		if (!auth.scope.includes(SCOPE)) return insufficientScope(auth, [SCOPE]);
		const printful = { token: props.token, storeId: props.storeId };
		return createMcpHandler(() => createServer(env.PRINTFUL_API_BASE, printful))(request, env, ctx);
	},
};

const siteHandler = {
	fetch(request: Request, env: Env) {
		const { origin, pathname } = new URL(request.url);
		if (pathname === "/authorize") return handleAuthorize(request, env as Env & Parameters<typeof handleAuthorize>[1]);
		if (pathname === callbackPath) {
			return handlePrintfulCallback(request, env as Env & Parameters<typeof handlePrintfulCallback>[1]);
		}
		if (pathname === "/") {
			return new Response(
				`Printful MCP connector for the printful-automation plugin.\nAdd ${origin}/mcp as a connector in Claude; you'll be asked for a Printful private token.\n`,
				{ headers: { "Content-Type": "text/plain; charset=utf-8" } },
			);
		}
		return new Response("Not found", { status: 404 });
	},
};

/**
 * Keeps a "Sign in with Printful" grant's Printful token fresh. Our access tokens never outlive the
 * Printful token inside them, so when Claude refreshes ours, Printful's is refreshed too if needed.
 * Grants made with a private token have no refresh token and pass through unchanged.
 */
async function syncPrintfulToken({
	grantType,
	props,
	env,
}: TokenExchangeCallbackOptions<Env>): Promise<TokenExchangeCallbackResult | void> {
	const current = props as Props;
	if (!current.refreshToken || current.expiresAt === undefined) return;
	const now = Math.floor(Date.now() / 1000);
	let next = current;
	if (grantType === "refresh_token" && current.expiresAt - now < REFRESH_MARGIN_SECONDS) {
		try {
			const tokens = await refreshTokens(env, current.refreshToken);
			next = { ...current, token: tokens.accessToken, refreshToken: tokens.refreshToken, expiresAt: tokens.expiresAt };
		} catch (error) {
			if (error instanceof PrintfulGrantRevoked) {
				// Revokes this grant, so Claude asks the user to connect again.
				throw new OAuthError("invalid_grant", { description: "Printful access was revoked or has expired." });
			}
			throw new OAuthError("temporarily_unavailable", { description: "Printful is unavailable.", statusCode: 503 });
		}
	}
	const accessTokenTTL = Math.max(60, Math.min(3600, next.expiresAt! - now - 60));
	return next === current
		? { accessTokenTTL }
		: { accessTokenProps: next, newProps: next, accessTokenTTL };
}

// Tokens are bound to the origin the client used (workers.dev, a custom domain or
// localhost), so each origin gets its own provider and resource identifier.
const providers = new Map<string, OAuthProvider<Env>>();

function providerFor(origin: string): OAuthProvider<Env> {
	let provider = providers.get(origin);
	if (!provider) {
		provider = new OAuthProvider<Env>({
			apiRoute: "/mcp",
			apiHandler: mcpHandler,
			defaultHandler: siteHandler,
			authorizeEndpoint: "/authorize",
			tokenEndpoint: "/oauth/token",
			clientRegistrationEndpoint: "/oauth/register",
			clientIdMetadataDocumentEnabled: true,
			scopesSupported: [SCOPE],
			requiredScopes: [SCOPE],
			resourceMetadata: {
				resource: `${origin}/mcp`,
				authorization_servers: [origin],
			},
			refreshTokenTTL: 365 * DAY,
			refreshTokenIdleTTL: 90 * DAY,
			tokenExchangeCallback: syncPrintfulToken,
		});
		providers.set(origin, provider);
	}
	return provider;
}

export default {
	fetch(request: Request, env: Env, ctx: ExecutionContext) {
		return providerFor(new URL(request.url).origin).fetch(request, env, ctx);
	},
} satisfies ExportedHandler<Env>;
