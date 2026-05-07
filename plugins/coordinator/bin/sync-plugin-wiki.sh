#!/usr/bin/env bash
# sync-plugin-wiki.sh — mirror plugin-cited wiki files from dev-side authoring tree
# into the plugin-bundled docs/wiki/ so marketplace consumers can resolve them.
#
# Source of truth: ~/.claude/docs/wiki/<name>.md (dev-side authoring).
# Sync target: ~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/<name>.md.
#
# Wiki files to sync are auto-discovered by grepping plugin files for
# `docs/wiki/<name>.md` references. New demotes pick up automatically.
#
# Exit codes:
#   0 — sync OK (no changes OR changes applied; missing sources warned, not failed)
#   2 — usage error / unexpected
#   3 — drift detected (only with --check-only)
#
# Missing-source policy: if a plugin file references docs/wiki/<name>.md but
# <name>.md is absent from the dev-side wiki, warn and continue. That is a
# doc-link issue (handled by the doc-link-checker), not a sync issue.
#
# Flags:
#   --check-only  report drift without writing; exit 0 if in sync, 3 if drift detected
#   --quiet       suppress per-file output

set -euo pipefail

PLUGIN_ROOT="${HOME}/.claude/plugins/coordinator-claude/coordinator"
DEV_WIKI="${HOME}/.claude/docs/wiki"
BUNDLED_WIKI="${PLUGIN_ROOT}/docs/wiki"

CHECK_ONLY=0
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=1 ;;
    --quiet) QUIET=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

log() { [ "$QUIET" -eq 1 ] || echo "$@"; }

# Discover wiki names cited from plugin files. Strategy: grep for the literal
# substring `docs/wiki/` in plugin files (CLAUDE.md, README, agents/, commands/,
# skills/, snippets/, pipelines/, hooks/), then extract the wiki filename token.
mapfile -t names < <(
  grep -rhoE 'docs/wiki/[a-zA-Z0-9_-]+\.md' \
    "${PLUGIN_ROOT}/CLAUDE.md" \
    "${PLUGIN_ROOT}/README.md" \
    "${PLUGIN_ROOT}/em-operating-model.md" \
    "${PLUGIN_ROOT}/capability-catalog.md" \
    "${PLUGIN_ROOT}/agents" \
    "${PLUGIN_ROOT}/commands" \
    "${PLUGIN_ROOT}/skills" \
    "${PLUGIN_ROOT}/snippets" \
    "${PLUGIN_ROOT}/pipelines" \
    "${PLUGIN_ROOT}/hooks" \
    --include='*.md' --include='*.sh' \
    --exclude='*.test.js' \
    2>/dev/null \
  | sed -E 's|^docs/wiki/||; s|\.md$||' \
  | sort -u
)

if [ "${#names[@]}" -eq 0 ]; then
  log "No docs/wiki/ references found in plugin files. Nothing to sync."
  exit 0
fi

mkdir -p "$BUNDLED_WIKI"

drift=0
synced=0
missing=0
for name in "${names[@]}"; do
  src="${DEV_WIKI}/${name}.md"
  dst="${BUNDLED_WIKI}/${name}.md"

  if [ ! -f "$src" ]; then
    log "WARN: $name.md referenced by plugin file but absent from dev-side wiki ($src)"
    missing=$((missing + 1))
    continue
  fi

  if [ ! -f "$dst" ] || ! cmp -s "$src" "$dst"; then
    drift=1
    if [ "$CHECK_ONLY" -eq 1 ]; then
      log "DRIFT: $name.md"
    else
      cp "$src" "$dst"
      log "synced: $name.md"
      synced=$((synced + 1))
    fi
  fi
done

if [ "$missing" -gt 0 ]; then
  log "Note: $missing referenced wiki(s) missing from dev-side. doc-link-checker handles broken links separately."
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  if [ "$drift" -eq 1 ]; then
    log "Drift detected. Run without --check-only to apply."
    exit 3
  fi
  log "Plugin-bundled wiki in sync (${#names[@]} entries checked)."
  exit 0
fi

log "Plugin-bundled wiki: ${synced} synced, ${#names[@]} entries total."
exit 0
