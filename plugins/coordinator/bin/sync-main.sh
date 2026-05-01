#!/usr/bin/env bash
# sync-main.sh — ensure local origin/main ref (and local main when safe) are
#                at the latest pushed state before any branch creation.
#
# Spec backlink: docs/plans/2026-05-01-orphan-branch-prevention.md § 1.1.5
#
# Purpose: the branch-creation invariant. Every branch-creation site in the
# coordinator pipeline calls this before `git checkout -b`. After this script
# succeeds, local main == origin/main regardless of which branch the working
# tree is on — callers can trust `git checkout -b new-branch main`.
#
# Negative-spec: does NOT create branches, does NOT push, does NOT merge
# feature/work branches, does NOT touch anything other than the main ref.

set -euo pipefail

QUIET=0
STRICT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quiet)  QUIET=1;  shift ;;
    --strict) STRICT=1; shift ;;
    --help|-h)
      cat <<'EOF'
Usage: sync-main.sh [OPTIONS]

Ensures local main == origin/main before any branch creation.

Options:
  --quiet     Suppress normal informational output
  --strict    Treat >50-commits-behind warning as a hard error (exit 1)
  --help      Show this help

Exits 0 on success, non-zero when divergence cannot be resolved silently.
Skips silently when not inside a git repository.
EOF
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Guard: must be inside a git repo
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
  exit 0
fi

info() {
  [[ $QUIET -eq 1 ]] && return
  echo "[sync-main] $*" >&2
}

warn() {
  echo "[sync-main] WARNING: $*" >&2
}

die() {
  echo "[sync-main] ERROR: $*" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Verify origin/main is reachable
# ---------------------------------------------------------------------------
if ! git ls-remote --exit-code origin main &>/dev/null; then
  # No remote named origin or no main branch there — silently skip
  info "origin/main not reachable — skipping sync (offline or non-standard remote)"
  exit 0
fi

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || true)

if [[ "$CURRENT_BRANCH" == "main" ]]; then
  # On main: fetch + ff-only pull
  info "On main — fetching and fast-forwarding..."
  git fetch origin main 2>/dev/null

  # Check whether local main is ahead of origin/main
  LOCAL_AHEAD=$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo 0)
  if [[ $LOCAL_AHEAD -gt 0 ]]; then
    die "Local main is ${LOCAL_AHEAD} commit(s) ahead of origin/main. This should never happen — investigate before branching. (Did a previous operation commit directly to main?)"
  fi

  git pull --ff-only origin main 2>/dev/null || \
    die "Fast-forward pull failed. Local main has diverged from origin/main in a way sync-main.sh cannot resolve automatically."

  info "main is now at $(git rev-parse --short HEAD)"

else
  # On a non-main branch: update the local main ref via refspec without checkout
  info "On branch '${CURRENT_BRANCH}' — updating local main ref from origin..."
  git fetch origin "main:main" 2>/dev/null || {
    # fetch with refspec fails when local main is ahead of origin/main
    git fetch origin main 2>/dev/null
    # Check if local main is ahead
    LOCAL_AHEAD=$(git rev-list --count "refs/remotes/origin/main..refs/heads/main" 2>/dev/null || echo 0)
    if [[ $LOCAL_AHEAD -gt 0 ]]; then
      die "Local main is ${LOCAL_AHEAD} commit(s) ahead of origin/main. Investigate before branching."
    fi
    # Otherwise just let the remote ref update
    git fetch origin main 2>/dev/null
  }
  info "Local main ref is now at $(git rev-parse --short main 2>/dev/null || git rev-parse --short origin/main)"
fi

# ---------------------------------------------------------------------------
# Warn if current branch is >50 commits behind updated main
# ---------------------------------------------------------------------------
if [[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "main" ]]; then
  BEHIND=$(git rev-list --count "HEAD..main" 2>/dev/null || echo 0)
  if [[ $BEHIND -gt 50 ]]; then
    if [[ $STRICT -eq 1 ]]; then
      die "Current branch is ${BEHIND} commits behind main. Resolve divergence before proceeding (--strict mode)."
    else
      warn "Current branch '${CURRENT_BRANCH}' is ${BEHIND} commits behind main. Consider rebasing or merging main before creating a new branch from here."
    fi
  fi
fi

info "sync-main complete."
exit 0
