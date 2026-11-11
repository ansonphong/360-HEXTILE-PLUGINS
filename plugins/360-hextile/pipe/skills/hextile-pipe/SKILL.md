---
name: hextile-pipe
description: "Hub for 360 Hextile studio matte tools — route to knockout, cutout, recolor, despeckle; run doctor. Use when user says /hextile-pipe or needs studio matte help."
user-invocable: true
---

# hextile-pipe

Studio matte utilities for 360 Hextile. Agents run real Python CLIs from the **installed plugin root**, never the art project's cwd.

## Resolve plugin root

```bash
ROOT="${HEXTILE_PIPE_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}}"
# Prefer fp-run (resolves via scripts/lib/plugin-root.sh if env unset):
bash "${ROOT}/scripts/fp-run.sh" <tool> [args…]
bash "${ROOT}/scripts/fp-doctor.sh"
```

If ROOT is empty, locate `scripts/fp-run.sh` from this skill's package (plugin install path) and use that.

**WSL paths:** convert `C:\…` / `D:\…` to `/mnt/c/…` / `/mnt/d/…` before passing paths to Python.

## Subcommands / routes

| User intent | Skill or tool | fp-run tool |
|-------------|---------------|-------------|
| Doctor / install health | `fp-doctor.sh` | — |
| Recolor SVG (default white) | `/hextile-recolor-svg` | `recolor_svg` |
| Recolor PNG (default white) | `/hextile-recolor-png` | `recolor_png` |
| White-on-black cutout | `/hextile-cutout` | `cutout` |
| Art-on-black knockout | `/hextile-knockout` | `knockout` |
| Dust / freckles | `/hextile-despeckle` | `despeckle` |

Hub usage:

```bash
bash "$ROOT/scripts/fp-doctor.sh"
bash "$ROOT/scripts/fp-run.sh" knockout path/to/file.png --new
bash "$ROOT/scripts/fp-run.sh" recolor_png path/to/file.png --new --color "#e13e13"
```

## Agent defaults

- **Always inject `--new`** unless the user explicitly asks to overwrite the source.
- Discover flags with `bash "$ROOT/scripts/fp-run.sh" <tool> -h` — do not invent options.
- Fence CLI stdout/stderr in the reply.
- Human CLI default (outside this plugin) is overwrite; **agent default is sidecar**.

## Adobe

Illustrator / Photoshop are **reference only** — see `references/adobe-manual.md`. Do not pretend agent automation for JSX.

## Install

```text
hextile-pipe@360-hextile
```
