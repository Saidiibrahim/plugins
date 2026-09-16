#!/usr/bin/env python3
"""confirm-gate.py - decide whether a Printful v2 order may be confirmed.

Usage:
  confirm-gate.py ORDER_JSON [--config PATH]
  bash pf.sh GET /v2/orders/123 | confirm-gate.py - [--config PATH]

ORDER_JSON is a file path or "-" for stdin (the default). It may be the full
v2 response ({"data": {...}}) or the bare order object. The config defaults to
${PRINTFUL_CONFIG:-$HOME/.config/printful-automation/config.json}.

Prints one JSON object:
  {"ready": bool, "auto_confirm_allowed": bool, "reasons": [...], "summary": {...}}

ready                 status is draft or failed AND costs.calculation_status is done
                      AND costs.total is a valid amount.
auto_confirm_allowed  ready AND config auto_confirm_max_total is a number AND
                      costs.total <= cap (Decimal math) AND costs.currency equals
                      config currency AND status is draft (a failed order is never
                      auto-confirmed) AND the order has at least one item with
                      quantity > 0 AND the recipient matches config ship_to
                      (name, address1, address2, city, state_code, country_code,
                      zip; all but address2/state_code must be non-empty).

The script cannot know whether the user asked for this order to be placed in
the current conversation; the caller must check that before auto-confirming.

Exit codes: 0 verdict printed (whatever it says), 64 usage / unreadable input.
Standard library only.
"""

import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

RECIPIENT_FIELDS = ("name", "address1", "address2", "city", "state_code", "country_code", "zip")
# Fields that may legitimately be blank on both sides; every other field must be non-empty.
OPTIONAL_RECIPIENT_FIELDS = ("address2", "state_code")
COST_FIELDS = (
    "subtotal", "discount", "shipping", "digitization", "additional_fee",
    "fulfillment_fee", "retail_delivery_fee", "vat", "tax", "total",
)


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(64)


def load_json(text, what):
    try:
        # parse_float=Decimal keeps money exact (no binary float rounding).
        return json.loads(text, parse_float=Decimal)
    except ValueError as exc:
        fail(f"{what} is not valid JSON: {exc}")


def parse_args(argv):
    order_src = "-"
    config = os.environ.get("PRINTFUL_CONFIG") or os.path.expanduser(
        "~/.config/printful-automation/config.json"
    )
    args = list(argv)
    positional = []
    while args:
        a = args.pop(0)
        if a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif a == "--config":
            if not args:
                fail("--config needs a path")
            config = args.pop(0)
        elif a.startswith("--config="):
            config = a.split("=", 1)[1]
        else:
            positional.append(a)
    if len(positional) > 1:
        fail("usage: confirm-gate.py [ORDER_JSON|-] [--config PATH]")
    if positional:
        order_src = positional[0]
    return order_src, config


def to_decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def norm(field, value):
    s = "" if value is None else str(value)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    if field == "zip":
        s = s.replace(" ", "")
    if field in ("state_code", "country_code"):
        s = s.upper()
    return s


def money(value):
    return None if value is None else str(value)


def main():
    order_src, config_path = parse_args(sys.argv[1:])

    if order_src == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(order_src, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            fail(f"cannot read order JSON: {exc}")
    doc = load_json(raw, "order")
    order = doc.get("data", doc) if isinstance(doc, dict) else None
    if not isinstance(order, dict):
        fail("order JSON must be an object (or {\"data\": {...}})")

    reasons = []
    costs = order.get("costs") if isinstance(order.get("costs"), dict) else {}
    status = order.get("status")
    calc = costs.get("calculation_status")
    currency = costs.get("currency")
    total = to_decimal(costs.get("total"))

    # --- readiness -------------------------------------------------------
    ready = True
    if status not in ("draft", "failed"):
        ready = False
        reasons.append(f"status is '{status}'; only draft or failed orders can be confirmed")
    if calc != "done":
        ready = False
        if calc == "failed":
            reasons.append("costs.calculation_status is 'failed'; fix the order (items, placements, recipient) before confirming")
        else:
            reasons.append(f"costs.calculation_status is '{calc}'; wait until it is 'done'")
    elif total is None:
        ready = False
        reasons.append("costs.total is missing or not a valid amount")

    # --- config ------------------------------------------------------------
    config = None
    try:
        with open(os.path.expanduser(config_path), encoding="utf-8") as fh:
            config = load_json(fh.read(), "config")
    except OSError:
        reasons.append(f"config not found at {config_path}; auto-confirm is off")
    if config is not None and not isinstance(config, dict):
        reasons.append("config is not a JSON object; auto-confirm is off")
        config = None

    cap_raw = config.get("auto_confirm_max_total") if config else None
    cfg_currency = config.get("currency") if config else None
    ship_to = config.get("ship_to") if config and isinstance(config.get("ship_to"), dict) else None

    # --- auto-confirm --------------------------------------------------------
    auto = ready and config is not None
    cap = None
    if config is not None:
        if cap_raw is None:
            auto = False
            reasons.append("auto_confirm_max_total is null; explicit approval required")
        elif isinstance(cap_raw, bool) or not isinstance(cap_raw, (int, Decimal)):
            auto = False
            reasons.append("auto_confirm_max_total is not a number; explicit approval required")
        else:
            cap = Decimal(cap_raw)
            if not cap.is_finite():
                auto = False
                cap = None
                reasons.append("auto_confirm_max_total is not a finite number; explicit approval required")
            elif total is not None and total > cap:
                auto = False
                reasons.append(f"total {total} exceeds auto_confirm_max_total {cap}")

        if not cfg_currency:
            auto = False
            reasons.append("config currency is not set")
        elif not currency or str(currency).upper() != str(cfg_currency).upper():
            auto = False
            reasons.append(f"order currency '{currency}' does not match config currency '{cfg_currency}'")

        recipient = order.get("recipient") if isinstance(order.get("recipient"), dict) else {}
        if ship_to is None:
            auto = False
            reasons.append("config ship_to is missing")
        else:
            mismatched = [
                f for f in RECIPIENT_FIELDS
                if norm(f, recipient.get(f)) != norm(f, ship_to.get(f))
            ]
            blank = [
                f for f in RECIPIENT_FIELDS
                if f not in OPTIONAL_RECIPIENT_FIELDS and not norm(f, ship_to.get(f))
            ]
            if mismatched:
                auto = False
                reasons.append("recipient differs from config ship_to in: " + ", ".join(mismatched))
            if blank:
                auto = False
                reasons.append("config ship_to is missing: " + ", ".join(blank))

        if status == "failed":
            auto = False
            reasons.append("order is 'failed'; re-confirming needs an explicit yes after the user has fixed billing or the order")

        quantities = [
            to_decimal(it.get("quantity"))
            for it in (order.get("order_items") or [])
            if isinstance(it, dict) and it.get("type", "order_item") == "order_item"
        ]
        if not any(q is not None and q > 0 for q in quantities):
            auto = False
            reasons.append("order has no items with quantity > 0")
    if not ready:
        auto = False

    if auto:
        reasons.append("all automatic checks pass; auto-confirm still requires that the user asked to place this order in this conversation")
    elif ready:
        reasons.append("ready for confirmation after an explicit yes from the user")

    # --- summary -------------------------------------------------------------
    recipient = order.get("recipient") if isinstance(order.get("recipient"), dict) else {}
    items = []
    for it in order.get("order_items") or []:
        if not isinstance(it, dict):
            continue
        items.append({
            "id": it.get("id"),
            "type": it.get("type"),
            "source": it.get("source"),
            "name": it.get("name"),
            "catalog_variant_id": it.get("catalog_variant_id"),
            "product_template_id": it.get("product_template_id"),
            "quantity": it.get("quantity"),
            "price": money(it.get("price")),
            "currency": it.get("currency"),
        })

    summary = {
        "order_id": order.get("id"),
        "external_id": order.get("external_id"),
        "status": status,
        "calculation_status": calc,
        "shipping": order.get("shipping"),
        "recipient": {k: recipient.get(k) for k in (
            "name", "address1", "address2", "city", "state_code", "country_code", "zip", "email")},
        "items": items,
        "costs": {k: money(costs.get(k)) for k in COST_FIELDS},
        "currency": currency,
        "total": None if total is None else str(total),
        "auto_confirm_max_total": None if cap is None else str(cap),
        "config_currency": cfg_currency,
    }

    print(json.dumps({
        "ready": ready,
        "auto_confirm_allowed": auto,
        "reasons": reasons,
        "summary": summary,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
