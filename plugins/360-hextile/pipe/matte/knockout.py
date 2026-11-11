#!/usr/bin/env python3
"""Art-on-black PNG/JPG → solid fill + greyscale alpha (levels cutoff).

Process (simple):
  1. RGB → greyscale luminance
  2. Levels: anything under --cutoff (0–100%) → black; rest stretched to 0–255
  3. That greyscale becomes the alpha channel
  4. RGB filled with --color (default pure white)

On a pure black background the look matches the original greys (alpha * white).

Usage:
  python knockout.py path/to/file.png              # overwrite; default crush 3 / 97
  python knockout.py path/to/folder/
  python knockout.py path/to/folder/ --recursive
  python knockout.py path/to/file.png --new        # → file.png.knockout.png
  python knockout.py path/to/file.jpg --new        # JPEG needs --new
  python knockout.py path/to/file.png --cutoff 0 --white 100   # no margin
  python knockout.py path/to/file.png --black-point 13 --white-point 242  # 0–255 aliases
  python knockout.py path/to/file.png --color "#e13e13"
  python knockout.py path/to/file.png --invert     # dark art on light BG
  python knockout.py path/to/file.png --silhouette # key black; keep greys; blur 2 then levels 150–170
  python knockout.py path/to/file.png --silhouette --blur 0   # hard key, no edge refine
  python knockout.py path/to/file.png --wand       # key only backdrop connected to the image edge
  python knockout.py path/to/file.png --force      # reprocess hextile-pipe outputs
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from PIL.PngImagePlugin import PngInfo

from colorutil import COLOR_HELP, RECURSIVE_HELP, collect_files, parse_color, resolve_levels_pct

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from scipy import ndimage as ndi

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
META_TOOL_KEY = "hextile-pipe-tool"
META_TOOL_VALUE = "knockout"
SIDECAR_MARKER = ".knockout.png"
# Few-point default crush: dirty black (~8/255) and dirty white (~247/255).
# After --invert, this is near-white bg / near-black art. Pass 0 and 100 for none.
DEFAULT_CUTOFF = 3.0
DEFAULT_WHITE = 97.0
# --silhouette: blur the hard mask, then Photoshop-style input levels.
# Photoshop-checked: 2px blur, then input levels 150–170.
DEFAULT_BLUR = 2.0
DEFAULT_LO = 150.0
DEFAULT_HI = 170.0
# --wand: dilate keep this many px to seal AA leaks, flood, then erode back.
DEFAULT_CLOSE = 2.0


def _validate_levels(cutoff: float, white: float, gamma: float) -> None:
    if not (math.isfinite(cutoff) and math.isfinite(white)):
        raise ValueError("cutoff/white must be finite numbers")
    if not 0.0 <= cutoff < white <= 100.0:
        raise ValueError("need 0 <= cutoff < white <= 100")
    if not (math.isfinite(gamma) and gamma > 0):
        raise ValueError("gamma must be a finite number > 0")


def _validate_cutoff(cutoff: float) -> None:
    if not (math.isfinite(cutoff) and 0.0 <= cutoff <= 100.0):
        raise ValueError("cutoff must be a finite number 0–100")


def _validate_edge(blur: float, lo: float, hi: float) -> None:
    if not (math.isfinite(blur) and blur >= 0):
        raise ValueError("blur must be a finite number ≥ 0")
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError("lo/hi must be finite numbers")
    if not 0.0 <= lo < hi <= 255.0:
        raise ValueError("need 0 <= --lo < --hi <= 255")


def _validate_close(close_px: float) -> None:
    if not (math.isfinite(close_px) and close_px >= 0):
        raise ValueError("close must be a finite number ≥ 0")


def _morph_size(im: Image.Image, radius: int) -> int | None:
    if radius <= 0:
        return None
    size = radius * 2 + 1
    w, h = im.size
    if size > w or size > h:
        size = min(w, h)
        if size % 2 == 0:
            size -= 1
        if size < 3:
            return None
    return size


def _dilate_l(im: Image.Image, radius: int) -> Image.Image:
    im = im.convert("L")
    size = _morph_size(im, radius)
    if size is None:
        return im
    return im.filter(ImageFilter.MaxFilter(size=size))


def _erode_l(im: Image.Image, radius: int) -> Image.Image:
    im = im.convert("L")
    size = _morph_size(im, radius)
    if size is None:
        return im
    return im.filter(ImageFilter.MinFilter(size=size))


def _flood_border_np(bg: "np.ndarray") -> "np.ndarray":
    """True where bg is 4-connected to the image border."""
    if HAS_SCIPY:
        seed = np.zeros_like(bg, dtype=bool)
        seed[0] = bg[0]
        seed[-1] = bg[-1]
        seed[:, 0] = bg[:, 0]
        seed[:, -1] = bg[:, -1]
        struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
        return ndi.binary_propagation(seed, mask=bg, structure=struct)
    h, w = bg.shape
    out = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    def seed(y: int, x: int) -> None:
        if bg[y, x] and not out[y, x]:
            out[y, x] = True
            q.append((y, x))

    for x in range(w):
        seed(0, x)
        seed(h - 1, x)
    for y in range(h):
        seed(y, 0)
        seed(y, w - 1)
    while q:
        y, x = q.popleft()
        if y > 0 and bg[y - 1, x] and not out[y - 1, x]:
            out[y - 1, x] = True
            q.append((y - 1, x))
        if y + 1 < h and bg[y + 1, x] and not out[y + 1, x]:
            out[y + 1, x] = True
            q.append((y + 1, x))
        if x > 0 and bg[y, x - 1] and not out[y, x - 1]:
            out[y, x - 1] = True
            q.append((y, x - 1))
        if x + 1 < w and bg[y, x + 1] and not out[y, x + 1]:
            out[y, x + 1] = True
            q.append((y, x + 1))
    return out


def _flood_border_pil(sealed_keep: Image.Image) -> Image.Image:
    """sealed_keep 255=keep / 0=bg. Return 255 where flood from the border cannot reach."""
    work = sealed_keep.convert("L").copy()
    w, h = work.size
    px = work.load()
    for x in range(w):
        if px[x, 0] == 0:
            ImageDraw.floodfill(work, (x, 0), 64)
        if px[x, h - 1] == 0:
            ImageDraw.floodfill(work, (x, h - 1), 64)
    for y in range(h):
        if px[0, y] == 0:
            ImageDraw.floodfill(work, (0, y), 64)
        if px[w - 1, y] == 0:
            ImageDraw.floodfill(work, (w - 1, y), 64)
    return work.point(lambda v: 0 if v == 64 else 255)


def _wand_wrap(hard: Image.Image, close_px: float) -> Image.Image:
    """Seal AA leaks, key only backdrop connected to the edge, unseal.

    Interior black (not reachable from the border) stays 255.
    """
    _validate_close(close_px)
    hard = hard.convert("L")
    radius = int(round(close_px))
    sealed = _dilate_l(hard, radius)
    if HAS_NUMPY:
        keep = np.array(sealed) > 127
        wrap = ~_flood_border_np(~keep)
        wrap_im = Image.fromarray(np.where(wrap, np.uint8(255), np.uint8(0)), mode="L")
    else:
        wrap_im = _flood_border_pil(sealed)
    return _erode_l(wrap_im, radius)


def _refine_silhouette_alpha(
    alpha_img: Image.Image, blur_px: float, lo: float, hi: float
) -> Image.Image:
    """Blur the hard mask, then input-levels it (black=lo, white=hi).

    Values ≤ lo → 0; ≥ hi → 255; between is the AA ramp.
    Raising both sliders chokes; lowering both expands. blur=0 skips refine.
    """
    _validate_edge(blur_px, lo, hi)
    im = alpha_img.convert("L")
    if blur_px <= 0:
        return im
    im = im.filter(ImageFilter.GaussianBlur(radius=float(blur_px)))
    span = hi - lo
    table = []
    for i in range(256):
        if i <= lo:
            table.append(0)
        elif i >= hi:
            table.append(255)
        else:
            table.append(int(round((i - lo) * 255.0 / span)))
    return im.point(table)


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
    cutoff: float = DEFAULT_CUTOFF,
    white: float = DEFAULT_WHITE,
    gamma: float = 1.0,
    color: tuple[int, int, int] = (255, 255, 255),
    invert: bool = False,
    silhouette: bool = False,
    wand: bool = False,
    close: float = DEFAULT_CLOSE,
    blur: float = DEFAULT_BLUR,
    lo: float = DEFAULT_LO,
    hi: float = DEFAULT_HI,
) -> Image.Image:
    """Default: greyscale→alpha after levels; RGB = solid fill.

    --silhouette: key luma at/under cutoff to alpha 0; keep original RGB.
    Then blur the matte and input-levels it (default blur 2, lo 150, hi 170).
    --wand: implies --silhouette; key only backdrop connected to the image
    edge (2px seal, flood, unseal). Interior black stays opaque.
    --color unused with either.
    """
    _validate_cutoff(cutoff)
    black_pt = cutoff / 100.0 * 255.0
    rgba = im.convert("RGBA")
    keep_rgb = silhouette or wand

    if keep_rgb:
        _validate_edge(blur, lo, hi)
        if wand:
            _validate_close(close)
        if HAS_NUMPY:
            arr = np.array(rgba, dtype=np.uint8)
            r = arr[:, :, 0].astype(np.float32)
            g = arr[:, :, 1].astype(np.float32)
            b = arr[:, :, 2].astype(np.float32)
            L = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if invert:
                L = 255.0 - L
            keep = (L > black_pt) & (arr[:, :, 3] > 0)
            hard_im = Image.fromarray(
                np.where(keep, np.uint8(255), np.uint8(0)), mode="L"
            )
            if wand:
                hard_im = _wand_wrap(hard_im, close)
            refined = _refine_silhouette_alpha(hard_im, blur, lo, hi)
            out = arr.copy()
            out[:, :, 3] = np.array(refined, dtype=np.uint8)
            return Image.fromarray(out, mode="RGBA")
        pixels = rgba.load()
        w, h = rgba.size
        hard_im = Image.new("L", (w, h), 0)
        hp = hard_im.load()
        for y in range(h):
            for x in range(w):
                r, g, b, src_a = pixels[x, y]
                if src_a <= 0:
                    continue
                L = 0.2126 * r + 0.7152 * g + 0.0722 * b
                if invert:
                    L = 255.0 - L
                if L > black_pt:
                    hp[x, y] = 255
        if wand:
            hard_im = _wand_wrap(hard_im, close)
        refined = _refine_silhouette_alpha(hard_im, blur, lo, hi)
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        op = out.load()
        rp = refined.load()
        for y in range(h):
            for x in range(w):
                a = rp[x, y]
                if a > 0:
                    r, g, b, _ = pixels[x, y]
                    op[x, y] = (r, g, b, a)
        return out

    _validate_levels(cutoff, white, gamma)
    fr, fg, fb = color
    if not all(0 <= c <= 255 for c in (fr, fg, fb)):
        raise ValueError("fill color components must be 0–255")

    white_pt = white / 100.0 * 255.0

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
    cutoff: float = DEFAULT_CUTOFF,
    white: float = DEFAULT_WHITE,
    gamma: float = 1.0,
    color: tuple[int, int, int] = (255, 255, 255),
    invert: bool = False,
    silhouette: bool = False,
    wand: bool = False,
    close: float = DEFAULT_CLOSE,
    blur: float = DEFAULT_BLUR,
    lo: float = DEFAULT_LO,
    hi: float = DEFAULT_HI,
) -> None:
    with Image.open(src) as im:
        out = knockout_image(
            im,
            cutoff=cutoff,
            white=white,
            gamma=gamma,
            color=color,
            invert=invert,
            silhouette=silhouette,
            wand=wand,
            close=close,
            blur=blur,
            lo=lo,
            hi=hi,
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
            "Levels cutoff on luminance, then fill RGB. "
            "--silhouette keys only the black, keeps original greys, "
            "then blur the matte and levels it (default blur 2, 150–170). "
            "--wand keys only backdrop connected to the image edge "
            "(implies --silhouette; interior black stays). "
            "Default: overwrite source PNG."
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
        help="Levels black point 0–100: brightness under this → alpha 0 (default 3)",
    )
    ap.add_argument(
        "--white",
        type=float,
        default=None,
        metavar="PCT",
        help="Levels white point 0–100: brightness at/above this → alpha 255 (default 97; unused with --silhouette/--wand)",
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
    ap.add_argument(
        "--silhouette",
        action="store_true",
        help="Key only luma at/under --cutoff; keep original RGB; blur then levels the matte",
    )
    ap.add_argument(
        "--wand",
        action="store_true",
        help=(
            "Key only backdrop connected to the image edge (implies --silhouette). "
            "Seals 2px, floods from the border, unseals. Interior black stays opaque"
        ),
    )
    ap.add_argument(
        "--blur",
        type=float,
        default=None,
        metavar="PX",
        help="Silhouette/--wand: Gaussian blur on the matte in pixels (default 2; 0 = off)",
    )
    ap.add_argument(
        "--lo",
        type=float,
        default=None,
        metavar="N",
        help="Silhouette/--wand: levels black point on the blurred matte 0–255 (default 150)",
    )
    ap.add_argument(
        "--hi",
        type=float,
        default=None,
        metavar="N",
        help="Silhouette/--wand: levels white point on the blurred matte 0–255 (default 170)",
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
        keep_rgb = args.silhouette or args.wand
        if keep_rgb:
            cutoff, _ignored_white = resolve_levels_pct(
                cutoff=args.cutoff,
                white=None,
                black_point=args.black_point,
                white_point=None,
                default_cutoff=DEFAULT_CUTOFF,
                default_white=DEFAULT_WHITE,
            )
            _validate_cutoff(cutoff)
            white = DEFAULT_WHITE
            blur = DEFAULT_BLUR if args.blur is None else float(args.blur)
            lo = DEFAULT_LO if args.lo is None else float(args.lo)
            hi = DEFAULT_HI if args.hi is None else float(args.hi)
            _validate_edge(blur, lo, hi)
        else:
            if args.blur is not None or args.lo is not None or args.hi is not None:
                raise ValueError("--blur/--lo/--hi only apply with --silhouette or --wand")
            cutoff, white = resolve_levels_pct(
                cutoff=args.cutoff,
                white=args.white,
                black_point=args.black_point,
                white_point=args.white_point,
                default_cutoff=DEFAULT_CUTOFF,
                default_white=DEFAULT_WHITE,
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
                silhouette=args.silhouette,
                wand=args.wand,
                blur=blur if keep_rgb else DEFAULT_BLUR,
                lo=lo if keep_rgb else DEFAULT_LO,
                hi=hi if keep_rgb else DEFAULT_HI,
            )
            print(f"OK  {src} -> {dest}")
        except Exception as e:
            print(f"ERR {src}: {e}", file=sys.stderr)
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
