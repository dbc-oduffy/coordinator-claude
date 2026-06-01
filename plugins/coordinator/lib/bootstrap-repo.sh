#!/usr/bin/env bash
# coordinator/lib/bootstrap-repo.sh — Git-as-revert bootstrap primitive for one target repo.
#
# Purpose: non-destructive, fully git-revertible pipeline that brings one target
# directory into coordinator scaffolding compliance. The commit this script lands
# (chore(coordinator): bootstrap) is the installation log; `git revert` undoes it
# completely on a pre-existing repo.
#
# Pipeline stages (in order):
#   1. ensure-git    — offer `git init` if absent (declinable; never silent).
#   2. assert-clean  — refuse to proceed on a dirty working tree without surfacing it.
#   3. scaffold      — idempotent scaffold-canonical-structure.sh --root <target>.
#   4. conflict-warn — three-way check-install-divergence.py classifier (percolate UX).
#   5. commit        — discrete labelled `chore(coordinator): bootstrap` unit.
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 2
#
# Contract (trust guarantees):
#   AC3a: Pre-existing repo — bootstrap commit + `git revert` ⇒ working tree
#         bit-identical to pre-bootstrap HEAD.
#   AC3b: git-init'd repo — bootstrap (init + first commit) + teardown ⇒ zero
#         coordinator-authored content remains; residual `.git/` is additive-
#         coordinator-owned and removable via `rm -rf .git/`.
#
# Usage:
#   bootstrap-repo.sh [--root <path>] [--non-interactive] [--dry-run] [--help]
#
# Flags:
#   --root <path>        Target repo root to bootstrap. Defaults to `git
#                        rev-parse --show-toplevel` of the current working dir.
#   --non-interactive    Skip all user prompts; decline git-init offer silently
#                        (mirrors /setup --non-interactive behaviour for chained
#                        callers that cannot present AskUserQuestion). Under this
#                        flag the script exits 0 with a status row if the repo is
#                        not yet a git repo (no init performed).
#   --dry-run            Print the plan; create no files; make no commits.
#   --help | -h          Show this help and exit.
#
# Exit codes:
#   0  Bootstrap complete (or dry-run completed without error).
#   1  Usage error, missing prerequisite, or git not available.
#   2  User declined git-init offer (repo is not a git repo; nothing done).
#   3  Dirty working tree detected; bootstrap refused without user acknowledgement.
#      (Under --non-interactive, exits 3 on a dirty tree — never silently proceeds.)
#   4  Conflict-warn gate fired: consumer-modified or consumer-added files detected.
#      (Printed with full three-way hunk detail; operator must re-run after review.)

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate siblings relative to THIS script
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/../bin"
SCAFFOLD="${BIN_DIR}/scaffold-canonical-structure.sh"
DIVERGENCE_PY="${BIN_DIR}/check-install-divergence.py"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

ROOT_PATH=""
NON_INTERACTIVE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -n '3,/^set -euo pipefail/p' "${BASH_SOURCE[0]}" | grep '^#' | sed 's/^#[[:space:]]\{0,1\}//'
            exit 0
            ;;
        --root)
            if [[ $# -lt 2 ]]; then
                echo "bootstrap-repo.sh: --root requires an argument" >&2
                exit 1
            fi
            ROOT_PATH="$2"
            shift 2
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -*)
            echo "bootstrap-repo.sh: unknown flag: $1" >&2
            exit 1
            ;;
        *)
            echo "bootstrap-repo.sh: unexpected argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

if ! command -v git >/dev/null 2>&1; then
    echo "bootstrap-repo.sh: git is not available on PATH" >&2
    exit 1
fi

if [[ ! -f "$SCAFFOLD" ]]; then
    echo "bootstrap-repo.sh: scaffold-canonical-structure.sh not found at: $SCAFFOLD" >&2
    exit 1
fi

if [[ ! -f "$DIVERGENCE_PY" ]]; then
    echo "bootstrap-repo.sh: check-install-divergence.py not found at: $DIVERGENCE_PY" >&2
    exit 1
fi

# Resolve Python interpreter — use the shared resolver so PYTHON_ARGS (e.g. "-3"
# for the Windows py launcher) are correctly set; a bare `py script.py` without
# -3 defaults to Python 2 on mixed machines.
_BOOTSTRAP_LIB="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
[[ ! -f "$_BOOTSTRAP_LIB" ]] && _BOOTSTRAP_LIB="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
if [[ -f "$_BOOTSTRAP_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_BOOTSTRAP_LIB"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "bootstrap-repo.sh: no python interpreter (python3/python/py) found (required for conflict-warn stage)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve target root
# ---------------------------------------------------------------------------

if [[ -z "$ROOT_PATH" ]]; then
    ROOT_PATH="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        echo "bootstrap-repo.sh: --root not provided and not inside a git repo" >&2
        exit 1
    }
fi

# Normalise path separators on Windows (Git-Bash/MSYS)
ROOT_PATH="${ROOT_PATH//\\//}"

if [[ ! -d "$ROOT_PATH" ]]; then
    echo "bootstrap-repo.sh: target root does not exist: $ROOT_PATH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Dry-run header
# ---------------------------------------------------------------------------

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[bootstrap-repo dry-run] target: $ROOT_PATH"
    echo "[bootstrap-repo dry-run] non-interactive: $NON_INTERACTIVE"
fi

# ---------------------------------------------------------------------------
# Stage 1 — ensure-git
# Offer `git init` if the target directory is not already a git repo.
# Per AC5: never silent; declinable under interactive; skip under --non-interactive.
# ---------------------------------------------------------------------------

IS_GIT_REPO=0
if git -C "$ROOT_PATH" rev-parse --show-toplevel >/dev/null 2>&1; then
    IS_GIT_REPO=1
fi

if [[ $IS_GIT_REPO -eq 0 ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[bootstrap-repo dry-run] stage 1 (ensure-git): NOT a git repo"
        echo "[bootstrap-repo dry-run]   would offer: git init $ROOT_PATH"
        echo "[bootstrap-repo dry-run]   (--non-interactive would decline and exit 2)"
        # For dry-run purposes, treat as if we would init and continue
    elif [[ $NON_INTERACTIVE -eq 1 ]]; then
        echo "bootstrap-repo: $ROOT_PATH is not a git repository." >&2
        echo "  Under --non-interactive, git-init is not offered. Skipping bootstrap." >&2
        echo "  Re-run interactively to be offered git-init." >&2
        exit 2
    else
        echo ""
        echo "bootstrap-repo: $ROOT_PATH is not a git repository."
        echo ""
        echo "  Coordinator scaffolding uses git as the revert substrate — initializing"
        echo "  a git repo is the precondition that makes the bootstrap fully reversible."
        echo "  The .git/ directory is additive and non-destructive; it can be removed"
        echo "  via 'rm -rf .git/' if you later decide you don't want it."
        echo ""
        echo "  [Recommended] Initialize git repo and continue bootstrap"
        echo "  [Skip]        Decline — no changes will be made"
        echo ""
        read -r -p "  Initialize git repo at $ROOT_PATH? [Y/n] " _reply
        _reply="${_reply:-Y}"
        case "$_reply" in
            [Yy]|[Yy][Ee][Ss])
                git -C "$ROOT_PATH" init --quiet
                echo "  git init: done ($ROOT_PATH/.git/ created)"
                IS_GIT_REPO=1
                ;;
            *)
                echo "  Declined. No changes made."
                exit 2
                ;;
        esac
    fi
else
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[bootstrap-repo dry-run] stage 1 (ensure-git): already a git repo"
    fi
fi

# ---------------------------------------------------------------------------
# Stage 2 — assert clean baseline
# Refuse to bootstrap a dirty working tree without surfacing it.
# Under --non-interactive: dirty tree is still an error (exit 3) — never silent.
# ---------------------------------------------------------------------------

if [[ $DRY_RUN -eq 0 ]]; then
    _dirty="$(git -C "$ROOT_PATH" status --porcelain 2>/dev/null || true)"
    if [[ -n "$_dirty" ]]; then
        echo ""
        echo "bootstrap-repo: $ROOT_PATH has uncommitted changes (dirty working tree)."
        echo ""
        echo "$_dirty"
        echo ""
        echo "  Bootstrap requires a clean baseline so that 'git revert' fully restores"
        echo "  the pre-bootstrap state. Please commit or stash your changes first."
        echo ""
        if [[ $NON_INTERACTIVE -eq 1 ]]; then
            echo "  Under --non-interactive: refusing to proceed." >&2
            exit 3
        else
            echo "  [Abort] — stop here and let you clean up (recommended)"
            echo "  [Force] — proceed anyway (git revert guarantee does NOT hold)"
            echo ""
            read -r -p "  Proceed despite dirty tree? [y/N] " _dirty_reply
            _dirty_reply="${_dirty_reply:-N}"
            case "$_dirty_reply" in
                [Yy]|[Yy][Ee][Ss])
                    echo "  Proceeding (git revert guarantee voided)."
                    ;;
                *)
                    echo "  Aborted. No changes made."
                    exit 3
                    ;;
            esac
        fi
    fi
fi

if [[ $DRY_RUN -eq 1 ]]; then
    _dirty_dry="$(git -C "$ROOT_PATH" status --porcelain 2>/dev/null || true)" || true
    if [[ -n "$_dirty_dry" ]]; then
        echo "[bootstrap-repo dry-run] stage 2 (assert-clean): DIRTY TREE — bootstrap would be refused"
    else
        echo "[bootstrap-repo dry-run] stage 2 (assert-clean): working tree is clean"
    fi
fi

# ---------------------------------------------------------------------------
# Stage 3 — scaffold
# Invoke idempotent scaffold-canonical-structure.sh; never clobbers existing content.
# ---------------------------------------------------------------------------

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[bootstrap-repo dry-run] stage 3 (scaffold): would run scaffold-canonical-structure.sh --root $ROOT_PATH"
    "$SCAFFOLD" --dry-run --root "$ROOT_PATH" 2>&1 | sed 's/^/  /'
else
    chmod +x "$SCAFFOLD" 2>/dev/null || true
    _scaffold_out="$("$SCAFFOLD" --root "$ROOT_PATH" 2>&1)" || {
        echo "bootstrap-repo: scaffold-canonical-structure.sh failed:" >&2
        echo "$_scaffold_out" >&2
        # Scaffold failure is advisory per setup.md Phase 3 — do NOT halt the chain.
        echo "  Warning: scaffold exited non-zero; continuing bootstrap (scaffold is advisory)."
    }
    if [[ -n "$_scaffold_out" ]]; then
        echo "$_scaffold_out"
    fi
fi

# ---------------------------------------------------------------------------
# Stage 4 — conflict-warn
# Three-way check-install-divergence.py classifier.
# Percolate UX: "we will overwrite X — check this."
#
# The classifier compares the coordinator source against the target repo's
# coordinator-owned subtree. This check is only meaningful when the target
# was previously bootstrapped (i.e., has a version.txt sentinel), because:
#
#   - First-time bootstrap: scaffold only CREATES new files/dirs — it never
#     clobbers existing content (scaffold-canonical-structure.sh is no-clobber).
#     No consumer-modification risk; classifier would compare entire coordinator
#     source against an unrelated repo tree and produce false positives.
#   - Re-bootstrap (has version.txt): the three-way classifier uses version.txt
#     as the baseline SHA to identify files the consumer has modified since the
#     last bootstrap — exactly where the overwrite-warn is useful.
#
# Negative-spec: do NOT run the divergence check on first-time bootstraps; the
# two-way fallback (no version.txt) walks the entire coordinator source tree
# and false-positively flags unrelated files in the target as "consumer-modified".
# ---------------------------------------------------------------------------

_has_baseline=0
[[ -f "$ROOT_PATH/version.txt" ]] && _has_baseline=1

_conflict_exit=0
if [[ $DRY_RUN -eq 1 ]]; then
    if [[ $_has_baseline -eq 1 ]]; then
        echo "[bootstrap-repo dry-run] stage 4 (conflict-warn): version.txt found — would run check-install-divergence.py"
        echo "  --source $COORDINATOR_ROOT --live $ROOT_PATH"
    else
        echo "[bootstrap-repo dry-run] stage 4 (conflict-warn): no version.txt — first-time bootstrap, skipping classifier"
    fi
elif [[ $_has_baseline -eq 1 ]]; then
    "$PYTHON_BIN" "${PYTHON_ARGS[@]}" "$DIVERGENCE_PY" \
        --source "$COORDINATOR_ROOT" \
        --live "$ROOT_PATH" \
        --format text 2>&1 || _conflict_exit=$?

    # Exit codes per check-install-divergence.py contract:
    #   0 — unchanged + forward-safe only; safe to proceed
    #   2 — no/malformed baseline; two-way clean; safe to proceed
    #   3 — consumer-modified or consumer-added files detected
    if [[ $_conflict_exit -eq 3 ]]; then
        echo ""
        echo "bootstrap-repo: conflict-warn gate FIRED — consumer-modified or consumer-added files detected."
        echo "  The files listed above will be overwritten by the bootstrap scaffold. Check them first."
        echo "  To proceed anyway, remove or reconcile the conflicting files, then re-run bootstrap."
        echo ""
        exit 4
    elif [[ $_conflict_exit -ne 0 && $_conflict_exit -ne 2 ]]; then
        # Unexpected non-zero (e.g. 1 = usage error) — fail loud
        echo "bootstrap-repo: check-install-divergence.py exited with unexpected code: $_conflict_exit" >&2
        exit 1
    fi
else
    # No version.txt: first-time bootstrap. Scaffold is no-clobber; no conflict risk.
    echo "[bootstrap-repo] stage 4 (conflict-warn): first-time bootstrap (no version.txt) — skipping classifier"
fi

# ---------------------------------------------------------------------------
# Stage 5 — commit
# Discrete labelled `chore(coordinator): bootstrap` unit.
# Commits only files written by the scaffold into the TARGET repo (not ~/.claude).
# ---------------------------------------------------------------------------

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[bootstrap-repo dry-run] stage 5 (commit): would commit staged scaffold files"
    echo "  message: chore(coordinator): bootstrap"
    echo "[bootstrap-repo dry-run] done — no changes made"
    exit 0
fi

# Collect newly-created or modified files under the scaffold
_staged_any=0
_untracked="$(git -C "$ROOT_PATH" ls-files --others --exclude-standard 2>/dev/null || true)"
_modified="$(git -C "$ROOT_PATH" diff --name-only 2>/dev/null || true)"

if [[ -n "$_untracked" ]]; then
    # Stage new untracked files (these are the scaffold-created READMEs and dirs)
    while IFS= read -r _f; do
        [[ -z "$_f" ]] && continue
        if git -C "$ROOT_PATH" add -- "$_f" 2>&1; then
            _staged_any=1
        else
            echo "bootstrap-repo: WARNING — failed to stage untracked file: $_f" >&2
        fi
    done <<< "$_untracked"
fi

if [[ -n "$_modified" ]]; then
    # Stage modified tracked files (idempotent re-run updating files)
    while IFS= read -r _f; do
        [[ -z "$_f" ]] && continue
        if git -C "$ROOT_PATH" add -- "$_f" 2>&1; then
            _staged_any=1
        else
            echo "bootstrap-repo: WARNING — failed to stage modified file: $_f" >&2
        fi
    done <<< "$_modified"
fi

# Check if anything is actually staged
_staged_files="$(git -C "$ROOT_PATH" diff --cached --name-only 2>/dev/null || true)"

if [[ -z "$_staged_files" ]]; then
    echo "bootstrap-repo: nothing to commit (scaffold was already up to date)."
    echo "  status: bootstrap already current — no commit made."
    exit 0
fi

# Determine git user config for the commit (use coordinator defaults if absent)
_git_user_name="$(git -C "$ROOT_PATH" config user.name 2>/dev/null || echo "Coordinator")"
_git_user_email="$(git -C "$ROOT_PATH" config user.email 2>/dev/null || echo "coordinator@coordinator")"

GIT_AUTHOR_NAME="$_git_user_name" \
GIT_AUTHOR_EMAIL="$_git_user_email" \
GIT_COMMITTER_NAME="$_git_user_name" \
GIT_COMMITTER_EMAIL="$_git_user_email" \
git -C "$ROOT_PATH" commit \
    -m "chore(coordinator): bootstrap" \
    2>&1

echo ""
echo "bootstrap-repo: bootstrap complete."
echo "  Commit: chore(coordinator): bootstrap"
echo "  Revert: git -C '$ROOT_PATH' revert HEAD   (restores pre-bootstrap state)"
