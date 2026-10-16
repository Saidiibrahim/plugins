import assert from "node:assert/strict";
import { test } from "node:test";
import { errorSummary, guardReason, type Method, normalizePath, PathError } from "../src/printful.ts";

const guarded: [Method, string][] = [
	["POST", "/v2/orders/123/confirmation"],
	["POST", "/orders/123/confirm"],
	["POST", "/orders?confirm=true"],
	["PUT", "/orders/123?confirm=1"],
	["DELETE", "/v2/orders/123"],
	["DELETE", "/orders/@ext-id"],
	["DELETE", "/store/products/9"],
	["DELETE", "/store/variants/9"],
	["DELETE", "/sync/products/9"],
	["DELETE", "/sync/variant/9"],
	["DELETE", "/product-templates/9"],
];

const unguarded: [Method, string][] = [
	["GET", "/v2/orders/123"],
	["POST", "/v2/orders"],
	["POST", "/v2/orders/123/order-items"],
	["PATCH", "/v2/orders/123"],
	["PUT", "/orders/123"],
	["POST", "/orders"],
	["DELETE", "/v2/orders/123/order-items/5"],
	["POST", "/v2/mockup-tasks"],
];

test("calls that spend money or can't be undone are guarded", () => {
	for (const [method, path] of guarded) {
		assert.ok(guardReason(method, normalizePath(path)), `${method} ${path} should be guarded`);
	}
});

test("everyday reads and writes are not guarded", () => {
	for (const [method, path] of unguarded) {
		assert.equal(guardReason(method, normalizePath(path)), null, `${method} ${path} should not be guarded`);
	}
});

test("path tricks can't sneak a guarded call past the guard", () => {
	assert.ok(guardReason("POST", normalizePath("//v2//orders/1/confirmation#x")));
	assert.ok(guardReason("POST", normalizePath("/v2/orders/1/confirmation/")));
	assert.ok(guardReason("POST", normalizePath("/orders?CONFIRM=TRUE")));
	assert.ok(guardReason("DELETE", normalizePath("v2/orders/1")));
	for (const path of ["/v2/orders/1/../1/confirmation", "/v2/./orders", "/v2/orders/1%2fconfirmation", "/v2/%2E%2E/x", "/a%5cb"]) {
		assert.throws(() => normalizePath(path), PathError, path);
	}
});

test("errors are summarised for both API versions", () => {
	assert.equal(errorSummary('{"code":400,"result":"x","error":{"reason":"BadRequest","message":"Missing zip"}}'), "Missing zip");
	assert.equal(errorSummary('{"type":"t","status":404,"title":"Not Found","detail":"Order 1 not found"}'), "Not Found - Order 1 not found");
	assert.equal(errorSummary('{"error":{"message":"Bad item"}}'), "Bad item");
	assert.equal(errorSummary("<html>"), "non-JSON response");
});
