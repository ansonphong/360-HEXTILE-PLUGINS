#!/usr/bin/env bash
# Dispatch a matte CLI by short tool name from the plugin package root.
# Usage: fp-run.sh <tool> [args…]
# Tools: recolor_svg | recolor_png | cutout | knockout | despeckle
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/plugin-root.sh
source "${SCRIPT_DIR}/lib/plugin-root.sh"

ROOT="$(_fp_plugin_root)" || exit 1
export HEXTILE_PIPE_PLUGIN_ROOT="$ROOT"

TOOLS_HELP="recolor_svg recolor_png cutout knockout despeckle"

if [[ $# -lt 1 ]]; then
  echo "usage: fp-run.sh <tool> [args…]" >&2
  echo "tools: $TOOLS_HELP" >&2
  exit 2
fi

TOOL="$1"
shift

case "$TOOL" in
  recolor_svg|recolor-svg|whiten_svg|whiten-svg)  SCRIPT="recolor_svg.py" ;;
  recolor_png|recolor-png|whiten_png|whiten-png)  SCRIPT="recolor_png.py" ;;
  cutout)                                         SCRIPT="cutout.py" ;;
  knockout)                                       SCRIPT="knockout.py" ;;
  despeckle)                                      SCRIPT="despeckle.py" ;;
  *)
    echo "hextile-pipe: unknown tool '$TOOL'" >&2
    echo "tools: $TOOLS_HELP" >&2
    exit 2
    ;;
esac

PY="${ROOT}/matte/${SCRIPT}"
if [[ ! -f "$PY" ]]; then
  echo "hextile-pipe: missing matte script: $PY" >&2
  exit 1
fi

exec python3 "$PY" "$@"
