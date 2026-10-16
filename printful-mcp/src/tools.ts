import { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import {
	errorSummary,
	guardReason,
	type Method,
	normalizePath,
	PathError,
	type PrintfulAuth,
	printfulFetch,
} from "./printful.ts";

/** Responses bigger than this are cut so one catalog listing can't flood the conversation. */
const MAX_RESPONSE_CHARS = 100_000;

const pathSchema = z
	.string()
	.min(1)
	.describe(
		'Printful API path with any query string, e.g. "/v2/orders?limit=20". Paths starting with /v2/ use API v2; anything else is v1.',
	);
const bodySchema = z
	.record(z.string(), z.unknown())
	.optional()
	.describe("JSON request body, for POST, PUT and PATCH.");

type ToolResult = { content: { type: "text"; text: string }[]; isError?: boolean };

const text = (value: string, isError = false): ToolResult => ({
	content: [{ type: "text", text: value }],
	...(isError ? { isError } : {}),
});

async function call(
	base: string,
	auth: PrintfulAuth,
	method: Method,
	rawPath: string,
	body: Record<string, unknown> | undefined,
	allow: "unguarded" | "guarded",
): Promise<ToolResult> {
	let path: string;
	try {
		path = normalizePath(rawPath);
	} catch (error) {
		if (error instanceof PathError) return text(error.message, true);
		throw error;
	}
	const guarded = guardReason(method, path);
	if (allow === "unguarded" && guarded) {
		return text(
			`Refusing ${method} ${path}: this ${guarded}. Get the user's explicit approval for this exact action, then use printful_guarded_request.`,
			true,
		);
	}
	if (allow === "guarded" && !guarded) {
		return text(
			`${method} ${path} doesn't spend money or delete anything, so it doesn't belong in printful_guarded_request. Use printful_get or printful_request.`,
			true,
		);
	}

	const response = await printfulFetch(base, auth, method, path, body);
	let payload = response.body;
	if (payload.length > MAX_RESPONSE_CHARS) {
		payload = `${payload.slice(0, MAX_RESPONSE_CHARS)}\n…[truncated ${payload.length - MAX_RESPONSE_CHARS} characters; use limit/offset or a narrower path]`;
	}
	if (response.status === 429) {
		return text(`HTTP 429 from ${method} ${path}: rate limited. Stop and retry later.\n${payload}`, true);
	}
	if (response.status < 200 || response.status >= 300) {
		return text(`HTTP ${response.status} from ${method} ${path}: ${errorSummary(response.body)}\n${payload}`, true);
	}
	return text(payload);
}

export function createServer(base: string, auth: PrintfulAuth): McpServer {
	const server = new McpServer({ name: "printful", version: "0.4.0" });

	server.registerTool(
		"printful_get",
		{
			title: "Read from Printful",
			description:
				"GET any Printful API v1 or v2 path with the signed-in store's token and return the raw JSON. Covers the catalog, prices, stock, mockup tasks, files, orders, shipments, invoices and store statistics. Follow the printful-api skill for which version to use.",
			inputSchema: z.object({ path: pathSchema }),
			annotations: { readOnlyHint: true, openWorldHint: true },
		},
		async ({ path }) => call(base, auth, "GET", path, undefined, "unguarded"),
	);

	server.registerTool(
		"printful_request",
		{
			title: "Write to Printful",
			description:
				"POST, PUT, PATCH or DELETE a Printful API path that doesn't spend money or permanently delete anything: draft orders and their items, mockup tasks, file uploads, saved products, shipping-rate and cost estimates. Calls that confirm (charge) an order or cancel/delete one are refused here; they go through printful_guarded_request.",
			inputSchema: z.object({
				method: z.enum(["POST", "PUT", "PATCH", "DELETE"]),
				path: pathSchema,
				body: bodySchema,
			}),
			annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
		},
		async ({ method, path, body }) => call(base, auth, method, path, body, "unguarded"),
	);

	server.registerTool(
		"printful_guarded_request",
		{
			title: "Confirm, cancel or delete in Printful",
			description:
				"Run a Printful call that charges the billing method or can't be undone: confirming an order (POST /v2/orders/{id}/confirmation), cancelling a v1 order, deleting a v2 order, or deleting a saved product, variant or template. Only call this after the user has explicitly approved this exact action, with its cost, in this conversation. Anything else is refused.",
			inputSchema: z.object({
				method: z.enum(["POST", "PUT", "DELETE"]),
				path: pathSchema,
				body: bodySchema,
			}),
			annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
		},
		async ({ method, path, body }) => call(base, auth, method, path, body, "guarded"),
	);

	return server;
}
