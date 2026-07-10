#!/usr/bin/env bash
# sync-plugin-wiki.sh — verify no plugin-doctrine wiki accidentally has a dev-side mirror.
#
# Spec backlink: docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md § Phase 4
#
# Under Option B (adopted 2026-05-15), plugin-doctrine wikis live ONLY at
# <plugin>/docs/wiki/<name>.md. There is no dev-side authoring copy. This
# script confirms the invariant: for each wiki name cited from plugin files,
# check that no mirror exists at ~/.claude/docs/wiki/<name>.md.
#
# If a dev-side mirror is found, the single-tree invariant is broken — the
# write-direction trap has been re-introduced. Exit 5 with a structured error
# message naming both paths, their mtimes, and a remediation instruction.
#
# Exit codes:
#   0 — clean: no dev-side mirrors found for any plugin-cited wiki
#   2 — usage error / unexpected
#   3 — drift detected (only with --check-only, reserved for future use)
#   5 — dev-side mirror of plugin-doctrine wiki detected; single-tree invariant broken
#
# Missing-bundled policy: if a plugin file references docs/wiki/<name>.md but
# <name>.md is absent from the bundled wiki, warn and continue. That is a
# doc-link issue (handled by the doc-link-checker), not a mirror issue.
#
# Flags:
#   --check-only  report status without exiting non-zero on warnings; exit 5 still fires on mirrors
#   --quiet       suppress per-file output
#   COORDINATOR_OVERRIDE_WIKI_MIRROR=1  suppress exit-5 and warn instead (rare-use; e.g., authoring
#                 a dev-side wiki that genuinely should not exist in plugin tree)

set -euo pipefail

# Resolve coordinator content root via the portable resolver (CLAUDE_PLUGIN_ROOT →
# COORDINATOR_ROOT → registry clone → versioned cache → flat layout).
_rcc_resolver="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/resolve-coordinator-clone.sh"
if [[ -f "$_rcc_resolver" ]]; then
    # shellcheck source=../lib/resolve-coordinator-clone.sh
    source "$_rcc_resolver"
fi
# Defensive fallback: if resolver absent or COORDINATOR_CONTENT_ROOT still empty, use flat layout.
if [[ -z "${COORDINATOR_CONTENT_ROOT:-}" ]]; then
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
    echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
    exit 1
  fi
  COORDINATOR_CONTENT_ROOT="$_doe_root/coordinator"
fi

PLUGIN_ROOT="$COORDINATOR_CONTENT_ROOT"
DEV_WIKI="${HOME}/.claude/docs/wiki"
BUNDLED_WIKI="${PLUGIN_ROOT}/docs/wiki"

QUIET=0
for arg in "$@"; do
  case "$arg" in
    --check-only) ;;  # kept for caller compatibility; new semantics always report-only (no writes to avoid)
    --quiet) QUIET=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^#[[:space:]]\{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

log() { [ "$QUIET" -eq 1 ] || echo "$@"; }

# Discover wiki names cited from plugin files. Strategy: grep for the literal
# substring `docs/wiki/` in plugin files (CLAUDE.md, README, agents/, commands/,
# skills/, snippets/, pipelines/, hooks/), then extract the wiki filename token.
#
# Placeholder filter: names matching common example/placeholder tokens (foo, bar,
# baz, qux, example, name, your-wiki-name) are filtered out — these appear in
# illustrative tables/code-fences inside snippets and agent prompts and are not
# real wiki citations.
# Cross-repo citation false-positives: held-out-slice-sealing-pattern.md and lfs-coordinator-auto-push-merge.md
# use "project-rag-ue-addon/docs/wiki/<name>.md" source attribution. The grep extracts only the suffix
# fragment, making these look like plugin-internal citations when they are not.
PLACEHOLDER_RE='^(foo|bar|baz|qux|example|name|your-wiki-name|wiki-name|held-out-slice-sealing-doctrine|lfs-gitattributes-discipline)$'
names=()
while IFS= read -r line; do names+=("$line"); done < <(
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
    "${BUNDLED_WIKI}" \
    --include='*.md' --include='*.sh' \
    --exclude='*.test.js' \
    2>/dev/null \
  | sed -E 's|^docs/wiki/||; s|\.md$||' \
  | sort -u \
  | grep -vE "$PLACEHOLDER_RE"
)

if [ "${#names[@]}" -eq 0 ]; then
  log "No docs/wiki/ references found in plugin files. Nothing to validate."
  exit 0
fi

mirror_count=0
mirror_files=()
missing_bundled=0
validated=0

for name in "${names[@]}"; do
  dev="${DEV_WIKI}/${name}.md"
  bundled="${BUNDLED_WIKI}/${name}.md"

  # Check for dev-side mirror — this is the primary invariant check
  if [ -f "$dev" ]; then
    mirror_count=$((mirror_count + 1))
    mirror_files+=("${name}.md")
    dev_mtime=$(stat -c "%y" "$dev" 2>/dev/null || stat -f "%Sm" "$dev" 2>/dev/null || echo "unknown")
    bundled_mtime="(not present)"
    if [ -f "$bundled" ]; then
      bundled_mtime=$(stat -c "%y" "$bundled" 2>/dev/null || stat -f "%Sm" "$bundled" 2>/dev/null || echo "unknown")
    fi
    if [ "${COORDINATOR_OVERRIDE_WIKI_MIRROR:-0}" = "1" ]; then
      log "WARN (override): dev-side mirror exists for $name.md — single-tree invariant suppressed by COORDINATOR_OVERRIDE_WIKI_MIRROR=1"
      log "  dev-side mirror: $dev (mtime: $dev_mtime)"
      log "  bundled:         $bundled (mtime: $bundled_mtime)"
    else
      log "MIRROR DETECTED: $name.md — dev-side mirror breaks the single-tree invariant"
      log "  dev-side mirror: $dev"
      log "  bundled (canonical): $bundled"
      log "  dev-side mtime:  $dev_mtime"
      log "  bundled mtime:   $bundled_mtime"
      log "  Remediation: bundled is canonical; if dev-side mirror contains intentional content, port it to bundled and delete dev-side."
    fi
    continue
  fi

  # Check bundled copy exists (doc-link health, warn only)
  if [ ! -f "$bundled" ]; then
    log "WARN: $name.md referenced by plugin file but absent from bundled wiki ($bundled)"
    missing_bundled=$((missing_bundled + 1))
    continue
  fi

  validated=$((validated + 1))
done

if [ "$mirror_count" -gt 0 ] && [ "${COORDINATOR_OVERRIDE_WIKI_MIRROR:-0}" != "1" ]; then
  log ""
  log "SINGLE-TREE INVARIANT BROKEN: ${mirror_count} plugin-doctrine wiki(s) have dev-side mirrors."
  log "Files: ${mirror_files[*]}"
  log "Doctrine: plugin-doctrine wikis live ONLY at <plugin>/docs/wiki/<name>.md."
  log "See docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md § Phase 4."
  exit 5
fi

if [ "$missing_bundled" -gt 0 ]; then
  log "Note: $missing_bundled referenced wiki(s) missing from bundled tree. doc-link-checker handles broken links separately."
fi

log "Plugin-bundled wiki: clean (${validated} validated, ${missing_bundled} missing-bundled warnings)."
exit 0
