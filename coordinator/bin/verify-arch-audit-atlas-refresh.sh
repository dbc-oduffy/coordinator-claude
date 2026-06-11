#!/usr/bin/env bash
# verify-arch-audit-atlas-refresh.sh — pre-commit gate helper for
# /architecture-audit Step 6.5. Verifies that the targeted-system atlas page
# is being refreshed (Branch A) or asserted current (Branch B) as part of the
# closeout commit.
#
# Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C1
# Spec backlink: docs/plans/2026-06-08-atlas-attested-clock-split.md (clock split)
#
# Pre-commit gate: reads STAGED content via `git show :<path>` and
# `git diff --cached -- <path>`. Does NOT read HEAD. Reads the intended
# commit-message file ($3 or .git/COMMIT_EDITMSG).
#
# Two-clock semantics (atlas-attested-clock-split plan):
#   Atlas pages carry TWO date clocks in frontmatter:
#     last_mapped:   most recent CONTENT-ROTATION (body rewrite). Bumped only by Branch A.
#     last_attested: most recent CURRENCY assertion. Bumped by BOTH branches.
#
# Behavior:
#   - SKIP   — no atlas page exists for <TARGET_SYSTEM>
#   - PASS branch=A — staged body diff AND staged last_mapped == AUDIT_DATE
#                     AND staged last_attested == AUDIT_DATE
#                     (Branch A evaluated first; B ignored if A satisfies)
#   - PASS branch=B — commit-msg contains `atlas-current-as-of:<AUDIT_DATE>`
#                     AND staged last_attested == AUDIT_DATE
#                     AND zero staged body delta
#                     AND last_mapped UNCHANGED (no last_mapped diff)
#   - FAIL — neither branch satisfied; verbatim multi-line message emitted
#
# Exit code: always 0 (informational — caller decides whether to abort).
#
# Negative-spec: does NOT modify any file; does NOT auto-bump last_mapped or
# last_attested; does NOT touch the health-ledger; does NOT read or write
# `Last full audit`; does NOT read HEAD. The two-clock contract is preserved —
# this gate touches only `Last targeted audit` semantics via the atlas page.
#
# Portability: bash 3.2 + BSD coreutils + Git-Bash per DR-061. No bash-4
# features (declare -A, mapfile, ${v^^}). No GNU-isms (sed -i, grep -P,
# date -d, realpath).

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing — positional only.
# ---------------------------------------------------------------------------
if [[ $# -lt 2 ]]; then
  echo "usage: verify-arch-audit-atlas-refresh.sh AUDIT_DATE TARGET_SYSTEM [COMMIT_MSG_FILE]" >&2
  echo "  COMMIT_MSG_FILE defaults to .git/COMMIT_EDITMSG if absent" >&2
  exit 0
fi

AUDIT_DATE="$1"
TARGET_SYSTEM="$2"
COMMIT_MSG_FILE="${3:-}"

# ---------------------------------------------------------------------------
# Locate repo root.
# ---------------------------------------------------------------------------
REPO_ROOT=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

if [[ -z "$REPO_ROOT" ]]; then
  echo "SKIP — not inside a git work tree"
  exit 0
fi

ATLAS_REL="docs/architecture/systems/${TARGET_SYSTEM}.md"
ATLAS_ABS="$REPO_ROOT/$ATLAS_REL"

# ---------------------------------------------------------------------------
# Atlas page absence → SKIP (Step 6.5 short-circuits in this case).
# ---------------------------------------------------------------------------
if [[ ! -f "$ATLAS_ABS" ]]; then
  echo "SKIP — no atlas page for $TARGET_SYSTEM"
  exit 0
fi

# Resolve commit-message file. If $3 absent, default to .git/COMMIT_EDITMSG.
if [[ -z "$COMMIT_MSG_FILE" ]]; then
  COMMIT_MSG_FILE="$REPO_ROOT/.git/COMMIT_EDITMSG"
fi

# ---------------------------------------------------------------------------
# Read staged atlas content via `git show :<path>`. If the file is unstaged
# or unknown to the index, fall back to empty (treated as no staged content).
# ---------------------------------------------------------------------------
STAGED_CONTENT=$(cd "$REPO_ROOT" && git show ":$ATLAS_REL" 2>/dev/null || echo "")

# Extract staged frontmatter `last_mapped` — mirrors check-arch-audit-staleness.sh
# lines 64-73 idiom: grep -m1 + single-line sed.
STAGED_LAST_MAPPED_LINE=$(printf '%s\n' "$STAGED_CONTENT" \
  | grep -m1 '^last_mapped:' || true)
STAGED_LAST_MAPPED=$(printf '%s\n' "$STAGED_LAST_MAPPED_LINE" \
  | sed 's/^last_mapped:[[:space:]]*//' \
  | sed 's/[[:space:]]*$//')

# Extract staged frontmatter `last_attested` — mirrors last_mapped idiom above.
STAGED_LAST_ATTESTED_LINE=$(printf '%s\n' "$STAGED_CONTENT" \
  | grep -m1 '^last_attested:' || true)
STAGED_LAST_ATTESTED=$(printf '%s\n' "$STAGED_LAST_ATTESTED_LINE" \
  | sed 's/^last_attested:[[:space:]]*//' \
  | sed 's/[[:space:]]*$//')

# ---------------------------------------------------------------------------
# Determine whether the staged diff has body changes (changes past the YAML
# frontmatter block). Frontmatter-only bumps (last_mapped / last_attested /
# grade / etc.) do NOT count as body diff; actual body changes DO.
# ---------------------------------------------------------------------------
STAGED_DIFF=$(cd "$REPO_ROOT" && git diff --cached -- "$ATLAS_REL" 2>/dev/null || echo "")

# Body-diff detection uses frontmatter-position boundary (line-number against
# second '---' marker), NOT content-shape filtering — atlas bodies legitimately
# contain 'key: value' prose and '- item' bullet lists that the prior
# content-shape filter falsely rejected.
#
# Strategy: find the line number of the closing '---' frontmatter delimiter in
# the staged file content, then parse the unified-0 diff hunk headers to check
# whether any post-image lines fall past that boundary.
HAS_BODY_DIFF=0

# Find the line number of the second '---' in staged content (frontmatter end).
FM_END=$(printf '%s\n' "$STAGED_CONTENT" \
  | awk '/^---/{c++; if(c==2){print NR; exit}}')

# Parse the unified-0 diff once for both body-diff detection and last_mapped
# change detection.
DIFF_U0=$(cd "$REPO_ROOT" && git diff --cached -U0 -- "$ATLAS_REL" 2>/dev/null || echo "")

if [ -z "$FM_END" ] || [ "$FM_END" -lt 2 ]; then
  # Malformed frontmatter (no closing ---): conservatively treat any diff as body diff.
  if [[ -n "$STAGED_DIFF" ]]; then
    HAS_BODY_DIFF=1
  fi
else
  # Parse unified-0 diff hunk headers for precise post-image line numbers.
  # Each hunk header: @@ -A,B +C,D @@ (D omitted when 1).
  # C is the post-image start line. Check if the hunk extends past FM_END.
  while IFS= read -r hunk; do
    # Extract the +C,D portion via portable sed.
    plus_part=$(printf '%s' "$hunk" | sed -E 's/^@@ -[^ ]+ \+([0-9]+(,[0-9]+)?) @@.*/\1/')
    c=$(printf '%s' "$plus_part" | cut -d, -f1)
    d=$(printf '%s' "$plus_part" | awk -F, '{print ($2==""?1:$2)}')
    # Any hunk whose post-image start is past FM_END touches the body.
    if [ "$c" -gt "$FM_END" ]; then
      HAS_BODY_DIFF=1
      break
    fi
    # Hunk starting at or before FM_END but extending past it also touches body.
    if [ "$d" -gt 0 ] && [ $(( c + d - 1 )) -gt "$FM_END" ]; then
      HAS_BODY_DIFF=1
      break
    fi
  done <<EOF
$(printf '%s\n' "$DIFF_U0" | grep -E '^@@')
EOF
fi

# ---------------------------------------------------------------------------
# Detect whether last_mapped changed in the staged diff.
# HAS_LAST_MAPPED_DIFF=1 if any +/- line touching `^last_mapped:` appears
# in the unified diff (meaning the value changed). Grep the unified diff for
# added/removed last_mapped lines — any match means the field was touched.
# ---------------------------------------------------------------------------
HAS_LAST_MAPPED_DIFF=0
if printf '%s\n' "$DIFF_U0" | grep -Eq '^[+-]last_mapped:'; then
  HAS_LAST_MAPPED_DIFF=1
fi

# ---------------------------------------------------------------------------
# Branch A check (evaluated first) — atlas was refreshed this pass.
#   - body diff present
#   - staged last_mapped == AUDIT_DATE
#   - staged last_attested == AUDIT_DATE  (real audit IS an attestation)
# ---------------------------------------------------------------------------
if [[ "$HAS_BODY_DIFF" -eq 1 ]] && [[ "$STAGED_LAST_MAPPED" = "$AUDIT_DATE" ]]; then
  if [[ "$STAGED_LAST_ATTESTED" = "$AUDIT_DATE" ]]; then
    echo "PASS branch=A"
    exit 0
  else
    # AC6 teaching-shape failure: body diff + last_mapped bumped but last_attested not bumped.
    echo "FAIL: body diff + last_mapped bumped but last_attested not bumped. A real audit IS an attestation; bump both clocks."
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Branch B check — atlas already current, asserted via commit-message token.
#   - commit-msg file contains literal `atlas-current-as-of:<AUDIT_DATE>`
#     (tolerant of optional whitespace after the colon)
#   - staged last_attested == AUDIT_DATE
#   - zero body delta
#   - last_mapped UNCHANGED (no last_mapped diff — B is bare re-attestation only)
# ---------------------------------------------------------------------------
COMMIT_MSG_CONTENT=""
if [[ -f "$COMMIT_MSG_FILE" ]]; then
  COMMIT_MSG_CONTENT=$(cat "$COMMIT_MSG_FILE" 2>/dev/null || echo "")
fi

HAS_BRANCH_B_TOKEN=0
# Review: single grep covers all token positions including end-of-file without trailing newline.
if printf '%s\n' "$COMMIT_MSG_CONTENT" \
  | grep -Eq "atlas-current-as-of:[[:space:]]*${AUDIT_DATE}"; then
  HAS_BRANCH_B_TOKEN=1
fi

if [[ "$HAS_BRANCH_B_TOKEN" -eq 1 ]] \
  && [[ "$STAGED_LAST_ATTESTED" = "$AUDIT_DATE" ]] \
  && [[ "$HAS_BODY_DIFF" -eq 0 ]] \
  && [[ "$HAS_LAST_MAPPED_DIFF" -eq 0 ]]; then
  echo "PASS branch=B"
  exit 0
fi

# ---------------------------------------------------------------------------
# Neither branch satisfied → verbatim FAIL message (informational; exit 0).
# Both clocks are involved: last_mapped (rotation) and last_attested (currency).
# ---------------------------------------------------------------------------
cat <<EOF
FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied for $TARGET_SYSTEM.
Either (a) refresh docs/architecture/systems/$TARGET_SYSTEM.md inline before closing
(body diff + bump both last_mapped and last_attested to $AUDIT_DATE),
or (b) declare atlas-current-as-of:$AUDIT_DATE in the closeout commit message
(bump last_attested to $AUDIT_DATE only; last_mapped and body unchanged).
EOF
exit 0
