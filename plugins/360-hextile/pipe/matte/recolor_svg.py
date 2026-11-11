#!/usr/bin/env python3
"""Recolor all SVG shape paints (fill/stroke). Keeps structure.

Default fill is pure white. Use --color for any RGB.

Usage:
  python recolor_svg.py path/to/file.svg              # white (default), overwrites
  python recolor_svg.py path/to/folder/
  python recolor_svg.py path/to/folder/ --recursive
  python recolor_svg.py path/to/file.svg --new        # → file.recolor.svg
  python recolor_svg.py path/to/file.svg --color "#e13e13"
  python recolor_svg.py path/to/file.svg --color 0,200,255
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from colorutil import COLOR_HELP, RECURSIVE_HELP, collect_files, parse_color, rgb_to_hex

SHAPE_TAGS = {
    "path",
    "rect",
    "circle",
    "ellipse",
    "polygon",
    "polyline",
    "line",
    "text",
    "tspan",
}
SKIP_PAINT = {"none", "None", ""}
URL_RE = re.compile(r"^\s*url\s*\(", re.I)
STYLE_FILL_RE = re.compile(r"(fill)\s*:\s*([^;]+)", re.I)
STYLE_STROKE_RE = re.compile(r"(stroke)\s*:\s*([^;]+)", re.I)
NS_SVG = "http://www.w3.org/2000/svg"

SIDECAR_MARKER = ".recolor.svg"
_LEGACY_SIDECAR = ".white.svg"


def local_tag(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def should_recolor_paint(value: str | None) -> bool:
    if value is None:
        return False
    v = value.strip()
    if v in SKIP_PAINT or URL_RE.match(v):
        return False
    return True


def recolor_style(style: str, hex_color: str) -> str:
    def repl(m: re.Match[str]) -> str:
        prop, val = m.group(1), m.group(2)
        if should_recolor_paint(val):
            return f"{prop}:{hex_color}"
        return m.group(0)

    style = STYLE_FILL_RE.sub(repl, style)
    style = STYLE_STROKE_RE.sub(repl, style)
    return style


def recolor_element(el: ET.Element, hex_color: str) -> None:
    tag = local_tag(el.tag)
    if "fill" in el.attrib and should_recolor_paint(el.attrib["fill"]):
        el.set("fill", hex_color)
    if "stroke" in el.attrib and should_recolor_paint(el.attrib["stroke"]):
        el.set("stroke", hex_color)
    if "style" in el.attrib:
        el.set("style", recolor_style(el.attrib["style"], hex_color))
    # Unfilled drawing shapes default to black in SVG — force fill color
    if tag in SHAPE_TAGS and "fill" not in el.attrib:
        style = el.attrib.get("style", "")
        if not re.search(r"fill\s*:", style, re.I):
            if tag != "line":  # lines are stroke-only by convention
                el.set("fill", hex_color)


def recolor_svg_file(
    src: Path, dest: Path, color: tuple[int, int, int] = (255, 255, 255)
) -> None:
    hex_color = rgb_to_hex(color)
    ET.register_namespace("", NS_SVG)
    tree = ET.parse(src)
    root = tree.getroot()
    for el in root.iter():
        recolor_element(el, hex_color)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest, encoding="utf-8", xml_declaration=True)


def collect_svgs(path: Path, recursive: bool) -> list[Path]:
    return collect_files(
        path,
        recursive=recursive,
        suffixes={".svg"},
        skip_endings=(SIDECAR_MARKER, _LEGACY_SIDECAR),
        file_kind=".svg",
    )


def dest_for(src: Path, new: bool) -> Path:
    if new:
        return src.with_name(f"{src.stem}.recolor{src.suffix}")
    return src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Force SVG shape paints to a solid color (default white). "
            "Default: overwrite source."
        )
    )
    ap.add_argument(
        "path",
        type=Path,
        help="SVG file, or folder (files in that folder only)",
    )
    ap.add_argument(
        "--new",
        action="store_true",
        help="Write sidecar file.recolor.svg instead of overwriting",
    )
    ap.add_argument("--recursive", action="store_true", help=RECURSIVE_HELP)
    ap.add_argument(
        "--color",
        type=str,
        default="white",
        help=COLOR_HELP,
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
        files = collect_svgs(path, args.recursive)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1

    if not files:
        print(f"ERR no .svg files found under: {path}", file=sys.stderr)
        return 1

    errors = 0
    for src in files:
        dest = dest_for(src, args.new)
        try:
            recolor_svg_file(src, dest, color=fill)
            print(f"OK  {src} -> {dest}")
        except Exception as e:
            errors += 1
            print(f"ERR {src}: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
