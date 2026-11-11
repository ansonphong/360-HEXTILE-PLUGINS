---
name: hextile-cutout
description: "White-on-black cutout — solid fill RGB (default white) + transparent black with AA. Use for glyphs/logos on black."
user-invocable: true
---

# hextile-cutout

White-on-black image → solid fill + transparent black (crisp anti-alias via luminance→alpha).

## Run

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
bash "$ROOT/scripts/fp-run.sh" cutout <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Common flags

`bash "$ROOT/scripts/fp-run.sh" cutout -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.cutout.png` |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--black-point N` | L ≤ N → alpha 0 (0–255; default 8) |
| `--white-point N` | L ≥ N → alpha 255 (0–255; default 247) |
| `--cutoff` / `--white` | Percent 0–100 aliases for black/white point |
| `--gamma G` | Midtone gamma |
| `--color COLOR` | Solid fill RGB (default white) |
| `--invert` | Dark glyph on light background |

## Path rules

- WSL-normalize Windows paths.
- JPEG needs `--new`.
- Fence CLI output.
