#!/usr/bin/env bash
# Resolve hextile-pipe plugin package root (never art-project cwd).
# Prefer host-injected env, then walk from this script's location.

_fp_plugin_root() {
  local root candidate
  for candidate in \
    "${HEXTILE_PIPE_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "${GROK_PLUGIN_ROOT:-}" \
    "${PLUGIN_ROOT:-}" \
    "${FROG_PIPE_PLUGIN_ROOT:-}"
  do
    if [[ -n "$candidate" && -d "$candidate/matte" && -d "$candidate/scripts" ]]; then
      printf '%s\n' "$(cd "$candidate" && pwd)"
      return 0
    fi
  done

  # scripts/lib/plugin-root.sh → plugin root is ../..
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  if [[ -d "$root/matte" && -d "$root/scripts" ]]; then
    printf '%s\n' "$root"
    return 0
  fi

  echo "hextile-pipe: cannot resolve plugin root (set HEXTILE_PIPE_PLUGIN_ROOT)" >&2
  return 1
}
