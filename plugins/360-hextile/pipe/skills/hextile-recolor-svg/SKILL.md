---
name: hextile-recolor-svg
description: "Force SVG shape fills/strokes to a solid color (default white). Use for icon silhouettes that need a flat fill."
user-invocable: true
---

# hextile-recolor-svg

Forces SVG shape paints to a solid color (default `#ffffff`). Leaves `fill="none"` and `url(...)` paints alone.

## Run

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
bash "$ROOT/scripts/fp-run.sh" recolor_svg <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Flags

`bash "$ROOT/scripts/fp-run.sh" recolor_svg -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.recolor.svg` |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--color` | Fill RGB: name, `#rrggbb`, or `r,g,b` (default white) |

## Path rules

- SVG only. WSL-normalize paths. Fence CLI output.
