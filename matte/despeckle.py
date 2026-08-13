#!/usr/bin/env python3
"""Despeckle logo/sigil art on black OR transparent backgrounds.

Works on a single *coverage* channel (alpha or luminance), not RGB filters.

Process (Codex Sol–approved defaults):
  1. Mode auto: any A < 255 → alpha coverage; else luminance on black
  2. Support mask = coverage above --cutoff
  3. Drop 8-connected components smaller than --min-area (or --min-area-rel)
  4. Levels once (cutoff / white / gamma) on remaining coverage
  5. Pack: alpha keeps RGB (or --color); black → grey-on-black
     (or --to-alpha → white/color fill + alpha)
  6. Optional --passes P repeats steps 2–5 on the result

Usage:
  python despeckle.py path/to/file.png
  python despeckle.py path/to/folder/
  python despeckle.py path/to/file.png --new
  python despeckle.py path/to/file.png --min-area 8 --cutoff 2
  python despeckle.py path/to/file.png --min-area-rel 0.0001
  python despeckle.py path/to/file.png --passes 2
  python despeckle.py path/to/file.png --mode black --to-alpha
  python despeckle.py path/to/file.png --color white   # force fill when alpha out
  python despeckle.py path/to/file.png --black-point 3  # 0–255 alias for --cutoff
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

from colorutil import (
    RECURSIVE_HELP,
    collect_files,
    effective_min_area,
    parse_color,
    resolve_levels_pct,
)

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
MODE_CHOICES = ("auto", "alpha", "black")


def detect_mode(im: Image.Image, mode: str) -> str:
    if mode != "auto":
        return mode
    rgba = im.convert("RGBA")
    if HAS_NUMPY:
        a = np.array(rgba, dtype=np.uint8)[:, :, 3]
        if (a < 255).any():
            return "alpha"
        return "black"
    # Pillow fallback: sample extremes via extrema on alpha band
    alpha = rgba.getchannel("A")
    mn, mx = alpha.getextrema()
    if mn < 255:
        return "alpha"
    return "black"


def _luminance_np(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _levels_map_np(cov, black_pt: float, white_pt: float, gamma: float):
    a = np.zeros(cov.shape, dtype=np.uint8)
    solid = cov >= white_pt
    dead = cov <= black_pt
    mid = ~(solid | dead)
    a[solid] = 255
    a[dead] = 0
    if mid.any():
        t = (cov[mid] - black_pt) / (white_pt - black_pt)
        if gamma != 1.0:
            t = np.power(t, gamma)
        a[mid] = np.clip(np.rint(t * 255.0), 0, 255).astype(np.uint8)
    return a


def _remove_small_components_np(cov: np.ndarray, min_area: int, black_pt: float) -> np.ndarray:
    """Zero coverage on 8-connected components smaller than min_area (above black_pt)."""
    if min_area <= 0:
        return cov
    h, w = cov.shape
    mask = cov > black_pt
    if not mask.any():
        return cov

    labels = np.zeros((h, w), dtype=np.int32)
    sizes: list[int] = [0]  # label 0 unused
    next_label = 1

    # Two-pass union-find–lite via flood fill with stack (iterative)
    neighbors = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or labels[y, x] != 0:
                continue
            # BFS flood
            stack = [(y, x)]
            labels[y, x] = next_label
            count = 0
            while stack:
                cy, cx = stack.pop()
                count += 1
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue
                    if labels[ny, nx] != 0 or not mask[ny, nx]:
                        continue
                    labels[ny, nx] = next_label
                    stack.append((ny, nx))
            sizes.append(count)
            next_label += 1

    out = cov.copy()
    for lab in range(1, next_label):
        if sizes[lab] < min_area:
            out[labels == lab] = 0
    return out


def _remove_small_components_pil(
    cov_img: Image.Image, min_area: int, black_pt: float
) -> Image.Image:
    """Pillow-only component filter (slow; for no-numpy environments)."""
    if min_area <= 0:
        return cov_img
    w, h = cov_img.size
    px = cov_img.load()
    labels = [[0] * w for _ in range(h)]
    sizes: list[int] = [0]
    next_label = 1
    neighbors = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )
    for y in range(h):
        for x in range(w):
            if px[x, y] <= black_pt or labels[y][x] != 0:
                continue
            stack = [(y, x)]
            labels[y][x] = next_label
            count = 0
            while stack:
                cy, cx = stack.pop()
                count += 1
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue
                    if labels[ny][nx] != 0 or px[nx, ny] <= black_pt:
                        continue
                    labels[ny][nx] = next_label
                    stack.append((ny, nx))
            sizes.append(count)
            next_label += 1

    out = cov_img.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            lab = labels[y][x]
            if lab > 0 and sizes[lab] < min_area:
                op[x, y] = 0
    return out


def _levels_pil(cov_img: Image.Image, black_pt: float, white_pt: float, gamma: float) -> Image.Image:
    w, h = cov_img.size
    src = cov_img.load()
    out = Image.new("L", (w, h), 0)
    op = out.load()
    for y in range(h):
        for x in range(w):
            L = float(src[x, y])
            if L <= black_pt:
                op[x, y] = 0
            elif L >= white_pt:
                op[x, y] = 255
            else:
                t = (L - black_pt) / (white_pt - black_pt)
                if gamma != 1.0:
                    t = t**gamma
                op[x, y] = int(round(min(1.0, max(0.0, t)) * 255))
    return out


def _despeckle_once(
    im: Image.Image,
    *,
    mode: str,
    min_area: int,
    cutoff: float,
    white: float,
    gamma: float,
    to_alpha: bool,
    color: tuple[int, int, int] | None,
    invert: bool,
) -> Image.Image:
    """Single despeckle pass; return RGB (grey-on-black) or RGBA."""
    if mode not in MODE_CHOICES:
        raise ValueError(f"mode must be one of {MODE_CHOICES}")
    if not 0.0 <= cutoff < white <= 100.0:
        raise ValueError("need 0 <= cutoff < white <= 100")
    if gamma <= 0:
        raise ValueError("gamma must be > 0")
    if min_area < 0:
        raise ValueError("min_area must be >= 0")

    resolved = detect_mode(im, mode)
    black_pt = cutoff / 100.0 * 255.0
    white_pt = white / 100.0 * 255.0
    rgba = im.convert("RGBA")

    if HAS_NUMPY:
        arr = np.array(rgba, dtype=np.uint8)
        r = arr[:, :, 0].astype(np.float32)
        g = arr[:, :, 1].astype(np.float32)
        b = arr[:, :, 2].astype(np.float32)
        a_in = arr[:, :, 3].astype(np.float32)

        if resolved == "alpha":
            cov = a_in.copy()
        else:
            cov = _luminance_np(r, g, b)
        if invert:
            cov = 255.0 - cov

        cov = _remove_small_components_np(cov, min_area, black_pt)
        cleaned = _levels_map_np(cov, black_pt, white_pt, gamma)

        emit_alpha = resolved == "alpha" or to_alpha
        if emit_alpha:
            out = np.zeros_like(arr)
            vis = cleaned > 0
            if color is not None:
                fr, fg, fb = color
                out[vis, 0] = fr
                out[vis, 1] = fg
                out[vis, 2] = fb
            elif resolved == "alpha":
                # preserve original RGB where visible
                out[vis, 0] = arr[vis, 0]
                out[vis, 1] = arr[vis, 1]
                out[vis, 2] = arr[vis, 2]
            else:
                # black → alpha, default white fill
                out[vis, 0] = 255
                out[vis, 1] = 255
                out[vis, 2] = 255
            out[:, :, 3] = cleaned
            return Image.fromarray(out, mode="RGBA")

        # grey-on-black RGB
        out_rgb = np.zeros((arr.shape[0], arr.shape[1], 3), dtype=np.uint8)
        out_rgb[:, :, 0] = cleaned
        out_rgb[:, :, 1] = cleaned
        out_rgb[:, :, 2] = cleaned
        return Image.fromarray(out_rgb, mode="RGB")

    # ---- Pillow-only path ----
    if resolved == "alpha":
        cov_img = rgba.getchannel("A")
    else:
        cov_img = rgba.convert("L")
    if invert:
        cov_img = Image.eval(cov_img, lambda v: 255 - v)

    cov_img = _remove_small_components_pil(cov_img, min_area, black_pt)
    cleaned_img = _levels_pil(cov_img, black_pt, white_pt, gamma)

    emit_alpha = resolved == "alpha" or to_alpha
    if emit_alpha:
        if color is not None:
            fr, fg, fb = color
            base = Image.new("RGBA", rgba.size, (fr, fg, fb, 0))
        elif resolved == "alpha":
            base = rgba.copy()
        else:
            base = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
        base.putalpha(cleaned_img)
        r_b, g_b, b_b, _a_b = base.split()
        empty = Image.new("L", rgba.size, 0)
        mask = cleaned_img.point(lambda v: 255 if v > 0 else 0)
        r_b = Image.composite(r_b, empty, mask)
        g_b = Image.composite(g_b, empty, mask)
        b_b = Image.composite(b_b, empty, mask)
        return Image.merge("RGBA", (r_b, g_b, b_b, cleaned_img))

    return Image.merge("RGB", (cleaned_img, cleaned_img, cleaned_img))


def despeckle_image(
    im: Image.Image,
    *,
    mode: str = "auto",
    min_area: int = 4,
    cutoff: float = 1.0,
    white: float = 100.0,
    gamma: float = 1.0,
    to_alpha: bool = False,
    color: tuple[int, int, int] | None = None,
    invert: bool = False,
    passes: int = 1,
) -> Image.Image:
    """Despeckle coverage; optional multi-pass. Return RGB or RGBA."""
    if passes < 1:
        raise ValueError("passes must be >= 1")
    current = im
    for i in range(passes):
        # After first pass, alpha products should stay in alpha mode; black
        # grey-on-black stays black. detect_mode handles both.
        current = _despeckle_once(
            current,
            mode=mode if i == 0 else "auto",
            min_area=min_area,
            cutoff=cutoff,
            white=white,
            gamma=gamma,
            to_alpha=to_alpha,
            color=color,
            invert=invert if i == 0 else False,
        )
    return current


def _atomic_save(img: Image.Image, dest: Path, fmt: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=dest.suffix or ".png",
        dir=str(dest.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        img.save(tmp_path, format=fmt)
        os.replace(tmp_path, dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def despeckle_file(
    src: Path,
    dest: Path,
    **kwargs,
) -> None:
    with Image.open(src) as im:
        out = despeckle_image(im, **kwargs)
        fmt = "PNG" if out.mode == "RGBA" or dest.suffix.lower() == ".png" else "PNG"
        # always PNG for alpha; for grey RGB keep PNG if dest is png else JPEG
        if out.mode == "RGBA":
            _atomic_save(out, dest, "PNG")
        elif dest.suffix.lower() in {".jpg", ".jpeg"}:
            _atomic_save(out.convert("RGB"), dest, "JPEG")
        else:
            _atomic_save(out, dest, "PNG")


def collect_images(path: Path, recursive: bool) -> list[Path]:
    return collect_files(
        path,
        recursive=recursive,
        suffixes=IMAGE_EXTS,
        skip_endings=(".despeckle.png",),
        file_kind="PNG/JPG",
    )


def dest_for(src: Path, new: bool, emit_alpha: bool) -> Path:
    if new:
        return src.with_name(f"{src.stem}.despeckle.png")
    if emit_alpha and src.suffix.lower() in {".jpg", ".jpeg"}:
        raise SystemExit(
            f"ERR alpha output cannot overwrite JPEG; use --new: {src}"
        )
    if emit_alpha and src.suffix.lower() != ".png":
        # force png dest for alpha
        return src.with_suffix(".png")
    return src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Despeckle black-bg or transparent art via min-area components + levels. "
            "Default: overwrite source."
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
        help="Write sidecar file.despeckle.png instead of overwriting",
    )
    ap.add_argument("--recursive", action="store_true", help=RECURSIVE_HELP)
    ap.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default="auto",
        help="Coverage source (default auto: any A<255 → alpha, else black luma)",
    )
    ap.add_argument(
        "--min-area",
        type=int,
        default=None,
        metavar="N",
        help="Drop 8-connected components with area < N pixels (default 4; 0=off)",
    )
    ap.add_argument(
        "--min-area-rel",
        type=float,
        default=None,
        metavar="F",
        help=(
            "Scale-aware min-area: fraction of long_edge² "
            "(effective = max(1, round(F * long²)); mutually exclusive with --min-area)"
        ),
    )
    ap.add_argument(
        "--passes",
        type=int,
        default=1,
        metavar="P",
        help="Repeat min-area + levels cleanup P times (default 1)",
    )
    ap.add_argument(
        "--cutoff",
        type=float,
        default=None,
        metavar="PCT",
        help="Levels black point 0–100 (default 1)",
    )
    ap.add_argument(
        "--white",
        type=float,
        default=None,
        metavar="PCT",
        help="Levels white point 0–100 (default 100)",
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
        help="Midtone gamma after levels (default 1.0)",
    )
    ap.add_argument(
        "--to-alpha",
        action="store_true",
        help="BLACK mode: emit RGBA (white/color fill + cleaned alpha) instead of grey-on-black",
    )
    ap.add_argument(
        "--color",
        type=str,
        default=None,
        help="Fill RGB when emitting alpha (default: preserve RGB in alpha mode; white for --to-alpha)",
    )
    ap.add_argument(
        "--invert",
        action="store_true",
        help="Invert coverage before cleanup (dark art on light)",
    )
    args = ap.parse_args(argv)

    path = args.path.expanduser().resolve()
    if not path.exists():
        print(f"ERR path not found: {path}", file=sys.stderr)
        return 1

    try:
        cutoff, white = resolve_levels_pct(
            cutoff=args.cutoff,
            white=args.white,
            black_point=args.black_point,
            white_point=args.white_point,
            default_cutoff=1.0,
            default_white=100.0,
        )
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        return 1

    if not 0.0 <= cutoff < white <= 100.0:
        print("ERR need 0 <= cutoff < white <= 100", file=sys.stderr)
        return 1
    if args.passes < 1:
        print("ERR --passes must be >= 1", file=sys.stderr)
        return 1
    if args.min_area is not None and args.min_area_rel is not None:
        print(
            "ERR use only one of --min-area or --min-area-rel",
            file=sys.stderr,
        )
        return 1

    fill: tuple[int, int, int] | None = None
    if args.color is not None:
        try:
            fill = parse_color(args.color)
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

    errors = 0
    for src in files:
        try:
            with Image.open(src) as probe:
                resolved = detect_mode(probe, args.mode)
                w, h = probe.size
            emit_alpha = resolved == "alpha" or args.to_alpha
            # color default for to-alpha from black
            color_arg = fill
            if emit_alpha and color_arg is None and resolved == "black":
                color_arg = (255, 255, 255)
            dest = dest_for(src, args.new, emit_alpha)
            try:
                ma = effective_min_area(
                    width=w,
                    height=h,
                    min_area=args.min_area,
                    min_area_rel=args.min_area_rel,
                    default_min_area=4,
                )
            except ValueError as e:
                print(f"ERR {src}: {e}", file=sys.stderr)
                errors += 1
                continue
            despeckle_file(
                src,
                dest,
                mode=args.mode,
                min_area=ma,
                cutoff=cutoff,
                white=white,
                gamma=args.gamma,
                to_alpha=args.to_alpha,
                color=color_arg,
                invert=args.invert,
                passes=args.passes,
            )
            print(f"OK  {src} -> {dest}")
        except SystemExit as e:
            print(str(e), file=sys.stderr)
            errors += 1
        except Exception as e:
            print(f"ERR {src}: {e}", file=sys.stderr)
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
