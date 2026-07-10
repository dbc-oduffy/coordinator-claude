#!/usr/bin/env bash
# SessionStart hook: restore silently-dropped tracked files automatically when
# safe (count ≤ SAFE_THRESHOLD, no sensitive paths), or surface an offer banner
# for human review when the restore would be riskier.
#
# Design-as-offers (detect-and-DO): performs the reversible restore automatically
# on the common low-risk path; falls back to the offer banner on the high-risk
# path (large batch or sensitive paths).
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
# Auto-restore gate: count ≤ SAFE_THRESHOLD AND no sensitive paths
#   → git ls-files -dz | xargs -0 git checkout --   (NUL-delimited; space-safe)
#   → emit concise "restored N file(s)" notice as additionalContext
# Offer-banner gate: count > SAFE_THRESHOLD OR any sensitive path detected
#   → emit offer banner with restore one-liner (human gate warranted)
#
# Sensitive paths: .claude/settings*.json (harness config), *.lock (lockfiles)
# `git checkout --` on an unstaged deletion re-materialises from HEAD; it is
# fully reversible via the reflog.
#
# Skips mid-rebase/merge/cherry-pick, where worktree deletions are expected.
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

# --- Collect unstaged worktree deletions of tracked files (single git call) ---
# Review: code-reviewer (F2) — capture NUL-delimited list once into a temp file to avoid TOCTOU
# between safety-gate snapshot and restore pipeline. bash strips NUL bytes in $(...) so a temp
# file is required to preserve NUL delimiters for xargs -0 reuse.
_NUL_LIST=""
_NUL_LIST=$(mktemp 2>/dev/null) || true
if [[ -n "$_NUL_LIST" ]]; then
  git -C "$GIT_ROOT" ls-files -dz 2>/dev/null >"$_NUL_LIST" || true
  DELETED=$(tr '\0' '\n' <"$_NUL_LIST" | grep -v '^$' || true)
else
  # mktemp unavailable; two-call fallback (TOCTOU window accepted)
  DELETED=$(git -C "$GIT_ROOT" ls-files --deleted 2>/dev/null | grep -v '^$' || true)
fi
[[ -z "$DELETED" ]] && { rm -f "$_NUL_LIST"; exit 0; }

COUNT=$(printf '%s\n' "$DELETED" | wc -l | tr -d ' ')

# --- Safe-restore gate ---
SAFE_THRESHOLD=5

# _has_sensitive_path: returns 0 (true) if any line in $1 matches a sensitive
# pattern. Sensitive: .claude/settings*.json (harness config), *.lock (lockfiles)
_has_sensitive_path() {
  local path
  while IFS= read -r path; do
    case "$path" in
      # Review: code-reviewer (F3) — added */.claude/settings*.json to catch subdirectory occurrences
      .claude/settings*.json|*/.claude/settings*.json|*.lock) return 0 ;;
    esac
  done <<< "$1"
  return 1
}

if [[ "$COUNT" -le "$SAFE_THRESHOLD" ]] && ! _has_sensitive_path "$DELETED"; then
  # Low-risk: auto-restore from HEAD and emit a brief notice.
  # Review: code-reviewer (F1/F2) — restore uses the pre-captured NUL list (TOCTOU fix) and
  # gates the success notice on the actual exit code (false-notice fix). Falls back to a fresh
  # ls-files call only when mktemp was unavailable.
  _restore_ok=false
  if [[ -n "$_NUL_LIST" ]]; then
    xargs -0 git -C "$GIT_ROOT" checkout -- <"$_NUL_LIST" 2>/dev/null && _restore_ok=true
  else
    git -C "$GIT_ROOT" ls-files -dz | xargs -0 git -C "$GIT_ROOT" checkout -- 2>/dev/null && _restore_ok=true
  fi
  rm -f "$_NUL_LIST"
  if [[ "$_restore_ok" == true ]]; then
    printf '\n[check-dropped-tracked-files] Auto-restored %s silently-dropped file(s) from HEAD.\n\n' "$COUNT"
  else
    printf '\n[check-dropped-tracked-files] Restore attempted but could not complete — run: git ls-files -dz | xargs -0 git checkout --\n\n'
  fi
  exit 0
fi

# --- High-risk path: offer banner (human gate warranted) ---

# Build a capped, ║-prefixed file list for the banner (one variable, so the
# remainder line composes cleanly instead of being concatenated inline)
CAP=12
FILE_BLOCK=$(printf '%s\n' "$DELETED" | head -n "$CAP" | sed 's/^/║        /')
REMAINDER=$(( COUNT - CAP ))
if [[ "$REMAINDER" -gt 0 ]]; then
  FILE_BLOCK="${FILE_BLOCK}
║        … and ${REMAINDER} more"
fi

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

rm -f "$_NUL_LIST"
exit 0
