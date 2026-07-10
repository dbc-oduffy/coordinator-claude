#!/usr/bin/env bash
# bin/lib/exec-bit-scoping.sh — shared intersection logic for exec-bit pre-commit hook.
#
# Defines compute_scoped_fix_paths, used by BOTH:
#   - coordinator-precommit-exec-bit-check (the hook)
#   - tests/test-precommit-exec-bit-scoping.bats (the regression test)
#
# Keeping the logic here ensures the hook and its test cannot silently drift —
# any change to the intersection algorithm is automatically exercised by the
# test on the next run. Do NOT inline copies of this function in either consumer.
#
# Source via the consumer's own directory so it works regardless of cwd:
#   _LIBDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)"
#   source "$_LIBDIR/exec-bit-scoping.sh"
#
# Spec backlink: plugins/coordinator/bin/coordinator-precommit-exec-bit-check

# Review F9 (2026-06-27): bash 4.3+ required for local -n (nameref).
# Fail loud on older bash with brew remediation — DR-148 mandates this guard
# on every bash-4-using script. Plain arithmetic syntax so bash 3.2 can parse
# the check before executing it.
if (( BASH_VERSINFO[0] < 4 || ( BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3 ) )); then
  echo "exec-bit-scoping.sh: requires bash >= 4.3 (brew install bash on macOS)" >&2
  exit 1
fi

# compute_scoped_fix_paths <fix_paths_arrname> <staged_files_arrname> <out_arrname>
#
# Intersection: drift files (fix) that are also part of this commit (staged).
# All three arguments are nameref names (bash 4.3+) — pass the variable names
# as strings, not their values.
#
# Inputs:
#   fix_paths_arrname   — array of repo-relative paths with exec-bit drift
#                         (from exec-bit.test.js assertion output)
#   staged_files_arrname — array of repo-relative paths being committed
#                          (from git diff --cached --name-only --diff-filter=d)
# Output:
#   out_arrname         — array of paths in the intersection; empty if none.
#
# Review F5 (2026-06-27): empty-element defensive guard — `[ -n "$sf" ] || continue`
# prevents empty strings from polluting the staged set (e.g. trailing newline from
# mapfile on an empty git diff output).
compute_scoped_fix_paths() {
  local -n _fix="$1"; local -n _staged="$2"; local -n _scoped="$3"
  declare -A _staged_set
  for sf in "${_staged[@]}"; do
    [ -n "$sf" ] || continue   # Review F5: skip empty entries (defensive)
    _staged_set["$sf"]=1
  done
  _scoped=()
  for p in "${_fix[@]}"; do
    [ -n "$p" ] || continue
    if [ "${_staged_set[$p]+isset}" ]; then _scoped+=("$p"); fi
  done
}
