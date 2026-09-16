#!/usr/bin/env python3
"""Generate merch design candidates with a third-party image API.

Usage:
  generate-image.py --provider openai|ideogram|recraft --prompt TEXT
                    [--aspect W:H | --size WxH] [--n 2] [--out-dir designs/slug]
                    [--transparent] [--vector] [--model ID] [--quality high]
                    [--seed N] [--allow-more] [--dry-run] [--timeout 180]

Providers (verified 2026-09-16, see ../references/providers.md):
  openai    POST {base}/v1/images/generations        key OPENAI_API_KEY
            base default https://api.openai.com      override IMAGE_API_BASE_OPENAI
  ideogram  POST {base}/v1/ideogram-v4/generate[-transparent]
                                                     key IDEOGRAM_API_KEY
            base default https://api.ideogram.ai     override IMAGE_API_BASE_IDEOGRAM
  recraft   POST {base}/v1/images/generations        key RECRAFT_API_TOKEN
            base default https://external.api.recraft.ai
                                                     override IMAGE_API_BASE_RECRAFT

Saves candidate-NN.<ext> files plus a prompt.json sidecar in --out-dir and
prints a JSON summary to stdout. --dry-run prints the request(s) with the key
redacted and makes no network call.

Exit codes: 0 ok, 1 API/network error, 2 usage error, 3 missing API key.
Python 3 standard library only.
"""
import argparse
import base64
import datetime
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

MAX_N_WITHOUT_CONFIRM = 4

PROVIDERS = {
    "openai": {
        "env": "OPENAI_API_KEY",
        "base_env": "IMAGE_API_BASE_OPENAI",
        "base": "https://api.openai.com",
        "model": "gpt-image-2.5-flare",
    },
    "ideogram": {
        "env": "IDEOGRAM_API_KEY",
        "base_env": "IMAGE_API_BASE_IDEOGRAM",
        "base": "https://api.ideogram.ai",
        "model": "ideogram-v4",
    },
    "recraft": {
        "env": "RECRAFT_API_TOKEN",
        "base_env": "IMAGE_API_BASE_RECRAFT",
        "base": "https://external.api.recraft.ai",
        "model": "recraftv4_1",
    },
}

# Ideogram 4.0 generate-transparent aspect_ratio enum.
IDEOGRAM_ASPECTS = ["1x4", "1x3", "1x2", "9x16", "10x16", "2x3", "3x4", "4x5", "1x1",
                    "5x4", "4x3", "3x2", "16x10", "16x9", "2x1", "3x1", "4x1"]
# Ideogram 4.0 generate resolution enum.
IDEOGRAM_RESOLUTIONS = [
    "2048x2048", "1440x2880", "2880x1440", "1664x2496", "2496x1664", "1792x2240",
    "2240x1792", "1440x2560", "2560x1440", "1600x2560", "2560x1600", "1728x2304",
    "2304x1728", "1296x3168", "3168x1296", "1152x2944", "2944x1152", "1248x3328",
    "3328x1248", "1280x3072", "3072x1280", "1024x3072", "3072x1024", "1024x1024",
    "896x1120", "1120x896", "864x1152", "1152x864", "832x1248", "1248x832",
    "800x1280", "1280x800", "720x1280", "1280x720", "720x1440", "1440x720",
    "512x1536", "1536x512"]
# Recraft V4 / V4.1 supported aspect ratios.
RECRAFT_ASPECTS = ["1:1", "2:1", "1:2", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
                   "6:10", "14:10", "10:14", "16:9", "9:16"]


class UsageError(Exception):
    pass


class ApiError(Exception):
    pass


def eprint(*a):
    print(*a, file=sys.stderr)


def parse_ratio(text):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:xX]\s*(\d+(?:\.\d+)?)\s*", text or "")
    if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
        raise UsageError("expected W:H or WxH, got %r" % text)
    return float(m.group(1)), float(m.group(2))


def nearest(options, ratio, parse=parse_ratio):
    """Pick the option whose aspect ratio is closest (in log space) to ratio."""
    target = math.log(ratio)
    return min(options, key=lambda o: abs(math.log(parse(o)[0] / parse(o)[1]) - target))


def openai_size(args):
    if args.size:
        w, h = parse_ratio(args.size)
        return "%dx%d" % (w, h)
    if not args.aspect:
        return "1024x1024"
    w, h = parse_ratio(args.aspect)
    r = max(1 / 3, min(3.0, w / h))
    budget = 2560 * 1440  # largest non-experimental pixel count
    width = math.sqrt(budget * r)
    height = width / r
    width = max(16, int(width // 16) * 16)
    height = max(16, int(height // 16) * 16)
    if max(width, height) > 3840:
        scale = 3840 / max(width, height)
        width, height = int(width * scale // 16) * 16, int(height * scale // 16) * 16
    return "%dx%d" % (width, height)


def build_requests(args):
    """Return (list of request dicts, model, note list). One dict per HTTP call."""
    p = PROVIDERS[args.provider]
    base = os.environ.get(p["base_env"], p["base"]).rstrip("/")
    notes = []
    reqs = []
    if args.provider == "openai":
        if args.vector:
            raise UsageError("openai cannot produce vector output; use --provider recraft")
        model = args.model or p["model"]
        body = {
            "model": model,
            "prompt": args.prompt,
            "n": args.n,
            "size": openai_size(args),
            "quality": args.quality or "high",
            "output_format": "png",
        }
        if args.transparent:
            body["background"] = "transparent"
        reqs.append({"method": "POST", "url": base + "/v1/images/generations",
                     "headers": {"Authorization": "Bearer {KEY}",
                                 "Content-Type": "application/json"},
                     "body": body})
    elif args.provider == "ideogram":
        if args.vector:
            raise UsageError("ideogram cannot produce vector output; use --provider recraft")
        model = args.model or p["model"]
        if model != "ideogram-v4":
            raise UsageError("ideogram provider supports only --model ideogram-v4")
        if args.size and not args.aspect:
            w, h = parse_ratio(args.size)
        elif args.aspect:
            w, h = parse_ratio(args.aspect)
        else:
            w, h = 1, 1
        if args.transparent:
            path = "/v1/ideogram-v4/generate-transparent"
            body = {"text_prompt": args.prompt,
                    "aspect_ratio": nearest(IDEOGRAM_ASPECTS, w / h),
                    "output_resolution": args.resolution or "4K",
                    "rendering_speed": args.quality or "DEFAULT"}
        else:
            path = "/v1/ideogram-v4/generate"
            body = {"text_prompt": args.prompt,
                    "resolution": nearest(IDEOGRAM_RESOLUTIONS, w / h),
                    "rendering_speed": args.quality or "DEFAULT"}
        # Ideogram V4 has no num_images field: one call per image.
        for i in range(args.n):
            b = dict(body)
            if args.seed is not None:
                b["seed"] = args.seed + i
            reqs.append({"method": "POST", "url": base + path,
                         "headers": {"Api-Key": "{KEY}", "Content-Type": "application/json"},
                         "body": b})
    else:  # recraft
        model = args.model or ("recraftv4_1_vector" if args.vector else p["model"])
        if args.vector and not model.endswith("_vector"):
            raise UsageError("--vector needs a model ending in _vector")
        body = {"prompt": args.prompt, "n": args.n, "model": model, "response_format": "url"}
        if args.size and not args.aspect:
            body["size"] = args.size
        elif args.aspect:
            w, h = parse_ratio(args.aspect)
            body["size"] = nearest(RECRAFT_ASPECTS, w / h)
        if args.seed is not None:
            body["random_seed"] = args.seed
        if args.transparent:
            notes.append("recraft has no transparent-background generation option; "
                         "run background removal afterwards (see references/providers.md)")
        reqs.append({"method": "POST", "url": base + "/v1/images/generations",
                     "headers": {"Authorization": "Bearer {KEY}",
                                 "Content-Type": "application/json"},
                     "body": body})
    return reqs, model, notes


def http(method, url, headers=None, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        raise ApiError("HTTP %d from %s: %s" % (e.code, url.split("?")[0], detail))
    except urllib.error.URLError as e:
        raise ApiError("network error calling %s: %s" % (url.split("?")[0], e.reason))


def sniff_ext(data, content_type=""):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head:
        return "svg"
    if "svg" in content_type:
        return "svg"
    return "png"


def next_index(out_dir):
    n = 0
    for name in os.listdir(out_dir):
        m = re.match(r"candidate-(\d+)\.", name)
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def save(out_dir, idx, data, content_type=""):
    path = os.path.join(out_dir, "candidate-%02d.%s" % (idx, sniff_ext(data, content_type)))
    with open(path, "wb") as f:
        f.write(data)
    return path


def run(args):
    reqs, model, notes = build_requests(args)
    p = PROVIDERS[args.provider]

    if args.dry_run:
        print(json.dumps({"dry_run": True, "provider": args.provider, "model": model,
                          "key_env": p["env"], "key_present": bool(os.environ.get(p["env"])),
                          "http_calls": len(reqs), "requests": reqs, "notes": notes,
                          "out_dir": args.out_dir}, indent=2))
        return 0

    key = os.environ.get(p["env"])
    if not key:
        eprint("generate-image: %s is not set. Export your %s API key as %s "
               "(never paste it into chat), or choose another --provider."
               % (p["env"], args.provider, p["env"]))
        return 3

    os.makedirs(args.out_dir, exist_ok=True)
    idx = next_index(args.out_dir)
    saved, seeds, revised = [], [], []

    for r in reqs:
        headers = {k: v.replace("{KEY}", key) for k, v in r["headers"].items()}
        raw, _ = http(r["method"], r["url"], headers, r["body"], args.timeout)
        try:
            resp = json.loads(raw)
        except ValueError:
            raise ApiError("non-JSON response from %s" % r["url"])
        items = resp.get("data") or []
        if not items:
            raise ApiError("no images in response: %s" % json.dumps(resp)[:500])
        for item in items:
            if args.provider == "openai":
                b64 = item.get("b64_json")
                if not b64:
                    raise ApiError("openai response item has no b64_json")
                data, ctype = base64.b64decode(b64), "image/png"
                if item.get("revised_prompt"):
                    revised.append(item["revised_prompt"])
            else:
                if item.get("is_image_safe") is False or not item.get("url"):
                    notes.append("one image was withheld by the provider safety filter")
                    continue
                # URLs expire (Ideogram: limited period; Recraft: ~24 h). Download now.
                data, ctype = http("GET", item["url"], timeout=args.timeout)
                if item.get("seed") is not None:
                    seeds.append(item["seed"])
                if item.get("prompt") and item["prompt"] != args.prompt:
                    revised.append(item["prompt"])
            saved.append(save(args.out_dir, idx, data, ctype))
            idx += 1

    record = {
        "provider": args.provider,
        "model": model,
        "prompt": args.prompt,
        "request": [r["body"] for r in reqs],
        "seed": args.seed,
        "returned_seeds": seeds,
        "revised_prompts": revised,
        "transparent_requested": bool(args.transparent),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "files": [os.path.basename(s) for s in saved],
        "notes": notes,
    }
    sidecar = os.path.join(args.out_dir, "prompt.json")
    history = []
    if os.path.exists(sidecar):
        try:
            with open(sidecar) as f:
                old = json.load(f)
            history = old.get("generations", []) if isinstance(old, dict) else []
        except (OSError, ValueError):
            history = []
    history.append(record)
    with open(sidecar, "w") as f:
        json.dump({"generations": history}, f, indent=2)

    print(json.dumps({"provider": args.provider, "model": model, "files": saved,
                      "sidecar": sidecar, "seeds": seeds, "notes": notes}, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate merch design candidates.")
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--aspect", help="target aspect ratio W:H, e.g. 12:16 from the print area")
    ap.add_argument("--size", help="explicit WxH (openai, recraft); overrides --aspect only if no --aspect")
    ap.add_argument("--n", type=int, default=2, help="number of candidates (default 2)")
    ap.add_argument("--out-dir", default="designs/untitled")
    ap.add_argument("--transparent", action="store_true", help="request a transparent background")
    ap.add_argument("--vector", action="store_true", help="SVG output (recraft only)")
    ap.add_argument("--model", help="override the provider's default model id")
    ap.add_argument("--quality", help="openai: low|medium|high|xhigh|max|auto; "
                                      "ideogram: TURBO|DEFAULT|QUALITY (rendering_speed)")
    ap.add_argument("--resolution", help="ideogram transparent output_resolution: 1K|2K|4K|8K")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--allow-more", action="store_true",
                    help="permit --n above 4 (only after the user agreed to the cost)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args(argv)

    try:
        if not args.prompt.strip():
            raise UsageError("--prompt is empty")
        if args.n < 1:
            raise UsageError("--n must be at least 1")
        if args.n > MAX_N_WITHOUT_CONFIRM and not args.allow_more:
            raise UsageError("--n %d is more than %d images; confirm the cost with the user, "
                             "then pass --allow-more" % (args.n, MAX_N_WITHOUT_CONFIRM))
        limits = {"openai": 10, "recraft": 6, "ideogram": 10}
        if args.n > limits[args.provider]:
            raise UsageError("%s allows at most %d images per run" % (args.provider, limits[args.provider]))
        if args.vector and args.provider != "recraft":
            raise UsageError("--vector is only supported by --provider recraft")
        return run(args)
    except UsageError as e:
        eprint("generate-image: %s" % e)
        return 2
    except ApiError as e:
        eprint("generate-image: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
