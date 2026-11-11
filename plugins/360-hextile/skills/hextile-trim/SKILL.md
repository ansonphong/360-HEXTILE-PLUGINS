---
name: hextile-trim
description: "Crop transparent PNG to content bbox and/or add margin (px or %). Use for icon padding and auto-trim."
user-invocable: true
---

# hextile-trim

Crop a transparent PNG (or JPEG via sidecar) to the non-transparent content, and/or pad a uniform transparent margin in **pixels** or **percent of max content side**.

## Run

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}"
bash "$ROOT/pipe/scripts/fp-run.sh" trim <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Common flags

Discover full set: `bash "$ROOT/pipe/scripts/fp-run.sh" trim -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.trim.png` (required for agents) |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--mode crop\|pad` | `crop` (default): trim to content then margin; `pad`: expand canvas only |
| `--margin SPEC` | `10` / `10px` or `5%` (half-up % of max content side, all four sides) |
| `--threshold N` | Content if alpha > N (0–254; default 0) |

## Examples

```bash
bash "$ROOT/pipe/scripts/fp-run.sh" trim icon.png --new
bash "$ROOT/pipe/scripts/fp-run.sh" trim icon.png --new --margin 10
bash "$ROOT/pipe/scripts/fp-run.sh" trim icon.png --new --margin 5%
bash "$ROOT/pipe/scripts/fp-run.sh" trim icon.png --new --mode pad --margin 24
bash "$ROOT/pipe/scripts/fp-run.sh" trim icon.png --new --threshold 4 --margin 8
```

## Path rules

- Normalize Windows paths under WSL (`D:\x` → `/mnt/d/x`).
- JPEG has no alpha for overwrite — use `--new`.
- Fence CLI output in the reply.
