---
name: hextile-recolor-png
description: "Force PNG opaque pixels to a solid color (default white); preserve alpha. Use --min-alpha to skip AA fringe."
user-invocable: true
---

# hextile-recolor-png

Sets RGB for pixels with alpha ≥ `--min-alpha` (default 1 = all nonzero).
Fully transparent / sub-floor pixels keep original RGB.

## Run

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
bash "$ROOT/scripts/fp-run.sh" recolor_png <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Flags

`bash "$ROOT/scripts/fp-run.sh" recolor_png -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.recolor.png` |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--color` | Fill RGB: name, `#rrggbb`, or `r,g,b` (default white) |
| `--min-alpha N` | Only recolor when alpha ≥ N (default 1; try 8–16 for fringe) |

## Path rules

- PNG only. WSL-normalize paths. Fence CLI output.
