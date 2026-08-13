#!/usr/bin/env bash
# Focused synthetic smokes for cutout --color, recolor --min-alpha,
# despeckle --min-area-rel/--passes, and levels flag aliases.
# Exit 0 only if all assertions pass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${SMOKE_SCRATCH:-$(mktemp -d /tmp/hextile-matte-smoke.XXXXXX)}"
mkdir -p "$SCRATCH"
export PYTHONPATH="$ROOT/matte${PYTHONPATH:+:$PYTHONPATH}"

echo "hextile-pipe smoke-matte-flags"
echo "  root: $ROOT"
echo "  scratch: $SCRATCH"

python3 - <<PY
import subprocess, sys
from pathlib import Path
from PIL import Image
import numpy as np

root = Path("$ROOT")
scratch = Path("$SCRATCH")
py = sys.executable

def run(args):
    r = subprocess.run([py, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FAIL rc={r.returncode} cmd={args}\n{r.stdout}\n{r.stderr}")
    return r

# --- help flags ---
for tool, flags in {
    "cutout.py": ["--color", "--cutoff", "--black-point"],
    "recolor_png.py": ["--min-alpha", "--color"],
    "despeckle.py": ["--min-area-rel", "--passes", "--black-point"],
    "knockout.py": ["--black-point", "--cutoff", "--silhouette", "--blur", "--choke"],
}.items():
    text = subprocess.check_output([py, str(root / "matte" / tool), "-h"], text=True)
    for f in flags:
        assert f in text, f"missing {f} in {tool} -h"

# --- folder mode is this folder only unless --recursive ---
from colorutil import collect_files
nest = scratch / "nest"
(nest / "sub").mkdir(parents=True)
Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(nest / "top.png")
Image.new("RGBA", (4, 4), (40, 50, 60, 255)).save(nest / "sub" / "deep.png")
shallow = collect_files(
    nest, recursive=False, suffixes={".png"}, warn_skipped=False
)
deep = collect_files(
    nest, recursive=True, suffixes={".png"}, warn_skipped=False
)
assert [p.name for p in shallow] == ["top.png"], shallow
assert [p.name for p in deep] == ["deep.png", "top.png"], deep
run([str(root / "matte/recolor_png.py"), str(nest), "--color", "white"])
assert list(np.array(Image.open(nest / "top.png").convert("RGBA"))[0, 0, :3]) == [
    255, 255, 255,
]
assert list(np.array(Image.open(nest / "sub" / "deep.png").convert("RGBA"))[0, 0, :3]) == [
    40, 50, 60,
]
run([
    str(root / "matte/recolor_png.py"), str(nest),
    "--recursive", "--color", "red",
])
assert list(np.array(Image.open(nest / "sub" / "deep.png").convert("RGBA"))[0, 0, :3]) == [
    255, 0, 0,
]

# --- cutout --color ---
src = scratch / "cutout_src.png"
img = Image.new("RGB", (64, 64), (0, 0, 0))
px = img.load()
for y in range(16, 48):
    for x in range(16, 48):
        px[x, y] = (255, 255, 255)
img.save(src)
run([str(root / "matte/cutout.py"), str(src), "--new", "--color", "#e13e13"])
arr = np.array(Image.open(scratch / "cutout_src.cutout.png").convert("RGBA"))
c = arr[32, 32]
assert list(c) == [225, 62, 19, 255], c
assert arr[0, 0, 3] == 0

# --- recolor --min-alpha ---
src = scratch / "recolor_src.png"
a = np.zeros((8, 8, 4), dtype=np.uint8)
a[2, 2] = [10, 20, 30, 200]
a[3, 3] = [40, 50, 60, 5]
Image.fromarray(a, "RGBA").save(src)
run([str(root / "matte/recolor_png.py"), str(src), "--color", "red", "--min-alpha", "16"])
out = np.array(Image.open(src).convert("RGBA"))
assert list(out[2, 2]) == [255, 0, 0, 200]
assert list(out[3, 3]) == [40, 50, 60, 5]

# --- despeckle relative min-area ---
size = 200
src = scratch / "desp_rel.png"
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
px = img.load()
for y in range(60, 100):
    for x in range(60, 100):
        px[x, y] = (255, 255, 255, 255)
for dy in range(3):
    for dx in range(3):
        px[20 + dx, 160 + dy] = (255, 255, 255, 255)
img.save(src)
run([
    str(root / "matte/despeckle.py"), str(src), "--new", "--mode", "alpha",
    "--min-area-rel", "0.0003", "--cutoff", "0",
])
a2 = np.array(Image.open(scratch / "desp_rel.despeckle.png").convert("RGBA"))
assert a2[161, 21, 3] == 0
assert a2[80, 80, 3] == 255

# --- despeckle passes (no crash; P>=1) ---
src = scratch / "desp_pass.png"
arr = np.zeros((32, 32, 4), dtype=np.uint8)
arr[8:24, 8:24, :] = 255
arr[2, 2] = [255, 255, 255, 255]
Image.fromarray(arr, "RGBA").save(src)
run([
    str(root / "matte/despeckle.py"), str(src), "--mode", "alpha",
    "--min-area", "2", "--passes", "2", "--cutoff", "0",
])
assert np.array(Image.open(src).convert("RGBA"))[2, 2, 3] == 0

# --- levels aliases equivalence (cutout) ---
arr = np.zeros((32, 32, 3), dtype=np.uint8)
for x in range(32):
    arr[:, x] = int(x / 31 * 255)
src_a, src_b = scratch / "cut_a.png", scratch / "cut_b.png"
Image.fromarray(arr, "RGB").save(src_a)
Image.fromarray(arr, "RGB").save(src_b)
run([str(root / "matte/cutout.py"), str(src_a), "--black-point", "8", "--white-point", "247"])
run([
    str(root / "matte/cutout.py"), str(src_b),
    "--cutoff", str(8 / 255 * 100), "--white", str(247 / 255 * 100),
])
diff = np.abs(
    np.array(Image.open(src_a).convert("RGBA")).astype(int)
    - np.array(Image.open(src_b).convert("RGBA")).astype(int)
).max()
assert diff <= 1, diff

# conflict must fail
r = subprocess.run(
    [py, str(root / "matte/cutout.py"), str(src_a), "--black-point", "8", "--cutoff", "3"],
    capture_output=True, text=True,
)
assert r.returncode != 0

# --- knockout --silhouette keeps grey RGB, keys only black ---
sil = scratch / "sil_src.png"
sil_img = Image.new("RGB", (2, 1), (0, 0, 0))
sil_img.putpixel((1, 0), (128, 128, 128))
sil_img.save(sil)
run([
    str(root / "matte/knockout.py"), str(sil),
    "--silhouette", "--cutoff", "3", "--blur", "0",
])
sil_out = np.array(Image.open(sil).convert("RGBA"))
assert list(sil_out[0, 0]) == [0, 0, 0, 0], sil_out[0, 0]
assert list(sil_out[0, 1]) == [128, 128, 128, 255], sil_out[0, 1]

# default blur+choke: interior of a solid block stays opaque grey
blk = scratch / "sil_block.png"
bimg = Image.new("RGB", (32, 32), (0, 0, 0))
for y in range(8, 24):
    for x in range(8, 24):
        bimg.putpixel((x, y), (128, 128, 128))
bimg.save(blk)
run([str(root / "matte/knockout.py"), str(blk), "--silhouette", "--force"])
bout = np.array(Image.open(blk).convert("RGBA"))
assert list(bout[16, 16]) == [128, 128, 128, 255], bout[16, 16]
assert int(bout[0, 0, 3]) == 0

print("PASS smoke-matte-flags")
PY
