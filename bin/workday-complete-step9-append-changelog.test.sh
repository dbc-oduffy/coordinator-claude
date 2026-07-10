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
# Rationale for EXAMPLE_ORCHESTRATION_HUB_ROOT sentinel + cd:
#   strangle_route routes to the native cc_invoke op when EXAMPLE_ORCHESTRATION_HUB_ROOT is importable.
#   The native op resolves its own repo root from PWD and writes to the real (example-orchestration-hub)
#   state root — not the fixture — making all fixture-path assertions fail.
#   Setting EXAMPLE_ORCHESTRATION_HUB_ROOT to a non-existent sentinel forces _sf_seam_present to return 1
#   (seam absent) so legacy_append_day runs against the fixture. cd into FIXTURE_ROOT
#   ensures coordinator_state_root resolves via Rule 5 to ${FIXTURE_ROOT}/state (not
#   the real DoE state root) so CHANGELOG_FILE, HEADER_FILE, and HANDOFF_DIR all land
#   in the fixture. T12b and T13b use this same pattern.
run_step9() {
  ( cd "${FIXTURE_ROOT}" && \
    COORDINATOR_ROOT="${FIXTURE_ROOT}" \
    COORDINATOR_MACHINE="${MACHINE}" \
    COORDINATOR_ROOT_WARN_SUPPRESS=1 \
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/nonexistent_c2_test_sentinel" \
    RC_VALIDATE="skipped" \
    RC_PLUGIN_SUITE="n/a" \
      "${BASH}" "${STEP9}" "$@" 2>/dev/null )
}

run_step9_with_stderr() {
  ( cd "${FIXTURE_ROOT}" && \
    COORDINATOR_ROOT="${FIXTURE_ROOT}" \
    COORDINATOR_MACHINE="${MACHINE}" \
    COORDINATOR_ROOT_WARN_SUPPRESS=1 \
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/nonexistent_c2_test_sentinel" \
    RC_VALIDATE="skipped" \
    RC_PLUGIN_SUITE="n/a" \
      "${BASH}" "${STEP9}" "$@" 2>&1 )
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
# C4: Scope line omitted when no explicit override (was "no work today" in old code)
assert_file_not_contains "T1: Scope line absent (C4 omit-by-default)" "${CHANGELOG_FILE}" "**Scope:**"
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

# Review: code-reviewer — add a non-trivial commit so HAS_NON_TRIVIAL=true; without this
# the fixture has no non-trivial commits and the Reviewed line is omitted entirely when
# list-review-trail-records.sh is absent, producing an ambiguous diagnostic (F11).
touch "${FIXTURE_ROOT}/real-work.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/real-work.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: real work for T4"

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
# Review: code-reviewer — known ambiguity: two no-op exit paths exist in step9:
# (1) section-byte-equal path (line ~569), (2) staged-files-empty path (line ~663).
# T7 asserts the "idempotent no-op" message but cannot discriminate which path fired.
# A broken byte-comparison would still produce a passing test via the staged-files net.
# To fully discriminate, instrument the two paths with distinct messages (F13).
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
# Review: code-reviewer — verify replaced section content is byte-correct (F12)
assert_file_contains "T8: decisions replaced" "${CHANGELOG_FILE}" "Used strategy B"
assert_file_not_contains "T8: old handoffs line absent" "${CHANGELOG_FILE}" "**Handoffs:** none"

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
# TEST 11: Absent HEADER.md — staleness guard skipped, block still written
# ---------------------------------------------------------------------------
# Review: code-reviewer — the guard at line ~118 (skip staleness when HEADER absent)
# was never exercised; make_fixture_repo always writes HEADER.md (F17).
echo ""
echo "=== TEST 11: Absent HEADER.md — staleness guard skipped ==="
make_fixture_repo
CHANGELOG_FILE="${FIXTURE_ROOT}/state/week-changelog/${TODAY}-${MACHINE}.md"

# Remove the HEADER.md that make_fixture_repo wrote
rm "${FIXTURE_ROOT}/state/week-changelog/HEADER.md"

OUTPUT="$(run_step9 --no-push 2>/dev/null)"
RC=$?

assert_exit "T11: exit 0" "${RC}" 0
assert_pass "T11: block written despite absent HEADER" "${OUTPUT}" "[step9] block written"
assert_file_contains "T11: header present in changelog" "${CHANGELOG_FILE}" "## ${TODAY} — ${MACHINE}"

# ---------------------------------------------------------------------------
# TEST 12a: --dry-run --for-date past-day → **Backfilled:** in stdout (C2 block content)
# ---------------------------------------------------------------------------
# --dry-run exits before strangle_route (Zone B/C), so compose_block() is always exercised
# directly and the block is emitted to stdout. This test is portable regardless of whether
# ExampleOrchestrationHub is installed on the machine running the test.
echo ""
echo "=== TEST 12a: dry-run backfill → **Backfilled:** in stdout (C2 block content) ==="
make_fixture_repo

PAST_DATE="2026-01-15"

T12A_RC=0
T12A_OUTPUT="$(COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" --dry-run --for-date "${PAST_DATE}" 2>/dev/null)" || T12A_RC=$?

assert_exit "T12a: dry-run exit 0" "${T12A_RC}" 0

if [[ "${T12A_OUTPUT}" == *"**Backfilled:**"* ]]; then
  echo "PASS: T12a: **Backfilled:** line present in dry-run stdout"
  (( PASS++ )) || true
else
  echo "FAIL: T12a: **Backfilled:** line missing from dry-run stdout"
  echo "  block: ${T12A_OUTPUT}"
  (( FAIL++ )) || true
fi

# The line must reference FOR_DATE.
if [[ "${T12A_OUTPUT}" == *"ceremony not run on ${PAST_DATE}"* ]]; then
  echo "PASS: T12a: Backfilled line references FOR_DATE (${PAST_DATE})"
  (( PASS++ )) || true
else
  echo "FAIL: T12a: Backfilled line does not reference FOR_DATE (${PAST_DATE})"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 12b: legacy-path backfill → [backfill] commit subject + block in fixture (C2 commit)
# ---------------------------------------------------------------------------
# strangle_route routes Zone B to the ExampleOrchestrationHub native op when installed, writing to the
# real state root. To test Zone C (commit) via the fixture, force legacy path by setting
# EXAMPLE_ORCHESTRATION_HUB_ROOT to a non-existent dir — _sf_seam_present then fails the python import probe
# and falls back to legacy_append_day. Also run with cwd=fixture so coordinator_state_root
# resolves to the fixture state root.
echo ""
echo "=== TEST 12b: legacy backfill run → [backfill] commit subject (C2 commit) ==="
make_fixture_repo

BACKFILL_CHANGELOG_FIXTURE="${FIXTURE_ROOT}/state/week-changelog/${PAST_DATE}-${MACHINE}.md"

T12B_RC=0
T12B_OUTPUT="$(cd "${FIXTURE_ROOT}" && \
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="/nonexistent_c2_test_sentinel" \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" --no-push --for-date "${PAST_DATE}" 2>/dev/null)" || T12B_RC=$?

assert_exit "T12b: legacy backfill exit 0" "${T12B_RC}" 0

# The changelog file must exist in the fixture (legacy Zone-B wrote it there).
if [[ -f "${BACKFILL_CHANGELOG_FIXTURE}" ]]; then
  echo "PASS: T12b: changelog file written to fixture"
  (( PASS++ )) || true
else
  echo "FAIL: T12b: changelog file missing from fixture (legacy Zone-B may not have run)"
  (( FAIL++ )) || true
fi

# The commit subject in the fixture repo must contain [backfill].
T12B_COMMIT_MSG="$(git -C "${FIXTURE_ROOT}" log --format="%s" -1 2>/dev/null || echo "")"
if [[ "${T12B_COMMIT_MSG}" == *"[backfill]"* ]]; then
  echo "PASS: T12b: commit subject contains [backfill] token"
  (( PASS++ )) || true
else
  echo "FAIL: T12b: commit subject missing [backfill] token (got: '${T12B_COMMIT_MSG}')"
  (( FAIL++ )) || true
fi

# Commit subject must also reference the past date.
if [[ "${T12B_COMMIT_MSG}" == *"${PAST_DATE}"* ]]; then
  echo "PASS: T12b: commit subject references target date (${PAST_DATE})"
  (( PASS++ )) || true
else
  echo "FAIL: T12b: commit subject missing target date '${PAST_DATE}' (got: '${T12B_COMMIT_MSG}')"
  (( FAIL++ )) || true
fi

# The file in the fixture must also contain the **Backfilled:** line (legacy Zone-B).
if [[ -f "${BACKFILL_CHANGELOG_FIXTURE}" ]] && grep -q "\*\*Backfilled:\*\*" "${BACKFILL_CHANGELOG_FIXTURE}" 2>/dev/null; then
  echo "PASS: T12b: **Backfilled:** line present in fixture changelog (legacy Zone-B)"
  (( PASS++ )) || true
else
  echo "FAIL: T12b: **Backfilled:** line missing from fixture changelog (legacy Zone-B)"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 13: today path (no --for-date) has NO backfill markers (C2 negative guard)
# ---------------------------------------------------------------------------
echo ""
echo "=== TEST 13: today path — no backfill markers (C2 negative guard) ==="

# 13a: --dry-run (today) → stdout must NOT contain **Backfilled:** or [backfill].
make_fixture_repo
T13A_OUTPUT="$(COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" --dry-run 2>/dev/null)" || true

if [[ "${T13A_OUTPUT}" == *"**Backfilled:**"* ]]; then
  echo "FAIL: T13a: **Backfilled:** unexpectedly present in today dry-run stdout"
  (( FAIL++ )) || true
else
  echo "PASS: T13a: **Backfilled:** absent from today dry-run stdout (correct)"
  (( PASS++ )) || true
fi

# 13b: legacy-path today run → commit subject must NOT contain [backfill].
make_fixture_repo
T13B_RC=0
(cd "${FIXTURE_ROOT}" && \
  COORDINATOR_ROOT="${FIXTURE_ROOT}" \
  COORDINATOR_MACHINE="${MACHINE}" \
  COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  EXAMPLE_ORCHESTRATION_HUB_ROOT="/nonexistent_c2_test_sentinel" \
  RC_VALIDATE="skipped" \
  RC_PLUGIN_SUITE="n/a" \
    "${BASH}" "${STEP9}" --no-push 2>/dev/null) || T13B_RC=$?

assert_exit "T13b: legacy today run exit 0" "${T13B_RC}" 0

T13B_COMMIT_MSG="$(git -C "${FIXTURE_ROOT}" log --format="%s" -1 2>/dev/null || echo "")"
if [[ "${T13B_COMMIT_MSG}" == *"[backfill]"* ]]; then
  echo "FAIL: T13b: commit subject unexpectedly contains [backfill] on today path"
  (( FAIL++ )) || true
else
  echo "PASS: T13b: commit subject has no [backfill] token on today path (correct)"
  (( PASS++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 14 — C4: Scope derivation — omit-by-default + explicit override
# ---------------------------------------------------------------------------
# AC5: **Scope:** synthesizes from completion titles or is omitted; no mid-word
# tip-subject truncation; explicit override honoured.
# Spec backlink: docs/plans/2026-07-07-workday-complete-local-day-and-targeted-wrap.md § C4
echo ""
echo "=== TEST 14 — C4: Scope derivation (omit-by-default + explicit override) ==="

# T14a: no SCOPE_ARG, empty day → **Scope:** line absent
make_fixture_repo
T14A_OUTPUT="$(run_step9 --dry-run 2>/dev/null)"
T14A_RC=$?

assert_exit "T14a: exit 0" "${T14A_RC}" 0
if [[ "${T14A_OUTPUT}" == *"**Scope:**"* ]]; then
  echo "FAIL: T14a: **Scope:** line unexpectedly present with no SCOPE_ARG (empty day)"
  (( FAIL++ )) || true
else
  echo "PASS: T14a: **Scope:** absent with no SCOPE_ARG — omit-by-default (C4)"
  (( PASS++ )) || true
fi

# T14b: no SCOPE_ARG, non-trivial commit present → **Scope:** still absent (no truncated subject)
make_fixture_repo
touch "${FIXTURE_ROOT}/feature.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/feature.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: add non-trivial feature with a long commit message subject line"

T14B_OUTPUT="$(run_step9 --dry-run 2>/dev/null)"
T14B_RC=$?

assert_exit "T14b: exit 0" "${T14B_RC}" 0
if [[ "${T14B_OUTPUT}" == *"**Scope:**"* ]]; then
  echo "FAIL: T14b: **Scope:** present — truncated commit subject must NOT be used (C4)"
  (( FAIL++ )) || true
else
  echo "PASS: T14b: **Scope:** absent even with non-trivial commits — no mid-word truncation (C4)"
  (( PASS++ )) || true
fi

# T14c: explicit SCOPE_ARG positional → **Scope:** line present with exact text
make_fixture_repo
EXPLICIT_SCOPE="integration of new caching layer for session warm-up"
T14C_OUTPUT="$(run_step9 --dry-run "${EXPLICIT_SCOPE}" 2>/dev/null)"
T14C_RC=$?

assert_exit "T14c: exit 0" "${T14C_RC}" 0
if [[ "${T14C_OUTPUT}" == *"**Scope:** ${EXPLICIT_SCOPE}"* ]]; then
  echo "PASS: T14c: explicit SCOPE_ARG honoured — Scope line present with correct text (C4)"
  (( PASS++ )) || true
else
  echo "FAIL: T14c: Scope line missing or wrong text (expected '${EXPLICIT_SCOPE}')"
  echo "  block: ${T14C_OUTPUT}"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 15: --commit-span A..B — Commits count/range/Plans-touched keyed to span (F-A)
# ---------------------------------------------------------------------------
# With --commit-span BASE..TIP, commit count/range AND Plans-touched derive from the
# explicit span, not the derived date window. Creates 3 non-trivial commits; the span
# covers only the last 2 (B and C), so the count (2) is distinguishable from the
# date-window count (4: init + A + B + C), proving the span-keyed path ran.
echo ""
echo "=== TEST 15: --commit-span — Commits count/range/Plans-touched keyed to span ==="
make_fixture_repo

# Commit A: lower bound of span (exclusive); will appear in date window but not span.
touch "${FIXTURE_ROOT}/commit-a.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/commit-a.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: commit A — outside span"
T15_BASE="$(git -C "${FIXTURE_ROOT}" rev-parse HEAD)"

# Commits B and C: inside the span.
touch "${FIXTURE_ROOT}/commit-b.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/commit-b.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: commit B — inside span"

touch "${FIXTURE_ROOT}/commit-c.txt"
git -C "${FIXTURE_ROOT}" add -- "${FIXTURE_ROOT}/commit-c.txt"
git -C "${FIXTURE_ROOT}" commit -q -m "feat: commit C — inside span"
T15_TIP="$(git -C "${FIXTURE_ROOT}" rev-parse HEAD)"

T15_SPAN="${T15_BASE}..${T15_TIP}"
T15_RC=0
T15_OUTPUT="$(run_step9 --dry-run --commit-span "${T15_SPAN}")" || T15_RC=$?

assert_exit "T15: exit 0" "${T15_RC}" 0
# Date-window would count 4 (init + A + B + C); span gives exactly 2 (B and C).
assert_pass "T15: Commits count reflects span (2, not date-window 4)" "${T15_OUTPUT}" "**Commits:** 2"
# Neither B nor C touches docs/plans/; Plans-touched must key to the span too.
assert_pass "T15: Plans-touched derives from span (none)" "${T15_OUTPUT}" "**Plans touched:** none"
# Range field must be present in the Commits line (short SHA, 2-commit form).
if [[ "${T15_OUTPUT}" == *"range:"* ]]; then
  echo "PASS: T15: Commits line contains range field"
  (( PASS++ )) || true
else
  echo "FAIL: T15: Commits line missing range field"
  (( FAIL++ )) || true
fi

# ---------------------------------------------------------------------------
# TEST 16: --commit-span validation — 3-dot range rejected (F-C)
# ---------------------------------------------------------------------------
# The 2-dot-only guard must reject BASE...TIP (symmetric-difference) with exit 1.
echo ""
echo "=== TEST 16: --commit-span 3-dot range rejected (F-C) ==="
make_fixture_repo

T16_RC=0
T16_OUTPUT="$(run_step9 --dry-run --commit-span "abc123...def456")" || T16_RC=$?
assert_exit "T16: 3-dot range rejected (exit 1)" "${T16_RC}" 1

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Results: ${PASS} PASS / ${FAIL} FAIL"
echo "========================================"

[[ "${FAIL}" -eq 0 ]] && exit 0 || exit 1
