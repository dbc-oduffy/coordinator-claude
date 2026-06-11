#!/usr/bin/env bash
# coordinator/lib/bootstrap-orchestrate.sh — Discovery-to-per-repo orchestration for
# coordinator:setup (/coordinator:setup --batch command, consolidated 2026-06-08 from
# the former /bootstrap-repos). Script filename kept for git-mv history continuity;
# the implementation logic and execution path are unchanged from its bootstrap-repos origin; only user-visible command names (in printf strings, summary headers, and error messages) were updated.
#
# Purpose: reads ~/.claude/working-repos.yaml, resolves the repo list, presents
# the EXPRESS/CUSTOM two-choice surface, then delegates each selected repo to the
# existing Wave-1 primitive lib/bootstrap-repo.sh. After a successful bootstrap
# stamps coordinator currency via lib/coordinator-currency.sh::coordinator_currency_write.
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4
#
# HOOK CONTRACT — target-repo commit hooks are RESPECTED:
#   bootstrap-repo.sh (Wave-1) does NOT pass --no-verify; it runs the target repo's
#   hooks exactly as the user would. If a hook exits non-zero, bootstrap-repo.sh exits
#   non-zero and this orchestrator surfaces the failure in the per-repo status row.
#   This orchestrator ALSO does not pass --no-verify on the currency-stamp commit —
#   both commits (bootstrap scaffold + currency stamp) honour the target repo's hooks.
#
# Usage (direct shell — command doc delegates to this script):
#   bootstrap-orchestrate.sh [--non-interactive] [--check-only] [--help]
#
# Flags:
#   --non-interactive   No AskUserQuestion; selects EXPRESS path automatically.
#                       Documented per-site fallback: choose EXPRESS (bootstrap all repos).
#                       Under --check-only this flag is a no-op (check-only already suppresses all writes).
#   --check-only        Dry-run: produce the per-repo action list, write nothing.
#                       Implies --non-interactive (check-only never prompts).
#                       bootstrap-repo.sh called with --dry-run; currency stamp skipped.
#   --help | -h         Show this help and exit.
#
# Exit codes:
#   0  All selected repos bootstrapped successfully (or dry-run completed).
#   1  Usage error, missing prerequisite, or working-repos.yaml unreadable.
#   2  working-repos.yaml absent — operator must run /setup first.
#   3  One or more repos failed to bootstrap; partial success. Per-repo status table
#      is printed; summary distinguishes succeeded/failed/skipped counts.
#
# Idempotency:
#   Re-running with the same repo list is a no-op (bootstrap-repo.sh + scaffold are
#   idempotent; currency stamp write is idempotent). EXPRESS re-run = no changes.
#
# Out-of-scope (this script does NOT):
#   - Modify ~/.claude/working-repos.yaml or any Wave-1 library file.
#   - Discover repos (delegates discovery entirely to working-repos.yaml).
#   - Author handoffs, spinoffs, or session artifacts.
#   - Commit into ~/.claude or any coordinator-managed repo.
#   - Run git operations against the coordinator meta-repo itself.
#
# Destructive-action prohibition:
#   This script MUST NOT run git reset, git rm, git push --force, or any
#   destructive git operation. It MUST NOT delete or overwrite user files outside
#   the bootstrap-repo.sh scaffold contract. All mutations are reversible via
#   `git revert HEAD` in the target repo.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate siblings relative to THIS script
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_REPO="${SCRIPT_DIR}/bootstrap-repo.sh"
CURRENCY_SH="${SCRIPT_DIR}/coordinator-currency.sh"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKING_REPOS_YAML="${HOME}/.claude/working-repos.yaml"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

NON_INTERACTIVE=0
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -n '3,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^#[[:space:]]\{0,1\}//'
            exit 0
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --check-only)
            CHECK_ONLY=1
            NON_INTERACTIVE=1   # check-only implies non-interactive
            shift
            ;;
        -*)
            echo "bootstrap-orchestrate.sh: unknown flag: $1" >&2
            exit 1
            ;;
        *)
            echo "bootstrap-orchestrate.sh: unexpected argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

if [[ ! -f "$BOOTSTRAP_REPO" ]]; then
    echo "bootstrap-orchestrate.sh: bootstrap-repo.sh not found at: $BOOTSTRAP_REPO" >&2
    exit 1
fi

if [[ ! -f "$CURRENCY_SH" ]]; then
    echo "bootstrap-orchestrate.sh: coordinator-currency.sh not found at: $CURRENCY_SH" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "bootstrap-orchestrate.sh: git is not available on PATH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Resolve working-repos.yaml
# ---------------------------------------------------------------------------

if [[ ! -f "$WORKING_REPOS_YAML" ]]; then
    echo "" >&2
    echo "bootstrap-orchestrate.sh: ~/.claude/working-repos.yaml not found." >&2
    echo "" >&2
    echo "  /repo-setup --batch requires the working-repos list produced by /setup Phase 2 Step 4." >&2
    echo "  Run /setup first (or /coordinator:install) to discover and record your working repos." >&2
    echo "" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Parse repo paths from working-repos.yaml
# YAML is read line-by-line (no yq/python-yaml dependency).
# We extract lines matching '  - path: <value>' under the repos: block.
# Negative-spec: out_of_tree: block paths are NOT bootstrapped — they are
# not git repos managed by the coordinator.
# ---------------------------------------------------------------------------

_in_repos_block=0
_in_out_of_tree=0
REPO_PATHS=()
# Set when a malformed path entry (leading '-') is rejected during parsing.
# Consumed at the terminal success exits to signal partial success (exit 3)
# rather than a silent exit 0 that hides the skipped entry from the operator.
_any_path_rejected=0

while IFS= read -r _line; do
    # Detect block transitions
    if [[ "$_line" =~ ^repos: ]]; then
        _in_repos_block=1
        _in_out_of_tree=0
        continue
    fi
    if [[ "$_line" =~ ^out_of_tree: ]]; then
        _in_repos_block=0
        _in_out_of_tree=1
        continue
    fi
    # Top-level key resets both blocks
    if [[ "$_line" =~ ^[a-zA-Z_] && ! "$_line" =~ ^[[:space:]] ]]; then
        _in_repos_block=0
        _in_out_of_tree=0
    fi

    # Collect path values only from the repos: block (not out_of_tree:)
    if [[ $_in_repos_block -eq 1 && $_in_out_of_tree -eq 0 ]]; then
        if [[ "$_line" =~ ^[[:space:]]*-[[:space:]]*path:[[:space:]]*(.+)$ ]]; then
            _raw_path="${BASH_REMATCH[1]}"
            # Strip a YAML inline comment ONLY when '#' is whitespace-preceded
            # (space OR tab — `[[:space:]]` covers both). A bare '#' with no
            # leading whitespace is a literal path character, not a comment — the
            # old `%%#*` strip silently truncated `/repos/a#b` to `/repos/a`
            # (detect-then-silently-pick footgun). Embedded '#' is now kept.
            # Assumes operator paths contain no literal whitespace-then-'#'
            # sequence (a safe constraint for filesystem paths).
            if [[ "$_raw_path" == *[[:space:]]#* ]]; then
                _raw_path="${_raw_path%%[[:space:]]#*}"
            fi
            # Trim trailing whitespace (nested-expansion idiom: strips everything
            # from the last non-space character onward).
            _raw_path="${_raw_path%"${_raw_path##*[![:space:]]}"}"
            # Guard: a leading-'-' value would be misread as a flag by
            # bootstrap-repo.sh (the `--root` consumer), silently skipping the
            # repo. Reject it loudly AND flag it so the run exits 3 (partial
            # success), not a silent 0 that hides the skipped entry.
            if [[ "$_raw_path" == -* ]]; then
                echo "bootstrap-orchestrate.sh: rejecting repo path '${_raw_path}' from working-repos.yaml — leading '-' is parsed as a flag, not a path." >&2
                _any_path_rejected=1
                continue
            fi
            [[ -n "$_raw_path" ]] && REPO_PATHS+=("$_raw_path")
        fi
    fi
done < "$WORKING_REPOS_YAML"

if [[ ${#REPO_PATHS[@]} -eq 0 ]]; then
    echo "bootstrap-orchestrate.sh: no repo paths found in ~/.claude/working-repos.yaml" >&2
    echo "  The file exists but the repos: block is empty or malformed." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Normalize paths: convert Windows-style X:\foo → POSIX /x/foo for existence checks
# ---------------------------------------------------------------------------

_normalize_path() {
    local p="$1"
    local out
    # Windows drive letter: X:\foo or X:/foo → /x/foo (Git-Bash/MSYS style).
    # Lowercase ONLY the drive letter; preserve path case for POSIX filesystems.
    out="$(printf '%s' "$p" | tr '\\' '/')"
    case "$out" in
        [A-Za-z]:/* )
            local drive_lc
            drive_lc="$(printf '%s' "${out:0:1}" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz')"
            echo "/${drive_lc}${out:2}"
            ;;
        *)
            echo "$out"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Filter to repos that exist on disk
# ---------------------------------------------------------------------------

EXISTING_REPOS=()
MISSING_REPOS=()

for _repo in "${REPO_PATHS[@]}"; do
    _posix="$(_normalize_path "$_repo")"
    if [[ -d "$_posix" || -d "$_repo" ]]; then
        EXISTING_REPOS+=("$_repo")
    else
        MISSING_REPOS+=("$_repo")
    fi
done

if [[ ${#EXISTING_REPOS[@]} -eq 0 ]]; then
    echo "bootstrap-orchestrate.sh: none of the repos in working-repos.yaml exist on disk." >&2
    echo "  Either the repo paths are wrong or this machine has no local checkouts." >&2
    echo "  Repos listed: ${REPO_PATHS[*]}" >&2
    exit 1
fi

# Report missing repos (informational — not fatal; machine may have a subset)
if [[ ${#MISSING_REPOS[@]} -gt 0 ]]; then
    echo ""
    echo "Note: ${#MISSING_REPOS[@]} repo(s) in working-repos.yaml not found on disk (will be skipped):"
    for _m in "${MISSING_REPOS[@]}"; do
        echo "  - $_m"
    done
fi

# ---------------------------------------------------------------------------
# check-only: print action list and exit
# ---------------------------------------------------------------------------

if [[ $CHECK_ONLY -eq 1 ]]; then
    echo ""
    echo "=== /repo-setup --batch --check-only: per-repo action list ==="
    echo ""
    echo "Repos that WOULD be bootstrapped (${#EXISTING_REPOS[@]}):"
    for _repo in "${EXISTING_REPOS[@]}"; do
        _posix="$(_normalize_path "$_repo")"
        _actual_path="$([[ -d "$_posix" ]] && echo "$_posix" || echo "$_repo")"
        echo ""
        echo "  Repo: $_repo"
        # Delegate to bootstrap-repo.sh --dry-run for per-stage detail
        chmod +x "$BOOTSTRAP_REPO" 2>/dev/null || true
        "$BOOTSTRAP_REPO" --root "$_actual_path" --non-interactive --dry-run 2>&1 | sed 's/^/    /'
        echo "  [currency] would stamp coordinator currency (lib/coordinator-currency.sh)"
    done
    if [[ ${#MISSING_REPOS[@]} -gt 0 ]]; then
        echo ""
        echo "Repos SKIPPED (not on disk) (${#MISSING_REPOS[@]}):"
        for _m in "${MISSING_REPOS[@]}"; do
            echo "  - $_m"
        done
    fi
    echo ""
    echo "=== check-only complete — no changes made ==="
    # A malformed path rejected during parsing is partial success even in a
    # dry-run: the operator's YAML has an entry that would never bootstrap.
    if [[ "${_any_path_rejected}" -eq 1 ]]; then
        echo "  Note: one or more malformed repo paths were rejected during parsing (see warnings above)." >&2
        exit 3
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# SELECT: EXPRESS or CUSTOM
# ---------------------------------------------------------------------------
# EXPRESS: bootstrap all existing repos.
# CUSTOM:  walk per-repo offers.
# Under --non-interactive: auto-select EXPRESS (documented default-with-warning).
# ---------------------------------------------------------------------------

SELECTED_REPOS=()

if [[ $NON_INTERACTIVE -eq 1 ]]; then
    echo ""
    echo "repo-setup: --non-interactive — selecting EXPRESS path (bootstrap all ${#EXISTING_REPOS[@]} repo(s))."
    SELECTED_REPOS=("${EXISTING_REPOS[@]}")
else
    echo ""
    echo "=== /repo-setup --batch — Coordinator Bootstrap ==="
    echo ""
    echo "  Repos discovered in ~/.claude/working-repos.yaml (${#EXISTING_REPOS[@]} on disk):"
    for _r in "${EXISTING_REPOS[@]}"; do
        echo "    - $_r"
    done
    echo ""
    echo "  How would you like to proceed?"
    echo ""
    echo "  [EXPRESS]  Bootstrap all repos above (recommended — safe to re-run, fully reversible)"
    echo "  [CUSTOM]   Choose repos one by one"
    echo ""
    read -r -p "  Choice [E/C, default E]: " _choice
    _choice="${_choice:-E}"

    case "$(printf '%s' "$_choice" | tr '[:lower:]' '[:upper:]')" in
        E|EXPRESS)
            SELECTED_REPOS=("${EXISTING_REPOS[@]}")
            echo "  Express selected — bootstrapping all ${#EXISTING_REPOS[@]} repo(s)."
            ;;
        C|CUSTOM)
            echo ""
            echo "  Per-repo selection:"
            for _repo in "${EXISTING_REPOS[@]}"; do
                read -r -p "  Bootstrap '$_repo'? [Y/n] " _repo_choice
                _repo_choice="${_repo_choice:-Y}"
                case "$(printf '%s' "$_repo_choice" | tr '[:lower:]' '[:upper:]')" in
                    Y|YES)
                        SELECTED_REPOS+=("$_repo")
                        echo "    Added."
                        ;;
                    *)
                        echo "    Skipped."
                        ;;
                esac
            done
            ;;
        *)
            echo "  Unrecognised choice '$_choice' — defaulting to EXPRESS."
            SELECTED_REPOS=("${EXISTING_REPOS[@]}")
            ;;
    esac
fi

if [[ ${#SELECTED_REPOS[@]} -eq 0 ]]; then
    echo ""
    echo "repo-setup: no repos selected. Nothing to do."
    exit 0
fi

# ---------------------------------------------------------------------------
# Source currency helper (for post-bootstrap stamp)
# ---------------------------------------------------------------------------

# shellcheck source=./coordinator-currency.sh
source "$CURRENCY_SH"

# ---------------------------------------------------------------------------
# Bootstrap each selected repo
# ---------------------------------------------------------------------------

SUCCEEDED=()
FAILED=()
SKIPPED_ALREADY_CURRENT=()

chmod +x "$BOOTSTRAP_REPO" 2>/dev/null || true

for _repo in "${SELECTED_REPOS[@]}"; do
    _posix="$(_normalize_path "$_repo")"
    _actual_path="$([[ -d "$_posix" ]] && echo "$_posix" || echo "$_repo")"

    echo ""
    echo "--- Bootstrapping: $_repo"

    # Invoke bootstrap-repo.sh.
    # Hook-respect contract: we do NOT pass --no-verify. bootstrap-repo.sh runs the
    # target repo's hooks exactly as the user would. A hook failure exits non-zero,
    # which we collect and report in the per-repo FAILED summary.
    _bs_exit=0
    "$BOOTSTRAP_REPO" \
        --root "$_actual_path" \
        --non-interactive \
        2>&1 || _bs_exit=$?

    case $_bs_exit in
        0)
            echo "  bootstrap: OK"
            # Stamp coordinator currency, then commit the stamp into the target repo.
            # The stamp write creates docs/coordinator-currency.yaml as an untracked file.
            # Without committing it, subsequent bootstrap-repo.sh runs see a dirty tree
            # and exit 3 — breaking idempotency. Committing the stamp keeps the tree clean.
            _stamp_written=0
            if coordinator_currency_write "$_actual_path" "$PLUGIN_ROOT" 2>&1; then
                _stamp_written=1
            fi
            if [[ $_stamp_written -eq 1 ]]; then
                _stamp_path="${_actual_path}/docs/coordinator-currency.yaml"
                if [[ -f "$_stamp_path" ]]; then
                    # Stage and commit the stamp file if it's new or modified.
                    # Hook-respect contract: no --no-verify. If the target repo's hooks
                    # reject the commit, surface the failure and move to FAILED.
                    _stamp_status="$(git -C "$_actual_path" status --porcelain -- docs/coordinator-currency.yaml 2>/dev/null || true)"
                    if [[ -n "$_stamp_status" ]]; then
                        git -C "$_actual_path" add -- docs/coordinator-currency.yaml 2>/dev/null || true
                        _stamp_commit_exit=0
                        git -C "$_actual_path" commit \
                            -m "chore(coordinator): record currency stamp" \
                            2>&1 || _stamp_commit_exit=$?
                        if [[ $_stamp_commit_exit -ne 0 ]]; then
                            echo "  currency: FAILED — target repo hook rejected currency-stamp commit (exit $_stamp_commit_exit)"
                            echo "  currency: resolve the hook failure in '$_repo' and re-run /repo-setup --batch."
                            FAILED+=("$_repo")
                            continue
                        fi
                        echo "  currency: stamped and committed"
                    else
                        echo "  currency: stamp already current (no commit needed)"
                    fi
                else
                    echo "  currency: stamp write skipped (coordinator-schema-version may be absent)"
                fi
            else
                echo "  currency: stamp failed (non-fatal — bootstrap succeeded)"
            fi
            SUCCEEDED+=("$_repo")
            ;;
        2)
            # bootstrap-repo.sh exits 2 when repo is not git-init'd under --non-interactive.
            # Surface it clearly; not a fatal orchestrator error.
            echo "  bootstrap: SKIPPED (not a git repo — run interactively to be offered git init)"
            SKIPPED_ALREADY_CURRENT+=("$_repo")
            ;;
        *)
            echo "  bootstrap: FAILED (bootstrap-repo.sh exit $_bs_exit)"
            FAILED+=("$_repo")
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

echo ""
echo "=== /repo-setup --batch summary ==="
echo ""
echo "  Succeeded:  ${#SUCCEEDED[@]}"
echo "  Failed:     ${#FAILED[@]}"
echo "  Skipped:    ${#SKIPPED_ALREADY_CURRENT[@]}"
echo "  Not on disk: ${#MISSING_REPOS[@]}"
echo ""

if [[ ${#SUCCEEDED[@]} -gt 0 ]]; then
    echo "  Bootstrapped:"
    for _r in "${SUCCEEDED[@]}"; do
        echo "    OK  $_r"
    done
fi

if [[ ${#SKIPPED_ALREADY_CURRENT[@]} -gt 0 ]]; then
    echo "  Skipped:"
    for _r in "${SKIPPED_ALREADY_CURRENT[@]}"; do
        echo "    --  $_r"
    done
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo "  Failed:"
    for _r in "${FAILED[@]}"; do
        echo "    XX  $_r"
    done
    echo ""
    echo "  One or more repos failed to bootstrap. Check per-repo output above."
    echo "  bootstrap-repo.sh exits:"
    echo "    3 — dirty working tree (commit or stash first)"
    echo "    4 — conflict-warn gate (consumer-modified files detected)"
    echo "    1 — usage/prerequisite error"
    exit 3
fi

echo "  /repo-setup --batch complete."
echo "  Revert any bootstrap commit: git -C <repo> revert HEAD"
# All bootstraps succeeded, but a malformed path was skipped during parsing —
# signal partial success rather than a clean 0.
if [[ "${_any_path_rejected}" -eq 1 ]]; then
    echo "  Note: one or more malformed repo paths were rejected during parsing (see warnings above)." >&2
    exit 3
fi
exit 0
