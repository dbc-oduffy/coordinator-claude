#!/bin/bash
# coordinator-daily-branch.sh — Shared helpers for daily-branch discipline enforcement
#
# Consumers:
#   - hooks/scripts/block-off-daily-branch.sh (PreToolUse hook — branch create/switch/rename)
#   - hooks/scripts/validate-commit.sh (formerly Check 6 — commit-time defence-in-depth,
#     now in block-off-daily-branch.sh commit-time section after F11 refactor)
#
# Source this file; do NOT execute it directly. Functions are prefixed cs_ to
# match coordinator-session.sh convention.
#
# Source pattern (same as coordinator-session.sh):
#   LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-daily-branch.sh"
#   if [[ ! -f "$LIB_PATH" ]]; then
#     LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-daily-branch.sh"
#   fi
#   [[ -f "$LIB_PATH" ]] && source "$LIB_PATH"

# cs_compute_machine — echo the coordinator machine name
# Resolution order: $COORDINATOR_MACHINE → $COMPUTERNAME → hostname → $HOSTNAME → "unknown"
cs_compute_machine() {
  if [[ -n "${COORDINATOR_MACHINE:-}" ]]; then
    echo "$COORDINATOR_MACHINE"
    return
  fi
  if [[ -n "${COMPUTERNAME:-}" ]]; then
    echo "$COMPUTERNAME"
    return
  fi
  if command -v hostname &>/dev/null; then
    local h
    h=$(hostname 2>/dev/null | sed 's/\..*//')
    if [[ -n "$h" ]]; then
      echo "$h"
      return
    fi
  fi
  echo "${HOSTNAME:-unknown}"
}

# cs_compute_today_daily_lc — echo lowercase work/{machine}/{YYYY-MM-DD}
cs_compute_today_daily_lc() {
  local machine today
  machine=$(cs_compute_machine)
  today=$(date +%Y-%m-%d)
  echo "work/${machine}/${today}" | tr '[:upper:]' '[:lower:]'
}

# cs_is_allowed_branch <name> — return 0 if name is today's daily or main (case-insensitive)
cs_is_allowed_branch() {
  local name="$1"
  local lc daily_lc
  lc=$(echo "$name" | tr '[:upper:]' '[:lower:]')
  daily_lc=$(cs_compute_today_daily_lc)
  [[ "$lc" == "main" ]] && return 0
  [[ "$lc" == "$daily_lc" ]] && return 0
  return 1
}
