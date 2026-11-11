#!/usr/bin/env bash
# Health check for hextile-pipe plugin install.
# Hard-fail: root, 5 matte scripts, Pillow. Soft-warn: numpy. Each --help must work.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/plugin-root.sh
source "${SCRIPT_DIR}/lib/plugin-root.sh"

ROOT="$(_fp_plugin_root)" || exit 1
export HEXTILE_PIPE_PLUGIN_ROOT="$ROOT"

PASS=0
FAIL=0
WARN=0

ok()   { echo "  OK  $*"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL $*"; FAIL=$((FAIL + 1)); }
soft() { echo "  WARN $*"; WARN=$((WARN + 1)); }

echo "hextile-pipe doctor"
echo "  root: $ROOT"

if [[ -d "$ROOT/matte" && -d "$ROOT/scripts" ]]; then
  ok "plugin root layout (matte/ + scripts/)"
else
  bad "plugin root layout incomplete"
fi

TOOLS=(recolor_svg recolor_png cutout knockout despeckle)
for t in "${TOOLS[@]}"; do
  f="$ROOT/matte/${t}.py"
  if [[ -f "$f" ]]; then
    ok "matte/${t}.py present"
  else
    bad "matte/${t}.py missing"
  fi
done

if [[ -f "$ROOT/matte/colorutil.py" ]]; then
  ok "matte/colorutil.py present"
else
  bad "matte/colorutil.py missing"
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
  ok "Pillow importable"
else
  bad "Pillow missing — pip install -r requirements.txt (pillow>=10)"
fi

if python3 -c "import numpy" 2>/dev/null; then
  ok "numpy present (optional)"
else
  soft "numpy not installed (optional; knockout/despeckle fall back to pure Pillow)"
fi

for t in "${TOOLS[@]}"; do
  if bash "$ROOT/scripts/fp-run.sh" "$t" -h >/dev/null 2>&1; then
    ok "fp-run $t -h"
  else
    bad "fp-run $t -h failed"
  fi
done

# Version lockstep
CLAUDE_V="$(python3 -c "import json; print(json.load(open('$ROOT/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo missing)"
CODEX_V="$(python3 -c "import json; print(json.load(open('$ROOT/.codex-plugin/plugin.json'))['version'])" 2>/dev/null || echo missing)"
CLAUDE_N="$(python3 -c "import json; print(json.load(open('$ROOT/.claude-plugin/plugin.json'))['name'])" 2>/dev/null || echo missing)"
CODEX_N="$(python3 -c "import json; print(json.load(open('$ROOT/.codex-plugin/plugin.json'))['name'])" 2>/dev/null || echo missing)"

if [[ "$CLAUDE_N" == "hextile-pipe" && "$CODEX_N" == "hextile-pipe" ]]; then
  ok "plugin name hextile-pipe (claude+codex)"
else
  bad "plugin name mismatch: claude=$CLAUDE_N codex=$CODEX_N"
fi

if [[ "$CLAUDE_V" == "$CODEX_V" && "$CLAUDE_V" != "missing" ]]; then
  ok "version lockstep $CLAUDE_V"
else
  bad "version lockstep broken: claude=$CLAUDE_V codex=$CODEX_V"
fi

echo
echo "summary: $PASS ok, $WARN warn, $FAIL fail"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
