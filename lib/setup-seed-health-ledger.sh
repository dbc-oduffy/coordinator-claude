#!/usr/bin/env bash
# setup-seed-health-ledger.sh — repo-setup-time helper: seed state/health-ledger.md.
#
# Purpose: create a skeleton health-ledger in a target repo so workday-complete Step 4
# can immediately append to it without the "create if missing" branch. Called by
# skills/repo-setup/SKILL.md during coordinator setup of a new project repo.
#
# Idempotent: if state/health-ledger.md already exists in the target repo, the script
# prints a notice and exits 0 without modification. Never overwrites user-authored state.
#
# Usage:
#   setup-seed-health-ledger.sh [REPO_ROOT]
#
#   REPO_ROOT  — path to the target repo root; defaults to current working directory.
#
# Schema source: docs/wiki/daily-summary-procedure.md § "Health Ledger Entry Schema"
#   Two audit clocks above a per-system table; all system grades start at "?".
#
# Spec backlink: docs/plans/2026-06-23-setup-substrate-completeness.md § C1b
#
# Cross-platform: bash ≥ 3.2 + POSIX coreutils; no GNU-isms. Explicitly portable to
# macOS (BSD sed, BSD date). Uses printf not echo for portability.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument resolution
# ---------------------------------------------------------------------------

REPO_ROOT="${1:-$(pwd)}"

if [[ ! -d "$REPO_ROOT" ]]; then
    printf 'setup-seed-health-ledger: REPO_ROOT does not exist or is not a directory: %s\n' "$REPO_ROOT" >&2
    printf '  Remediation: pass a valid directory path as the first argument.\n' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# State-root resolution — route meta-repo REPO_ROOT through seam (C4/stop-the-rot).
#
# Uses command -v guards (not file-scope source of coordinator-state-root.sh) to
# avoid propagating set -uo pipefail from its transitive deps into a broadly-sourced
# lib context. FLAG: inline seam pattern (C4e) applied.
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4
# ---------------------------------------------------------------------------
_SSLH_STATE_ROOT="${REPO_ROOT}/state"
if command -v coordinator_is_meta_repo >/dev/null 2>&1 \
    && coordinator_is_meta_repo "${REPO_ROOT}" 2>/dev/null; then
    _SSLH_MR=""
    if command -v coordinator_example_orchestration_hub_root >/dev/null 2>&1; then
        _SSLH_MR="$(coordinator_example_orchestration_hub_root 2>/dev/null || true)"
    else
        _SSLH_MR="$(machine-local get repos.example_orchestration_hub_repo 2>/dev/null || true)"
    fi
    [[ -n "$_SSLH_MR" ]] && _SSLH_STATE_ROOT="${_SSLH_MR}/state"
fi

# ---------------------------------------------------------------------------
# Idempotency gate
# ---------------------------------------------------------------------------

LEDGER_PATH="${_SSLH_STATE_ROOT}/health-ledger.md"

if [[ -f "$LEDGER_PATH" ]]; then
    printf '[health-ledger] state/health-ledger.md already exists in %s — skipping (idempotent).\n' "$REPO_ROOT"
    exit 0
fi

# ---------------------------------------------------------------------------
# Create state/ directory if needed
# ---------------------------------------------------------------------------

STATE_DIR="${_SSLH_STATE_ROOT}"
if [[ ! -d "$STATE_DIR" ]]; then
    mkdir -p "$STATE_DIR" || {
        printf 'setup-seed-health-ledger: cannot create state/ directory at %s\n' "$STATE_DIR" >&2
        printf '  Remediation: check directory permissions for %s.\n' "$REPO_ROOT" >&2
        exit 1
    }
fi

# ---------------------------------------------------------------------------
# Write the seeded ledger
#
# Schema per docs/wiki/daily-summary-procedure.md § "Health Ledger Entry Schema":
#   - Two distinct audit clocks (Last full audit / Last targeted audit) plus Next rotation target.
#   - A per-system table; systems are added by workday-complete Step 4 with grade "?" on first touch.
#   - Do NOT pre-populate system rows: seeding with fabricated system names would be wrong for every
#     repo that isn't the coordinator meta-repo. The consumer (workday-complete Step 4) adds rows.
# ---------------------------------------------------------------------------

printf '[health-ledger] seeding state/health-ledger.md in %s\n' "$REPO_ROOT"

{
    printf '# Health Ledger\n'
    printf '\n'
    printf '<!-- Two distinct audit clocks (do not conflate):\n'
    printf '     - Last targeted audit  — written by /architecture-audit.\n'
    printf '     - Last full audit      — written only by a PM-invoked /architecture-survey.\n'
    printf '     A targeted audit must NOT touch the "Last full audit" field. -->\n'
    printf '\n'
    printf '**Last full audit:** (none — run /architecture-survey)\n'
    printf '**Last targeted audit:** (none)\n'
    printf '**Next rotation target:** (none — add systems as they are touched)\n'
    printf '\n'
    printf '<!-- Grade vocabulary: A-F (or ? = never graded). Grades are written only by\n'
    printf '     /architecture-audit or /architecture-survey, never by workday-complete. -->\n'
    printf '\n'
    printf '| System | Grade | Last Audited | Notes |\n'
    printf '|--------|-------|-------------|-------|\n'
} > "$LEDGER_PATH" || {
    printf 'setup-seed-health-ledger: failed to write %s\n' "$LEDGER_PATH" >&2
    printf '  Remediation: check write permissions on %s.\n' "$STATE_DIR" >&2
    exit 1
}

printf '[health-ledger] done — state/health-ledger.md seeded with two audit clocks and empty per-system table.\n'
printf '[health-ledger] Systems are added automatically by workday-complete Step 4 (grade: ?) on first commit touch.\n'
