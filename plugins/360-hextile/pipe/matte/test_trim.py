"""Focused tests for matte/trim.py — drive shipped functions only."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trim import (  # noqa: E402
    content_bbox,
    expand_bbox,
    margin_px_for_bbox,
    parse_margin,
    trim_image,
)


def _fixture() -> Image.Image:
    """100x80 transparent; red opaque rect at (20,10)-(50,40) → size 30x30."""
    im = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    for y in range(10, 40):
        for x in range(20, 50):
            im.putpixel((x, y), (255, 0, 0, 255))
    return im


def test_parse_margin_px_and_pct():
    assert parse_margin("10") == ("px", 10.0)
    assert parse_margin("10px") == ("px", 10.0)
    assert parse_margin("5%") == ("pct", 5.0)
    assert parse_margin("0") == ("px", 0.0)


def test_content_bbox_threshold():
    im = _fixture()
    assert content_bbox(im, threshold=0) == (20, 10, 50, 40)
    # faint pixel should be ignored when threshold high
    im.putpixel((5, 5), (0, 0, 0, 3))
    assert content_bbox(im, threshold=0) == (5, 5, 50, 40)
    assert content_bbox(im, threshold=3) == (20, 10, 50, 40)


def test_percent_margin_uses_max_side():
    # content 30x30 → 5% of max(30,30)=30 → int(1.5+0.5)=2 half-up
    bbox = (20, 10, 50, 40)
    m = margin_px_for_bbox(bbox, kind="pct", value=5.0)
    assert m == int(30 * 5.0 / 100.0 + 0.5)


def test_expand_bbox():
    assert expand_bbox((20, 10, 50, 40), margin_px=10) == (10, 0, 60, 50)


def test_trim_crop_tight():
    out = trim_image(_fixture(), mode="crop", margin="0")
    assert out.size == (30, 30)
    assert out.getpixel((0, 0)) == (255, 0, 0, 255)
    assert out.getpixel((29, 29)) == (255, 0, 0, 255)


def test_trim_crop_margin_px():
    out = trim_image(_fixture(), mode="crop", margin="10")
    assert out.size == (50, 50)  # 30+20
    # content should start at (10,10)
    assert out.getpixel((10, 10)) == (255, 0, 0, 255)
    assert out.getpixel((0, 0))[3] == 0


def test_trim_crop_margin_pct():
    # 5% of 30 → 2px each side → 34x34
    out = trim_image(_fixture(), mode="crop", margin="5%")
    assert out.size == (34, 34)
    assert out.getpixel((2, 2)) == (255, 0, 0, 255)
    assert out.getpixel((0, 0))[3] == 0


def test_trim_pad_only():
    out = trim_image(_fixture(), mode="pad", margin="5")
    assert out.size == (110, 90)
    # original top-left content at (20,10) moves to (25,15)
    assert out.getpixel((25, 15)) == (255, 0, 0, 255)
    assert out.getpixel((0, 0))[3] == 0


def test_trim_pad_percent_uses_content_not_canvas():
    # content 30x30 → 5% → 2px; pad keeps full 100x80 → final 104x84
    out = trim_image(_fixture(), mode="pad", margin="5%")
    assert out.size == (104, 84)
    # content was at (20,10), plus 2px pad → (22,12)
    assert out.getpixel((22, 12)) == (255, 0, 0, 255)
    assert out.getpixel((0, 0))[3] == 0


def test_empty_content_errors():
    im = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    try:
        trim_image(im, mode="crop", margin="0")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_threshold_bounds():
    im = _fixture()
    try:
        content_bbox(im, threshold=255)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        content_bbox(im, threshold=-1)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


if __name__ == "__main__":
    test_parse_margin_px_and_pct()
    test_content_bbox_threshold()
    test_percent_margin_uses_max_side()
    test_expand_bbox()
    test_trim_crop_tight()
    test_trim_crop_margin_px()
    test_trim_crop_margin_pct()
    test_trim_pad_only()
    test_trim_pad_percent_uses_content_not_canvas()
    test_empty_content_errors()
    test_threshold_bounds()
    print("PASS test_trim")
