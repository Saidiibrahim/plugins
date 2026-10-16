// Printful REST client shared by every MCP tool. Mirrors
// printful-automation/skills/printful-api/scripts/pf.sh: same path
// normalisation, same guarded calls, one retry on 429.

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface PrintfulAuth {
	token: string;
	storeId?: string;
}

export interface PrintfulResponse {
	status: number;
	body: string;
}

export class PathError extends Error {}

/** Drops any #fragment, collapses repeated slashes, and refuses dot segments or encoded separators. */
export function normalizePath(endpoint: string): string {
	const withoutFragment = endpoint.split("#", 1)[0];
	const queryStart = withoutFragment.indexOf("?");
	const rawPath = queryStart === -1 ? withoutFragment : withoutFragment.slice(0, queryStart);
	const query = queryStart === -1 ? "" : withoutFragment.slice(queryStart);
	const path = `/${rawPath.replace(/\/+/g, "/").replace(/^\//, "")}`;
	const lower = path.toLowerCase();
	if (
		`/${path}/`.includes("/./") ||
		`/${path}/`.includes("/../") ||
		lower.includes("%2e") ||
		lower.includes("%2f") ||
		lower.includes("%5c")
	) {
		throw new PathError(
			`Refusing ${endpoint}: dot segments or encoded '.', '/' or '\\' are not allowed in the path.`,
		);
	}
	return path + query;
}

/**
 * Why a call needs the user's explicit approval, or null when it doesn't.
 * Guarded calls spend money or can't be undone.
 */
export function guardReason(method: Method, endpoint: string): string | null {
	const queryStart = endpoint.indexOf("?");
	const path = queryStart === -1 ? endpoint : endpoint.slice(0, queryStart);
	const query = queryStart === -1 ? "" : endpoint.slice(queryStart).toLowerCase();
	switch (method) {
		case "POST":
			if (
				/^\/v2\/orders\/[^/]+\/confirmation\/?$/.test(path) ||
				/^\/orders\/[^/]+\/confirm\/?$/.test(path) ||
				(/^\/orders\/?$/.test(path) && query.includes("confirm"))
			) {
				return "confirms an order and charges the Printful billing method";
			}
			return null;
		case "PUT":
			if (/^\/orders\/[^/]+\/?$/.test(path) && query.includes("confirm")) {
				return "updates and confirms an order, charging the Printful billing method";
			}
			return null;
		case "DELETE":
			if (/^\/v2\/orders\/[^/]+\/?$/.test(path)) return "permanently deletes the v2 order";
			if (/^\/orders\/[^/]+\/?$/.test(path)) return "cancels the order (v1 DELETE means cancel)";
			if (/^\/(store\/products|store\/variants|sync\/products|sync\/variant|product-templates)\//.test(path)) {
				return "permanently deletes a product, variant or template";
			}
			return null;
		default:
			return null;
	}
}

const MAX_RETRY_WAIT_SECONDS = 10;

export async function printfulFetch(
	base: string,
	auth: PrintfulAuth,
	method: Method,
	endpoint: string,
	body?: unknown,
): Promise<PrintfulResponse> {
	const headers: Record<string, string> = {
		Authorization: `Bearer ${auth.token}`,
		Accept: "application/json",
	};
	if (auth.storeId) headers["X-PF-Store-Id"] = auth.storeId;
	if (body !== undefined) headers["Content-Type"] = "application/json";
	const send = () =>
		fetch(`${base}${endpoint}`, {
			method,
			headers,
			body: body === undefined ? undefined : JSON.stringify(body),
		});

	let response = await send();
	if (response.status === 429) {
		// v2 sends Retry-After / X-Ratelimit-Reset in seconds; v1 locks out for 60 s.
		const wait = Number(response.headers.get("retry-after") ?? response.headers.get("x-ratelimit-reset"));
		if (Number.isFinite(wait) && wait > 0 && wait <= MAX_RETRY_WAIT_SECONDS) {
			await response.body?.cancel();
			await new Promise((resolve) => setTimeout(resolve, Math.ceil(wait) * 1000));
			response = await send();
		}
	}
	return { status: response.status, body: await response.text() };
}

/** One-line summary of a Printful error for both the v1 and v2 envelopes. */
export function errorSummary(body: string): string {
	let data: unknown;
	try {
		data = JSON.parse(body);
	} catch {
		return "non-JSON response";
	}
	if (typeof data !== "object" || data === null) return "see response body";
	const record = data as Record<string, unknown>;
	const parts: string[] = [];
	const error = record.error;
	if (typeof error === "object" && error !== null) {
		const { message, reason } = error as Record<string, unknown>;
		if (message || reason) parts.push(String(message || reason));
	} else if (typeof error === "string") {
		parts.push(error);
	}
	for (const key of ["title", "detail"]) {
		if (record[key]) parts.push(String(record[key]));
	}
	if (parts.length === 0 && typeof record.result === "string") parts.push(record.result);
	return parts.join(" - ") || "see response body";
}
