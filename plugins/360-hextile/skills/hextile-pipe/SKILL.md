---
name: hextile-pipe
description: "Hub for 360 Hextile studio matte tools — route to knockout, cutout, recolor, despeckle, trim; run doctor. Use when user says /hextile-pipe or needs studio matte help."
user-invocable: true
---

# hextile-pipe

Studio matte utilities for 360 Hextile. Agents run real Python CLIs from the **installed plugin root**, never the art project's cwd.

## Resolve plugin root

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}}"
# Prefer fp-run (resolves via pipe/scripts/lib/plugin-root.sh if env unset):
bash "${ROOT}/pipe/scripts/fp-run.sh" <tool> [args…]
bash "${ROOT}/pipe/scripts/fp-doctor.sh"
```

If ROOT is empty, use the installed 360-hextile plugin root two levels above this skill folder (`skills/hextile-pipe/../..`) and run `pipe/scripts/fp-run.sh` from there.

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
| Crop to alpha / add margin | `/hextile-trim` | `trim` |

Hub usage:

```bash
bash "$ROOT/pipe/scripts/fp-doctor.sh"
bash "$ROOT/pipe/scripts/fp-run.sh" knockout path/to/file.png --new
bash "$ROOT/pipe/scripts/fp-run.sh" recolor_png path/to/file.png --new --color "#e13e13"
```

## Agent defaults

- **Always inject `--new`** unless the user explicitly asks to overwrite the source.
- Discover flags with `bash "$ROOT/pipe/scripts/fp-run.sh" <tool> -h` — do not invent options.
- Fence CLI stdout/stderr in the reply.
- Human CLI default (outside this plugin) is overwrite; **agent default is sidecar**.

## Adobe

Illustrator / Photoshop are **reference only** — see `pipe/references/adobe-manual.md`. Do not pretend agent automation for JSX.

## Install

```text
360-hextile@360-hextile
```

Pipe ships inside the 360-hextile plugin; there is no separate Pipe plugin to install.
