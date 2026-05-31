#!/usr/bin/env bash
# lib/detect-onboarding-offer.sh — Session-preflight onboarding currency detector.
#
# Purpose: detect whether the cwd repo needs /project-onboarding (unonboarded) or
# /project-onboarding --refresh (stale against current coordinator schema), and emit
# an offer line if action is warranted.  Consumed by /workday-start Step 1.10 at
# session-preflight cadence (NOT a PreToolUse hook — per-repo-stable fact, not
# per-command hot path).
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 3
#
# Decision rules (all silent on no-offer path):
#   1. Not a git repo              → silent (nothing to onboard against)
#   2. Distribution repo ((b) class) → silent (session infra doesn't belong there)
#   3. Dismissal sentinel present  → silent (user already saw offer, dismissed it)
#   4. Unonboarded (no docs/project-tracker.md) → emit OFFER line (unonboarded)
#   5. Stale (probe returns drift/unstamped) → emit OFFER line (stale)
#   6. Current                     → silent (healthy)
#
# Distribution repo detection (mirrors skills/project-onboarding/SKILL.md:50-53):
#   2+ of these dirs in .gitignore → treat as distribution repo:
#   tasks/, archive/, tasks/handoffs/
#
# Dismissal sentinel: <repo>/.git/coordinator-onboarding-dismissed
#   (inside .git/ — gitignore-additive, never shows in `git status`, per-repo)
#
# Offer shape (eager-agent-calibration.md): lead with the better alternative,
# not the problem.  Format uses a plain stdout line the Step 1.10 caller surfaces.
#
# Public API — two usage modes:
#
#   SOURCE mode (from workday-start step):
#     source detect-onboarding-offer.sh
#     detect_onboarding_offer          # emits to stdout; caller formats
#
#   STANDALONE mode (for tests — self-contained run):
#     bash detect-onboarding-offer.sh [--repo <path>] [--plugin-root <path>]
#     Env overrides (for tests):
#       DETECT_ONBOARDING_REPO_ROOT    — repo to check (default: cwd git root)
#       DETECT_ONBOARDING_PLUGIN_ROOT  — coordinator plugin root (default: auto)
#
# Exit codes:
#   0 — always (advisory only; never blocks)
#
# Output (stdout):
#   offer line when action warranted; nothing when silent.
#   Callers MUST NOT infer meaning from exit code — check stdout content.

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _gitignore_count_of_session_dirs <repo_root>
# Count how many of the three session infrastructure dirs are gitignored.
_doi_count_ignored_session_dirs() {
    local repo_root="${1:?repo_root required}"
    local gitignore="${repo_root}/.gitignore"
    [[ ! -f "$gitignore" ]] && echo 0 && return 0

    local count=0
    # Check for each of the three session dirs; match bare entry or trailing-slash form.
    if grep -qE '^(tasks/?|/tasks/?)$' "$gitignore" 2>/dev/null; then
        count=$((count + 1))
    fi
    if grep -qE '^(archive/?|/archive/?)$' "$gitignore" 2>/dev/null; then
        count=$((count + 1))
    fi
    if grep -qE '^(tasks/handoffs/?|/tasks/handoffs/?)$' "$gitignore" 2>/dev/null; then
        count=$((count + 1))
    fi
    echo "$count"
}

# _doi_is_distribution_repo <repo_root> → exit 0 if distribution, 1 if not
_doi_is_distribution_repo() {
    local repo_root="${1:?repo_root required}"
    local count
    count="$(_doi_count_ignored_session_dirs "$repo_root")"
    [[ "$count" -ge 2 ]] && return 0 || return 1
}

# _doi_is_onboarded <repo_root> → exit 0 if onboarded (docs/project-tracker.md exists), 1 if not
_doi_is_onboarded() {
    local repo_root="${1:?repo_root required}"
    [[ -f "${repo_root}/docs/project-tracker.md" ]] && return 0 || return 1
}

# ---------------------------------------------------------------------------
# Public: detect_onboarding_offer
# ---------------------------------------------------------------------------
# Emits a single offer line to stdout when action is warranted; silent otherwise.
# Caller (workday-start Step 1.10) surfaces the line in the ### Addon Health section.
#
# Arguments (optional env overrides for tests):
#   DETECT_ONBOARDING_REPO_ROOT   — absolute path to repo root (default: git root of cwd)
#   DETECT_ONBOARDING_PLUGIN_ROOT — absolute path to coordinator plugin root (default: auto)
detect_onboarding_offer() {
    # --- Resolve repo root ---
    local repo_root
    if [[ -n "${DETECT_ONBOARDING_REPO_ROOT:-}" ]]; then
        repo_root="$DETECT_ONBOARDING_REPO_ROOT"
    else
        repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    fi

    # Rule 1: not a git repo → silent
    [[ -z "$repo_root" ]] && return 0
    [[ ! -d "$repo_root/.git" ]] && return 0

    # Rule 2: distribution repo → silent
    if _doi_is_distribution_repo "$repo_root"; then
        return 0
    fi

    # Rule 3: dismissal sentinel present → silent
    local sentinel="${repo_root}/.git/coordinator-onboarding-dismissed"
    if [[ -f "$sentinel" ]]; then
        return 0
    fi

    # --- Resolve plugin root for currency probe ---
    local plugin_root
    if [[ -n "${DETECT_ONBOARDING_PLUGIN_ROOT:-}" ]]; then
        plugin_root="$DETECT_ONBOARDING_PLUGIN_ROOT"
    else
        # Auto-resolve: this script lives at <plugin_root>/lib/detect-onboarding-offer.sh
        local _script_dir
        # BASH_SOURCE[0] is reliable when sourced; fall back to script resolution
        if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "$0" ]]; then
            # sourced — resolve relative to source path
            _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        else
            # standalone execution
            _script_dir="$(cd "$(dirname "$0")" && pwd)"
        fi
        plugin_root="$(dirname "$_script_dir")"
    fi

    # Dismissal command — computed once here; used at all offer-emit sites below.
    local dismiss_cmd="touch '${repo_root}/.git/coordinator-onboarding-dismissed'"

    # Rule 4: unonboarded → offer
    if ! _doi_is_onboarded "$repo_root"; then
        printf '[onboarding] This repo is not yet onboarded — run /project-onboarding to get coordinator scaffolding, currency tracking, and a project tracker. (Dismiss: %s)\n' "$dismiss_cmd"
        return 0
    fi

    # Rule 5: stale (currency drift) → offer
    # Consume bin/probe-onboarding-currency.sh (Wave-1, W1) — do not reimplement.
    local probe_script="${plugin_root}/bin/probe-onboarding-currency.sh"
    if [[ -x "$probe_script" ]]; then
        local probe_status
        probe_status="$(CLAUDE_HOME="$repo_root" COORDINATOR_CURRENCY_PLUGIN_ROOT="$plugin_root" bash "$probe_script" 2>/dev/null || true)"

        case "$probe_status" in
            current|source_is_live)
                # Rule 6: current → silent
                return 0
                ;;
            drift*)
                printf '[onboarding] This repo was onboarded against an older coordinator (%s) — run /project-onboarding --refresh to bring it current. (Dismiss: %s)\n' "$probe_status" "$dismiss_cmd"
                return 0
                ;;
            unstamped*)
                printf '[onboarding] This repo was onboarded but has no currency stamp — run /project-onboarding --refresh to bring it current. (Dismiss: %s)\n' "$dismiss_cmd"
                return 0
                ;;
            inconclusive*)
                # Inconclusive means the probe couldn't determine status — treat as silent
                # (do not nag on infrastructure uncertainty per eager-agent-calibration.md)
                return 0
                ;;
            *)
                # Unknown status — silent (safe default)
                return 0
                ;;
        esac
    fi

    # Probe script not found or not executable — fall back to stamp-file read
    # via coordinator-currency.sh if available.
    # source_is_live check: if this script is running from inside repo_root/plugins/,
    # the repo being checked IS the coordinator source — no stamp is expected; treat as
    # silent (mirrors probe-onboarding-currency.sh source_is_live detection).
    local lib="${plugin_root}/lib/coordinator-currency.sh"
    if [[ -f "$lib" ]]; then
        # source_is_live: plugin_root is inside repo_root/plugins/ → repo is the meta-repo
        local _repo_norm="${repo_root%/}"
        local _plugin_norm="${plugin_root%/}"
        if [[ "$_plugin_norm" == "${_repo_norm}/plugins"* ]]; then
            # source_is_live → silent (no stamp expected on the meta-repo itself)
            return 0
        fi

        # shellcheck source=/dev/null
        source "$lib"
        local probe_result
        probe_result="$(coordinator_currency_probe "$repo_root" "$plugin_root" 2>/dev/null || true)"
        case "$probe_result" in
            current)
                return 0
                ;;
            drift*|unstamped*)
                printf '[onboarding] This repo was onboarded against an older coordinator (%s) — run /project-onboarding --refresh to bring it current. (Dismiss: %s)\n' "$probe_result" "$dismiss_cmd"
                return 0
                ;;
            *)
                return 0
                ;;
        esac
    fi

    # No probe available — conservative: stay silent (can't assess)
    return 0
}

# ---------------------------------------------------------------------------
# Standalone execution — run the detector and print result
# ---------------------------------------------------------------------------
# When executed directly (not sourced), call detect_onboarding_offer and print
# whatever it emits (or nothing, if silent).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # Parse CLI args for standalone use by tests
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                export DETECT_ONBOARDING_REPO_ROOT="$2"
                shift 2
                ;;
            --plugin-root)
                export DETECT_ONBOARDING_PLUGIN_ROOT="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    detect_onboarding_offer
fi
