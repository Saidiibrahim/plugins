#!/usr/bin/env python3
"""orders-summary.py - summarise Printful v2 order pages offline.

Reads the JSON bodies returned by `GET /v2/orders` (one or more pages, as files
or concatenated on stdin) and prints counts by status, spend per currency and
the orders that need attention. Makes no network calls. Standard library only.

Usage:
  orders-summary.py [--days 7 | --since 2026-09-01T00:00:00Z] [--now ISO]
                    [--draft-hours 48] [--stale-business-days 7]
                    [--json] [--csv orders.csv] [page.json ...]

Input: any mix of v2 list envelopes ({"data": [...], "paging": ...}), single
order envelopes ({"data": {...}}) or bare order objects/arrays. Several JSON
documents may be concatenated in one file or on stdin. Orders are de-duplicated
by id.

Rules:
- Period = created_at >= since and <= now. Counts, spend and the order table
  cover the period only.
- Spend = sum of costs.total per costs.currency for period orders whose status
  is not draft, failed or canceled (those are uncharged, or refunded when
  canceled). Retail totals are summed separately when retail_costs.total > 0.
- Attention = every supplied order (any age) that is failed, onhold or
  inreview; drafts older than --draft-hours (by created_at); pending or
  inprocess orders not updated for more than --stale-business-days weekdays.
- Shipment candidates = period orders (plus any partial/inprocess/pending
  order) that are not draft, failed or canceled: fetch their shipments.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

UNCHARGED = {"draft", "failed", "canceled"}
STATUS_ORDER = ["draft", "failed", "inreview", "onhold", "pending",
                "inprocess", "partial", "fulfilled", "canceled"]
ATTENTION_HINT = {
    "failed": "Not accepted (payment, address or file problem). If payment: top up the "
              "Printful Wallet or fix billing in the dashboard, then re-confirm; "
              "otherwise PATCH the draft/failed order and re-confirm.",
    "onhold": "Held during fulfillment; check GET /v2/approval-sheets?order_id=<id> "
              "and Printful support messages in the dashboard.",
    "inreview": "Being reviewed by Printful; still cancellable. Usually clears on its own.",
    "draft": "Forgotten draft (drafts are never charged). Confirm it or delete it.",
    "stale": "No status change for longer than the usual production window; "
             "check shipments or contact Printful support.",
}


def parse_ts(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def iter_json_docs(text):
    decoder = json.JSONDecoder()
    idx, end = 0, len(text)
    while idx < end:
        while idx < end and text[idx].isspace():
            idx += 1
        if idx >= end:
            break
        obj, idx = decoder.raw_decode(text, idx)
        yield obj


def extract_orders(doc):
    if isinstance(doc, list):
        for item in doc:
            yield from extract_orders(item)
    elif isinstance(doc, dict):
        if "data" in doc:
            yield from extract_orders(doc["data"])
        elif "id" in doc and "status" in doc:
            yield doc


def business_days_between(start, end):
    """Whole weekdays elapsed from start to end (UTC dates)."""
    if end <= start:
        return 0
    days = 0
    day = start.date()
    last = end.date()
    while day < last:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days += 1
    return days


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def summarise(orders, since, now, draft_hours, stale_bdays):
    period = []
    for o in orders:
        created = parse_ts(o.get("created_at"))
        if created and since <= created <= now:
            period.append(o)
    period.sort(key=lambda o: o.get("created_at") or "", reverse=True)

    counts = {}
    spend, retail = {}, {}
    for o in period:
        status = o.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
        if status in UNCHARGED:
            continue
        costs = o.get("costs") or {}
        cur = costs.get("currency") or "?"
        spend[cur] = spend.get(cur, Decimal("0")) + money(costs.get("total"))
        rc = o.get("retail_costs") or {}
        if money(rc.get("total")) > 0:
            rcur = rc.get("currency") or "?"
            retail[rcur] = retail.get(rcur, Decimal("0")) + money(rc.get("total"))

    attention = []
    for o in orders:
        status = o.get("status")
        created = parse_ts(o.get("created_at"))
        updated = parse_ts(o.get("updated_at")) or created
        reason = None
        if status in ("failed", "onhold", "inreview"):
            reason = status
        elif status == "draft" and created and now - created > timedelta(hours=draft_hours):
            reason = "draft"
        elif status in ("pending", "inprocess") and updated \
                and business_days_between(updated, now) > stale_bdays:
            reason = "stale"
        if reason:
            costs = o.get("costs") or {}
            attention.append({
                "id": o.get("id"),
                "external_id": o.get("external_id"),
                "status": status,
                "issue": reason,
                "created_at": o.get("created_at"),
                "updated_at": o.get("updated_at"),
                "age_days": round((now - created).total_seconds() / 86400, 1) if created else None,
                "recipient": (o.get("recipient") or {}).get("name"),
                "total": costs.get("total"),
                "currency": costs.get("currency"),
                "hint": ATTENTION_HINT[reason],
            })
    rank = {"failed": 0, "onhold": 1, "stale": 2, "inreview": 3, "draft": 4}
    attention.sort(key=lambda a: (rank[a["issue"]], a["created_at"] or ""))

    seen = set()
    candidates = []
    for o in period + [o for o in orders if o.get("status") in ("pending", "inprocess", "partial")]:
        if o.get("status") in UNCHARGED or o.get("id") in seen:
            continue
        seen.add(o.get("id"))
        candidates.append(o.get("id"))

    return {
        "since": fmt(since),
        "now": fmt(now),
        "orders_supplied": len(orders),
        "orders_in_period": len(period),
        "counts_by_status": {k: counts[k] for k in
                             sorted(counts, key=lambda s: (STATUS_ORDER.index(s)
                                                           if s in STATUS_ORDER else 99, s))},
        "spend_by_currency": {k: str(v) for k, v in sorted(spend.items())},
        "retail_by_currency": {k: str(v) for k, v in sorted(retail.items())},
        "attention": attention,
        "shipment_candidates": candidates,
        "period_orders": [{
            "id": o.get("id"),
            "external_id": o.get("external_id"),
            "status": o.get("status"),
            "created_at": o.get("created_at"),
            "items": sum(int(i.get("quantity") or 0) for i in (o.get("order_items") or [])),
            "total": (o.get("costs") or {}).get("total"),
            "currency": (o.get("costs") or {}).get("currency"),
        } for o in period],
    }


def print_text(r):
    out = sys.stdout
    out.write(f"Period: {r['since']} to {r['now']}\n")
    out.write(f"Orders in period: {r['orders_in_period']} (of {r['orders_supplied']} supplied)\n")
    if r["counts_by_status"]:
        out.write("By status: " + ", ".join(f"{k} {v}" for k, v in r["counts_by_status"].items()) + "\n")
    if r["spend_by_currency"]:
        out.write("Spent (charged orders): " +
                  ", ".join(f"{v} {k}" for k, v in r["spend_by_currency"].items()) + "\n")
    else:
        out.write("Spent (charged orders): 0\n")
    if r["retail_by_currency"]:
        out.write("Retail value: " +
                  ", ".join(f"{v} {k}" for k, v in r["retail_by_currency"].items()) + "\n")
    out.write(f"\nNeeds attention: {len(r['attention'])}\n")
    if r["attention"]:
        out.write("| Order | Status | Issue | Age (days) | Total | Next step |\n")
        out.write("| --- | --- | --- | --- | --- | --- |\n")
        for a in r["attention"]:
            total = f"{a['total']} {a['currency']}" if a["total"] else ""
            out.write(f"| {a['id']} | {a['status']} | {a['issue']} | {a['age_days']} | "
                      f"{total} | {a['hint']} |\n")
    out.write("\nShipment candidates: " +
              (" ".join(str(i) for i in r["shipment_candidates"]) or "none") + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="JSON files (default: stdin)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--days", type=float, default=7, help="period length in days (default 7)")
    grp.add_argument("--since", help="period start, ISO 8601 (overrides --days)")
    ap.add_argument("--now", help="reference time, ISO 8601 (default: current UTC time)")
    ap.add_argument("--draft-hours", type=float, default=48)
    ap.add_argument("--stale-business-days", type=int, default=7)
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--csv", metavar="PATH", help="also write period orders to a CSV file")
    args = ap.parse_args()

    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        ap.error("--now is not a valid ISO 8601 timestamp")
    if args.since:
        since = parse_ts(args.since)
        if since is None:
            ap.error("--since is not a valid ISO 8601 timestamp")
    else:
        since = now - timedelta(days=args.days)

    texts = []
    if args.files:
        for path in args.files:
            with open(path, encoding="utf-8") as fh:
                texts.append(fh.read())
    else:
        texts.append(sys.stdin.read())

    by_id = {}
    try:
        for text in texts:
            for doc in iter_json_docs(text):
                for order in extract_orders(doc):
                    by_id[order.get("id")] = order
    except json.JSONDecodeError as exc:
        print(f"orders-summary: invalid JSON input: {exc}", file=sys.stderr)
        return 65

    result = summarise(list(by_id.values()), since, now, args.draft_hours, args.stale_business_days)

    if args.csv:
        fields = ["id", "external_id", "status", "created_at", "items", "total", "currency"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result["period_orders"])

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
