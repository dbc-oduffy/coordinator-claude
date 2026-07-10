#!/usr/bin/env bash
# check-wsc-inline-budget.sh — gate on inline bash-block count in workstream-complete/SKILL.md.
#
# Purpose: counts ```bash fenced code blocks in the wsc SKILL.md and compares
# against a stored baseline integer. Inline bash blocks are a proxy for
# "mechanism logic that should live in a bin/wsc-*.sh script instead of
# inline in the skill." The script surfaces a WARN when the count grows.
#
# Spec backlink: wsc-asic task (2026-06-30) / skill-step-parallelization.md § wsc wiring rule
#
# Self-location: resolves SKILL.md relative to this script's directory so
# the path works on any machine without hardcoded absolute paths.
#
# Exit codes:
#   0 — count within baseline (or no baseline file — safe to ship before finalization)
#   1 — count exceeds baseline (WARN — non-blocking by caller convention)
#   2 — fatal error (SKILL.md not found)
#
# Callers: invoke as 'check-wsc-inline-budget.sh || true' to prevent exit-1 from
# aborting set -e callers. The workweek-complete wiring pipes through '2>&1 | tail -1'
# which masks the exit; direct callers must opt-in to non-blocking explicitly.
# Review: code-reviewer — exit-1-as-WARN is a footgun for set -e callers; document canonical invocation
#
# Env overrides (for testing):
#   WSC_SKILL_PATH     — substitute a different SKILL.md path
#   WSC_BASELINE_FILE  — substitute a different baseline file path
#
# Negative-spec: does NOT use grep -P (non-portable), sed -i, or realpath
# without a command -v guard (DR-148 / cross-platform-shell-portability.md).
# No bash-4-only features are used; BASH_VERSINFO guard is therefore omitted.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_DIR="$(dirname "$SCRIPT_DIR")"

SKILL_PATH="${WSC_SKILL_PATH:-$COORDINATOR_DIR/skills/workstream-complete/SKILL.md}"
BASELINE_FILE="${WSC_BASELINE_FILE:-$SCRIPT_DIR/.wsc-inline-budget-baseline}"

if [[ ! -f "$SKILL_PATH" ]]; then
  echo "ERROR: SKILL.md not found at $SKILL_PATH" >&2
  exit 2
fi

# Count ```bash opening fences with awk — portable across BSD and GNU coreutils.
# Single-quoted awk program: backticks are literal (no shell expansion).
# `c+0` ensures 0 is printed when no matches are found.
CURRENT=$(awk '/^```bash/{c++} END{print c+0}' "$SKILL_PATH")

if [[ ! -f "$BASELINE_FILE" ]]; then
  echo "INFO: no baseline set yet — current inline bash-block count: $CURRENT"
  exit 0
fi

BASELINE=$(cat "$BASELINE_FILE")

if [[ "$CURRENT" -gt "$BASELINE" ]]; then
  echo "WARN: workstream-complete inline bash-block count $CURRENT exceeds baseline $BASELINE — new mechanism should be a bin/wsc-*.sh script, not inline (see skill-step-parallelization.md § wsc wiring rule)"
  exit 1
fi

echo "OK: inline bash-block count $CURRENT within baseline $BASELINE"
exit 0
