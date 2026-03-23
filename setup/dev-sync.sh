#!/bin/bash
# dev-sync.sh — Sync coordinator-claude plugin source to Claude Code's cache
#
# For plugin developers: run after editing plugin files to make changes
# take effect without restarting Claude Code or bumping versions.
#
# Claude Code caches plugins by version. Edits to source files don't
# propagate to the cache automatically. This script bridges that gap.
#
# Usage:
#   bash setup/dev-sync.sh              # sync all plugins
#   bash setup/dev-sync.sh coordinator   # sync one plugin
#
# Requires: the plugins were previously installed via setup/install.sh
# (so the cache directory structure exists).

set -euo pipefail

PLUGINS_DIR="$HOME/.claude/plugins"
CACHE_DIR="$PLUGINS_DIR/cache/coordinator-claude"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/plugins"

# The marketplace name used during installation
MARKETPLACE="coordinator-claude"

# Optional: sync only a specific plugin
TARGET="${1:-}"

sync_plugin() {
  local name="$1"
  local src="$SOURCE_DIR/$name"

  if [[ ! -d "$src" ]]; then
    echo "  SKIP: $name (source dir not found)"
    return
  fi

  # Read version from plugin.json
  local plugin_json="$src/.claude-plugin/plugin.json"
  if [[ ! -f "$plugin_json" ]]; then
    echo "  SKIP: $name (no .claude-plugin/plugin.json)"
    return
  fi

  local version=""
  if command -v jq &>/dev/null; then
    version=$(jq -r '.version' "$plugin_json" 2>/dev/null || true)
  fi
  if [[ -z "$version" ]]; then
    version=$(sed -n 's/.*"version"\s*:\s*"\([^"]*\)".*/\1/p' "$plugin_json" | head -1)
  fi

  if [[ -z "$version" ]]; then
    echo "  SKIP: $name (couldn't read version)"
    return
  fi

  local cache_target="$CACHE_DIR/$name/$version"

  if [[ ! -d "$cache_target" ]]; then
    echo "  NEW:  $name ($version) — creating cache dir"
    mkdir -p "$cache_target"
  fi

  # Preserve .orphaned_at marker if present
  local orphaned_at=""
  if [[ -f "$cache_target/.orphaned_at" ]]; then
    orphaned_at=$(cat "$cache_target/.orphaned_at")
  fi

  # Remove old cache contents (except .orphaned_at) and copy fresh
  find "$cache_target" -mindepth 1 -maxdepth 1 ! -name '.orphaned_at' -exec rm -rf {} +
  cp -r "$src/." "$cache_target/"

  # Restore .orphaned_at if it existed
  if [[ -n "$orphaned_at" ]]; then
    echo "$orphaned_at" > "$cache_target/.orphaned_at"
  fi

  local file_count
  file_count=$(find "$cache_target" -type f | wc -l)
  echo "  SYNC: $name ($version) — $file_count files"
}

echo "dev-sync: $SOURCE_DIR → cache"
echo ""

if [[ -n "$TARGET" ]]; then
  sync_plugin "$TARGET"
else
  for dir in "$SOURCE_DIR"/*/; do
    [[ -d "$dir" ]] || continue
    sync_plugin "$(basename "$dir")"
  done
fi

echo ""
echo "Done. Changes take effect on next Claude Code session (or next hook invocation for hooks)."
