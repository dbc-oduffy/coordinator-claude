#!/usr/bin/env bash
# hooks/scripts/check-plugin-update-currency.sh — SessionStart boot hook.
#
# Purpose: passive update-available notification for installed coordinator-family
# plugins (coordinator + standalone deep-research). Compares each plugin's locally
# installed SHA (version.txt) against its own latest published GitHub release tag.
# Emits a one-line stdout nag — naming that plugin's own update action — when the
# install is behind or differs; stays silent when current or source_is_live.
# Throttled to one network check per 3 days per plugin via a per-plugin sentinel.
#
# Spec backlink: docs/plans/2026-06-01-boot-currency-notification-hook.md § C3
#   + spinoff state/handoffs/2026-06-01_122922_deep-research-currency-notification.md
#     (Leg 1: deep-research loop entry; Leg 2 option (a): per-plugin honest action).
#
# Output contract (SessionStart hook — stdout IS the additionalContext):
#   current / source_is_live : no output (silent)
#   behind                   : stdout one-liner naming /coordinator-update
#   differs                  : stdout one-liner naming /coordinator-update
#   offline                  : stdout note (low-key, awareness-only; see note below)
#
# NOTE — additionalContext validation outcome (the Staff Engineer/prior-art SILENT):
#   The {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}
#   JSON form is documented in our corpus ONLY for PreToolUse deny decisions. For
#   SessionStart hooks, plain stdout IS the proven mechanism: check-dropped-tracked-files.sh
#   and project-orientation.sh both confirm "Output (raw text) becomes additionalContext
#   injected into the session." (claude-code-platform-gotchas.md § PreToolUse deny).
#   Decision: FELL BACK TO STDOUT for all branches (plain stdout is the proven path for
#   SessionStart context injection). The JSON form was not validated — stdout is sufficient
#   and correct per the existing hook corpus. Offline branch uses plain stdout.
#
# Throttle sentinel: ${XDG_STATE_HOME:-$HOME/.claude}/.cache/coordinator-currency-check
#   Each line: <plugin> <ISO-date> <last-status>
#   CRITICAL (BOOT-CURRENCY-THROTTLE): offline results do NOT write the 3-day timestamp.
#   An offline result either skips the sentinel write (next boot retries the live fetch)
#   or writes a short-TTL marker distinct from the 3-day current/behind cadence.
#   This prevents a transient offline boot from silently disabling the check for 3 days.
#
# Per-plugin loop: coordinator + deep-research (standalone). Each entry checks its
# own release repo and renders its own update action (_action_hint_for). Adding a
# further plugin = one PLUGINS_TO_CHECK entry + one _action_hint_for case arm.
#
# Matcher: "startup" only (NOT "startup|compact") — an update notification is
# acted on between sessions (you update, then restart), not mid-flow. The 3-day
# throttle already bounds over-nagging; compact fires mid-work where the nag adds
# interruption without signal. → docs/plans/2026-06-01-boot-currency-notification-hook.md
# § Design decisions (the Staff Engineer F3).
#
# Exit: 0 always.
# set -e omitted intentionally — must not abort on probe non-zero.
set -uo pipefail

# ---------------------------------------------------------------------------
# Bootstrap: resolve lib location and source the C2 helper
# ---------------------------------------------------------------------------
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The hook lives under hooks/scripts/; the lib lives under lib/
PLUGIN_ROOT="$(cd "${HOOK_DIR}/../.." && pwd)"
RELEASE_CURRENCY_LIB="${PLUGIN_ROOT}/lib/release-currency.sh"

if [[ ! -f "$RELEASE_CURRENCY_LIB" ]]; then
    # Non-fatal: if the lib is missing we cannot check; exit silently.
    exit 0
fi
# shellcheck source=../../lib/release-currency.sh
source "$RELEASE_CURRENCY_LIB"

# ---------------------------------------------------------------------------
# Throttle sentinel
# ---------------------------------------------------------------------------
# Security (sec-audit MEDIUM 2026-06-01): XDG_STATE_HOME is env-controlled and
# feeds a file-write base path. Honor it only when absolute and free of '..'
# traversal segments; otherwise fall back to $HOME/.claude (also the unset
# default). This preserves the pinned `${XDG_STATE_HOME:-$HOME/.claude}/.cache`
# path while rejecting a hostile XDG_STATE_HOME redirecting writes out of tree.
_xdg_base="${XDG_STATE_HOME:-}"
if [[ -n "$_xdg_base" && ( "$_xdg_base" != /* || "$_xdg_base" == *..* ) ]]; then
    _xdg_base=""
fi
SENTINEL_DIR="${_xdg_base:-$HOME/.claude}/.cache"
SENTINEL_FILE="${SENTINEL_DIR}/coordinator-currency-check"

mkdir -p "$SENTINEL_DIR" 2>/dev/null && chmod 0700 "$SENTINEL_DIR" 2>/dev/null || true

# Helpers: read/write per-plugin lines in the sentinel
# Line format: <plugin> <ISO-date> <last-status>
_sentinel_read() {
    local plugin="$1"
    if [[ ! -f "$SENTINEL_FILE" ]]; then return 1; fi
    # Literal first-field match (sec-audit INFO 2026-06-01): awk '$1==p' is a
    # fixed-string compare, future-safe against a plugin name with regex-special
    # chars that a `grep "^${plugin} "` BRE would mis-match.
    # tail -1: last-writer-wins on the rare concurrent-boot race (two boots interleaving
    # the read→mv in _sentinel_write); the atomic mv makes this degenerate. (code-reviewer F11)
    awk -v p="$plugin" '$1==p' "$SENTINEL_FILE" 2>/dev/null | tail -1
}

_sentinel_write() {
    local plugin="$1"
    local date_str="$2"
    local status_str="$3"
    local tmp
    tmp="$(mktemp "${SENTINEL_FILE}.tmp.XXXXXX" 2>/dev/null)" || return 0
    chmod 0600 "$tmp" 2>/dev/null || true   # sec-audit LOW 2026-06-01: no world-read on the sentinel
    # Remove old line for this plugin, append new line (awk literal match — sec-audit INFO)
    { awk -v p="$plugin" '$1!=p' "$SENTINEL_FILE" 2>/dev/null || true; } > "$tmp"
    printf '%s %s %s\n' "$plugin" "$date_str" "$status_str" >> "$tmp"
    # mv failure (cross-device EXDEV / permission): sentinel not written; the temp is
    # removed and the next boot retries the live fetch — acceptable for an advisory-only,
    # throttle-only sentinel (same effect as the offline case). (code-reviewer F8)
    mv -f "$tmp" "$SENTINEL_FILE" 2>/dev/null || rm -f "$tmp"
}

_days_since() {
    # Returns the number of whole days since a date string (ISO-8601 YYYY-MM-DD).
    # Uses python3 / python / py for portability; returns 99 on failure (force recheck).
    local date_str="$1"
    local py_bin=""
    if   command -v python3 &>/dev/null; then py_bin="python3"
    elif command -v python  &>/dev/null; then py_bin="python"
    elif command -v py      &>/dev/null; then py_bin="py"
    fi
    if [[ -z "$py_bin" ]]; then echo 99; return; fi
    $py_bin -c "
import sys
from datetime import date
try:
    then = date.fromisoformat(sys.argv[1])
    print((date.today() - then).days)
except Exception:
    print(99)
" "$date_str" 2>/dev/null || echo 99
}

# _action_hint_for <plugin> → prints the honest update action for that plugin.
# coordinator installs are reconciled by the shipped /coordinator-update verb. A
# standalone deep-research install has NO such verb (2026-06-01 spinoff, Leg 2
# option (a)) — its honest action is re-running its own installer, never
# /coordinator-update. A new plugin adds one case arm here alongside its loop entry.
_action_hint_for() {
    case "$1" in
        coordinator)   printf 'run `/coordinator-update` to review' ;;
        deep-research) printf 're-run the deep-research install to update' ;;
        *)             printf 'review your install for updates' ;;
    esac
}

# ---------------------------------------------------------------------------
# Deep-research standalone install-root (2026-06-01 spinoff, Leg 1).
# A standalone deep-research-claude install lives at ~/.claude/plugins/deep-research-claude
# (mirrors coordinator-claude's install location, where version.txt is planted).
# Env-overridable for non-standard installs / tests. When absent (no version.txt),
# release_currency_probe returns source_is_live and the entry is silently inert —
# per-plugin independence: a missing standalone deep-research never affects the
# coordinator check, and vice-versa.
# ---------------------------------------------------------------------------
DEEP_RESEARCH_INSTALL_ROOT="${DEEP_RESEARCH_INSTALL_ROOT:-${HOME:-}/.claude/plugins/deep-research-claude}"

# ---------------------------------------------------------------------------
# Per-plugin check list. Format: "plugin_name|owner/repo|install_root"
# Each plugin checks its own release repo; the update action is per-plugin
# (see _action_hint_for). Adding a plugin = one entry here + one case arm above.
# ---------------------------------------------------------------------------
declare -a PLUGINS_TO_CHECK=(
    "coordinator|dbc-oduffy/coordinator-claude|${PLUGIN_ROOT}"
    "deep-research|dbc-oduffy/deep-research-claude|${DEEP_RESEARCH_INSTALL_ROOT}"
)

# ---------------------------------------------------------------------------
# Today's date (ISO-8601, used for sentinel writes)
# ---------------------------------------------------------------------------
# date failure → TODAY="" → sentinel writes are skipped (guarded at each write site) →
# throttle inactive, live fetch retries each boot (safe degradation). (code-reviewer F9)
TODAY="$(date -u +%Y-%m-%d 2>/dev/null)" || TODAY=""

# ---------------------------------------------------------------------------
# Process each plugin
# ---------------------------------------------------------------------------
for plugin_entry in "${PLUGINS_TO_CHECK[@]}"; do
    # Parse the entry
    IFS='|' read -r plugin_name owner_repo install_root <<< "$plugin_entry"

    # ------------------------------------------------------------------
    # Throttle check: read existing sentinel line
    # ------------------------------------------------------------------
    sentinel_line="$(_sentinel_read "$plugin_name")" || sentinel_line=""
    use_cached=0
    cached_status=""

    if [[ -n "$sentinel_line" ]]; then
        # sentinel_line: "<plugin> <date> <status...>"
        sentinel_date="$(echo "$sentinel_line" | awk '{print $2}')"
        # status is everything from field 3 onward
        cached_status="$(echo "$sentinel_line" | cut -d' ' -f3-)"
        days_old="$(_days_since "$sentinel_date")"
        if [[ "$days_old" =~ ^[0-9]+$ ]] && [[ "$days_old" -lt 3 ]]; then
            use_cached=1
        fi
    fi

    if [[ "$use_cached" -eq 1 ]]; then
        # Re-emit the cached nag (or silence for current/source_is_live)
        case "$cached_status" in
            current|source_is_live) : ;; # silent
            offline)
                # Short-TTL: offline sentinel should have been written with a very
                # recent date only if it was a short-TTL marker. In practice, offline
                # does NOT write the 3-day sentinel, so this branch should not be hit
                # from a cached 3-day record. If we see it, re-check live.
                use_cached=0
                ;;
            behind-clone*)
                # probe result: "behind-clone <n> <ref>"
                # install_root is still in scope from the loop header parse above.
                clone_n="$(echo "$cached_status"   | awk '{print $2}')"
                clone_ref="$(echo "$cached_status" | awk '{print $3}')"
                echo "📦 ${plugin_name} clone is ${clone_n} commits behind ${clone_ref} — git pull in ${install_root} to update"
                ;;
            behind*)
                from_ver="$(echo "$cached_status" | awk '{print $2}')"
                to_ver="$(echo "$cached_status"   | awk '{print $3}')"
                echo "📦 ${plugin_name} ${from_ver}→${to_ver} behind latest release — $(_action_hint_for "$plugin_name")"
                ;;
            differs*)
                to_ver="$(echo "$cached_status" | awk '{print $2}')"
                echo "📦 ${plugin_name} differs from latest release (${to_ver}) — $(_action_hint_for "$plugin_name")"
                ;;
            *) use_cached=0 ;; # unrecognised; force live check
        esac
    fi

    [[ "$use_cached" -eq 1 ]] && continue

    # ------------------------------------------------------------------
    # Live probe (network call wrapped in timeout 3 inside the lib)
    # ------------------------------------------------------------------
    probe_result="$(release_currency_probe "$plugin_name" "$owner_repo" "$install_root" 2>/dev/null)" || probe_result="offline"
    [[ -z "$probe_result" ]] && probe_result="offline"

    # ------------------------------------------------------------------
    # Render + update sentinel
    # ------------------------------------------------------------------
    case "$probe_result" in
        current|source_is_live)
            # Silent — write/refresh the 3-day sentinel so we don't recheck for 3 days
            if [[ -n "$TODAY" ]]; then
                _sentinel_write "$plugin_name" "$TODAY" "$probe_result"
            fi
            ;;
        behind-clone*)
            # probe_result: "behind-clone <n> <ref>"
            # BOOT-CURRENCY-THROTTLE: write 3-day sentinel so we don't re-fetch every boot.
            clone_n="$(echo "$probe_result"   | awk '{print $2}')"
            clone_ref="$(echo "$probe_result" | awk '{print $3}')"
            echo "📦 ${plugin_name} clone is ${clone_n} commits behind ${clone_ref} — git pull in ${install_root} to update"
            if [[ -n "$TODAY" ]]; then
                _sentinel_write "$plugin_name" "$TODAY" "$probe_result"
            fi
            ;;
        behind*)
            # probe_result: "behind <from> <to>"
            from_ver="$(echo "$probe_result" | awk '{print $2}')"
            to_ver="$(echo "$probe_result"   | awk '{print $3}')"
            echo "📦 ${plugin_name} ${from_ver}→${to_ver} behind latest release — $(_action_hint_for "$plugin_name")"
            if [[ -n "$TODAY" ]]; then
                _sentinel_write "$plugin_name" "$TODAY" "$probe_result"
            fi
            ;;
        differs*)
            # probe_result: "differs <to>"
            to_ver="$(echo "$probe_result" | awk '{print $2}')"
            echo "📦 ${plugin_name} differs from latest release (${to_ver}) — $(_action_hint_for "$plugin_name")"
            if [[ -n "$TODAY" ]]; then
                _sentinel_write "$plugin_name" "$TODAY" "$probe_result"
            fi
            ;;
        offline)
            # CRITICAL (BOOT-CURRENCY-THROTTLE, the Staff Engineer F6): do NOT write the 3-day
            # sentinel on offline. Skip the sentinel write entirely so the next boot
            # retries the live fetch rather than serving a stale offline result for 3 days.
            echo "[${plugin_name} update check] Release source temporarily unreachable — will retry at next session start."
            # No sentinel write for offline (next boot will retry live fetch)
            ;;
        *)
            # Unknown result — treat as offline; no sentinel write
            echo "[${plugin_name} update check] Unknown probe result '${probe_result}' — will retry."
            ;;
    esac

done

exit 0
