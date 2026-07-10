#!/usr/bin/env bash
# coordinator-daily-day.sh — canonical local-calendar-day anchor for the coordinator.
#
# Purpose: exposes coordinator_local_day(), the single authoritative source for
# today's date in the operator's LOCAL timezone. All anchor-sensitive ceremony
# day-keys (changelog filenames, daily-branch names, plan filenames,
# commit-window bounds) MUST derive from this function, not from `date -u`.
#
# Rationale: `date -u` returns UTC midnight — wrong for operators in UTC-4..UTC+14
# timezones once a session crosses midnight or runs in the morning before noon.
# The PM ratified local-day-everywhere on 2026-06-26 (plan D1).
# Spec backlink: docs/plans/2026-06-26-datetime-handling-coherence.md § D1, C-A1.
#
# INSTANT TIMESTAMPS: event/record timestamps that must be globally comparable
# (handoff `dispatched_at`, artifact `created_at`, audit log lines) stay UTC and
# MUST NOT use this function. This function is day-granularity LOCAL only.
#
# Future / NOT BUILT (YAGNI): a `coordinator.local.md` `ceremony_day_anchor: local|utc`
# key could make this configurable for a multi-TZ fleet; not built (YAGNI for
# single-operator fleet). The escape hatch is documented as Option-C in the plan.
#
# Usage: source this file, then call coordinator_local_day.
#   source "$(dirname "${BASH_SOURCE[0]}")/coordinator-daily-day.sh"
#   TODAY=$(coordinator_local_day)
#
# MUST be sourced, not executed directly. Sourcing guard enforced below.

# ---------------------------------------------------------------------------
# Sourcing guard: fail loud if invoked directly instead of sourced.
# (Mirrors the convention from other coordinator lib files that must be sourced.)
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: coordinator-daily-day.sh must be sourced, not executed directly." >&2
  echo "  Usage: source /path/to/coordinator-daily-day.sh" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# coordinator_local_day — print today's date in the operator's LOCAL timezone.
#
# Purpose: BSD/GNU portable local-day query; the verbatim idiom from standup.sh:96.
# `date -I` is GNU-only and silently exits non-zero on BSD (macOS); the
# `|| date +%Y-%m-%d` fallback is POSIX-portable and fires on macOS.
# DR-148: this two-clause safe-chain form is the sanctioned portable pattern.
# Review: code-reviewer chunk-5 (F7) — reordered: DR-148 claim now follows the
# fallback explanation rather than preceding it, so it endorses the chain not the GNU-only primary.
#
# Returns: YYYY-MM-DD string for the LOCAL calendar day (operator's TZ).
# ---------------------------------------------------------------------------
coordinator_local_day() {
  date -I 2>/dev/null || date +%Y-%m-%d
}
