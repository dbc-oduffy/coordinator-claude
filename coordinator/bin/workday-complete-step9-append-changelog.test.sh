#!/usr/bin/env bash
# workday-complete-step9-append-changelog.test.sh — Smoke tests for Step 9 script.
#
# Purpose: verifies all 10 contract cases for workday-complete-step9-append-changelog.sh
# in isolated mktemp fixture repos — NEVER touches the real state/week-changelog/ or
# pushes to origin.
#
# Usage: bash workday-complete-step9-append-changelog.test.sh
# Exit: 0 if all tests pass; non-zero if any fail.
#
# Spec backlink: commands/workday-complete.md § Step 9

set -uo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEP9="${SCRIPT_DIR}/workday-complete-step9-append-changelog.sh"

if [[ ! -f "${STEP9}" ]]; then
  echo "FATAL: step9 script not found at ${STEP9}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FIXTURE_DIRS=()

cleanup() {
  for d in "${FIXTURE_DIRS[@]}"; do
    [[ -d "${d}" ]] && rm -rf "${d}"
  done
}
trap cleanup EXIT

TODAY="$(date -u +%Y-%m-%d)"
MACHINE="test-machine"

# make_fixture_repo: create a minimal git repo with required directory structure.
# Sets FIXTURE_ROOT to the created path.
FIXTURE_ROOT=""
make_fixture_repo() {
  local dir
  dir="$(mktemp -d)"
  FIXTURE_DIRS+=("${dir}")
  FIXTURE_ROOT="${dir}"

  git -C "${dir}" init -q
  git -C "${dir}" config user.email "test@test.com"
  git -C "${dir}" config user.name "Test"
  git -C "${dir}" config commit.gpgsign false

  mkdir -p "${dir}/state/week-changelog"
  mkdir -p "${dir}/state/handoffs"
  mkdir -p "${dir}/state/review-trail"
  mkdir -p "${dir}/archive/daily-summaries"
  mkdir -p "${dir}/archive/review-trail"

  # Initial commit so git log works
  touch "${dir}/state/week-changelog/.keep"
  git -C "${dir}" add -- "${dir}/state/week-changelog/.keep"
  git -C "${dir}" commit -q -m "chore: init"

  # Write a current HEADER.md (not stale)
  cat > "${dir}/state/week-changelog/HEADER.md" <<EOF
Week starting: ${TODAY}
EOF
}

# run_step9: run the step9 script against FIXTURE_ROOT.
# Extra args forwarded to the script.
run_step9() {
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" "$@" 2>/dev/null
}

run_step9_with_stderr() {
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" "$@" 2>&1
}

assert_pass() {
  local name="$1"; shift
  local result="$1"; shift
  local expected="$1"
  if [[ "${result}" == *"${expected}"* ]]; then
    echo "PASS: ${name}"
    (( PASS++ )) || true
  else
    echo "FAIL: ${name}"
    echo "  expected to contain: ${expected}"
    echo "  got: ${result}"
    (( FAIL++ )) || true
  fi
}

assert_exit() {
  local name="$1"
  local actual="$2"
  local want="$3"
  if [[ "${actual}" -eq "${want}" ]]; then
    echo "PASS: ${name} (exit ${actual})"
    (( PASS++ )) || true
  else
    echo "FAIL: ${name} — expected exit ${want}, got ${actual}"
    (( FAIL++ )) || true
  fi
}

assert_file_contains() {
  local name="$1"
  local file="$2"
  local pattern="$3"
  if [[ -f "${file}" ]] && grep -qF "${pattern}" "${file}" 2>/dev/null; then
    echo "PASS: ${name}"
    (( PASS++ )) || true
  else
    echo "FAIL: ${name} — file '${file}' does not contain '${pattern}'"
    (( FAIL++ )) || true
  fi
}

assert_file_not_contains() {
  local name="$1"
  local file="$2"
  local pattern="$3"
  if [[ -f "${file}" ]] && grep -qF "${pattern}" "${file}" 2>/dev/null; then
    echo "FAIL: ${name} — file '${file}' unexpectedly contains '${pattern}'"
    (( FAIL++ )) || true
  else
    echo "PASS: ${name}"
    (( PASS++ )) || true
  fi
}

count_commits_since_init() {
  # Count commits after the "chore: init" commit in the fixture repo
  git -C "${FIXTURE_ROOT}" rev-list --count HEAD 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# TEST 1: Empty day — no handoffs, no daily summary, no review records
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 1: Empty day ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T1: exit 0" "${RC}" 0
assert_pass "T1: stdout block written" "${OUTPUT}" "[step9] block written"
assert_file_contains "T1: Scope is 'no work today'" "${CHANGELOG_FILE}" "no work today"
assert_file_contains "T1: header present" "${CHANGELOG_FILE}" "## ${TODAY} — ${MACHINE}"

# ---------------------------------------------------------------------------
# TEST 2: Stale HEADER — exit 3, SKIPPED reported
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 2: Stale HEADER ==="
make_fixture_repo

# Write a HEADER.md with a date 30 days ago
STALE_DATE=""
if command -v python3 >/dev/null 2>&1; then
  STALE_DATE="$(python3 -c "from datetime import date, timedelta; print(date.fromisoformat('${TODAY}') - timedelta(days=30))")"
else
  # Rough fallback: subtract 30 from day portion (may underflow for early month, acceptable in test)
  STALE_DATE="2026-05-01"
fi

cat > "${FIXTURE_ROOT}/state/week-changelog/HEADER.md" <<EOF
Week starting: ${STALE_DATE}
EOF

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T2: exit 3" "${RC}" 3
assert_pass "T2: stdout SKIPPED" "${OUTPUT}" "SKIPPED"

# ---------------------------------------------------------------------------
# TEST 3: One handoff with Decisions/Blockers extracted verbatim
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 3: Handoff with Decisions/Blockers ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

cat > "${FIXTURE_ROOT}/state/handoffs/${TODAY}-main.md" <<'EOF'
---
kind: daily
Decisions: Chose approach A over B for performance reasons
Blockers: Waiting on infra ticket XYZ-123
---

## Summary

Today we worked on feature X.
EOF

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T3: exit 0" "${RC}" 0
assert_file_contains "T3: Decisions extracted" "${CHANGELOG_FILE}" "Chose approach A over B"
assert_file_contains "T3: Blockers extracted" "${CHANGELOG_FILE}" "Waiting on infra ticket XYZ-123"

# ---------------------------------------------------------------------------
# TEST 4: Reviewed: records present → one line per record
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 4: Reviewed records present ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

# Write a fake review-trail JSON record dated today
cat > "${FIXTURE_ROOT}/state/review-trail/${TODAY}-120000-test.json" <<EOF
{
  "sha_range": "abc1234..def5678",
  "reviewer": "code-reviewer",
  "verdict": "approved",
  "diff_loc": "142"
}
EOF

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T4: exit 0" "${RC}" 0
assert_file_contains "T4: Reviewed line present" "${CHANGELOG_FILE}" "**Reviewed:**"
assert_file_contains "T4: sha_range present" "${CHANGELOG_FILE}" "sha_range=abc1234..def5678"
assert_file_contains "T4: reviewer present" "${CHANGELOG_FILE}" "reviewer=code-reviewer"

# ---------------------------------------------------------------------------
# TEST 5: Non-trivial commits + no review records → fallback Reviewed line
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 5: Non-trivial commits + no records → flag line ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

# Add a non-trivial commit to the fixture repo
touch "${FIXTURE_ROOT}/some-work.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/some-work.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: add some work"

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T5: exit 0" "${RC}" 0
assert_file_contains "T5: fallback Reviewed line" "${CHANGELOG_FILE}" "**Reviewed:** none — flag for /workweek-complete Step 7"

# ---------------------------------------------------------------------------
# TEST 6: All-trivial commits + no review records → Reviewed omitted
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 6: All-trivial commits + no records → Reviewed omitted ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

# Add only trivial commits
touch "${FIXTURE_ROOT}/docs-update.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/docs-update.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "chore: update docs"

touch "${FIXTURE_ROOT}/another-docs.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/another-docs.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "docs: readme tweak"

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T6: exit 0" "${RC}" 0
assert_file_not_contains "T6: Reviewed line absent" "${CHANGELOG_FILE}" "**Reviewed:**"

# ---------------------------------------------------------------------------
# TEST 7: Idempotency — second run with identical input → no-op, no new commit
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 7: Idempotency — second run is a no-op ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

run_step9 --no-push >/dev/null 2>/dev/null
RC1=$?
COMMITS_AFTER_FIRST="$(count_commits_since_init)"

OUTPUT2="$(run_step9 --no-push 2>/dev/null)"
RC2=$?
COMMITS_AFTER_SECOND="$(count_commits_since_init)"

assert_exit "T7: first run exit 0" "${RC1}" 0
assert_exit "T7: second run exit 0" "${RC2}" 0
assert_pass "T7: second run no-op signal" "${OUTPUT2}" "idempotent no-op"

if [[ "${COMMITS_AFTER_FIRST}" -eq "${COMMITS_AFTER_SECOND}" ]]; then
  echo "PASS: T7: no new commit on second run (${COMMITS_AFTER_FIRST} commits)"
  (( PASS++ )) || true
else
  echo "FAIL: T7: expected no new commit; before=${COMMITS_AFTER_FIRST} after=${COMMITS_AFTER_SECOND}"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 8: Idempotency with edit — first commits, then add handoff, second replaces
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 8: Idempotency with edit — second run replaces block ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

# First run: no handoffs
run_step9 --no-push >/dev/null 2>/dev/null
COMMITS_AFTER_FIRST="$(count_commits_since_init)"

# Verify first block has "none" for handoffs
assert_file_contains "T8: first block has no handoffs" "${CHANGELOG_FILE}" "**Handoffs:** none"

# Add a handoff
cat > "${FIXTURE_ROOT}/state/handoffs/${TODAY}-new.md" <<'EOF'
---
kind: daily
Decisions: Used strategy B
Blockers: none
---
EOF

# Second run: should replace the section with new content
OUTPUT2="$(run_step9 --no-push 2>/dev/null)"
RC2=$?
COMMITS_AFTER_SECOND="$(count_commits_since_init)"

assert_exit "T8: second run exit 0" "${RC2}" 0
# Should NOT report no-op
if [[ "${OUTPUT2}" == *"idempotent no-op"* ]]; then
  echo "FAIL: T8: second run unexpectedly reported no-op"
  (( FAIL++ )) || true
else
  echo "PASS: T8: second run did not report no-op"
  (( PASS++ )) || true
fi
assert_file_contains "T8: updated block has handoff" "${CHANGELOG_FILE}" "state/handoffs/${TODAY}-new.md"

# Should be one more commit than after first run
if [[ "${COMMITS_AFTER_SECOND}" -gt "${COMMITS_AFTER_FIRST}" ]]; then
  echo "PASS: T8: second run produced a new commit"
  (( PASS++ )) || true
else
  echo "FAIL: T8: expected new commit after edit; before=${COMMITS_AFTER_FIRST} after=${COMMITS_AFTER_SECOND}"
  (( FAIL++ )) || true
fi

# Changelog should not have duplicate headers
HEADER_COUNT="$(grep -c "## ${TODAY} — ${MACHINE}" "${CHANGELOG_FILE}" 2>/dev/null || echo 0)"
if [[ "${HEADER_COUNT}" -eq 1 ]]; then
  echo "PASS: T8: exactly one section header after replacement"
  (( PASS++ )) || true
else
  echo "FAIL: T8: expected 1 section header, found ${HEADER_COUNT}"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 9: --dry-run — block printed to stdout; no file write; no commit
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 9: --dry-run ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"
COMMITS_BEFORE="$(count_commits_since_init)"

OUTPUT="$(run_step9 --dry-run 2>/dev/null)"
RC=$?
COMMITS_AFTER="$(count_commits_since_init)"

assert_exit "T9: exit 0" "${RC}" 0
assert_pass "T9: block content in stdout" "${OUTPUT}" "## ${TODAY} — ${MACHINE}"
assert_pass "T9: push skipped in stdout" "${OUTPUT}" "skipped (--dry-run)"

# Changelog file must NOT have been written
if [[ ! -f "${CHANGELOG_FILE}" ]]; then
  echo "PASS: T9: no file written in dry-run"
  (( PASS++ )) || true
else
  echo "FAIL: T9: changelog file was written during --dry-run"
  (( FAIL++ )) || true
fi

if [[ "${COMMITS_BEFORE}" -eq "${COMMITS_AFTER}" ]]; then
  echo "PASS: T9: no commit in dry-run"
  (( PASS++ )) || true
else
  echo "FAIL: T9: unexpected commit during --dry-run"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 10: --no-push — file written, committed, but no push attempted
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 10: --no-push ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"
COMMITS_BEFORE="$(count_commits_since_init)"

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?
COMMITS_AFTER="$(count_commits_since_init)"

assert_exit "T10: exit 0" "${RC}" 0
assert_pass "T10: block written" "${OUTPUT}" "[step9] block written"
assert_pass "T10: push skipped" "${OUTPUT}" "skipped (--no-push)"

if [[ -f "${CHANGELOG_FILE}" ]]; then
  echo "PASS: T10: changelog file written"
  (( PASS++ )) || true
else
  echo "FAIL: T10: changelog file not written"
  (( FAIL++ )) || true
fi

if [[ "${COMMITS_AFTER}" -gt "${COMMITS_BEFORE}" ]]; then
  echo "PASS: T10: commit was made"
  (( PASS++ )) || true
else
  echo "FAIL: T10: expected a commit, found none"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Results: ${PASS} PASS / ${FAIL} FAIL"
echo "========================================"

[[ "${FAIL}" -eq 0 ]] && exit 0 || exit 1
