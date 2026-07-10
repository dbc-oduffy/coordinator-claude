#!/usr/bin/env bash
# lib/async-hook-status.sh
#
# Single shared failure-surfacing convention for LOAD-BEARING async hooks.
# Spec: plugins/coordinator/docs/plans/2026-06-30-async-hook-failure-surfacing.md § Design
#
# Producers (bootstrap-substrate.sh, platform-localize.sh) record failures via
# ahs_record_failure; session-init.sh surfaces+clears them via ahs_surface_and_clear.
# Markers live under ${CLAUDE_HOME:-$HOME}/.claude/.cache/async-hook-status/
# (per-machine, boot-transient — NOT git-tracked state/).
#
# This file is SOURCED, not executed. No set -e/set -u at file scope (would leak to callers).
#
# Negative-spec:
#   - No jq dependency on the write path (jq may be absent on fresh machines).
#   - ahs_record_failure MUST NOT abort its caller (producers run under set -e / async ERR
#     traps); the subshell+unconditional-return-0 mechanism enforces this structurally.
#   - Apply ONLY to load-bearing hooks with silent persistent harm AND no self-correction
#     window before harm lands. Do NOT apply to fire-and-forget nudges or high-frequency
#     hooks (coordinator-reminder, ue-knowledge-distrust, session-heartbeat,
#     runtime-tripwire-stop-watcher). The discriminator is the value — see plan § Problem.

# Sourcing guard — safe to source multiple times (functions are idempotent to redeclare,
# but the guard avoids any sourcing-order surprises).
[ -n "${_AHS_SOURCED:-}" ] && return 0
_AHS_SOURCED=1

# ---------------------------------------------------------------------------
# ahs_status_dir
#
# Purpose: echo the canonical marker directory and ensure it exists.
# Falls back to a /dev/null-style no-op sentinel path if .cache is unwritable,
# so callers degrade to a silent no-op without crashing.
# ---------------------------------------------------------------------------
ahs_status_dir() {
    # Use canonical ${CLAUDE_HOME:-$HOME}/.claude form (machine-local-registry.md §4a),
    # NOT the older ${XDG_STATE_HOME:-$HOME/.claude} shape seen in some prior files —
    # both resolve identically on unset-env machines, but the canonical form is the standard.
    local _dir="${CLAUDE_HOME:-$HOME}/.claude/.cache/async-hook-status"
    if mkdir -p "$_dir" 2>/dev/null; then
        echo "$_dir"
    else
        # .cache is unwritable — echo a sentinel path that callers detect and skip.
        # Any write attempt into /dev/null/... fails silently (not a directory),
        # and any glob of /dev/null/.../*.json matches nothing.
        echo "/dev/null/async-hook-status-noop"
    fi
}

# ---------------------------------------------------------------------------
# ahs_record_failure <hook-name> <exit-code> <detail> [logpath]
#
# Purpose: write a single-line JSON failure marker for a load-bearing async hook.
# Latest-wins: overwrites any prior marker for the same hook-name.
#
# Best-effort, never fatal: body runs in a subshell with set +e; outer function
# returns 0 unconditionally. A set -e caller (including ERR trap invocations)
# is never aborted and the original exit code is never masked.
#
# JSON fields: hook, failed_at (ISO-UTC), exit, detail, log, remediation ("").
# Emitted via printf — no jq dependency on the write path.
# detail and logpath are minimally JSON-escaped (backslash then double-quote) via sed.
#
# <hook-name> MUST be a simple slug [a-z0-9][a-z0-9-]* — no slashes/quotes/backslashes.
# ---------------------------------------------------------------------------
ahs_record_failure() {
    # All body logic runs in a subshell. Positional params are inherited.
    # Variables prefixed _ahs_ to avoid collision with inherited caller scope.
    ( set +e
      _ahs_dir=$(ahs_status_dir)
      # Sentinel check: .cache was unwritable — degrade silently.
      case "$_ahs_dir" in
          /dev/null/*) exit 0 ;;
      esac
      # Minimal JSON-escape of detail and logpath: escape backslash first, then double-quote.
      # bash parameter expansion only — no jq, no python.
      # Review: code-reviewer Slice-A — (F1) logpath ($4) had backslash/quote chars unescaped,
      # producing invalid JSON on Windows CLAUDE_HOME paths (e.g. C:\Users\...).
      _ahs_detail_esc=$(printf '%s' "${3:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')
      _ahs_log_esc=$(printf '%s' "${4:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')
      _ahs_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "unknown")
      printf '{"hook":"%s","failed_at":"%s","exit":%s,"detail":"%s","log":"%s","remediation":""}\n' \
          "${1:-unknown}" \
          "$_ahs_ts" \
          "${2:-1}" \
          "$_ahs_detail_esc" \
          "$_ahs_log_esc" \
          > "${_ahs_dir}/${1:-unknown}.json" 2>/dev/null
    )
    return 0
}

# ---------------------------------------------------------------------------
# ahs_surface_and_clear
#
# Purpose: surface any recorded load-bearing async hook failures to the operator,
# then clear them so they don't re-nag on subsequent sessions.
#
# Design: atomic claim via mv (POSIX rename(2)) before reading, so concurrent
# readers skip silently on a lost race rather than double-surfacing. A re-fail
# on the NEXT boot causes the producer to overwrite a fresh marker, which
# re-surfaces on the boot after that — correct "failed last boot" semantics.
#
# Primary caller: session-init.sh (async: false, stdout reliably reaches operator).
# Must not error under set -e/set -u callers — all error paths use || guards.
# ---------------------------------------------------------------------------
ahs_surface_and_clear() {
    local _dir
    _dir=$(ahs_status_dir)  # always returns 0; sentinel path handled by case below
    # Sentinel check: .cache was unwritable — nothing to surface.
    case "$_dir" in
        /dev/null/*) return 0 ;;
    esac
    local _marker
    for _marker in "${_dir}"/*.json; do
        # Guard against the glob returning the literal pattern when no files match
        # (nullglob may be off in the caller's environment). The -e test is false
        # on a literal "*.json" that doesn't exist as a file.
        [ -e "$_marker" ] || continue
        # Atomic claim: rename to a PID-namespaced copy before reading.
        # mv is atomic within the same filesystem (POSIX rename(2) guarantee).
        # A concurrent reader that loses the mv silently skips — not an error.
        local _claimed="${_marker}.claimed.$$"
        mv "$_marker" "$_claimed" 2>/dev/null || continue
        # Read the claimed copy; if it's unreadable, clean up and move on.
        local _content
        _content=$(cat "$_claimed" 2>/dev/null) || { rm -f "$_claimed"; continue; }
        # Parse fields from single-line JSON via sed — no jq dependency.
        # Patterns are safe for the printf-emitted format produced by ahs_record_failure.
        # Review: code-reviewer Slice-A — (F2) use -n + /p so a no-match returns empty
        # (not the full content line), preventing garbled output from foreign/malformed markers.
        local _hook _exit _detail _remediation
        _hook=$(printf '%s' "$_content"        | sed -n 's/.*"hook":"\([^"]*\)".*/\1/p'); _hook="${_hook:-unknown}"
        _exit=$(printf '%s' "$_content"        | sed -n 's/.*"exit":\([0-9]*\).*/\1/p'); _exit="${_exit:-1}"
        _detail=$(printf '%s' "$_content"      | sed -n 's/.*"detail":"\([^"]*\)".*/\1/p'); _detail="${_detail:-}"
        _remediation=$(printf '%s' "$_content" | sed -n 's/.*"remediation":"\([^"]*\)".*/\1/p'); _remediation="${_remediation:-}"
        echo "[async-hook] ${_hook} failed last boot (exit ${_exit}): ${_detail} — ${_remediation}"
        rm -f "$_claimed"
    done
    return 0
}
