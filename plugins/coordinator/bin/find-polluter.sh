#!/usr/bin/env bash
# Bisection script to find which test creates unwanted files/state
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: ./find-polluter.sh '.git' 'src/**/*.test.ts'
#
# TEST_PATTERN supports bash globstar syntax (** for recursive matching):
#   'src/**/*.test.ts'   — all .test.ts files under src/
#   '**/*.spec.js'       — all .spec.js files anywhere
#   'tests/*.test.ts'    — all .test.ts files directly in tests/
# The pattern is evaluated by bash globstar, not find, so ** works correctly.

set -euo pipefail

# Pre-flight: npm must be available — without it the test loop silently reports "no polluter"
if ! command -v npm > /dev/null 2>&1; then
  echo "Error: npm not found in PATH. Install Node.js/npm before running this script." >&2
  exit 1
fi

if [ $# -ne 2 ]; then
  echo "Usage: $0 <file_to_check> <test_pattern>"
  echo "Example: $0 '.git' 'src/**/*.test.ts'"
  exit 1
fi

POLLUTION_CHECK="$1"
TEST_PATTERN="$2"

echo "Searching for test that creates: $POLLUTION_CHECK"
echo "Test pattern: $TEST_PATTERN"
echo ""

# Get list of test files using bash globstar so ** is handled correctly.
# find -path does not support **, causing silent zero-match false negatives.
shopt -s globstar nullglob
# shellcheck disable=SC2206 — intentional glob expansion with globstar
TEST_FILES=($TEST_PATTERN)
TOTAL=${#TEST_FILES[@]}

if [ "$TOTAL" -eq 0 ]; then
  echo "Error: no test files matched pattern '$TEST_PATTERN'" >&2
  echo "Check that the pattern is correct and you are running from the right directory." >&2
  exit 1
fi

echo "Found $TOTAL test files"
echo ""

# Pre-flight: fail fast if pollution already exists before any test runs
if [ -e "$POLLUTION_CHECK" ]; then
  echo "Error: $POLLUTION_CHECK already exists before testing. Remove it first."
  exit 1
fi

COUNT=0
for TEST_FILE in "${TEST_FILES[@]}"; do
  COUNT=$((COUNT + 1))

  echo "[$COUNT/$TOTAL] Testing: $TEST_FILE"

  # Run the test — suppress output but propagate real failures (exit 1 = test failures are expected/ok)
  npm test "$TEST_FILE" > /dev/null 2>&1 || true  # test failure is expected; npm-not-found already caught above

  # Check if pollution appeared
  if [ -e "$POLLUTION_CHECK" ]; then
    echo ""
    echo "FOUND POLLUTER!"
    echo "   Test: $TEST_FILE"
    echo "   Created: $POLLUTION_CHECK"
    echo ""
    echo "Pollution details:"
    ls -la "$POLLUTION_CHECK"
    echo ""
    echo "To investigate:"
    echo "  npm test $TEST_FILE    # Run just this test"
    echo "  cat $TEST_FILE         # Review test code"
    exit 1
  fi
done

echo ""
echo "No polluter found - all tests clean!"
exit 0
