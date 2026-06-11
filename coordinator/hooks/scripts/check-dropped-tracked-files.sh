#!/bin/bash
# SessionStart hook: surface (offer-shaped) tracked files that were silently
# deleted from the working tree — the harness-drop / CRLF-race / concurrent-
# session failure mode that has repeatedly clobbered config in this repo
# (settings.json and package.json were both dropped mid-session 2026-05-28).
#
# Git is the restore net, but only if the drop is NOTICED before the deletion is
# committed or the missing file breaks tooling. This hook makes the drop loud at
# the next boot so it gets restored promptly.
#
# Signal: `git ls-files --deleted` lists tracked files present in the index but
# missing from the working tree — i.e. UNSTAGED worktree deletions. A staged
# deletion (intentional `git rm`) removes the path from the index, so it does NOT
# appear here; this hook is therefore quiet on deliberate removals and fires only
# on the "file vanished" shape.
#
# Offer-shape (design-as-offers): lead with the restore command, not a scold.
# Skips mid-rebase/merge/cherry-pick, where worktree deletions are expected.
#
# Always exits 0 — never blocks session start. Output (raw text) becomes
# additionalContext injected into the session.

# --- Drain stdin (mirror existing hook pattern; we need no field from it) ---
if command -v timeout &>/dev/null; then
  timeout 2 cat >/dev/null 2>&1 || true
else
  cat >/dev/null 2>&1 || true
fi

# --- Locate git root (skip if not in a repo) ---
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

# --- Skip when a multi-step git operation is in flight (deletions expected) ---
GIT_DIR=$(git -C "$GIT_ROOT" rev-parse --git-dir 2>/dev/null) || exit 0
case "$GIT_DIR" in
  /*) : ;;                       # absolute
  *)  GIT_DIR="${GIT_ROOT}/${GIT_DIR}" ;;  # relative → anchor to root
esac
for marker in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
  [[ -e "${GIT_DIR}/${marker}" ]] && exit 0
done

# --- Collect unstaged worktree deletions of tracked files ---
DELETED=$(git -C "$GIT_ROOT" ls-files --deleted 2>/dev/null | grep -v '^$' || true)
[[ -z "$DELETED" ]] && exit 0

COUNT=$(printf '%s\n' "$DELETED" | wc -l | tr -d ' ')

# --- Build a capped, ║-prefixed file list for the banner (one variable, so the
#     remainder line composes cleanly instead of being concatenated inline) ---
CAP=12
FILE_BLOCK=$(printf '%s\n' "$DELETED" | head -n "$CAP" | sed 's/^/║        /')
REMAINDER=$(( COUNT - CAP ))
if [[ "$REMAINDER" -gt 0 ]]; then
  FILE_BLOCK="${FILE_BLOCK}
║        … and ${REMAINDER} more"
fi

# --- Emit the offer ---
# The restore one-liner is NUL-delimited (ls-files -dz | xargs -0) so it survives
# paths containing spaces — `git checkout -- $(git ls-files -d)` word-splits and
# would corrupt such a restore.
cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  ⚠  ${COUNT} TRACKED FILE(S) DELETED FROM THE WORKING TREE (unstaged)
║
║  These are tracked in git but missing on disk — the silent-drop
║  shape (buggy harness update, CRLF race, concurrent session), NOT a
║  deliberate \`git rm\`. If unintended, restore from HEAD before the
║  deletion is committed or the missing file breaks tooling:
║
║      git ls-files -dz | xargs -0 git checkout --
║
║  Files:
${FILE_BLOCK}
║
║  If a deletion IS intentional, stage it (\`git rm <path>\`) to silence
║  this for that file.
╚══════════════════════════════════════════════════════════════════╝

EOF

exit 0
