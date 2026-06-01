#!/bin/bash
# workday-start-step0-reconcile.sh — Step 0.4.5 (Reconcile with origin/main).
#
# Called by workday-start-step0.sh after the precedence switch resolves on a
# non-main active branch. Folds origin/main into the current branch so the
# active workstream stays mergeable; never abandons in-progress work.
#
# Exit codes:
#   0 — already-includes / fast-forward / merge succeeded.
#   3 — merge conflict; PM resolves first.
#   1 — unexpected error.

set -euo pipefail

git fetch origin main >&2

CURRENT=$(git branch --show-current)

if git merge-base --is-ancestor origin/main HEAD; then
  echo "ALREADY-CURRENT branch=$CURRENT"
  exit 0
fi

if COORDINATOR_OVERRIDE_BRANCH=1 \
   COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main (ff)" \
   git merge --ff-only origin/main >/dev/null 2>&1; then
  echo "RECONCILED-FF branch=$CURRENT"
  exit 0
fi

if COORDINATOR_OVERRIDE_BRANCH=1 \
   COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main (merge)" \
   git merge --no-ff origin/main \
     -m "reconcile origin/main into $CURRENT (workday-start)" >&2; then
  echo "RECONCILED-MERGE branch=$CURRENT"
  exit 0
fi

git merge --abort >&2 || true
echo "RECONCILE-CONFLICT branch=$CURRENT"
echo "Reconcile with origin/main hit a conflict — surface A/B/C Branch Reconciliation Decision." >&2
exit 3
