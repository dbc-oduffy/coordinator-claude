#!/usr/bin/env bash
# hooks/scripts/bootstrap-substrate.sh — SessionStart startup hook.
#
# Purpose: self-heal the out-of-tree contract surface (~/.claude/bin/) when it
# is absent. Marketplace-plugin installs drop the coordinator plugin tree under
# ~/.claude/plugins/coordinator-claude/ but never invoke lib/install-substrate.sh,
# so ~/.claude/bin/resolve-coordinator-clone (and its sibling resolvers) would be
# missing. Out-of-tree consumers (project-rag, project-rag-ue-addon, example-game-repo)
# that call that fixed-path shim then hard-fail their prereq gates.
#
# This hook closes the gap: on the first boot where ~/.claude/bin/resolve-coordinator-clone
# is absent, it runs install-substrate.sh --setup-only to lay the full substrate down,
# then stays silent once the shim exists. Shim-presence is the idempotency guard —
# no separate sentinel needed.
#
# Why not set -e: must never abort the session boot on a probe non-zero exit.
#
# Spec backlink: docs/wiki/plugin-extraction-and-distribution.md § Out-of-tree entry shim (marketplace self-heal)
#
# Output contract (SessionStart hook — stdout IS the additionalContext):
#   shim already present (meta-repo dev or already bootstrapped) : silent (exit 0)
#   install-substrate.sh not found in plugin tree                : one stdout line pointing at /coordinator:install (exit 0)
#   substrate deployed successfully                              : one stdout line confirming deploy (exit 0)
#   substrate deploy failed                                      : one stdout line with log path + remediation (exit 0)
#
# NOTE — additionalContext validation outcome: plain stdout is the proven mechanism
# for SessionStart context injection (confirmed by check-dropped-tracked-files.sh and
# project-orientation.sh corpus). All branches use plain stdout.
#
# Async caveat: this hook runs async (up to ~120s including detect-hardware.sh on the
# --setup-only path); the stdout notice may arrive after initial session context is
# composed or be silently dropped on very slow deploys. The deploy still succeeds;
# results are logged to ~/.claude/.cache/bootstrap-substrate.log. Next boot retries
# idempotently via shim-presence guard.
# Review: code-reviewer — async hook stdout timing caveat; deploy correctness unaffected
#
# Exit: 0 always.
# set -e omitted intentionally — must not abort on probe non-zero.
set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve plugin root from BASH_SOURCE (same idiom as check-plugin-update-currency.sh)
# ---------------------------------------------------------------------------
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${HOOK_DIR}/../.." && pwd)"

# Source async-hook-status helper if present; existence-guarded so a missing file is non-fatal
# (under set -u an unguarded source of a missing path would error).
# Review: code-reviewer Slice-B F4 — split onto two lines to match the codebase's guarded-source style.
_ahs_helper="${PLUGIN_ROOT}/lib/async-hook-status.sh"
[[ -f "$_ahs_helper" ]] && source "$_ahs_helper"

# ---------------------------------------------------------------------------
# Resolve claude home (same pattern as install-substrate.sh and platform-localize.sh)
# CLAUDE_HOME is a $HOME substitute — .claude suffix appended OUTSIDE the default.
# NEVER use ${CLAUDE_HOME:-$HOME/.claude}: that breaks sandbox/CI redirect.
# ---------------------------------------------------------------------------
_home="${CLAUDE_HOME:-$HOME}/.claude"

# ---------------------------------------------------------------------------
# Idempotency guard — shim-presence is the single check
# Covers both (a) meta-repo dev checkout where bin/resolve-coordinator-clone is
# git-tracked and present, and (b) any already-bootstrapped marketplace install.
# ---------------------------------------------------------------------------
_shim="${_home}/bin/resolve-coordinator-clone"
if [[ -x "$_shim" ]]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Shim is absent — attempt substrate deploy via install-substrate.sh --setup-only
# ---------------------------------------------------------------------------
_substrate="${PLUGIN_ROOT}/lib/install-substrate.sh"

if [[ ! -f "$_substrate" ]]; then
    echo "[coordinator] substrate shim absent and install-substrate.sh not found in plugin tree — run \`/coordinator:install\` to install the full coordinator substrate"
    exit 0
fi

# Prepare log destination; if .cache is not writable, fall back to /dev/null
# Review: code-reviewer — mkdir failure previously silent; now surface note in operator-facing message
_log="${_home}/.cache/bootstrap-substrate.log"
if ! mkdir -p "${_home}/.cache" 2>/dev/null; then
    _log=/dev/null
    _log_note=" (log capture unavailable — ${_home}/.cache not writable)"
else
    _log_note=""
fi

# Run install-substrate.sh --setup-only under non-interactive mode so the
# AppX consent prompt is suppressed. Capture all output to the log.
CLAUDE_PLUGIN_ROOT="${PLUGIN_ROOT}" COORDINATOR_NON_INTERACTIVE=1 \
    bash "$_substrate" --setup-only >"${_log}" 2>&1
_rc=$?

if [[ "$_rc" -eq 0 ]] && [[ -x "$_shim" ]]; then
    # Review: code-reviewer (F8) — replaced emoji with ASCII bracket tag to match
    # the plain-ASCII convention used across the hook set (no-emoji for operator-facing output).
    echo "[coordinator] substrate deployed to ${_home}/bin (first marketplace-install boot) — out-of-tree consumers can now resolve the coordinator clone."
else
    command -v ahs_record_failure >/dev/null 2>&1 && ahs_record_failure "bootstrap-substrate" "$_rc" "install-substrate.sh --setup-only failed" "$_log"
    echo "[coordinator] substrate not deployed (install-substrate.sh --setup-only failed) — run \`/coordinator:install\` or \`bash ${_substrate} --setup-only\`; log: ${_log}${_log_note}"
fi

exit 0
