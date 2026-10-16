// "Sign in with Printful": the Worker is a Printful public app. Printful
// access tokens last an hour; their refresh tokens rotate on every use and
// lapse after 90 days without one.

export interface PrintfulOAuthEnv {
	PRINTFUL_OAUTH_BASE: string;
	PRINTFUL_CLIENT_ID: string;
	PRINTFUL_CLIENT_SECRET?: string;
}

export interface PrintfulTokens {
	accessToken: string;
	refreshToken: string;
	/** Seconds since the Unix epoch. */
	expiresAt: number;
}

/** A refresh Printful refused for good (revoked app, expired refresh token), as opposed to an outage. */
export class PrintfulGrantRevoked extends Error {}

export const callbackPath = "/printful/callback";

export const signInAvailable = (env: PrintfulOAuthEnv) => Boolean(env.PRINTFUL_CLIENT_ID && env.PRINTFUL_CLIENT_SECRET);

export function authorizeUrl(env: PrintfulOAuthEnv, origin: string, state: string): string {
	const url = new URL("/oauth/authorize", env.PRINTFUL_OAUTH_BASE);
	url.searchParams.set("client_id", env.PRINTFUL_CLIENT_ID);
	url.searchParams.set("state", state);
	url.searchParams.set("redirect_url", `${origin}${callbackPath}`);
	return url.toString();
}

async function tokenRequest(env: PrintfulOAuthEnv, fields: Record<string, string>): Promise<PrintfulTokens> {
	const response = await fetch(new URL("/oauth/token", env.PRINTFUL_OAUTH_BASE), {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
		body: new URLSearchParams({
			client_id: env.PRINTFUL_CLIENT_ID,
			client_secret: env.PRINTFUL_CLIENT_SECRET ?? "",
			...fields,
		}),
	});
	const text = await response.text();
	if (response.status >= 400 && response.status < 500 && response.status !== 429) {
		throw new PrintfulGrantRevoked(`Printful refused the ${fields.grant_type} exchange (HTTP ${response.status}).`);
	}
	if (!response.ok) throw new Error(`Printful's token endpoint returned HTTP ${response.status}.`);
	const data = JSON.parse(text) as { access_token?: string; refresh_token?: string; expires_at?: string | number };
	const expiresAt = Number(data.expires_at);
	if (!data.access_token || !data.refresh_token || !Number.isFinite(expiresAt)) {
		throw new Error("Printful's token response was missing access_token, refresh_token or expires_at.");
	}
	return { accessToken: data.access_token, refreshToken: data.refresh_token, expiresAt };
}

export const exchangeCode = (env: PrintfulOAuthEnv, code: string) =>
	tokenRequest(env, { grant_type: "authorization_code", code });

export const refreshTokens = (env: PrintfulOAuthEnv, refreshToken: string) =>
	tokenRequest(env, { grant_type: "refresh_token", refresh_token: refreshToken });
