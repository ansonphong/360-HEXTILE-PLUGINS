#!/usr/bin/env bash
# Resolve the Pipe package root (pipe/ inside the 360-hextile plugin; never
# art-project cwd). Prefer host-injected env, then walk from this script.
# HEXTILE_PIPE_PLUGIN_ROOT names the Pipe root itself; host plugin-root
# variables name the 360-hextile plugin root, whose Pipe root is ./pipe.

_fp_plugin_root() {
  local root candidate
  for candidate in \
    "${HEXTILE_PIPE_PLUGIN_ROOT:-}" \
    "${FROG_PIPE_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/pipe}" \
    "${GROK_PLUGIN_ROOT:+${GROK_PLUGIN_ROOT}/pipe}" \
    "${PLUGIN_ROOT:+${PLUGIN_ROOT}/pipe}"
  do
    if [[ -n "$candidate" && -d "$candidate/matte" && -d "$candidate/scripts" ]]; then
      printf '%s\n' "$(cd "$candidate" && pwd)"
      return 0
    fi
  done

  # pipe/scripts/lib/plugin-root.sh → Pipe root is ../..
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  if [[ -d "$root/matte" && -d "$root/scripts" ]]; then
    printf '%s\n' "$root"
    return 0
  fi

  echo "360-hextile pipe: cannot resolve Pipe root (set HEXTILE_PIPE_PLUGIN_ROOT)" >&2
  return 1
}
