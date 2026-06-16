#!/usr/bin/env bash
# run-smoke.sh — behavior smoke test for check-workstream-complete-deletion-blocks.sh
#
# Sets up a throwaway git repo via `mktemp -d`, stages expected changes, runs the gate
# against each fixture, asserts exit codes (0 / 1 / 1 / 0 — see expectations below),
# cleans up. Exits 0 if all assertions pass, non-zero with diagnostics otherwise.
#
# Spec: docs/plans/2026-06-15-workstream-complete-self-clean.md (Chunk 6, AC18)

set -euo pipefail

# Resolve paths relative to this script
FIXTURES_DIR="$(cd "$(dirname "$0")" && pwd)"
GATE="$(cd "$FIXTURES_DIR/../.." && pwd)/check-workstream-complete-deletion-blocks.sh"

if [ ! -x "$GATE" ]; then
  printf 'gate script not executable: %s\n' "$GATE" >&2
  exit 2
fi

# Throwaway repo. Plain `mktemp -d` is the portable form across BSD/macOS and GNU/Linux;
# `mktemp -d -t prefix.XXXXXX` has divergent flag semantics across platforms.
repo=$(mktemp -d)
trap 'rm -rf "$repo"' EXIT
cd "$repo"

git init -q
git config user.email smoke@test.local
git config user.name "Smoke Test"

# HEAD-1 baseline — three fixture files exist and are committed
mkdir -p fixture
echo "scratch a" > fixture/scratch-a.md
echo "scratch b" > fixture/scratch-b.md
echo "kept doc" > fixture/kept-doc.md
git add fixture/
git commit -q -m "baseline"

# Stage the deletions the fixtures CLAIM (scratch-a and scratch-b deleted; kept-doc untouched)
git rm -q fixture/scratch-a.md fixture/scratch-b.md

# Track pass/fail
fail_count=0
report() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" -eq "$actual" ]; then
    printf '  OK  %-40s expected=%d actual=%d\n' "$name" "$expected" "$actual"
  else
    printf '  FAIL %-40s expected=%d actual=%d\n' "$name" "$expected" "$actual" >&2
    fail_count=$((fail_count + 1))
  fi
}

# Fixture 1: well-formed (Deleted matches staged, Kept exists at HEAD) → expect 0
set +e
bash "$GATE" "$FIXTURES_DIR/msg-ok-deleted-and-kept.txt" >/dev/null 2>&1
rc=$?
set -e
report "msg-ok-deleted-and-kept.txt" 0 $rc

# Fixture 2: claims a third Deleted path that is NOT staged → expect 1
set +e
bash "$GATE" "$FIXTURES_DIR/msg-unstaged-deleted.txt" >/dev/null 2>&1
rc=$?
set -e
report "msg-unstaged-deleted.txt" 1 $rc

# Fixture 3: claims a Kept path that does not exist anywhere → expect 1
set +e
bash "$GATE" "$FIXTURES_DIR/msg-missing-kept.txt" >/dev/null 2>&1
rc=$?
set -e
report "msg-missing-kept.txt" 1 $rc

# Fixture 4: well-formed body with blank lines inside the Deleted block (paragraph grouping) → expect 0
set +e
bash "$GATE" "$FIXTURES_DIR/msg-with-blank-lines.txt" >/dev/null 2>&1
rc=$?
set -e
report "msg-with-blank-lines.txt" 0 $rc

# Fixture 5: no Step 2.67 blocks at all, but staged deletions exist → expect 1 (inverse check)
set +e
bash "$GATE" "$FIXTURES_DIR/msg-no-blocks.txt" >/dev/null 2>&1
rc=$?
set -e
report "msg-no-blocks.txt" 1 $rc

if [ "$fail_count" -ne 0 ]; then
  printf '\n%d assertion(s) failed.\n' "$fail_count" >&2
  exit 1
fi
printf '\nAll 5 fixtures behaved as expected.\n'
exit 0
