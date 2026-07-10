#!/usr/bin/env bash
# rollup-derive.test.sh — self-contained tests for bin/rollup-derive.sh.
#
# Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C5
#
# Builds a bare "origin" + working clone fixture (same shape as
# review-coverage-gate.test.sh), seeds commits carrying `Resolves: <id>`
# trailers, and asserts all four rollup-derive.sh contract tokens plus the
# re-derive-not-cached behaviour (a resolving commit dropping off origin/main
# flips a prior "shipped" verdict to "not-shipped" on the very next call, with
# no stale state surviving).
#
# Test coverage:
#   T1  shipped              — resolving commit is an ancestor of origin/main
#   T2  not-shipped           — resolving commit exists locally but not on origin/main
#   T3  unknown-error         — not inside a git repository at all
#   T4  no-resolving-commits  — zero commits carry the artifact's trailer (vacuous pass)
#   T5  re-derive-not-cached  — a "shipped" verdict flips to "not-shipped" after the
#                               resolving commit's branch is reset off origin/main,
#                               proving no stored/cached state is trusted
#   T6  prefix-collision      — a shorter artifact-id is a proper prefix of a
#                               longer one's trailer value; the resolving-commit
#                               set for the shorter id must NOT include the
#                               longer id's commit (Review: code-reviewer F2 —
#                               regression test for the F1 unanchored-substring
#                               --grep bug)
#
# Usage: bash <this-file>
# Exit:  0 if all tests pass, non-zero on any failure.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/rollup-derive.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "ERROR: subject not found: $SUBJECT" >&2
  exit 1
fi

PASS=0
FAIL=0
_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

# ---------------------------------------------------------------------------
# _make_fixture DIR — build a git repo with a local-bare origin remote.
#
# Structure:
#   $DIR/origin.git  — bare repo (the "remote")
#   $DIR/repo        — working clone of origin, checked out on main
# ---------------------------------------------------------------------------
_make_fixture() {
  local base="$1"

  local origin_dir="$base/origin.git"
  mkdir -p "$origin_dir"
  git -C "$origin_dir" init -q --bare

  local seed_dir="$base/seed"
  git clone -q "$origin_dir" "$seed_dir" 2>/dev/null
  git -C "$seed_dir" config user.email "test@test.local"
  git -C "$seed_dir" config user.name  "Test"
  git -C "$seed_dir" checkout -q -b main 2>/dev/null || git -C "$seed_dir" checkout -q main 2>/dev/null || true
  touch "$seed_dir/.gitkeep"
  git -C "$seed_dir" add -- .gitkeep
  git -C "$seed_dir" commit -q -m "root"
  git -C "$seed_dir" push -q origin main
  rm -rf "$seed_dir"

  local repo_dir="$base/repo"
  git clone -q "$origin_dir" "$repo_dir" 2>/dev/null
  git -C "$repo_dir" config user.email "test@test.local"
  git -C "$repo_dir" config user.name  "Test"
  git -C "$repo_dir" checkout -q main 2>/dev/null || true
}

# Helper: add a commit in $1 (repo dir) with message body $2 (may embed a
# Resolves: trailer). Returns SHA on stdout.
_add_commit_msg() {
  local repo="$1" msg="$2" fname="$3"
  printf 'content\n' >> "$repo/$fname"
  git -C "$repo" add -- "$fname"
  git -C "$repo" commit -q -m "$msg"
  git -C "$repo" rev-parse HEAD
}

_run_subject() {
  local repo="$1"; shift
  RC=0
  OUT=$( (cd "$repo" && bash "$SUBJECT" "$@") 2>"$TMPBASE/stderr" ) || RC=$?
  ERR=$(cat "$TMPBASE/stderr" 2>/dev/null || true)
}

RC=0
OUT=""
ERR=""

# ---------------------------------------------------------------------------
# T1 — shipped: resolving commit pushed to origin/main.
# ---------------------------------------------------------------------------
T1="$TMPBASE/t1"
_make_fixture "$T1"
sha1=$(_add_commit_msg "$T1/repo" "$(printf 'finish artifact\n\nResolves: hnd-t1-aaa111')" "f1.txt")
git -C "$T1/repo" push -q origin main

_run_subject "$T1/repo" hnd-t1-aaa111
token=$(printf '%s\n' "$OUT" | head -1)
shas=$(printf '%s\n' "$OUT" | tail -n +2)

if [[ "$token" == "shipped" && "$RC" -eq 0 ]]; then
  _pass "T1: shipped token + exit 0"
else
  _fail "T1: shipped token + exit 0" "got token='$token' rc=$RC out='$OUT'"
fi

if printf '%s\n' "$shas" | grep -qx "$sha1"; then
  _pass "T1: resolving SHA listed on stdout"
else
  _fail "T1: resolving SHA listed on stdout" "expected $sha1 in: $shas"
fi

# ---------------------------------------------------------------------------
# T2 — not-shipped: resolving commit exists locally but never pushed.
# ---------------------------------------------------------------------------
T2="$TMPBASE/t2"
_make_fixture "$T2"
sha2=$(_add_commit_msg "$T2/repo" "$(printf 'finish artifact\n\nResolves: hnd-t2-bbb222')" "f2.txt")
# Deliberately do NOT push — commit stays off origin/main.

_run_subject "$T2/repo" hnd-t2-bbb222
token2=$(printf '%s\n' "$OUT" | head -1)

if [[ "$token2" == "not-shipped" && "$RC" -eq 0 ]]; then
  _pass "T2: not-shipped token + exit 0"
else
  _fail "T2: not-shipped token + exit 0" "got token='$token2' rc=$RC out='$OUT'"
fi

# ---------------------------------------------------------------------------
# T3 — unknown-error: not inside a git repository at all.
# ---------------------------------------------------------------------------
T3="$TMPBASE/t3"
mkdir -p "$T3/plain-dir"

_run_subject "$T3/plain-dir" hnd-t3-ccc333
token3=$(printf '%s\n' "$OUT" | head -1)

if [[ "$token3" == "unknown-error" ]]; then
  _pass "T3: unknown-error token when not inside a git repo"
else
  _fail "T3: unknown-error token when not inside a git repo" "got token='$token3' rc=$RC out='$OUT'"
fi

# ---------------------------------------------------------------------------
# T4 — no-resolving-commits: zero commits carry the artifact's trailer.
# ---------------------------------------------------------------------------
T4="$TMPBASE/t4"
_make_fixture "$T4"
_add_commit_msg "$T4/repo" "unrelated work, no trailer" "f4.txt" >/dev/null

_run_subject "$T4/repo" hnd-t4-does-not-exist
token4=$(printf '%s\n' "$OUT" | head -1)

if [[ "$token4" == "no-resolving-commits" && "$RC" -eq 0 ]]; then
  _pass "T4: no-resolving-commits token + exit 0 (vacuous pass)"
else
  _fail "T4: no-resolving-commits token + exit 0 (vacuous pass)" "got token='$token4' rc=$RC out='$OUT'"
fi

# ---------------------------------------------------------------------------
# T5 — re-derive-not-cached: a "shipped" verdict flips to "not-shipped" once
# the resolving commit is no longer reachable from origin/main, proving the
# primitive re-derives on every call and never trusts a stale/cached result.
# ---------------------------------------------------------------------------
T5="$TMPBASE/t5"
_make_fixture "$T5"
sha5=$(_add_commit_msg "$T5/repo" "$(printf 'finish artifact\n\nResolves: hnd-t5-ddd444')" "f5.txt")
git -C "$T5/repo" push -q origin main

_run_subject "$T5/repo" hnd-t5-ddd444
token5_before=$(printf '%s\n' "$OUT" | head -1)

if [[ "$token5_before" == "shipped" ]]; then
  _pass "T5 (pre): shipped before origin/main is rewound"
else
  _fail "T5 (pre): shipped before origin/main is rewound" "got token='$token5_before'"
fi

# Simulate a history rewrite: force origin/main back to the root commit,
# dropping sha5 off origin/main. sha5 still exists locally (reachable via
# git log --all), so the trailer search still finds it — but it is no
# longer an ancestor of the (rewound) origin/main.
root_sha=$(git -C "$T5/repo" rev-list --max-parents=0 HEAD | tail -1)
git -C "$T5/repo" push -q --force origin "${root_sha}:refs/heads/main"
git -C "$T5/repo" fetch -q origin

_run_subject "$T5/repo" hnd-t5-ddd444
token5_after=$(printf '%s\n' "$OUT" | head -1)

if [[ "$token5_after" == "not-shipped" ]]; then
  _pass "T5 (post): re-derive flips shipped -> not-shipped after origin/main rewind (no cache trusted)"
else
  _fail "T5 (post): re-derive flips shipped -> not-shipped after origin/main rewind (no cache trusted)" "got token='$token5_after'"
fi

# ---------------------------------------------------------------------------
# T6 — prefix-collision: querying the shorter artifact-id `hnd-abc` must NOT
# match a commit whose trailer value is the longer `hnd-abc-def456` (Review:
# code-reviewer F2 — regression test for the F1 unanchored-substring --grep
# bug: `git log --grep --fixed-strings` alone would substring-match both).
# ---------------------------------------------------------------------------
T6="$TMPBASE/t6"
_make_fixture "$T6"
sha6_short=$(_add_commit_msg "$T6/repo" "$(printf 'finish shorter artifact\n\nResolves: hnd-abc')" "f6a.txt")
sha6_long=$(_add_commit_msg "$T6/repo" "$(printf 'finish longer artifact\n\nResolves: hnd-abc-def456')" "f6b.txt")
git -C "$T6/repo" push -q origin main

_run_subject "$T6/repo" hnd-abc
token6=$(printf '%s\n' "$OUT" | head -1)
shas6=$(printf '%s\n' "$OUT" | tail -n +2)

if [[ "$token6" == "shipped" && "$RC" -eq 0 ]]; then
  _pass "T6: shipped token + exit 0 for shorter artifact-id"
else
  _fail "T6: shipped token + exit 0 for shorter artifact-id" "got token='$token6' rc=$RC out='$OUT'"
fi

if printf '%s\n' "$shas6" | grep -qx "$sha6_short" \
   && ! printf '%s\n' "$shas6" | grep -qx "$sha6_long"; then
  _pass "T6: resolving-commit set contains ONLY the exact-match SHA, not the prefix-collision SHA"
else
  _fail "T6: resolving-commit set contains ONLY the exact-match SHA, not the prefix-collision SHA" "expected only $sha6_short in: $shas6 (must NOT contain $sha6_long)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "PASS=${PASS} FAIL=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
