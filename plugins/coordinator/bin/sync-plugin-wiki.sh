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
#   4 — asymmetric drift: bundled file is newer than dev-side source (suspected write-direction trap); use --force to overwrite
#
# Missing-source policy: if a plugin file references docs/wiki/<name>.md but
# <name>.md is absent from the dev-side wiki, warn and continue. That is a
# doc-link issue (handled by the doc-link-checker), not a sync issue.
#
# Asymmetry policy: dev-side is the source of truth. If the bundled file
# diverges AND its mtime is newer than the dev-side source, that suggests an
# executor wrote to the bundled tree directly (write-direction trap). Default
# behaviour is to escalate (exit 4) rather than silently overwrite the
# bundled-side edit. Use --force to overwrite (CI / automated runs).
#
# Flags:
#   --check-only  report drift without writing; exit 0 if in sync, 3 if drift detected
#   --force       overwrite bundled-side asymmetric edits without escalating
#   --quiet       suppress per-file output

set -euo pipefail

PLUGIN_ROOT="${HOME}/.claude/plugins/coordinator-claude/coordinator"
DEV_WIKI="${HOME}/.claude/docs/wiki"
BUNDLED_WIKI="${PLUGIN_ROOT}/docs/wiki"

# Self-claim: source coordinator session lib for touch tracking.
# Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
# Best-effort — no-op if lib absent or no active session.
_CS_LIB="${PLUGIN_ROOT}/lib/coordinator-session.sh"
if [[ -f "$_CS_LIB" ]]; then
    # shellcheck source=/dev/null
    source "$_CS_LIB"
    _CS_LIB_LOADED=1
else
    _CS_LIB_LOADED=0
fi

_cs_claim_if_session() {
    [[ "$_CS_LIB_LOADED" -eq 0 ]] && return 0
    local _sids
    _sids="$(cs_live_session_ids 2>/dev/null)" || return 0
    local _sid_count
    if [[ -z "$_sids" ]]; then _sid_count=0
    else _sid_count=$(echo "$_sids" | wc -l | tr -d ' \n'); fi
    if [[ "$_sid_count" -eq 0 ]]; then
        echo "coordinator-session: no active session found — skipping self-claim for $1" >&2
        return 0
    fi
    if [[ "$_sid_count" -gt 1 ]]; then
        echo "coordinator-session: ${_sid_count} live sessions (ambiguous) — skipping self-claim for $1" >&2
        return 0
    fi
    local _sid
    _sid=$(echo "$_sids" | head -1)
    local _sdir
    _sdir=$(_cs_session_dir "$_sid" 2>/dev/null) || return 0
    cs_atomic_dedup_append "${_sdir}/touched.txt" "$1" 2>/dev/null || return 0
}

CHECK_ONLY=0
QUIET=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=1 ;;
    --force) FORCE=1 ;;
    --quiet) QUIET=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
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
PLACEHOLDER_RE='^(foo|bar|baz|qux|example|name|your-wiki-name|wiki-name)$'
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
  | sort -u \
  | grep -vE "$PLACEHOLDER_RE"
)

if [ "${#names[@]}" -eq 0 ]; then
  log "No docs/wiki/ references found in plugin files. Nothing to sync."
  exit 0
fi

mkdir -p "$BUNDLED_WIKI"

drift=0
synced=0
missing=0
asymmetric=0
asymmetric_files=()
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
    # Asymmetry check: bundled exists, content differs, and bundled mtime is
    # newer than source → suspect write-direction trap (executor wrote bundled
    # directly). Escalate instead of overwriting silently.
    if [ -f "$dst" ] && [ "$dst" -nt "$src" ] && [ "$FORCE" -eq 0 ]; then
      asymmetric=1
      asymmetric_files+=("$name.md")
      log "ASYMMETRIC DRIFT: $name.md — bundled is newer than dev-side source"
      log "  src: $src"
      log "  dst: $dst"
      log "  Likely cause: executor wrote bundled wiki directly (write-direction trap)."
      log "  Required: copy bundled → dev-side (the authoring direction), then re-run sync."
      log "  Override: --force overwrites bundled with dev-side."
      continue
    fi
    if [ "$CHECK_ONLY" -eq 1 ]; then
      # Per-file delta summary — defends against the CRLF/LF blind spot where
      # an agent reports "in sync" but the byte-stream differs. Line-by-line
      # change count makes content-drift vs line-ending-drift visible at a
      # glance; pure CRLF flips show as N changes on N-line files.
      changes=$(diff "$src" "$dst" 2>/dev/null | grep -cE '^[<>]' || true)
      log "DRIFT: $name.md (${changes} line-level differences)"
    else
      cp "$src" "$dst"
      log "synced: $name.md"
      synced=$((synced + 1))
      _cs_claim_if_session "$dst"
    fi
  fi
done

if [ "$asymmetric" -gt 0 ]; then
  log ""
  log "ESCALATION: ${asymmetric} bundled wiki file(s) newer than dev-side source."
  log "Files: ${asymmetric_files[*]}"
  log "Resolve direction-of-truth before syncing. See docs/wiki/plugin-extraction-and-distribution.md § Plugin-Bundled Wiki Authoring Direction."
  exit 4
fi

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
