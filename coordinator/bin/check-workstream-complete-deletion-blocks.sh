#!/usr/bin/env bash
# check-workstream-complete-deletion-blocks.sh — validate Step 2.67 commit-body blocks against staged reality
#
# Usage: check-workstream-complete-deletion-blocks.sh <prepared-commit-msg-file>
#
# Exit codes:
#   0 — all claims match staged reality (gate green; safe to commit)
#   1 — claim mismatch (one or more Deleted/Kept paths inconsistent with staged set); fix commit body or re-stage
#   2 — usage error (missing arg, msg_file unreadable)
#   3 — environment error (not in a git repo)
#
# Called from /workstream-complete Step 3 step 1.5 between stage and commit.
# The validated file MUST be the same file passed to `git commit -F <file>` in step 2 —
# `git commit -m "..."` is forbidden for this commit (it would let a divergent message
# land that the gate never saw).
#
# Spec: docs/plans/2026-06-15-workstream-complete-self-clean.md (Chunk 6)
# Doctrine: docs/wiki/cruft-sweep-cadence.md § Three-layer design (Layer 3)

set -euo pipefail

# Exit 2 — usage
if [ "$#" -lt 1 ]; then
  printf 'usage: %s <prepared-commit-msg-file>\n' "$0" >&2
  exit 2
fi
msg_file="$1"
if [ ! -r "$msg_file" ]; then
  printf 'cannot read prepared commit message file: %s\n' "$msg_file" >&2
  exit 2
fi

# Exit 3 — environment
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  printf 'not in a git repository (run from inside a repo)\n' >&2
  exit 3
fi

# Block-end pattern: next "Word (Step 2.67):" header OR literal footer.
# Blank lines INSIDE a block do NOT terminate it (paragraph grouping permitted).
# Deleted block: each line is a bare path (no leading whitespace, no separator).
# Kept block: each line is "<path> — <reason>"; we split on the em-dash separator to extract the path.
# F2: explicit awk exit-code handling — tool failure (parse error, missing awk) exits 2,
# not silently passing as if the blocks were empty.
if ! deleted_claimed=$(awk '
  /^Deleted \(Step 2\.67\):/ { in_del=1; in_kept=0; next }
  /^Kept \(Step 2\.67\):/    { in_del=0; in_kept=1; next }
  /^[A-Z][a-z]+ \(Step 2\.67\):/ { in_del=0; in_kept=0; next }
  /^--- end Step 2\.67 blocks ---$/ { in_del=0; in_kept=0; next }
  in_del && /^[^[:space:]]/ { print }
' "$msg_file"); then
  printf 'awk failed parsing Deleted block\n' >&2
  exit 2
fi

# Kept block parsing — POSIX octal escapes for U+2014 em-dash (\342\200\224); gawk extension
# `\xe2\x80\x94` is silently mis-interpreted as literal backslash-x on BSD awk and mawk.
# Malformed Kept lines (no em-dash separator) are flagged with a `MALFORMED:` prefix so the
# bash loop can emit a distinct diagnostic instead of treating the raw line as a path.
if ! kept_claimed=$(awk '
  /^Deleted \(Step 2\.67\):/ { in_del=1; in_kept=0; next }
  /^Kept \(Step 2\.67\):/    { in_del=0; in_kept=1; next }
  /^[A-Z][a-z]+ \(Step 2\.67\):/ { in_del=0; in_kept=0; next }
  /^--- end Step 2\.67 blocks ---$/ { in_del=0; in_kept=0; next }
  in_kept && /^[^[:space:]]/ {
    sep = " \342\200\224 "  # U+2014 em-dash, POSIX octal
    idx = index($0, sep)
    if (idx > 0) print substr($0, 1, idx - 1)
    else print "MALFORMED:" $0
  }
' "$msg_file"); then
  printf 'awk failed parsing Kept block\n' >&2
  exit 2
fi

# Staged reality
staged_deletions=$(git diff --cached --diff-filter=D --name-only 2>/dev/null || true)
staged_all=$(git diff --cached --name-only 2>/dev/null || true)
tracked_at_head=$(git ls-tree -r HEAD --name-only 2>/dev/null || true)

mismatch=0
diagnostic=""

# Every claimed-deleted path MUST be in staged_deletions
while IFS= read -r path; do
  [ -z "$path" ] && continue
  if ! printf '%s\n' "$staged_deletions" | grep -Fxq "$path"; then
    diagnostic+="  Deleted-claim NOT staged for deletion: $path"$'\n'
    mismatch=1
  fi
done <<< "$deleted_claimed"

# Every claimed-kept path MUST exist (either pre-commit at HEAD, or be staged).
# Malformed lines (no em-dash separator) flagged earlier with MALFORMED: prefix get a
# distinct diagnostic so the EM doesn't see the raw line printed as "path."
while IFS= read -r path; do
  [ -z "$path" ] && continue
  case "$path" in
    MALFORMED:*)
      raw="${path#MALFORMED:}"
      diagnostic+="  Kept-line has no em-dash separator (unparseable, expected '<path> \xe2\x80\x94 <reason>'): $raw"$'\n'
      mismatch=1
      ;;
    *)
      if ! { printf '%s\n' "$tracked_at_head" | grep -Fxq "$path" || \
             printf '%s\n' "$staged_all" | grep -Fxq "$path"; }; then
        diagnostic+="  Kept-claim does not exist at HEAD or in staged set: $path"$'\n'
        mismatch=1
      fi
      ;;
  esac
done <<< "$kept_claimed"

# F3: inverse check — if staged deletions exist but the commit body has no Step 2.67 block,
# the EM forgot to write the Deleted block (or wrote it under a different header). The
# gate cannot rule out a legitimate doc-only session, but a session WITH staged deletions
# MUST account for them in a Step 2.67 block per Layer 3 doctrine.
if [ -n "$staged_deletions" ] && ! grep -qE '^(Deleted|Kept) \(Step 2\.67\):' "$msg_file"; then
  diagnostic+="  Staged deletions present but commit body has no Step 2.67 block:"$'\n'
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    diagnostic+="    $path"$'\n'
  done <<< "$staged_deletions"
  diagnostic+="  Layer 3 doctrine requires the block; see Step 2.67 procedure."$'\n'
  mismatch=1
fi

if [ "$mismatch" -eq 1 ]; then
  printf 'workstream-complete Step 2.67 block validation failed:\n%s' "$diagnostic" >&2
  printf '\nFix the commit body to match `git diff --cached` reality, then re-run.\n' >&2
  exit 1
fi
exit 0
