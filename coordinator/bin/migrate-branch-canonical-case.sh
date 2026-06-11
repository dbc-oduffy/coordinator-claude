#!/usr/bin/env bash
# migrate-branch-canonical-case.sh — One-shot rename of mixed-case work/* refs
# to their canonical lowercase form.
#
# Spec backlink: docs/plans/2026-05-07-mixed-case-branch-creation-tripwire.md
#
# Why: on Windows's case-insensitive FS, a ref created via `git checkout -b
# work/STRIKER/...` lands on disk as lowercase but `.git/HEAD` stores the
# mixed-case literal. `git branch --show-current` returns HEAD's stored case;
# `git push origin <that>` fails ref lookup (case-sensitive against canonical).
# The hook now blocks creating new mixed-case refs (cs_is_canonical_branch);
# this script remediates pre-existing ones.
#
# Idempotent: a second invocation finds no mixed-case refs and exits clean.
#
# Usage:
#   bin/migrate-branch-canonical-case.sh                # local rename only
#   bin/migrate-branch-canonical-case.sh --push-cleanup # also delete mixed-case
#                                                       # remote refs and push
#                                                       # canonical form
#
# Exit codes:
#   0 — no-op (no mixed-case refs found) OR migration succeeded
#   1 — usage error
#   2 — migration failed mid-flight (partial; rerun is safe and resumes)

set -uo pipefail

PUSH_CLEANUP=0
case "${1:-}" in
  "")            PUSH_CLEANUP=0 ;;
  --push-cleanup) PUSH_CLEANUP=1 ;;
  -h|--help)
    sed -n '2,/^$/p' "$0"  # print top-of-file usage
    exit 0
    ;;
  *)
    echo "ERROR: unknown argument: $1" >&2
    echo "Usage: $0 [--push-cleanup]" >&2
    exit 1
    ;;
esac

# Override the daily-branch hook for the duration: rename ops would self-deny
# once the canonical-case enforcement is live. We're the legitimate remediation
# path. Logged via the hook's override audit log.
export COORDINATOR_OVERRIDE_BRANCH=1
export COORDINATOR_OVERRIDE_BRANCH_REASON="migrate-branch-canonical-case.sh"

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "ERROR: not in a git repo" >&2
  exit 1
}
cd "$GIT_ROOT"

echo "=== migrate-branch-canonical-case.sh ==="
echo "Repo: $GIT_ROOT"
echo "Mode: $([[ "$PUSH_CLEANUP" == "1" ]] && echo "local + remote cleanup" || echo "local only")"
echo ""

# --- Step 0: HEAD-text fix (the actual failure mode on this repo) -----------
# `.git/HEAD` can store a mixed-case ref name even when the on-disk ref file
# is lowercase. Windows FS resolves case-insensitively so `git status` works,
# but `git push origin <stored-name>` fails ref-lookup against the remote.
# git symbolic-ref rewrites HEAD to point at the canonical name without
# touching the working tree.
HEAD_REF=$(git symbolic-ref HEAD 2>/dev/null || true)
if [[ -n "$HEAD_REF" ]]; then
  HEAD_REF_LC=$(echo "$HEAD_REF" | tr '[:upper:]' '[:lower:]')
  if [[ "$HEAD_REF" != "$HEAD_REF_LC" ]]; then
    # Confirm the canonical form exists as a real ref before pointing HEAD at it.
    if git show-ref --verify --quiet "$HEAD_REF_LC"; then
      echo "HEAD-FIX: $HEAD_REF → $HEAD_REF_LC"
      git symbolic-ref HEAD "$HEAD_REF_LC"
    else
      echo "HEAD-FIX-SKIP: HEAD points at '$HEAD_REF' but canonical '$HEAD_REF_LC' does not exist as a ref"
    fi
  fi
fi

# --- Step 1: Mixed-case ref-file rename (the documented failure mode) -------
# Enumerate local work/* refs. Idempotent: a clean repo has no mixed-case files.
LOCAL_REFS=()
while IFS= read -r _ref; do LOCAL_REFS+=("$_ref"); done < <(git for-each-ref --format='%(refname:short)' 'refs/heads/work/*')

RENAMED=0
SKIPPED=0
FAILED=0

for ref in "${LOCAL_REFS[@]}"; do
  lc=$(echo "$ref" | tr '[:upper:]' '[:lower:]')
  if [[ "$ref" == "$lc" ]]; then
    continue  # already canonical
  fi

  # Mixed-case ref found. Check if canonical sibling already exists.
  if git show-ref --verify --quiet "refs/heads/$lc"; then
    echo "SKIP: '$ref' — canonical sibling '$lc' already exists; remove the mixed-case form manually:"
    echo "       git branch -D '$ref'  # only if its commits are reachable from '$lc'"
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  # Rename. git branch -m updates HEAD if this is the current branch.
  echo "RENAME: $ref → $lc"
  if git branch -m "$ref" "$lc"; then
    RENAMED=$((RENAMED+1))
  else
    echo "  FAIL: rename '$ref' → '$lc' returned non-zero"
    FAILED=$((FAILED+1))
    continue
  fi

  # Remote cleanup if requested.
  if [[ "$PUSH_CLEANUP" == "1" ]]; then
    # Only attempt remote ops if the canonical ref now has an upstream OR if
    # the remote carries the mixed-case ref.
    if git ls-remote --exit-code origin "refs/heads/$ref" > /dev/null 2>&1; then
      echo "  REMOTE-DELETE: origin/$ref"
      if ! git push origin --delete "$ref"; then
        echo "  WARN: remote delete of '$ref' failed (may already be gone)"
      fi
    fi
    echo "  REMOTE-PUSH: origin/$lc"
    if ! git push -u origin "$lc"; then
      echo "  WARN: push of '$lc' returned non-zero (may need re-run)"
    fi
  fi
done

echo ""
echo "=== Summary ==="
echo "  Renamed: $RENAMED"
echo "  Skipped: $SKIPPED"
echo "  Failed:  $FAILED"

if (( FAILED > 0 )); then
  exit 2
fi
exit 0
