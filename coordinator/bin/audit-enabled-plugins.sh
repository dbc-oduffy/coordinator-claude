#!/bin/bash
# audit-enabled-plugins.sh — drift-check this repo's enabledPlugins against project_type / stack_tags.
#
# Lesson source: state/lessons.md:302 (claude-central, 2026-05-14) — project-scoped
# `enabledPlugins: true` entries drift silently across repos. Plugin installs write
# a `true` line into the active project's settings.json and never review it;
# cross-contamination compounds over months. This advisory is wired into
# /workweek-complete Step 4f.
#
# Reads:
#   .claude/settings.json              (enabledPlugins object)
#   coordinator.local.md frontmatter   (project_type, stack_tags)
#
# Writes:
#   stdout — one line per unjustified plugin entry; empty stdout = no drift.
#   exit 0 always (advisory; do not propagate to ceremony exit).
#
# Usage:
#   audit-enabled-plugins.sh [repo-root]
#   (default repo-root = pwd)

set -uo pipefail

REPO_ROOT="${1:-$(pwd)}"
SETTINGS="${REPO_ROOT}/.claude/settings.json"
LOCAL_MD="${REPO_ROOT}/coordinator.local.md"

if [[ ! -f "$SETTINGS" ]]; then
  # No settings.json → no enabledPlugins to audit. Silent no-op.
  exit 0
fi

# ---- Extract enabled plugin keys ----
# Each key is "<plugin>@<marketplace>"; we audit on the plugin segment.
if command -v jq >/dev/null 2>&1; then
  enabled_raw=$(jq -r '.enabledPlugins // {} | to_entries[] | select(.value == true) | .key' "$SETTINGS" 2>/dev/null)
else
  # jq absent — grep fallback. Less robust against multi-line JSON but works for
  # the canonical claude-code-written shape (one key per line).
  enabled_raw=$(grep -oE '"[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+"[[:space:]]*:[[:space:]]*true' "$SETTINGS" 2>/dev/null \
                | sed -E 's/^"([^"]+)".*/\1/')
fi

[[ -z "$enabled_raw" ]] && exit 0

# ---- Extract project_type + stack_tags from coordinator.local.md frontmatter ----
project_type=""
stack_tags=""
if [[ -f "$LOCAL_MD" ]]; then
  fm=$(awk '/^---$/{n++; if (n==2) exit; next} n==1' "$LOCAL_MD" 2>/dev/null)
  project_type=$(echo "$fm" | grep -m1 '^project_type:' | sed -E 's/^project_type:[[:space:]]*//' | tr -d '"' | tr -d "'" | xargs)
  # stack_tags can be inline `[a, b, c]` or block-list; normalize to space-separated.
  stack_tags=$(echo "$fm" | awk '
    /^stack_tags:/ { in_block = 1; sub(/^stack_tags:[[:space:]]*/, ""); print; next }
    in_block && /^[[:space:]]*-[[:space:]]*/ { sub(/^[[:space:]]*-[[:space:]]*/, ""); print; next }
    in_block && /^[^[:space:]]/ { in_block = 0 }
  ' | tr -d '[]"' | tr ',' ' ' | tr '\n' ' ')
fi

# ---- Plugin → justification rule table ----
# Returns 0 if the plugin is justified by the repo's project_type / stack_tags, 1 otherwise.
# Tuning surface — extend as new plugins land or drift cases surface.
is_justified() {
  local plugin="$1"
  local pt="$2"
  local tags="$3"
  # Meta short-circuit: ~/.claude is the orchestration brain where cross-cutting
  # work happens; all plugins are intentionally enabled here per global CLAUDE.md.
  # Audit on meta is a no-op by design.
  [[ "$pt" == "meta" ]] && return 0
  case "$plugin" in
    # Universal — always justified
    coordinator|coordinator-claude|deep-research|deep-research-claude)
      return 0 ;;
    # UE / game development
    game-dev|holodeck|holodeck-control|holodeck-docs)
      [[ " $tags " == *" unreal-engine "* || " $tags " == *" game "* || "$pt" == "game" ]] && return 0
      return 1 ;;
    # Web
    web-dev)
      [[ " $tags " == *" web "* || "$pt" == "web" ]] && return 0
      return 1 ;;
    # Data science
    data-science)
      [[ " $tags " == *" data-science "* || "$pt" == "data-science" ]] && return 0
      return 1 ;;
    # MCP development
    mcp-server-dev)
      [[ " $tags " == *" mcp-server "* || " $tags " == *" mcp-plugin "* ]] && return 0
      return 1 ;;
    # Plugin development (meta-work on plugins themselves).
    # Note: project_type=meta is handled by the short-circuit above; the only
    # remaining justification path here is the claude-plugin stack tag.
    plugin-dev)
      [[ " $tags " == *" claude-plugin "* ]] && return 0
      return 1 ;;
    # Unknown plugin — surface for triage rather than silently OK.
    *)
      return 1 ;;
  esac
}

# ---- Audit each enabled plugin ----
findings=""
while IFS= read -r key; do
  [[ -z "$key" ]] && continue
  plugin="${key%@*}"
  marketplace="${key#*@}"
  if ! is_justified "$plugin" "$project_type" "$stack_tags"; then
    findings+="  - ${key}: enabled, but not justified by project_type='${project_type:-unset}' stack_tags='${stack_tags:-unset}'"$'\n'
  fi
done <<< "$enabled_raw"

if [[ -n "$findings" ]]; then
  echo "enabledPlugins drift advisory (repo: ${REPO_ROOT}):"
  printf "%s" "$findings"
  echo "  Full uninstall = (1) remove enabledPlugins line from every project's settings.json,"
  echo "                   (2) remove entry from ~/.claude/plugins/installed_plugins.json,"
  echo "                   (3) rm -rf ~/.claude/plugins/cache/<marketplace>/<plugin>/."
fi

exit 0
