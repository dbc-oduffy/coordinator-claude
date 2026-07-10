#!/usr/bin/env bash
# query-records-facets.test.sh — Verify facet-bearing lessons are queryable via --where.
#
# Spec backlink: docs/plans/2026-06-30-lesson-structured-facets-and-emit-metadata-fix.md § C4
#
# Mechanism:
#   1. Writes 2 fixture lessons with distinct trigger/why/how_to_apply values into a
#      temp dir via coordinator-queue-append (QUEUE_APPEND_OUTPUT_ROOT isolation).
#   2. Queries via query-records.js --root <tmpdir> so the reader is pointed at the
#      same temp surface (not the real state/lessons/).
#   3. Asserts positive + negative filters on trigger and how_to_apply facet keys.
#
# Root-isolation mechanism:
#   coordinator-queue-append honours QUEUE_APPEND_OUTPUT_ROOT → writes to
#   <override>/state/lessons/*.yaml (no real-repo pollution).
#   query-records.js --root <path> → detectRoot() uses the supplied path directly
#   (query-records.js:531), then walkGlob reads <root>/state/lessons/*.yaml.
#   The two are wired to the same $TMPROOT so fixture files are always found.
#
# Run: bash ~/.claude/plugins/coordinator/bin/query-records-facets.test.sh
#
# Tests:
#   1. trigger filter returns lesson A, excludes lesson B (positive + negative on trigger).
#   2. how_to_apply filter returns lesson B, excludes lesson A (second facet).
#   3. why filter matches lesson A precisely (third facet, extra coverage).

set -euo pipefail

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR"
QUERY_RECORDS="$BIN_DIR/query-records.js"
QUEUE_APPEND="$BIN_DIR/coordinator-queue-append"

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# ---------------------------------------------------------------------------
# Temp dir lifecycle
# ---------------------------------------------------------------------------
_TMPDIRS=()
cleanup() {
  for d in "${_TMPDIRS[@]+"${_TMPDIRS[@]}"}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

make_tmpdir() {
  local d
  d=$(mktemp -d)
  _TMPDIRS+=("$d")
  echo "$d"
}

# ---------------------------------------------------------------------------
# Setup: create isolated temp lessons surface
# ---------------------------------------------------------------------------
echo "--- Setup: writing fixture lessons into isolated temp surface"

TMPROOT=$(make_tmpdir)
LESSONS_DIR="$TMPROOT/state/lessons"
mkdir -p "$LESSONS_DIR"

# Lesson A — trigger: concurrent-git, why: overlapping-writes, how_to_apply: use-scoped-staging
set +e
QUEUE_APPEND_OUTPUT_ROOT="$TMPROOT" "$QUEUE_APPEND" \
  --schema lessons \
  --title "Test lesson A: concurrent git discipline" \
  --body "Two sessions writing the same path simultaneously causes silent overwrite." \
  --scope "project" \
  --trigger "concurrent-git" \
  --why "overlapping-writes-cause-silent-data-loss" \
  --how-to-apply "use-scoped-staging" \
  2>/dev/null
_APPEND_A=$?
set -e

if [[ $_APPEND_A -ne 0 ]]; then
  echo "ERROR: coordinator-queue-append failed for lesson A (exit $_APPEND_A)" >&2
  exit 1
fi

# Lesson B — trigger: schema-drift, why: validation-gap, how_to_apply: grep-schema-contract
set +e
QUEUE_APPEND_OUTPUT_ROOT="$TMPROOT" "$QUEUE_APPEND" \
  --schema lessons \
  --title "Test lesson B: schema drift detection" \
  --body "Schema fields added without updating the validator go undetected until runtime." \
  --scope "project" \
  --trigger "schema-drift" \
  --why "validation-gap-allows-invalid-records" \
  --how-to-apply "grep-schema-contract" \
  2>/dev/null
_APPEND_B=$?
set -e

if [[ $_APPEND_B -ne 0 ]]; then
  echo "ERROR: coordinator-queue-append failed for lesson B (exit $_APPEND_B)" >&2
  exit 1
fi

# Verify fixtures landed
_LESSON_COUNT=$(ls "$LESSONS_DIR"/*.yaml 2>/dev/null | wc -l | tr -d ' ')
echo "  Fixture lessons written: $_LESSON_COUNT (in $LESSONS_DIR)"
if [[ "$_LESSON_COUNT" -lt 2 ]]; then
  echo "ERROR: expected ≥2 fixture files in $LESSONS_DIR, found $_LESSON_COUNT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helper: run query-records against the temp root
# Sets _QR_OUT (stdout) and _QR_RC (exit code).
# ---------------------------------------------------------------------------
run_query() {
  local where_arg="$1"
  set +e
  _QR_OUT=$(node "$QUERY_RECORDS" --type lesson --root "$TMPROOT" --where "$where_arg" 2>/dev/null)
  _QR_RC=$?
  set -e
}

# ---------------------------------------------------------------------------
# Test 1: trigger=concurrent-git → returns A, excludes B
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 1: --where \"trigger=concurrent-git\" returns lesson A, excludes lesson B"

run_query "trigger=concurrent-git"

if [[ $_QR_RC -ne 0 ]]; then
  fail "Test 1: query-records exited $_QR_RC (expected 0)"
else
  pass "Test 1: query-records exited 0"
fi

if echo "$_QR_OUT" | grep -q "concurrent git discipline"; then
  pass "Test 1: lesson A title present in output"
else
  fail "Test 1: lesson A title NOT found in output — got: $(echo "$_QR_OUT" | head -5)"
fi

if echo "$_QR_OUT" | grep -q "schema drift detection"; then
  fail "Test 1: lesson B title incorrectly present in output (should be filtered out)"
else
  pass "Test 1: lesson B title correctly absent from output"
fi

# ---------------------------------------------------------------------------
# Test 2: trigger=schema-drift → returns B, excludes A
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 2: --where \"trigger=schema-drift\" returns lesson B, excludes lesson A"

run_query "trigger=schema-drift"

if [[ $_QR_RC -ne 0 ]]; then
  fail "Test 2: query-records exited $_QR_RC (expected 0)"
else
  pass "Test 2: query-records exited 0"
fi

if echo "$_QR_OUT" | grep -q "schema drift detection"; then
  pass "Test 2: lesson B title present in output"
else
  fail "Test 2: lesson B title NOT found in output — got: $(echo "$_QR_OUT" | head -5)"
fi

if echo "$_QR_OUT" | grep -q "concurrent git discipline"; then
  fail "Test 2: lesson A title incorrectly present in output (should be filtered out)"
else
  pass "Test 2: lesson A title correctly absent from output"
fi

# ---------------------------------------------------------------------------
# Test 3: how_to_apply=grep-schema-contract → returns B, excludes A
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 3: --where \"how_to_apply=grep-schema-contract\" returns lesson B, excludes lesson A"

run_query "how_to_apply=grep-schema-contract"

if [[ $_QR_RC -ne 0 ]]; then
  fail "Test 3: query-records exited $_QR_RC (expected 0)"
else
  pass "Test 3: query-records exited 0"
fi

if echo "$_QR_OUT" | grep -q "schema drift detection"; then
  pass "Test 3: lesson B title present in output"
else
  fail "Test 3: lesson B title NOT found in output — got: $(echo "$_QR_OUT" | head -5)"
fi

if echo "$_QR_OUT" | grep -q "concurrent git discipline"; then
  fail "Test 3: lesson A title incorrectly present in output (should be filtered out)"
else
  pass "Test 3: lesson A title correctly absent from output"
fi

# ---------------------------------------------------------------------------
# Test 4: why=overlapping-writes-cause-silent-data-loss → returns A, excludes B
# ---------------------------------------------------------------------------
echo ""
echo "--- Test 4: --where \"why=overlapping-writes-cause-silent-data-loss\" returns lesson A, excludes lesson B"

run_query "why=overlapping-writes-cause-silent-data-loss"

if [[ $_QR_RC -ne 0 ]]; then
  fail "Test 4: query-records exited $_QR_RC (expected 0)"
else
  pass "Test 4: query-records exited 0"
fi

if echo "$_QR_OUT" | grep -q "concurrent git discipline"; then
  pass "Test 4: lesson A title present in output"
else
  fail "Test 4: lesson A title NOT found in output — got: $(echo "$_QR_OUT" | head -5)"
fi

if echo "$_QR_OUT" | grep -q "schema drift detection"; then
  fail "Test 4: lesson B title incorrectly present in output (should be filtered out)"
else
  pass "Test 4: lesson B title correctly absent from output"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi
exit 0
