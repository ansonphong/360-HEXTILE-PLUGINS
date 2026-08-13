#!/usr/bin/env python3
"""Art-on-black PNG/JPG → solid fill + greyscale alpha (levels cutoff).

Process (simple):
  1. RGB → greyscale luminance
  2. Levels: anything under --cutoff (0–100%) → black; rest stretched to 0–255
  3. That greyscale becomes the alpha channel
  4. RGB filled with --color (default pure white)

On a pure black background the look matches the original greys (alpha * white).

Usage:
  python knockout.py path/to/file.png              # overwrite (default)
  python knockout.py path/to/folder/
  python knockout.py path/to/folder/ --recursive
  python knockout.py path/to/file.png --new        # → file.png.knockout.png
  python knockout.py path/to/file.jpg --new        # JPEG needs --new
  python knockout.py path/to/file.png --cutoff 5   # crush dark greys
  python knockout.py path/to/file.png --black-point 13 --white-point 242  # 0–255 aliases
  python knockout.py path/to/file.png --color "#e13e13"
  python knockout.py path/to/file.png --invert     # dark art on light BG
  python knockout.py path/to/file.png --force      # reprocess hextile-pipe outputs
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from colorutil import COLOR_HELP, RECURSIVE_HELP, collect_files, parse_color, resolve_levels_pct

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
META_TOOL_KEY = "hextile-pipe-tool"
META_TOOL_VALUE = "knockout"
SIDECAR_MARKER = ".knockout.png"


def _validate_levels(cutoff: float, white: float, gamma: float) -> None:
    if not (math.isfinite(cutoff) and math.isfinite(white)):
        raise ValueError("cutoff/white must be finite numbers")
    if not 0.0 <= cutoff < white <= 100.0:
        raise ValueError("need 0 <= cutoff < white <= 100")
    if not (math.isfinite(gamma) and gamma > 0):
        raise ValueError("gamma must be a finite number > 0")


def _levels_u8(L: float, black: float, white: float, gamma: float) -> int:
    """Map luminance through levels → alpha 0–255."""
    if L <= black:
        return 0
    if L >= white:
        return 255
    t = (L - black) / (white - black)
    if gamma != 1.0:
        t = t**gamma
    return int(round(min(1.0, max(0.0, t)) * 255))


def is_knockout_product(path: Path, im: Image.Image | None = None) -> bool:
    """True if this file was produced by knockout (sidecar name or PNG metadata)."""
    if path.name.lower().endswith(SIDECAR_MARKER):
        return True
    if path.suffix.lower() != ".png":
        return False
    try:
        img = im if im is not None else Image.open(path)
        close = im is None
        try:
            meta = getattr(img, "text", None) or {}
            if meta.get(META_TOOL_KEY) == META_TOOL_VALUE:
                return True
            # Pillow sometimes keeps info dict
            info = getattr(img, "info", None) or {}
            if info.get(META_TOOL_KEY) == META_TOOL_VALUE:
                return True
        finally:
            if close:
                img.close()
    except Exception:
        return False
    return False


def knockout_image(
    im: Image.Image,
    *,
    cutoff: float = 0.0,
    white: float = 100.0,
    gamma: float = 1.0,
    color: tuple[int, int, int] = (255, 255, 255),
    invert: bool = False,
) -> Image.Image:
    """Greyscale→alpha after levels; RGB = solid fill color."""
    _validate_levels(cutoff, white, gamma)
    fr, fg, fb = color
    if not all(0 <= c <= 255 for c in (fr, fg, fb)):
        raise ValueError("fill color components must be 0–255")

    black_pt = cutoff / 100.0 * 255.0
    white_pt = white / 100.0 * 255.0

    rgba = im.convert("RGBA")
    if HAS_NUMPY:
        arr = np.array(rgba, dtype=np.uint8)
        r = arr[:, :, 0].astype(np.float32)
        g = arr[:, :, 1].astype(np.float32)
        b = arr[:, :, 2].astype(np.float32)
        # 1) greyscale luminance of the image
        L = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if invert:
            L = 255.0 - L

        # 2) levels → alpha
        a = np.zeros(L.shape, dtype=np.uint8)
        solid = L >= white_pt
        dead = L <= black_pt
        mid = ~(solid | dead)
        a[solid] = 255
        a[dead] = 0
        if mid.any():
            t = (L[mid] - black_pt) / (white_pt - black_pt)
            if gamma != 1.0:
                t = np.power(t, gamma)
            a[mid] = np.clip(np.rint(t * 255.0), 0, 255).astype(np.uint8)

        # 3) solid fill RGB where visible
        out = np.zeros_like(arr)
        vis = a > 0
        out[vis, 0] = fr
        out[vis, 1] = fg
        out[vis, 2] = fb
        out[:, :, 3] = a
        return Image.fromarray(out, mode="RGBA")

    # Pillow-only fallback
    pixels = rgba.load()
    w, h = rgba.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _ = pixels[x, y]
            L = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if invert:
                L = 255.0 - L
            a = _levels_u8(L, black_pt, white_pt, gamma)
            if a > 0:
                op[x, y] = (fr, fg, fb, a)
    return out


def _pnginfo() -> PngInfo:
    info = PngInfo()
    info.add_text(META_TOOL_KEY, META_TOOL_VALUE)
    return info


def _atomic_save_png(img: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".png", dir=str(dest.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        img.save(tmp_path, format="PNG", pnginfo=_pnginfo())
        os.replace(tmp_path, dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def knockout_file(
    src: Path,
    dest: Path,
    *,
    cutoff: float = 0.0,
    white: float = 100.0,
    gamma: float = 1.0,
    color: tuple[int, int, int] = (255, 255, 255),
    invert: bool = False,
) -> None:
    with Image.open(src) as im:
        out = knockout_image(
            im,
            cutoff=cutoff,
            white=white,
            gamma=gamma,
            color=color,
            invert=invert,
        )
        _atomic_save_png(out, dest)


def collect_images(path: Path, recursive: bool, *, force: bool) -> list[Path]:
    files = collect_files(
        path,
        recursive=recursive,
        suffixes=IMAGE_EXTS,
        skip_endings=() if force else (SIDECAR_MARKER,),
        file_kind="PNG/JPG",
    )
    if force:
        return files
    return [p for p in files if not is_knockout_product(p)]


def dest_for(src: Path, new: bool) -> Path:
    """Sidecar includes source extension so asset.png / asset.jpg never collide."""
    if new:
        # e.g. photo.png → photo.png.knockout.png ; photo.jpg → photo.jpg.knockout.png
        ext = src.suffix.lower().lstrip(".") or "img"
        return src.with_name(f"{src.stem}.{ext}{SIDECAR_MARKER}")
    if src.suffix.lower() in {".jpg", ".jpeg"}:
        raise SystemExit(
            f"ERR default overwrites PNG only (JPEG has no alpha); use --new: {src}"
        )
    return src


def preflight_jobs(
    files: list[Path], *, new: bool, force: bool
) -> list[tuple[Path, Path]]:
    """Resolve all destinations and validate *before* any write."""
    jobs: list[tuple[Path, Path]] = []
    errors: list[str] = []

    for src in files:
        try:
            if not force and is_knockout_product(src):
                errors.append(
                    f"ERR already a knockout product (use --force to reprocess): {src}"
                )
                continue
            dest = dest_for(src, new)
            jobs.append((src, dest))
        except SystemExit as e:
            errors.append(str(e))

    # Unique destinations
    seen: dict[Path, Path] = {}
    for src, dest in jobs:
        key = dest.resolve()
        if key in seen:
            errors.append(
                f"ERR destination collision: {seen[key]} and {src} both → {dest}"
            )
        else:
            seen[key] = src

    # Dest must not clobber a different queued source (e.g. --force --new on
    # asset.png + asset.png.knockout.png would overwrite the latter mid-batch)
    source_keys = {src.resolve() for src, _ in jobs}
    for src, dest in jobs:
        dkey = dest.resolve()
        skey = src.resolve()
        if dkey in source_keys and dkey != skey:
            errors.append(
                f"ERR destination is another queued source (would clobber mid-batch): "
                f"{src} -> {dest}"
            )

    if errors:
        raise SystemExit("\n".join(errors))
    return jobs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Art-on-black → solid fill + greyscale alpha. "
            "Levels cutoff on luminance, then fill RGB. Default: overwrite source PNG."
        )
    )
    ap.add_argument(
        "path",
        type=Path,
        help="PNG/JPG file, or folder (files in that folder only)",
    )
    ap.add_argument(
        "--new",
        action="store_true",
        help="Write sidecar stem.ext.knockout.png instead of overwriting",
    )
    ap.add_argument("--recursive", action="store_true", help=RECURSIVE_HELP)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Allow reprocessing files already tagged/named as knockout outputs",
    )
    ap.add_argument(
        "--cutoff",
        type=float,
        default=None,
        metavar="PCT",
        help="Levels black point 0–100: brightness under this → alpha 0 (default 0)",
    )
    ap.add_argument(
        "--white",
        type=float,
        default=None,
        metavar="PCT",
        help="Levels white point 0–100: brightness at/above this → alpha 255 (default 100)",
    )
    ap.add_argument(
        "--black-point",
        type=float,
        default=None,
        metavar="N",
        help="Alias for --cutoff as raw luma 0–255 (mutually exclusive with --cutoff)",
    )
    ap.add_argument(
        "--white-point",
        type=float,
        default=None,
        metavar="N",
        help="Alias for --white as raw luma 0–255 (mutually exclusive with --white)",
    )
    ap.add_argument(
        "--gamma",
        type=float,
        default=1.0,
        help="Midtone gamma on alpha after levels; >1 = crisper (default 1.0)",
    )
    ap.add_argument(
        "--color",
        type=str,
        default="white",
        help=COLOR_HELP,
    )
    ap.add_argument(
        "--invert",
        action="store_true",
        help="Dark art on light background (invert greyscale before levels)",
    )
    args = ap.parse_args(argv)

    path = args.path.expanduser().resolve()
    if not path.exists():
        print(f"ERR path not found: {path}", file=sys.stderr)
        return 1

    try:
        fill = parse_color(args.color)
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        return 1

    try:
        cutoff, white = resolve_levels_pct(
            cutoff=args.cutoff,
            white=args.white,
            black_point=args.black_point,
            white_point=args.white_point,
            default_cutoff=0.0,
            default_white=100.0,
        )
        _validate_levels(cutoff, white, args.gamma)
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        return 1

    try:
        files = collect_images(path, args.recursive, force=args.force)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1

    if not files:
        print(f"ERR no PNG/JPG files found under: {path}", file=sys.stderr)
        return 1

    try:
        jobs = preflight_jobs(files, new=args.new, force=args.force)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1

    if not jobs:
        print(f"ERR nothing to process under: {path}", file=sys.stderr)
        return 1

    errors = 0
    for src, dest in jobs:
        try:
            knockout_file(
                src,
                dest,
                cutoff=cutoff,
                white=white,
                gamma=args.gamma,
                color=fill,
                invert=args.invert,
            )
            print(f"OK  {src} -> {dest}")
        except Exception as e:
            print(f"ERR {src}: {e}", file=sys.stderr)
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
