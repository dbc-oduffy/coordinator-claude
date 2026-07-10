#!/usr/bin/env bash
# parse-resolves-trailer.test.sh — Self-contained tests for parse-resolves-trailer.sh
#
# Purpose: Verifies that parse-resolves-trailer.sh correctly extracts
#          artifact-IDs from a commit's `Resolves:` trailers across the
#          one/multiple/zero cases.
#
# Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C4

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/parse-resolves-trailer.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp git repo, never touches the real repo state
# ---------------------------------------------------------------------------
TMP_REPO="$(mktemp -d)"
cleanup() { rm -rf "$TMP_REPO"; }
trap cleanup EXIT

git -C "$TMP_REPO" init -q
git -C "$TMP_REPO" config user.email "test@example.com"
git -C "$TMP_REPO" config user.name "Test"

# ---------------------------------------------------------------------------
# Test 1: zero Resolves: trailers -> empty output, exit 0
# ---------------------------------------------------------------------------
echo "zero" > "$TMP_REPO/file.txt"
git -C "$TMP_REPO" add file.txt
git -C "$TMP_REPO" commit -q -m "no trailer commit"

zero_sha="$(git -C "$TMP_REPO" rev-parse HEAD)"
set +e
zero_output="$(cd "$TMP_REPO" && bash "$HELPER" "$zero_sha")"
zero_exit=$?
set -e

if [[ "$zero_exit" -eq 0 && -z "$zero_output" ]]; then
  pass "zero trailers: empty output, exit 0"
else
  fail "zero trailers: expected empty output + exit 0, got exit=${zero_exit} output='${zero_output}'"
fi

# ---------------------------------------------------------------------------
# Test 2: one Resolves: trailer -> single artifact-id emitted
# ---------------------------------------------------------------------------
echo "one" > "$TMP_REPO/file.txt"
git -C "$TMP_REPO" add file.txt
git -C "$TMP_REPO" commit -q -m "$(printf 'one trailer commit\n\nResolves: hnd-2026-07-08-abc123\n')"

one_sha="$(git -C "$TMP_REPO" rev-parse HEAD)"
one_output="$(cd "$TMP_REPO" && bash "$HELPER" "$one_sha")"

if [[ "$one_output" == "hnd-2026-07-08-abc123" ]]; then
  pass "one trailer: extracted single artifact-id"
else
  fail "one trailer: expected 'hnd-2026-07-08-abc123', got '${one_output}'"
fi

# ---------------------------------------------------------------------------
# Test 3: multiple Resolves: trailers -> all artifact-ids emitted
# ---------------------------------------------------------------------------
echo "multi" > "$TMP_REPO/file.txt"
git -C "$TMP_REPO" add file.txt
git -C "$TMP_REPO" commit -q -m "$(printf 'multi trailer commit\n\nResolves: hnd-2026-07-08-abc123\nResolves: cmp-2026-07-08-def456\n')"

multi_sha="$(git -C "$TMP_REPO" rev-parse HEAD)"
multi_output="$(cd "$TMP_REPO" && bash "$HELPER" "$multi_sha")"
multi_count="$(printf '%s\n' "$multi_output" | grep -c . || true)"

if printf '%s\n' "$multi_output" | grep -qx 'hnd-2026-07-08-abc123' \
   && printf '%s\n' "$multi_output" | grep -qx 'cmp-2026-07-08-def456' \
   && [[ "$multi_count" -eq 2 ]]; then
  pass "multiple trailers: both artifact-ids extracted, no extras"
else
  fail "multiple trailers: expected 2 ids (hnd-2026-07-08-abc123, cmp-2026-07-08-def456), got '${multi_output}'"
fi

# ---------------------------------------------------------------------------
# Test 4: invalid commit -> non-zero exit
# ---------------------------------------------------------------------------
set +e
(cd "$TMP_REPO" && bash "$HELPER" "not-a-real-commit-sha") >/dev/null 2>&1
invalid_exit=$?
set -e

if [[ "$invalid_exit" -ne 0 ]]; then
  pass "invalid commit: non-zero exit"
else
  fail "invalid commit: expected non-zero exit, got 0"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "----"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
