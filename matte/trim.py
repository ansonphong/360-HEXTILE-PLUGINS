#!/usr/bin/env python3
"""Crop transparent PNG to content bbox and/or add transparent margin (px or %).

Modes:
  crop (default) — find alpha content, optional margin pad, new canvas
  pad            — expand full canvas by margin only (no content trim)

Usage:
  python trim.py path/to/file.png              # tight crop, overwrite PNG
  python trim.py path/to/folder/
  python trim.py path/to/folder/ --recursive
  python trim.py path/to/file.png --new        # → file.trim.png
  python trim.py path/to/file.png --margin 10
  python trim.py path/to/file.png --margin 5%
  python trim.py path/to/file.png --mode pad --margin 24
  python trim.py path/to/file.png --threshold 4 --margin 8 --new
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
SIDECAR_MARKER = ".trim.png"
MODE_CHOICES = ("crop", "pad")

_MARGIN_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>%|px)?\s*$",
    re.IGNORECASE,
)


def parse_margin(spec: str) -> tuple[str, float]:
    """Return ("px", n) or ("pct", p). Raises ValueError on bad input."""
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("margin must be a non-empty string (e.g. 10, 10px, 5%)")
    m = _MARGIN_RE.match(spec)
    if not m:
        raise ValueError(f"invalid margin {spec!r}; use N, Npx, or N%")
    num = float(m.group("num"))
    unit = (m.group("unit") or "px").lower()
    if unit == "%":
        if num < 0:
            raise ValueError("percent margin must be >= 0")
        return ("pct", num)
    # px — must be non-negative integer-valued
    if num < 0:
        raise ValueError("pixel margin must be >= 0")
    if abs(num - round(num)) > 1e-9:
        raise ValueError("pixel margin must be an integer (e.g. 10 or 10px)")
    return ("px", float(int(round(num))))


def _validate_threshold(threshold: int) -> None:
    if not isinstance(threshold, int) or isinstance(threshold, bool):
        raise ValueError("threshold must be an int in 0..254")
    if not 0 <= threshold <= 254:
        raise ValueError("threshold must be in 0..254")


def content_bbox(
    im: Image.Image,
    *,
    threshold: int = 0,
) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) exclusive box of pixels with A > threshold."""
    _validate_threshold(threshold)
    rgba = im.convert("RGBA")
    if HAS_NUMPY:
        arr = np.array(rgba, dtype=np.uint8)
        a = arr[:, :, 3]
        ys, xs = np.where(a > threshold)
        if ys.size == 0:
            return None
        left = int(xs.min())
        top = int(ys.min())
        right = int(xs.max()) + 1
        bottom = int(ys.max()) + 1
        return (left, top, right, bottom)

    # Pillow-only: threshold alpha then getbbox
    alpha = rgba.getchannel("A")
    if threshold == 0:
        mask = alpha
    else:
        # keep pixels with A > threshold as white for getbbox
        mask = alpha.point(lambda v, t=threshold: 255 if v > t else 0)
    box = mask.getbbox()
    if box is None:
        return None
    return box  # already exclusive right/bottom


def expand_bbox(
    bbox: tuple[int, int, int, int],
    *,
    margin_px: int,
) -> tuple[int, int, int, int]:
    """Expand by margin_px on each side (may go negative / past image size)."""
    if margin_px < 0:
        raise ValueError("margin_px must be >= 0")
    left, top, right, bottom = bbox
    return (left - margin_px, top - margin_px, right + margin_px, bottom + margin_px)


def margin_px_for_bbox(
    bbox: tuple[int, int, int, int],
    *,
    kind: str,
    value: float,
) -> int:
    """Uniform pixel margin from px value or % of max(content_w, content_h)."""
    left, top, right, bottom = bbox
    cw = right - left
    ch = bottom - top
    if kind == "px":
        if value < 0:
            raise ValueError("pixel margin must be >= 0")
        return int(value)
    if kind == "pct":
        if value < 0:
            raise ValueError("percent margin must be >= 0")
        # half-up for non-negative (avoid banker's round())
        return int(max(cw, ch) * value / 100.0 + 0.5)
    raise ValueError(f"unknown margin kind {kind!r}")


def trim_image(
    im: Image.Image,
    *,
    mode: str = "crop",
    margin: str = "0",
    threshold: int = 0,
) -> Image.Image:
    """Crop to alpha content and/or pad transparent margin. Preserve RGB+A."""
    if mode not in MODE_CHOICES:
        raise ValueError(f"mode must be one of {MODE_CHOICES}")
    _validate_threshold(threshold)
    kind, value = parse_margin(margin)
    rgba = im.convert("RGBA")
    w, h = rgba.size

    if mode == "pad":
        # Keep full canvas; % margin still measures content (not empty border).
        bbox = (0, 0, w, h)
        if kind == "pct":
            found = content_bbox(rgba, threshold=threshold)
            ref = found if found is not None else bbox
            mpx = margin_px_for_bbox(ref, kind=kind, value=value)
        else:
            mpx = margin_px_for_bbox(bbox, kind=kind, value=value)
    else:
        found = content_bbox(rgba, threshold=threshold)
        if found is None:
            raise ValueError("no content above alpha threshold")
        bbox = found
        mpx = margin_px_for_bbox(bbox, kind=kind, value=value)

    left, top, right, bottom = expand_bbox(bbox, margin_px=mpx)
    out_w = right - left
    out_h = bottom - top
    if out_w <= 0 or out_h <= 0:
        raise ValueError("expanded canvas has non-positive size")

    out = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    # Paste original so world coords align: pixel (x,y) of src → (x-left, y-top)
    out.paste(rgba, (-left, -top))
    return out


def trim_file(
    src: Path,
    dest: Path,
    *,
    mode: str = "crop",
    margin: str = "0",
    threshold: int = 0,
) -> None:
    with Image.open(src) as im:
        out = trim_image(im, mode=mode, margin=margin, threshold=threshold)
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.save(dest, format="PNG")


def collect_images(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTS:
            raise SystemExit(f"ERR not a PNG/JPG file: {path}")
        return [path]
    if not path.is_dir():
        raise SystemExit(f"ERR path not found: {path}")
    files: list[Path] = []
    patterns = ("*.png", "*.PNG", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG")
    if recursive:
        for pat in patterns:
            files.extend(path.glob(f"**/{pat}"))
    else:
        for pat in patterns:
            files.extend(path.glob(pat))
    files = sorted({p for p in files if p.is_file()})
    return [p for p in files if not p.name.lower().endswith(SIDECAR_MARKER)]


def dest_for(src: Path, new: bool) -> Path:
    if new:
        return src.with_name(f"{src.stem}{SIDECAR_MARKER}")
    if src.suffix.lower() in {".jpg", ".jpeg"}:
        raise SystemExit(
            f"ERR default overwrites PNG only (JPEG has no alpha); use --new: {src}"
        )
    return src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Crop transparent images to content bbox and/or add transparent margin. "
            "Modes: crop (default) or pad. Margin: N / Npx / N%. "
            "Default: overwrite source PNG."
        )
    )
    ap.add_argument("path", type=Path, help="PNG/JPG file or directory")
    ap.add_argument(
        "--new",
        action="store_true",
        help="Write sidecar file.trim.png instead of overwriting",
    )
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default="crop",
        help="crop=trim to content then margin; pad=expand canvas only (default crop)",
    )
    ap.add_argument(
        "--margin",
        type=str,
        default="0",
        metavar="SPEC",
        help="Uniform pad: pixels (10 or 10px) or percent of max content side (5%%). "
        "Percent uses half-up: int(max(w,h)*pct/100+0.5). Default 0",
    )
    ap.add_argument(
        "--threshold",
        type=int,
        default=0,
        metavar="N",
        help="Content if alpha > N (0..254; default 0 = any non-zero)",
    )
    args = ap.parse_args(argv)

    path = args.path.expanduser().resolve()
    if not path.exists():
        print(f"ERR path not found: {path}", file=sys.stderr)
        return 1

    try:
        _validate_threshold(args.threshold)
        parse_margin(args.margin)
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        return 1

    try:
        files = collect_images(path, args.recursive)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1

    if not files:
        print(f"ERR no PNG/JPG files found under: {path}", file=sys.stderr)
        return 1

    # Preflight destinations so batch never silently clobbers (e.g. a.png + a.jpg → a.trim.png)
    jobs: list[tuple[Path, Path]] = []
    seen: dict[Path, Path] = {}
    pre_errs: list[str] = []
    for src in files:
        try:
            dest = dest_for(src, args.new)
        except SystemExit as e:
            pre_errs.append(str(e))
            continue
        key = dest.resolve()
        if key in seen:
            pre_errs.append(
                f"ERR destination collision: {seen[key]} and {src} both → {dest}"
            )
        else:
            seen[key] = src
            jobs.append((src, dest))
    if pre_errs:
        print("\n".join(pre_errs), file=sys.stderr)
        return 1
    if not jobs:
        print(f"ERR nothing to process under: {path}", file=sys.stderr)
        return 1

    errors = 0
    for src, dest in jobs:
        try:
            trim_file(
                src,
                dest,
                mode=args.mode,
                margin=args.margin,
                threshold=args.threshold,
            )
            print(f"OK  {src} -> {dest}")
        except Exception as e:
            print(f"ERR {src}: {e}", file=sys.stderr)
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
