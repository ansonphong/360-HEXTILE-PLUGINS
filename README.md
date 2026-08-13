# ⬡ hextile-pipe

Loose bag of **studio utility scripts** for art assets — not a product pipeline.

- **Python** (`matte/`) — recolor, cutout, knockout, despeckle, trim  
- **Illustrator** (`illustrator/`) — batch-export selected groups  
- **Photoshop** (`photoshop/`) — design for layer export (jsx TBD)  

Use whatever you need; nothing requires anything else.

GitHub: [`github.com/ansonphong/hextile-pipe`](https://github.com/ansonphong/hextile-pipe)

## Layout

```
hextile-pipe/
  matte/                 Python CLIs (Pillow) + colorutil
  illustrator/           ExtendScript (.jsx)
  photoshop/             Photoshop script design (WIP)
  fixtures/              Optional sample assets (LFS)
  scripts/               fp-run, doctor, plugin test, smoke
  skills/                Claude/Codex plugin skills
  README.md              SSOT docs (this file)
```

**Conventions:** lowercase folders · Python `snake_case` · JSX/docs `kebab-case`.

---

## Matte (Python)

Python utilities for artwork mattes: recolor silhouettes, cut black→transparent
(glyph + fill), knock out black with a fill color, despeckle dust, or trim
transparent margins.

Requires: `pip install pillow` (numpy optional, speeds large images).

**Default: overwrite the source.** Pass `--new` for a sidecar.  
**`--color`** (where present): name · `#rgb` / `#rrggbb` · `r,g,b` — **default white**.  
Shared parser: `matte/colorutil.py`.

Discover live flags anytime:

```bash
python3 matte/<tool>.py -h
bash scripts/fp-run.sh <tool> -h
bash scripts/fp-run.sh <tool> path/to/file.png --new
bash scripts/smoke-matte-flags.sh   # synthetic regression smoke
```

### Quick map

| Need | Script |
|------|--------|
| Force fills/pixels to a color (default white) | `recolor_svg.py` / `recolor_png.py` |
| Glyph cutout (luma→alpha + solid fill color) | `cutout.py` |
| Grey art on black → alpha + any fill color | `knockout.py` |
| Remove dust / freckles (black or transparent) | `despeckle.py` |
| Crop to transparency / add margin (px or %) | `trim.py` |
| Shared color + levels helpers (not a CLI) | `colorutil.py` |

```bash
python3 matte/recolor_svg.py icon.svg
python3 matte/recolor_png.py sprite.png --color "#e13e13" --min-alpha 16
python3 matte/cutout.py file.png --color "#e13e13"
python3 matte/knockout.py file.png --cutoff 5 --color white
python3 matte/despeckle.py file.png --min-area-rel 0.0001 --passes 2
python3 matte/trim.py file.png --margin 5%
python3 matte/knockout.py file.png --new          # sidecar
```

### Levels language (shared)

Cutout, knockout, and despeckle accept **both** unit systems. Use **one system per end** (error if both set).

| Unit | Flags | Range | Native on |
|------|-------|--------|-----------|
| Percent | `--cutoff` / `--white` | **0–100** | knockout, despeckle |
| Raw luma | `--black-point` / `--white-point` | **0–255** | cutout |

Conversion: `u8 = pct/100*255`, `pct = u8/255*100` (rounded when going to integer points).

### Shared flags (most tools)

| Flag | Meaning |
|------|---------|
| `path` | File or directory |
| `--new` | Write sidecar instead of overwrite |
| `--recursive` | Also process files in subfolders (default: only files in the given folder) |
| `--color COLOR` | Fill RGB (default **white**) — *recolor, cutout, knockout, despeckle* |
| `--invert` | Flip coverage / greyscale (dark art on light) — *cutout, knockout, despeckle* |
| `--gamma G` | Midtone gamma; `>1` = crisper (default `1.0`) — *cutout, knockout, despeckle* |

### SVG recolor — `recolor_svg.py`

Sets shape fills and strokes to a solid color (default `#ffffff`).
Leaves `fill="none"` and `url(...)` paints alone.

```bash
python3 matte/recolor_svg.py icon.svg              # white, overwrites
python3 matte/recolor_svg.py icon.svg --new        # → icon.recolor.svg
python3 matte/recolor_svg.py icon.svg --color "#e13e13"
python3 matte/recolor_svg.py ./icons/ --recursive
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `file.recolor.svg` |
| `--recursive` | off | Recurse subfolders |
| `--color` | `white` | Fill/stroke color |

### PNG recolor — `recolor_png.py`

Sets RGB for pixels with alpha ≥ `--min-alpha` (default pure white).
Fully transparent / sub-floor pixels keep their original RGB.

```bash
python3 matte/recolor_png.py sprite.png            # white, overwrites
python3 matte/recolor_png.py sprite.png --new      # → sprite.recolor.png
python3 matte/recolor_png.py sprite.png --color red
python3 matte/recolor_png.py sprite.png --color "#e13e13" --min-alpha 16
python3 matte/recolor_png.py ./sprites/ --recursive
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `file.recolor.png` |
| `--recursive` | off | Recurse subfolders |
| `--color` | `white` | RGB fill |
| `--min-alpha` | `1` | Only recolor when alpha ≥ N (1 = all nonzero; 8–16 skips AA fringe) |

### Cutout — `cutout.py`

White-on-black PNG/JPG → RGBA: **solid fill RGB** (default white), **black transparent**,
anti-alias via luminance→alpha.

```bash
python3 matte/cutout.py file.png                  # white fill, overwrites
python3 matte/cutout.py file.png --new            # → file.cutout.png
python3 matte/cutout.py file.png --color "#e13e13"
python3 matte/cutout.py file.png --black-point 12 --gamma 1.3
python3 matte/cutout.py file.png --cutoff 5 --white 97   # percent aliases
python3 matte/cutout.py file.png --invert
python3 matte/cutout.py file.jpg --new            # JPEG needs --new
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `file.cutout.png` |
| `--recursive` | off | Recurse subfolders |
| `--black-point` | `8` | Luma ≤ N → alpha 0 (**0–255**) |
| `--white-point` | `247` | Luma ≥ N → alpha 255 (**0–255**) |
| `--cutoff` / `--white` | — | Percent **0–100** aliases |
| `--gamma` | `1.0` | Midtone gamma |
| `--color` | `white` | Solid RGB where visible |
| `--invert` | off | Dark glyph on light BG |

JPEG needs `--new` (no alpha).

### Knockout — `knockout.py`

Art-on-black PNG/JPG → RGBA:

1. RGB → greyscale luminance  
2. **Levels** (`--cutoff` / `--white`, **0–100%**) → **alpha**  
3. **RGB** filled with `--color` (default pure white)

```bash
python3 matte/knockout.py file.png                # white fill
python3 matte/knockout.py file.png --new          # → file.png.knockout.png
python3 matte/knockout.py file.png --cutoff 5 --white 95
python3 matte/knockout.py file.png --black-point 13 --white-point 242
python3 matte/knockout.py file.png --color "#e13e13"
python3 matte/knockout.py file.png --silhouette   # key black; keep original greys
python3 matte/knockout.py file.png --force
python3 matte/knockout.py file.jpg --new
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `stem.ext.knockout.png` |
| `--recursive` | off | Recurse |
| `--force` | off | Reprocess knockout products |
| `--cutoff` | `3` | Black point **0–100** → alpha 0 (crushes near-black; after `--invert`, near-white) |
| `--white` | `97` | White point **0–100** → alpha 255 (crushes near-white; after `--invert`, near-black) |
| `--black-point` / `--white-point` | — | Raw **0–255** aliases |
| `--gamma` | `1.0` | Midtone gamma |
| `--color` | `white` | Solid fill (unused with `--silhouette`) |
| `--invert` | off | Invert greyscale first |
| `--silhouette` | off | Key only `--cutoff`; keep original RGB; then blur+choke the matte |
| `--blur` | `1` | Silhouette: Gaussian on the matte, pixels (`0` = off) |
| `--choke` | `1.2` | Silhouette: how far in to pull after blur, pixels |

PNG metadata `hextile-pipe-tool=knockout`; refuse reprocess unless `--force`.
Batch safety: preflight destinations; unique sidecars per source extension.

### Despeckle — `despeckle.py`

Coverage-channel cleanup (alpha or luminance) — not RGB blur.

1. Mode `auto`: any `A < 255` → alpha; else luminance  
2. Drop 8-connected components &lt; `--min-area` or scale-aware `--min-area-rel`  
3. Levels once  
4. Optional `--passes P` repeats steps 2–3  

```bash
python3 matte/despeckle.py file.png
python3 matte/despeckle.py file.png --new
python3 matte/despeckle.py file.png --min-area 64
python3 matte/despeckle.py file.png --min-area-rel 0.0001   # scales with long_edge²
python3 matte/despeckle.py file.png --passes 2
python3 matte/despeckle.py file.png --mode black --to-alpha --color white
python3 matte/despeckle.py file.png --black-point 3         # 0–255 alias
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `file.despeckle.png` |
| `--recursive` | off | Recurse |
| `--mode` | `auto` | `auto` \| `alpha` \| `black` |
| `--min-area` | `4` | Absolute pixel threshold (`0` = off) |
| `--min-area-rel` | — | Fraction of long_edge² (exclusive with `--min-area`) |
| `--passes` | `1` | Repeat cleanup P times |
| `--cutoff` | `1` | Levels black **0–100** |
| `--white` | `100` | Levels white **0–100** |
| `--black-point` / `--white-point` | — | Raw **0–255** aliases |
| `--gamma` | `1.0` | Midtone gamma |
| `--to-alpha` | off | BLACK → RGBA |
| `--color` | (see help) | Fill when emitting alpha |
| `--invert` | off | Invert coverage first |

`--min-area-rel F` → `effective = max(1, round(F * long_edge²))` (F=0 → off).

High-res freckles: prefer relative, or absolute 32–64+, and/or `--passes 2`.

### Trim — `trim.py`

Crop a transparent PNG to the content bounding box (alpha above `--threshold`),
and/or pad a **uniform** transparent margin in pixels or percent of the larger
content side. Preserves original RGB+alpha of content pixels.

**Modes:** `crop` (default) finds content then applies margin; `pad` expands the
full canvas by margin only (no content trim). Percent margins always measure
**content** size (not empty border), including in `pad` mode.

**Percent formula (locked):**  
`m = int(max(content_w, content_h) * pct / 100 + 0.5)` (half-up) on all four sides.

```bash
python3 matte/trim.py file.png                     # tight crop, overwrite
python3 matte/trim.py file.png --new               # → file.trim.png
python3 matte/trim.py file.png --margin 10
python3 matte/trim.py file.png --margin 5%
python3 matte/trim.py file.png --mode pad --margin 24
python3 matte/trim.py file.png --threshold 4 --margin 8 --new
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--new` | off | Sidecar `file.trim.png` |
| `--recursive` | off | Recurse subfolders |
| `--mode` | `crop` | `crop` or `pad` |
| `--margin` | `0` | `N` / `Npx` or `N%` |
| `--threshold` | `0` | Content if alpha > N (0–254) |

Empty image under `crop` → `ERR` and non-zero exit for that file. JPEG overwrite
refused — use `--new`. Batch preflight rejects destination collisions.

### Sidecars (`--new`)

| Tool | Output name |
|------|-------------|
| recolor | `file.recolor.png` / `file.recolor.svg` |
| cutout | `file.cutout.png` |
| knockout | `file.ext.knockout.png` (e.g. `a.png.knockout.png`) |
| despeckle | `file.despeckle.png` |
| trim | `file.trim.png` |

### Naming & notes

- `snake_case.py`, verb first  
- Format suffix only when engines differ (`recolor_svg` / `recolor_png`)  
- Shared helpers: `colorutil.py`  
- Folder mode is non-recursive unless `--recursive`  
- Sidecar-named files are skipped on re-run so `--new` is safe (recolor also skips legacy `*.white.*`)  
- Default **overwrites** the source  
- `despeckle` is not fully idempotent if you raise cutoff/min-area between runs — prefer one clean pass from backup  
- Old names `whiten_svg` / `whiten_png` still work via `scripts/fp-run.sh` aliases  

---

## Illustrator

`illustrator/export-grouped-assets.jsx` — select objects (grouped or not) → dialog → export AI / SVG / PNG.

| File | Role |
|------|------|
| `export-grouped-assets.jsx` | Runnable ExtendScript |
| `export-grouped-assets-design.md` | Design notes |
| `artboard-export-all-groups.md` | Earlier brief |
| `test-pure-helpers.js` | Pure-helper tests (no Illustrator) |

Run: **File → Scripts → Other Script…**

---

## Photoshop

`photoshop/export-selected-layers-design.md` — selected-layer PNG export design.  
**Not implemented yet** (no `.jsx`).

---

## Git / LFS

Large binaries (PNG/JPG/PSD/AI/PDF/…) use **Git LFS**.

```bash
git lfs install
git clone https://github.com/ansonphong/hextile-pipe.git
cd hextile-pipe && git lfs pull
```

| File | Role |
|------|------|
| `.gitignore` | Python, OS, Adobe junk, secrets, generated sidecars |
| `.gitattributes` | LF text + LFS globs |
| `.editorconfig` | indent / charset / newlines |
| `.env.example` | template only — never commit `.env` |

Don’t commit export dumps or machine prefs (`prefs.txt`, `export-report.txt`).

## License

Private / studio tooling unless you add a LICENSE.
