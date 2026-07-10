#!/usr/bin/env bash
# learn-lessons-roots.sh — emit every on-disk repo root that learn-lessons should
# process ON THIS MACHINE, one per line, in a stable de-duplicated order.
#
# Contract:
#   1. $CLAUDE_HOME (default $HOME/.claude) is always the first line — the meta-repo
#      is always a lessons source, unconditionally, before any registry call.
#   2. Each machine-local repos.* key that resolves to an existing directory is
#      included, EXCLUDING publish-target/mirror repos.
#   3. Optional supplemental roots from the BEGIN/END learn-lessons-roots sentinel in
#      state/learn-lessons-config.md are appended (empty by default after C4).
#   4. The output list is de-duplicated; every emitted line is an existing directory.
#   5. Exit 0 always — graceful degradation if machine-local is absent or returns
#      nothing (OSS fresh-install: emits exactly $CLAUDE_HOME).
#
# Spec backlink: docs/plans/2026-06-19-portability-tracked-per-machine-config.md § C1
# OSS requirement: works for any coordinator-claude installer with zero registered repos.
#
# set -uo pipefail — NOT set -e. A failed machine-local lookup must not abort the emit.
# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
MACHINE_LOCAL="${CLAUDE_HOME}/bin/machine-local"

# ---------------------------------------------------------------------------
# Accumulate candidate roots into a temp file to de-duplicate later.
# Using a tempfile (rather than an array) avoids bash-4-only constructs.
# ---------------------------------------------------------------------------
# mktemp fallback uses $$ (PID) + $RANDOM for uniqueness. The fallback path is best-effort
# and not atomic-safe under concurrent invocations — if mktemp is failing, the system has
# larger problems. The trap below ensures cleanup on exit.
_tmpfile="$(mktemp 2>/dev/null || echo "/tmp/llroots_$$_${RANDOM}")"
_pub_tmpfile="$(mktemp 2>/dev/null || echo "/tmp/llpub_$$_${RANDOM}")"
trap 'rm -f "$_tmpfile" "$_pub_tmpfile"' EXIT

# 1. $CLAUDE_HOME — always first, unconditional.
printf '%s\n' "$CLAUDE_HOME" >> "$_tmpfile"

# ---------------------------------------------------------------------------
# 2. Build publish-target exclusion set.
#    publish.targets lines: name|type|source|dest  — dest (field 4) is the
#    outward mirror directory; never a lessons source.
#    If machine-local is absent or publish.targets is unreadable/empty, fall
#    back to a hardcoded denylist of registry KEYS (harmless no-op for OSS
#    installers where these keys are simply absent).
# ---------------------------------------------------------------------------
_ml_ok=false
if [ -x "$MACHINE_LOCAL" ]; then
  _ml_ok=true
fi

if $_ml_ok; then
  # Read publish.targets array; each line is name|type|source|dest.
  "$MACHINE_LOCAL" get "publish.targets" 2>/dev/null \
    | awk -F'|' 'NF>=4{print $4}' \
    >> "$_pub_tmpfile" || true
fi

# Hardcoded denylist of REGISTRY KEYS (not paths) for OSS-installer safety —
# iterated inline in _is_publish_target (see below) to avoid word-split fragility.
# On a machine where these keys exist, their resolved paths are also caught by the
# publish.targets check above; this is belt-and-suspenders when publish.targets is
# unreadable. Harmless no-op for OSS installers where the keys are simply absent.

# ---------------------------------------------------------------------------
# Helper: returns 0 if a path matches any publish-target or denylist.
# ---------------------------------------------------------------------------
_is_publish_target() {
  local candidate="$1"
  # Check against publish.targets paths (if any were collected).
  if [ -s "$_pub_tmpfile" ]; then
    if grep -qxF "$candidate" "$_pub_tmpfile" 2>/dev/null; then
      return 0
    fi
  fi
  # Fallthrough: check denylist keys by resolving them (if machine-local available).
  if $_ml_ok; then
    local k
    for k in coordinator_claude deep_research_claude; do
      local deny_path
      deny_path="$("$MACHINE_LOCAL" get "repos.$k" 2>/dev/null || true)"
      if [ -n "$deny_path" ] && [ "$deny_path" = "$candidate" ]; then
        return 0
      fi
    done
  fi
  return 1
}

# ---------------------------------------------------------------------------
# 2. Registry repos — enumerate via `machine-local keys | grep '^repos\.'`
#    then resolve each with `machine-local get`.
# ---------------------------------------------------------------------------
if $_ml_ok; then
  while IFS= read -r key; do
    [ -z "$key" ] && continue
    resolved="$("$MACHINE_LOCAL" get "$key" 2>/dev/null || true)"
    [ -z "$resolved" ] && continue
    [ -d "$resolved" ] || continue       # skip-absent: silently skip non-existent dirs
    if _is_publish_target "$resolved"; then
      continue                           # exclude publish-target/mirror repos
    fi
    printf '%s\n' "$resolved" >> "$_tmpfile"
  done < <("$MACHINE_LOCAL" keys 2>/dev/null | grep '^repos\.' || true)
fi

# ---------------------------------------------------------------------------
# 3. Optional supplemental roots from state/learn-lessons-config.md sentinel.
#    Empty by default after C4 — this is an escape hatch for non-registry roots.
# ---------------------------------------------------------------------------
# learn-lessons-config is empty-by-default (learn-lessons-config-update.sh inert); stale-read accepted no-op — migrate config to DoE when class becomes active
_config="$(coordinator_state_root --central)/learn-lessons-config.md"
if [ -f "$_config" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    [ -d "$line" ] && printf '%s\n' "$line" >> "$_tmpfile" || true
  done < <(sed -n '/BEGIN learn-lessons-roots/,/END learn-lessons-roots/p' "$_config" \
           2>/dev/null | grep -E '^- ' | sed 's/^- //' || true)
fi

# ---------------------------------------------------------------------------
# 4. De-duplicate and emit, PRESERVING INSERTION ORDER (NOT sorted) so the
#    contract "$CLAUDE_HOME is the first line" holds — sort -u would reorder it.
#    awk seen-set keeps the first occurrence of each line and drops later dupes.
# ---------------------------------------------------------------------------
awk '!seen[$0]++' "$_tmpfile"

exit 0
