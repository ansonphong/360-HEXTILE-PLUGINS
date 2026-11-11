---
name: hextile-despeckle
description: "Despeckle dust/freckles on black-bg or transparent art via min-area components + levels; scale-aware and multi-pass."
user-invocable: true
---

# hextile-despeckle

Removes small islands on black-bg or transparent coverage (not RGB blur).

## Run

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
bash "$ROOT/scripts/fp-run.sh" despeckle <path> --new [flags…]
```

**Agent default:** always pass `--new` unless user insists on overwrite.

## Common flags

`bash "$ROOT/scripts/fp-run.sh" despeckle -h`

| Flag | Meaning |
|------|---------|
| `--new` | Sidecar `file.despeckle.png` |
| `--recursive` | Also process files in subfolders (default: this folder only) |
| `--mode auto\|alpha\|black` | Coverage source |
| `--min-area N` | Drop components under N pixels (default 4) |
| `--min-area-rel F` | Scale-aware: max(1, round(F × long_edge²)); exclusive with `--min-area` |
| `--passes P` | Repeat cleanup P times (default 1) |
| `--cutoff` / `--white` | Levels 0–100 |
| `--black-point` / `--white-point` | Levels 0–255 aliases |
| `--gamma` | Midtone gamma |
| `--to-alpha` | BLACK mode: emit RGBA |
| `--color` / `--invert` | Fill / invert |

## Path rules

- WSL-normalize paths. Fence CLI output.
