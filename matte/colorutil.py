"""Shared color + levels helpers for matte CLIs.

Color: named | #rgb | #rrggbb | r,g,b (default fill is white).
Levels dual units: percent 0–100 ↔ raw luma 0–255.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RECURSIVE_HELP = (
    "Also process files in subfolders "
    "(default: only files directly in the given folder)"
)

NAMED = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
}

COLOR_HELP = "Fill RGB: name, #rrggbb, or r,g,b (default white)"


def parse_color(s: str) -> tuple[int, int, int]:
    """Parse fill color: name | #rgb | #rrggbb | r,g,b."""
    raw = s.strip()
    key = raw.lower()
    if key in NAMED:
        return NAMED[key]
    if raw.startswith("#"):
        h = raw[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            raise ValueError(f"bad hex color: {s!r}")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.fullmatch(r"\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*", raw)
    if m:
        rgb = tuple(int(x) for x in m.groups())
        if any(v > 255 for v in rgb):
            raise ValueError(f"RGB components must be 0–255: {s!r}")
        return rgb  # type: ignore[return-value]
    raise ValueError(
        f"bad color {s!r} — use name, #rrggbb, or r,g,b (e.g. white / #fff / 255,0,0)"
    )


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def pct_to_u8(pct: float) -> float:
    """Levels percent 0–100 → luma 0–255 (float)."""
    return float(pct) / 100.0 * 255.0


def u8_to_pct(u8: float) -> float:
    """Luma 0–255 → levels percent 0–100."""
    return float(u8) / 255.0 * 100.0


def resolve_levels_pct(
    *,
    cutoff: float | None,
    white: float | None,
    black_point: float | None,
    white_point: float | None,
    default_cutoff: float,
    default_white: float,
) -> tuple[float, float]:
    """Resolve to (cutoff_pct, white_pct) in 0–100.

    Prefer native percent flags; convert 0–255 points when only those are set.
    Error if both unit systems are set for the same end.
    """
    if cutoff is not None and black_point is not None:
        raise ValueError(
            "use only one of --cutoff (0–100%) or --black-point (0–255), not both"
        )
    if white is not None and white_point is not None:
        raise ValueError(
            "use only one of --white (0–100%) or --white-point (0–255), not both"
        )

    if cutoff is not None:
        c = float(cutoff)
    elif black_point is not None:
        c = u8_to_pct(black_point)
    else:
        c = float(default_cutoff)

    if white is not None:
        w = float(white)
    elif white_point is not None:
        w = u8_to_pct(white_point)
    else:
        w = float(default_white)

    return c, w


def resolve_levels_u8(
    *,
    black_point: int | None,
    white_point: int | None,
    cutoff: float | None,
    white: float | None,
    default_black: int,
    default_white: int,
) -> tuple[int, int]:
    """Resolve to (black_point, white_point) as integer 0–255 luma.

    Prefer native 0–255 flags; convert percent when only those are set.
    Error if both unit systems are set for the same end.
    """
    if black_point is not None and cutoff is not None:
        raise ValueError(
            "use only one of --black-point (0–255) or --cutoff (0–100%), not both"
        )
    if white_point is not None and white is not None:
        raise ValueError(
            "use only one of --white-point (0–255) or --white (0–100%), not both"
        )

    if black_point is not None:
        bp = int(black_point)
    elif cutoff is not None:
        bp = int(round(pct_to_u8(cutoff)))
    else:
        bp = int(default_black)

    if white_point is not None:
        wp = int(white_point)
    elif white is not None:
        wp = int(round(pct_to_u8(white)))
    else:
        wp = int(default_white)

    return bp, wp


def effective_min_area(
    *,
    width: int,
    height: int,
    min_area: int | None,
    min_area_rel: float | None,
    default_min_area: int = 4,
) -> int:
    """Resolve absolute pixel min-area from absolute and/or relative flags.

    If --min-area-rel is set, effective = max(1, round(rel * long_edge²))
    (rel ≤ 0 → 0 = off). Error if both absolute and relative are given.
    """
    if min_area is not None and min_area_rel is not None:
        raise ValueError(
            "use only one of --min-area (pixels) or --min-area-rel (fraction of long²)"
        )
    if min_area_rel is not None:
        if min_area_rel < 0:
            raise ValueError("--min-area-rel must be >= 0")
        if min_area_rel == 0:
            return 0
        long_edge = max(int(width), int(height))
        return max(1, int(round(min_area_rel * long_edge * long_edge)))
    if min_area is not None:
        if min_area < 0:
            raise ValueError("--min-area must be >= 0")
        return int(min_area)
    return int(default_min_area)


def collect_files(
    path: Path,
    *,
    recursive: bool = False,
    suffixes: set[str] | frozenset[str] | tuple[str, ...],
    skip_endings: tuple[str, ...] = (),
    file_kind: str | None = None,
    warn_skipped: bool = True,
) -> list[Path]:
    """List matching files. A folder means that folder only unless recursive.

    Uses iterdir / rglob, not Path.glob('*.ext'). On Windows/WSL mounts,
    '*' can match across subdirectories and a folder run then goes too deep.
    An explicit file is always returned (skip_endings apply to folder scans).
    """
    suf = {
        s.lower() if s.startswith(".") else f".{s.lower()}" for s in suffixes
    }
    skip = tuple(e.lower() for e in skip_endings)

    if path.is_file():
        if path.suffix.lower() not in suf:
            kind = file_kind or "/".join(
                sorted(s.lstrip(".").upper() for s in suf)
            )
            raise SystemExit(f"ERR not a {kind} file: {path}")
        return [path]
    if not path.is_dir():
        raise SystemExit(f"ERR path not found: {path}")

    def wanted(p: Path) -> bool:
        if not p.is_file():
            return False
        if p.suffix.lower() not in suf:
            return False
        if skip and any(p.name.lower().endswith(e) for e in skip):
            return False
        return True

    if recursive:
        return sorted(p for p in path.rglob("*") if wanted(p))

    files = sorted(p for p in path.iterdir() if wanted(p))
    if warn_skipped:
        deeper = [p for p in path.rglob("*") if wanted(p) and p.parent != path]
        if deeper:
            print(
                f"note: skipped {len(deeper)} file(s) in subfolders "
                f"(pass --recursive)",
                file=sys.stderr,
            )
    return files
