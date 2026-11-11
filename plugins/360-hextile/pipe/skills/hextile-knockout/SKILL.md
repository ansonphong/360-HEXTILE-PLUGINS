---
name: hextile-knockout
description: "Knock out black (or light) background — greyscale→alpha + solid fill. Use for art-on-black PNGs needing transparent matte."
user-invocable: true
---

# hextile-knockout

Art-on-black PNG/JPG → RGBA: levels on luminance become **alpha**, RGB filled with a solid color (default white).

## Run

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
bash "$ROOT/scripts/fp-run.sh" knockout <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Common flags

Discover full set: `bash "$ROOT/scripts/fp-run.sh" knockout -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.ext.knockout.png` (required for agents) |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--cutoff PCT` | Levels black point 0–100 (default **3** — crush near-black / near-white after `--invert`) |
| `--white PCT` | Levels white point 0–100 (default **97** — crush near-white / near-black after `--invert`) |
| `--black-point` / `--white-point` | Raw luma 0–255 aliases |
| `--gamma G` | Midtone gamma on alpha |
| `--color COLOR` | Fill RGB: name, `#rrggbb`, or `r,g,b` (unused with `--silhouette` / `--wand`) |
| `--invert` | Dark art on light background |
| `--silhouette` | Key only `--cutoff`; keep original greys; blur then levels (default `--blur 2 --lo 150 --hi 170`) |
| `--wand` | Key only backdrop connected to the image edge (implies `--silhouette`). Seals 2px, floods, unseals. Interior black stays |
| `--blur PX` | Silhouette / wand: Gaussian on the matte (default 2; `0` = hard key) |
| `--lo` / `--hi` | Silhouette / wand: input levels on the blurred matte 0–255 (default 150–170) |
| `--force` | Allow reprocessing tagged outputs |

## Path rules

- Normalize Windows paths under WSL (`D:\x` → `/mnt/d/x`).
- JPEG has no alpha — use `--new`.
- Fence CLI output in the reply.
