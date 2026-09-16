#!/usr/bin/env python3
"""Make a print-ready PNG for a Printful print area.

Usage:
  prepare-print-file.py IMAGE --width-in W --height-in H [--dpi 300]
                        [--out PATH] [--allow-upscale] [--no-trim]
                        [--valign center|top] [--background transparent|#RRGGBB]
                        [--force]

Steps: apply EXIF rotation, convert to 8-bit sRGB with alpha, trim fully
transparent padding, scale the artwork to fit the print-area aspect ratio,
and centre it on a canvas of exactly that aspect ratio.

Canvas size is W*dpi x H*dpi. If the artwork is too small for that and
--allow-upscale is not given, the artwork is not enlarged; the canvas is
built at the artwork's own resolution instead (same aspect, lower dpi) and
the result reports that dpi so you can judge it.

Never overwrites the input. Default output: <input stem>-print.png next to
the input. Prints a JSON summary. Exit codes: 0 success, 2 error.
"""

import argparse
import io
import json
import os
import sys

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.stderr.write(
        "prepare-print-file: Pillow is not installed. Install it with\n"
        "  python3 -m pip install --user Pillow\n"
        "(or inside a virtualenv) and run again.\n"
    )
    sys.exit(2)


def die(msg):
    sys.stderr.write(f"prepare-print-file: {msg}\n")
    sys.exit(2)


def to_srgb_rgba(img, notes):
    icc = img.info.get("icc_profile")
    mode = img.mode
    if icc:
        try:
            from PIL import ImageCms
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            desc = ImageCms.getProfileDescription(src).strip()
            if "srgb" not in desc.lower() or mode == "CMYK":
                dst = ImageCms.createProfile("sRGB")
                out_mode = "RGB" if mode in ("CMYK", "RGB", "L") else "RGBA"
                if mode not in ("CMYK", "RGB", "RGBA", "L"):
                    img = img.convert("RGBA")
                    out_mode = "RGBA"
                img = ImageCms.profileToProfile(img, src, dst, outputMode=out_mode)
                notes.append(f"converted colour profile '{desc}' to sRGB")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"could not apply embedded colour profile ({exc}); used a plain conversion")
    if img.mode == "CMYK":
        notes.append("converted CMYK to RGB without a profile; check colours on the mockup")
        img = img.convert("RGB")
    if img.mode in ("I", "I;16", "I;16B", "I;16L", "F"):
        # Scale high bit depth greyscale down to 8 bits.
        img = img.point(lambda v: v / 257).convert("L")
        notes.append(f"reduced {mode} to 8-bit")
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def parse_bg(value):
    if value == "transparent":
        return (0, 0, 0, 0)
    v = value.lstrip("#")
    if len(v) != 6:
        die("--background must be 'transparent' or #RRGGBB")
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255)
    except ValueError:
        die("--background must be 'transparent' or #RRGGBB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--width-in", type=float, required=True)
    ap.add_argument("--height-in", type=float, required=True)
    ap.add_argument("--dpi", type=float, default=300, help="target dpi (default 300)")
    ap.add_argument("--out", help="output path (default <stem>-print.png)")
    ap.add_argument("--allow-upscale", action="store_true", help="enlarge small artwork to the target dpi")
    ap.add_argument("--no-trim", action="store_true", help="keep transparent padding")
    ap.add_argument("--valign", choices=["center", "top"], default="center",
                    help="vertical placement inside the canvas (top suits shirt fronts)")
    ap.add_argument("--background", default="transparent", help="'transparent' (default) or #RRGGBB")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file (never the input)")
    args = ap.parse_args()

    if args.width_in <= 0 or args.height_in <= 0 or args.dpi <= 0:
        die("--width-in, --height-in and --dpi must be positive")

    src_path = os.path.abspath(args.image)
    if args.out:
        out_path = os.path.abspath(args.out)
    else:
        stem, _ = os.path.splitext(src_path)
        out_path = stem + "-print.png"
    if not out_path.lower().endswith(".png"):
        die("output must be a .png file")
    if out_path == src_path or (os.path.exists(out_path) and os.path.exists(src_path)
                                and os.path.samefile(out_path, src_path)):
        die("refusing to overwrite the original image; choose another --out")
    if os.path.exists(out_path) and not args.force:
        die(f"{out_path} already exists; pass --force to replace it")

    try:
        img = Image.open(src_path)
        img.load()
    except Exception as exc:  # noqa: BLE001
        die(f"cannot read {args.image}: {exc}")

    notes = []
    orig_size = img.size
    orig_mode = img.mode
    img = ImageOps.exif_transpose(img)
    img = to_srgb_rgba(img, notes)

    if not args.no_trim:
        bbox = img.getchannel("A").getbbox()
        if bbox is None:
            die("image is fully transparent")
        if bbox != (0, 0, img.width, img.height):
            img = img.crop(bbox)
            notes.append(f"trimmed transparent padding to {img.width}x{img.height}")

    wi, hi = args.width_in, args.height_in
    target_w, target_h = round(wi * args.dpi), round(hi * args.dpi)
    fit = min(target_w / img.width, target_h / img.height)

    if fit > 1 and not args.allow_upscale:
        # Build the canvas at the artwork's own resolution instead: the
        # smallest canvas with the print-area aspect that contains the artwork.
        out_dpi = max(img.width / wi, img.height / hi)
        canvas_w = max(img.width, round(wi * out_dpi))
        canvas_h = max(img.height, round(hi * out_dpi))
        scale = 1.0
        notes.append(
            f"artwork is smaller than {args.dpi:.0f} dpi; not upscaled, canvas built at {out_dpi:.0f} dpi"
        )
    else:
        out_dpi = args.dpi
        canvas_w, canvas_h = target_w, target_h
        scale = fit
        if fit > 1:
            notes.append(f"upscaled artwork by {fit:.2f}x; this adds no detail")

    # Same scale on both axes; rounding can only overshoot by a pixel.
    new_w = max(1, min(canvas_w, round(img.width * scale)))
    new_h = max(1, min(canvas_h, round(img.height * scale)))
    if (new_w, new_h) != img.size:
        img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (canvas_w, canvas_h), parse_bg(args.background))
    left = (canvas_w - new_w) // 2
    top = 0 if args.valign == "top" else (canvas_h - new_h) // 2
    canvas.alpha_composite(img, (left, top))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    canvas.save(out_path, "PNG", dpi=(out_dpi, out_dpi), optimize=True)

    print(json.dumps({
        "input": src_path,
        "input_size_px": list(orig_size),
        "input_mode": orig_mode,
        "output": out_path,
        "output_size_px": [canvas_w, canvas_h],
        "artwork_size_px": [new_w, new_h],
        "artwork_offset_px": [left, top],
        "dpi": round(out_dpi, 1),
        "print_area_in": [wi, hi],
        "below_150_dpi": out_dpi < 150,
        "notes": notes,
    }, indent=2))


if __name__ == "__main__":
    main()
