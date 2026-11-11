#!/usr/bin/env bash
# Packaging smoke — no LFS required. Synthetic SVG/PNG only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export HEXTILE_PIPE_PLUGIN_ROOT="$ROOT"

SCRATCH="${TMPDIR:-/tmp}/hextile-pipe-test-$$"
mkdir -p "$SCRATCH"
trap 'rm -rf "$SCRATCH"' EXIT

PASS=0
FAIL=0
ok()  { echo "  OK  $*"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL $*"; FAIL=$((FAIL + 1)); }

echo "hextile-pipe test-plugin"
echo "  root: $ROOT"
echo "  scratch: $SCRATCH"

# --- manifests ---
for m in .claude-plugin/plugin.json .codex-plugin/plugin.json; do
  if [[ ! -f "$ROOT/$m" ]]; then
    bad "missing $m"
    continue
  fi
  name="$(python3 -c "import json; print(json.load(open('$ROOT/$m'))['name'])")"
  ver="$(python3 -c "import json; print(json.load(open('$ROOT/$m'))['version'])")"
  if [[ "$name" == "hextile-pipe" ]]; then
    ok "$m name=$name version=$ver"
  else
    bad "$m name=$name (want hextile-pipe)"
  fi
done

CV="$(python3 -c "import json; print(json.load(open('$ROOT/.claude-plugin/plugin.json'))['version'])")"
XV="$(python3 -c "import json; print(json.load(open('$ROOT/.codex-plugin/plugin.json'))['version'])")"
if [[ "$CV" == "$XV" ]]; then
  ok "version lockstep $CV"
else
  bad "version lockstep $CV vs $XV"
fi

if [[ -f "$ROOT/marketplace.json" ]] || [[ -f "$ROOT/.claude-plugin/marketplace.json" ]]; then
  bad "marketplace.json must not live in the plugin package"
else
  ok "no marketplace.json in plugin package"
fi

# --- skills ---
SKILLS=(hextile-pipe hextile-knockout hextile-cutout hextile-recolor-png hextile-recolor-svg hextile-despeckle)
for s in "${SKILLS[@]}"; do
  f="$ROOT/skills/$s/SKILL.md"
  if [[ -f "$f" ]]; then
    n="$(grep -m1 '^name:' "$f" | sed 's/name:[[:space:]]*//')"
    if [[ "$n" == "$s" ]]; then
      ok "skill $s"
    else
      bad "skill $s name field='$n'"
    fi
  else
    bad "missing skill $s"
  fi
done

if grep -RIn --include='*.md' -E 'frog-pipe|/frog-' "$ROOT/skills" 2>/dev/null; then
  bad "frog brand leaked into skills/"
else
  ok "no frog brand in skills/"
fi

# --- scripts executable + doctor ---
chmod +x "$ROOT/scripts/fp-run.sh" "$ROOT/scripts/fp-doctor.sh" "$ROOT/scripts/test-plugin.sh" 2>/dev/null || true

# cwd independence: run from /tmp
if (cd /tmp && bash "$ROOT/scripts/fp-doctor.sh") >/dev/null 2>&1; then
  ok "fp-doctor from /tmp"
else
  bad "fp-doctor from /tmp"
  (cd /tmp && bash "$ROOT/scripts/fp-doctor.sh") || true
fi

if (cd /tmp && bash "$ROOT/scripts/fp-run.sh" knockout -h) >/dev/null 2>&1; then
  ok "fp-run knockout -h from /tmp"
else
  bad "fp-run knockout -h from /tmp"
fi

# --- synthetic assets ---
# Minimal white-on-black PNG via Python
python3 - <<'PY' "$SCRATCH"
import sys
from pathlib import Path
from PIL import Image

d = Path(sys.argv[1])
# 32x32: white circle-ish blob on black
img = Image.new("RGB", (32, 32), (0, 0, 0))
px = img.load()
for y in range(8, 24):
    for x in range(8, 24):
        px[x, y] = (255, 255, 255)
img.save(d / "blob.png")

# black-bg grey art for knockout
img2 = Image.new("RGB", (32, 32), (0, 0, 0))
px2 = img2.load()
for y in range(10, 22):
    for x in range(10, 22):
        px2[x, y] = (180, 180, 180)
img2.save(d / "grey.png")

(d / "icon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
    '<rect width="16" height="16" fill="#e13e13"/></svg>\n',
    encoding="utf-8",
)
print("synthetic ok")
PY

bash "$ROOT/scripts/fp-run.sh" recolor_svg "$SCRATCH/icon.svg" --new
if [[ -f "$SCRATCH/icon.recolor.svg" ]]; then
  ok "recolor_svg sidecar"
else
  bad "recolor_svg no sidecar"
fi

bash "$ROOT/scripts/fp-run.sh" cutout "$SCRATCH/blob.png" --new
if [[ -f "$SCRATCH/blob.cutout.png" ]]; then
  ok "cutout sidecar"
else
  bad "cutout no sidecar"
fi

bash "$ROOT/scripts/fp-run.sh" knockout "$SCRATCH/grey.png" --new
# knockout sidecar naming: file.ext.knockout.png
if ls "$SCRATCH"/grey.png.knockout.png >/dev/null 2>&1 || ls "$SCRATCH"/*knockout* >/dev/null 2>&1; then
  ok "knockout sidecar"
else
  bad "knockout no sidecar"
  ls -la "$SCRATCH" || true
fi

bash "$ROOT/scripts/fp-run.sh" despeckle "$SCRATCH/blob.png" --new
if ls "$SCRATCH"/*despeckle* >/dev/null 2>&1; then
  ok "despeckle sidecar"
else
  bad "despeckle no sidecar"
fi

bash "$ROOT/scripts/fp-run.sh" recolor_png "$SCRATCH/blob.cutout.png" --new --color "#e13e13"
if ls "$SCRATCH"/*recolor.png >/dev/null 2>&1; then
  ok "recolor_png sidecar"
else
  bad "recolor_png no sidecar"
fi

echo
echo "summary: $PASS ok, $FAIL fail"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
echo "PASS"
exit 0
