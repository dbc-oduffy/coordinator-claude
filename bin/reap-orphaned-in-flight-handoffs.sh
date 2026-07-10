#!/usr/bin/env bash
# reap-orphaned-in-flight-handoffs.sh — crash-orphan DETECTOR for consumed+in_flight handoffs.
#
# Purpose: find handoffs stuck at status:consumed + deployment_state:in_flight whose
# claiming session (consumed_by:) is no longer live, and dispatch the EXISTING `supersede`
# transition (bin/handoff-transition.js supersede) to close them out — status→consumed
# (already true, no-op) + deployment_state→abandoned. This script is a DETECTOR, not a
# writer: it never mutates handoff frontmatter itself; the atomic freeze-hook-safe write
# is entirely delegated to handoff-transition.js's tested supersede verb (single-writer
# invariant, AC5). Companion to the `repark` verb (handoff-transition.js) — repark is the
# INTENTIONAL-pause path for a LIVE session; this reaper is the crash-orphan path for a
# DEAD one. They solve different sub-problems, not alternatives to pick between.
#
# The `kind: recovery` handoff mechanism (docs/wiki/multi-session-crash-recovery.md:107-113)
# already provides the SUCCESSOR-path exit out of a crashed in_flight state. This reaper
# closes the separate gap: the ORIGINAL crashed consumed+in_flight node itself, which the
# recovery handoff bypasses but never sweeps/reaps/transitions to abandoned — it would
# otherwise stay orphaned and invisible to sweep-shipped-handoffs.sh.
#
# Anti-scope (RAW-PID-LIVENESS tripwire): the orphan predicate gates on session liveness
# ONLY — _cs_session_live (cs_live_session_ids / cs_claim_holder_live's shared liveness
# key) — NEVER mtime/pid of the handoff file itself. A slow-but-live in_flight session is
# never reaped; liveness is decided by the session-claim layer, not filesystem staleness.
#
# Usage:
#   reap-orphaned-in-flight-handoffs.sh [--dry-run]
#
# --dry-run: report orphan candidates on stdout without dispatching supersede.
#
# Exit codes:
#   0 — normal (including zero orphans found; reaping is best-effort)
#   2 — internal error (not inside a git repo, or state/handoffs/ unresolvable)
#
# Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5a
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "reap-orphaned-in-flight-handoffs.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_SESSION="${SCRIPT_DIR}/../lib/coordinator-session.sh"
TRANSITION_CLI="${SCRIPT_DIR}/handoff-transition.js"

# shellcheck source=../lib/coordinator-session.sh
source "$LIB_SESSION"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "reap-orphaned-in-flight-handoffs.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Repo root / handoffs dir resolution — direct git rev-parse (same primitive
# _cs_git_root wraps), not coordinator_state_root: this reaper needs to run
# from a cold session-init-hook shell like sweep-shipped-handoffs.sh, and
# scans state/handoffs/ directly (no per-repo redirection concern here since
# session-claim liveness — _cs_session_live — is itself keyed off this same
# git root's .git/coordinator-sessions/).
# ---------------------------------------------------------------------------
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "reap-orphaned-in-flight-handoffs.sh: not inside a git repo" >&2
  exit 2
fi

handoffs_dir="${repo_root}/state/handoffs"

# ---------------------------------------------------------------------------
# Field-extraction helper — same frontmatter-scan awk pattern as
# sweep-shipped-handoffs.sh process_file (single-key value, whitespace-stripped).
# ---------------------------------------------------------------------------
_fm_field() {
  local f="$1" key="$2"
  local val
  val="$(awk -v key="${key}:" '
    !infm && /^---[[:space:]]*$/ { infm=1; next }
    infm && /^---[[:space:]]*$/ { exit }
    infm && index($0, key) == 1 {
      val=$0
      sub("^" key "[[:space:]]*", "", val)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
      print val
      exit
    }
  ' "$f" 2>/dev/null || true)"
  # Review: review-integrator B-F4 — strip a single matched pair of surrounding
  # quotes. serializeYamlScalar (coordinator/bin/lib/schema.js) single-quotes
  # all-digit values (e.g. a synthetic all-digit session-id); an unstripped quoted
  # consumed_by would read as not-live below and could mis-reap a live handoff.
  if [[ "$val" =~ ^\"(.*)\"$ || "$val" =~ ^\'(.*)\'$ ]]; then
    val="${BASH_REMATCH[1]}"
  fi
  printf '%s' "$val"
}

reaped=0
would_reap=0
skipped_live=0
skipped_no_holder=0

if [[ -d "$handoffs_dir" ]]; then
  for f in "${handoffs_dir}"/*.md; do
    # Empty-glob guard: bash expands to literal pattern when no files match
    [[ -f "$f" ]] || continue

    # TOCTOU guard — a concurrent archival/consume can vanish or rewrite the file
    # between glob-enumeration and per-file processing.
    [[ -f "$f" ]] || continue

    status="$(_fm_field "$f" status)"
    deployment_state="$(_fm_field "$f" deployment_state)"

    # Orphan candidate shape: status:consumed + deployment_state:in_flight ONLY.
    [[ "$status" == "consumed" && "$deployment_state" == "in_flight" ]] || continue

    consumed_by="$(_fm_field "$f" consumed_by)"

    # No claim holder recorded — cannot evaluate liveness; skip (fail-closed, do not reap).
    if [[ -z "$consumed_by" ]]; then
      (( skipped_no_holder++ )) || true
      continue
    fi

    # Liveness gate: _cs_session_live ONLY (cs_live_session_ids / cs_claim_holder_live's
    # shared liveness key) — NEVER mtime/pid of the handoff file (RAW-PID-LIVENESS).
    if _cs_session_live "$consumed_by"; then
      (( skipped_live++ )) || true
      continue
    fi

    # Dead holder — orphan confirmed. Dispatch the EXISTING supersede transition
    # (this script never writes frontmatter itself — single-writer invariant, AC5).
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "reap-orphaned-in-flight-handoffs.sh: [dry-run] would reap ${f} (dead holder: ${consumed_by})"
      # Review: code-reviewer F2 — distinct counter from `reaped` so the dry-run path
      # never reports mutation-never-performed work as "reaped" in the summary.
      (( would_reap++ )) || true
      continue
    fi

    if node "$TRANSITION_CLI" supersede --handoff "$f" >/dev/null 2>&1; then
      echo "reap-orphaned-in-flight-handoffs.sh: reaped ${f} (dead holder: ${consumed_by})"
      (( reaped++ )) || true
    else
      echo "reap-orphaned-in-flight-handoffs.sh: error superseding ${f}; skipping" >&2
    fi
  done
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ "$would_reap" -eq 0 ]]; then
    echo "no orphaned in_flight handoffs would be reaped (dry-run)"
  else
    echo "${would_reap} orphaned in_flight handoffs would be reaped (dry-run)"
  fi
elif [[ "$reaped" -eq 0 ]]; then
  echo "no orphaned in_flight handoffs reaped"
else
  echo "${reaped} orphaned in_flight handoffs reaped"
fi

if [[ "$skipped_live" -gt 0 ]]; then
  echo "${skipped_live} in_flight handoffs retained (live holder)"
fi

if [[ "$skipped_no_holder" -gt 0 ]]; then
  echo "${skipped_no_holder} consumed+in_flight handoffs retained (no consumed_by recorded)"
fi

exit 0
