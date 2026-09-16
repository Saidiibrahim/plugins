#!/usr/bin/env python3
"""Check whether an image is print-ready for a Printful print area.

Usage:
  check-print-ready.py IMAGE --width-in W --height-in H [--dpi 150]
                       [--ideal-dpi 300] [--technique dtg]

Prints one JSON object to stdout with the measurements and a verdict
("ok", "warn" or "fail") plus the reasons. Exit codes: 0 ok or warn,
1 fail, 2 usage error / unreadable file / Pillow missing.
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.stderr.write(
        "check-print-ready: Pillow is not installed. Install it with\n"
        "  python3 -m pip install --user Pillow\n"
        "(or inside a virtualenv) and run again.\n"
    )
    sys.exit(2)

TECHNIQUES = ["dtg", "digital", "cut-sew", "uv", "embroidery", "sublimation", "dtfilm"]
# Techniques where the design is printed onto a coloured blank, so the
# background must be transparent or it prints as a visible box.
TRANSPARENT_BG = {"dtg", "dtfilm", "embroidery", "uv"}
# Techniques that normally expect a full-bleed opaque image.
FULL_BLEED = {"sublimation", "cut-sew", "digital"}
ASPECT_TOLERANCE = 0.02  # 2 %
MAX_FILE_BYTES = 200 * 1024 * 1024
EMBROIDERY_MAX_COLOURS = 15


def alpha_info(img):
    """Return (has_alpha_channel, transparent_fraction, content_bbox)."""
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    if img.mode not in ("RGBA", "LA", "PA"):
        return False, 0.0, None
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    total = img.width * img.height
    transparent = hist[0]
    return True, transparent / total if total else 0.0, alpha.getbbox()


def colour_stats(img):
    """Rough colour complexity over opaque pixels.

    Quantise every channel to 8 levels (512 buckets), then count buckets that
    hold at least 0.5 % of the opaque pixels and how much of the image the top
    15 buckets cover. Flat artwork concentrates in a few buckets; gradients,
    photos and soft shadows spread out.
    """
    # Convert first: thumbnail() rejects some modes (e.g. 16-bit "I;16").
    rgba = img.convert("RGBA")
    rgba.thumbnail((400, 400))
    data = rgba.tobytes()  # flat RGBA bytes; avoids getdata(), deprecated in newer Pillow
    pixels = [data[i:i + 4] for i in range(0, len(data), 4)]
    counts = {}
    opaque = 0
    for r, g, b, a in pixels:
        if a < 128:
            continue
        opaque += 1
        key = (r >> 5, g >> 5, b >> 5)
        counts[key] = counts.get(key, 0) + 1
    if not opaque:
        return {"opaque_pixels_sampled": 0, "significant_colours": 0, "top15_coverage": 1.0,
                "partial_alpha_fraction": 0.0}
    ordered = sorted(counts.values(), reverse=True)
    significant = sum(1 for c in ordered if c / opaque >= 0.005)
    top15 = sum(ordered[:EMBROIDERY_MAX_COLOURS]) / opaque
    partial = sum(1 for p in pixels if 0 < p[3] < 255) / len(pixels)
    return {
        "opaque_pixels_sampled": opaque,
        "significant_colours": significant,
        "top15_coverage": round(top15, 3),
        "partial_alpha_fraction": round(partial, 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--width-in", type=float, required=True, help="print area width in inches")
    ap.add_argument("--height-in", type=float, required=True, help="print area height in inches")
    ap.add_argument("--dpi", type=float, default=150, help="minimum acceptable dpi (default 150)")
    ap.add_argument("--ideal-dpi", type=float, default=300, help="ideal dpi (default 300)")
    ap.add_argument("--technique", choices=TECHNIQUES, default="dtg")
    args = ap.parse_args()

    if args.width_in <= 0 or args.height_in <= 0 or args.dpi <= 0:
        ap.error("--width-in, --height-in and --dpi must be positive")

    try:
        img = Image.open(args.image)
        img.load()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"check-print-ready: cannot read {args.image}: {exc}\n")
        sys.exit(2)

    fmt = img.format
    original_mode = img.mode
    embedded_dpi = img.info.get("dpi")
    icc = img.info.get("icc_profile")
    img = ImageOps.exif_transpose(img)

    fail, warn, notes = [], [], []
    w, h = img.size
    wi, hi = args.width_in, args.height_in

    eff_dpi = min(w / wi, h / hi)
    limiting_axis = "width" if w / wi <= h / hi else "height"
    img_ratio = w / h
    area_ratio = wi / hi
    aspect_diff = abs(img_ratio - area_ratio) / area_ratio

    has_alpha, transparent_frac, bbox = alpha_info(img)
    content = None
    if has_alpha and bbox and bbox != (0, 0, w, h):
        cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
        content = {
            "bbox": list(bbox),
            "width_px": cw,
            "height_px": ch,
            "effective_dpi_if_trimmed": round(min(cw / wi, ch / hi), 1),
        }

    size_bytes = os.path.getsize(args.image)

    # Resolution
    if eff_dpi < args.dpi:
        fail.append(
            f"effective resolution {eff_dpi:.0f} dpi (limited by {limiting_axis}) is below the "
            f"{args.dpi:.0f} dpi minimum; needs at least {round(wi * args.dpi)}x{round(hi * args.dpi)} px"
        )
    elif eff_dpi < args.ideal_dpi:
        warn.append(
            f"effective resolution {eff_dpi:.0f} dpi is acceptable but below the ideal "
            f"{args.ideal_dpi:.0f} dpi ({round(wi * args.ideal_dpi)}x{round(hi * args.ideal_dpi)} px)"
        )

    # Aspect ratio
    if aspect_diff > ASPECT_TOLERANCE:
        warn.append(
            f"aspect ratio {img_ratio:.3f} differs from the print area {area_ratio:.3f} by "
            f"{aspect_diff * 100:.1f}%; the design will not fill the area (pad or crop it)"
        )

    # Colour mode
    if original_mode == "CMYK":
        warn.append("image is CMYK; convert to sRGB before printing (prepare-print-file.py does this)")
    elif original_mode in ("I", "I;16", "I;16B", "F"):
        warn.append(f"image mode {original_mode} (high bit depth); convert to 8-bit sRGB")
    if icc and original_mode != "CMYK":
        try:
            from PIL import ImageCms
            import io
            desc = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip()
            if "srgb" not in desc.lower():
                warn.append(f"embedded colour profile '{desc}' is not sRGB; convert to sRGB")
            else:
                notes.append(f"embedded colour profile: {desc}")
        except Exception:  # noqa: BLE001
            notes.append("has an embedded colour profile that could not be read")

    # Transparency by technique
    if args.technique in TRANSPARENT_BG:
        if not has_alpha:
            warn.append(
                f"no transparency: for {args.technique} the whole rectangle prints, including any "
                "background colour; use a PNG with a transparent background"
            )
        elif transparent_frac == 0:
            warn.append("has an alpha channel but no transparent pixels; the background will print")
    elif args.technique in FULL_BLEED and has_alpha and transparent_frac > 0.01:
        notes.append(
            f"{transparent_frac * 100:.0f}% transparent pixels; for {args.technique} these show the "
            "base material (usually white)"
        )

    if content:
        notes.append(
            "transparent padding around the artwork; trimming it gives "
            f"{content['effective_dpi_if_trimmed']:.0f} dpi for the artwork itself"
        )

    if fmt not in ("PNG", "JPEG"):
        warn.append(f"file format {fmt}; Printful prefers PNG (transparent) or JPG")
    if size_bytes > MAX_FILE_BYTES:
        fail.append("file is larger than 200 MB")

    colours = None
    if args.technique == "embroidery":
        colours = colour_stats(img)
        if colours["significant_colours"] > EMBROIDERY_MAX_COLOURS or colours["top15_coverage"] < 0.9:
            warn.append(
                f"about {colours['significant_colours']} distinct colours "
                f"(top {EMBROIDERY_MAX_COLOURS} cover {colours['top15_coverage'] * 100:.0f}%); embroidery "
                "needs flat colours from a limited thread palette, no gradients, photos or shadows"
            )
        if colours["partial_alpha_fraction"] > 0.02:
            warn.append("soft or semi-transparent edges; embroidery needs hard edges")
        notes.append("embroidery: keep lines at least 0.05 in thick and text at least 0.25 in tall")

    verdict = "fail" if fail else ("warn" if warn else "ok")
    report = {
        "file": args.image,
        "format": fmt,
        "size_bytes": size_bytes,
        "width_px": w,
        "height_px": h,
        "mode": original_mode,
        "has_alpha": has_alpha,
        "transparent_fraction": round(transparent_frac, 3),
        "embedded_dpi": list(embedded_dpi) if embedded_dpi else None,
        "technique": args.technique,
        "print_area": {"width_in": wi, "height_in": hi, "min_dpi": args.dpi, "ideal_dpi": args.ideal_dpi},
        "required_px": {
            "min": [round(wi * args.dpi), round(hi * args.dpi)],
            "ideal": [round(wi * args.ideal_dpi), round(hi * args.ideal_dpi)],
        },
        "effective_dpi": round(eff_dpi, 1),
        "limiting_axis": limiting_axis,
        "aspect": {"image": round(img_ratio, 4), "print_area": round(area_ratio, 4),
                   "mismatch_pct": round(aspect_diff * 100, 1)},
        "content": content,
        "colours": colours,
        "verdict": verdict,
        "reasons": fail + warn,
        "notes": notes,
    }
    print(json.dumps(report, indent=2))
    sys.exit(1 if verdict == "fail" else 0)


if __name__ == "__main__":
    main()
