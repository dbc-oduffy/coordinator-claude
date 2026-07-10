#!/usr/bin/env bash
# coordinator-safe-commit.test.sh — Tests for the --blanket foreign-path subtract behaviour.
#
# Covers do_blanket foreign-SUBTRACT semantics: sibling-claimed paths are removed
# from the staged index (not warned) so a blanket sweep captures orphans but never
# absorbs a concurrent sibling EM's in-flight files.
# COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 skips the subtract and sweeps the full tree.
#
# Run: bash ~/.claude/plugins/coordinator/bin/coordinator-safe-commit.test.sh
#
# Spec backlink: docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md § C1a F0/F1.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/coordinator-safe-commit"
LIB="${SCRIPT_DIR}/../lib/coordinator-session.sh"

# ---------------------------------------------------------------------------
# Test framework — matches conventions in bin/tests/test-coordinator-safe-commit.sh
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

run_test() {
  local name="$1"
  local fn="$2"
  echo "--- $name"
  "$fn" && pass "$name" || fail "$name"
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    return 0
  else
    echo "    Expected to contain: ${needle}" >&2
    echo "    In: ${haystack}" >&2
    return 1
  fi
}

assert_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  if ! echo "$haystack" | grep -qF "$needle"; then
    return 0
  else
    echo "    Expected NOT to contain: ${needle}" >&2
    echo "    In: ${haystack}" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Scratch repo setup / teardown
# ---------------------------------------------------------------------------

SCRATCH_DIR=""
ORIG_DIR="$(pwd)"

setup_repo() {
  SCRATCH_DIR=$(mktemp -d)
  cd "$SCRATCH_DIR"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  # Initial commit so HEAD exists
  echo "root" > root.txt
  git add root.txt
  git commit -q -m "init"
}

teardown_repo() {
  cd "$ORIG_DIR"
  if [[ -n "$SCRATCH_DIR" && -d "$SCRATCH_DIR" ]]; then
    rm -rf "$SCRATCH_DIR"
  fi
  SCRATCH_DIR=""
}

# make_session <session_id> <pid> [file1 file2 ...]
#   Creates a fake sibling session directory with the necessary meta.json,
#   touched.txt, and started_at files.  Uses the same layout as the sessions
#   store so cs_live_session_ids / _cs_session_dir resolve correctly against
#   the scratch repo's .git/coordinator-sessions/.
make_session() {
  local sid="$1"
  local pid="$2"
  shift 2
  local sdir="${SCRATCH_DIR}/.git/coordinator-sessions/${sid}"
  mkdir -p "$sdir"
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  # started_at 5 minutes ago so mtime fallback in liveness check works
  local five_min_ago
  if date --version 2>/dev/null | grep -q GNU; then
    five_min_ago=$(date -u -d "5 minutes ago" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "$now")
  else
    five_min_ago=$(date -u -v-5M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "$now")
  fi
  echo "$five_min_ago" > "${sdir}/started_at"
  git rev-parse HEAD 2>/dev/null > "${sdir}/head_at_start" || echo "unknown" > "${sdir}/head_at_start"
  touch "${sdir}/touched.txt"
  cat > "${sdir}/meta.json" <<METAJSON
{
  "session_id": "${sid}",
  "branch": "main",
  "pid": "${pid}",
  "last_activity": "${now}",
  "goal": "test"
}
METAJSON
  for f in "$@"; do
    echo "$f" >> "${sdir}/touched.txt"
  done
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# TF1: No foreign overlap — blanket proceeds silently, no WARN block on stderr.
#
# Current session stages file1.txt; sibling session claims file2.txt (no overlap).
# Expects: exit 0, no WARN in stderr.
test_no_foreign_overlap_silent() {
  setup_repo
  local my_sid="blanket-mine-$$"
  local sib_sid="blanket-sib-$$"

  make_session "$my_sid" "$$"
  make_session "$sib_sid" "99999" "file2.txt"

  echo "mine" > file1.txt
  git add file1.txt    # pre-stage so there is something to commit

  local stderr_out rc
  rc=0
  stderr_out=$(CLAUDE_INVOKING_COMMAND="workstream-start" CLAUDE_SESSION_ID="$my_sid" \
    bash "$HELPER" --blanket "test: no overlap" 2>&1 >/dev/null) || rc=$?

  local head_moved=false
  [[ "$(git rev-parse HEAD)" != "$(git rev-parse HEAD~1 2>/dev/null)" ]] && head_moved=true

  teardown_repo

  [[ $rc -eq 0 ]] \
    && assert_not_contains "TF1-no-warn" "WARN:" "$stderr_out" \
    && [[ "$head_moved" == true ]]
}

# TF2: Foreign overlap, default mode — foreign path is SUBTRACTED (unstaged), own
#      path (mine.txt) IS committed; no WARN emitted; exits 0, HEAD advances.
#
# Current session stages mine.txt + foreign.txt; sibling's touched.txt claims foreign.txt.
# The subtract removes foreign.txt from the index before commit; mine.txt is committed.
test_foreign_overlap_subtracts_and_commits() {
  setup_repo
  local my_sid="blanket-mine-$$"
  local sib_sid="blanket-sib-$$"

  make_session "$my_sid" "$$"
  # Use $$ (a known-alive PID) so cs_live_session_ids treats sibling as live
  make_session "$sib_sid" "$$" "foreign.txt"

  # Both files are staged; do_blanket should subtract foreign.txt, commit only mine.txt
  echo "shared content" > foreign.txt
  echo "mine" > mine.txt
  git add mine.txt foreign.txt

  local stderr_out rc
  rc=0
  stderr_out=$(CLAUDE_INVOKING_COMMAND="workstream-start" CLAUDE_SESSION_ID="$my_sid" \
    bash "$HELPER" --blanket "test: overlap subtract" 2>&1 >/dev/null) || rc=$?

  local head_advanced=false
  local pre_head post_head
  pre_head=$(git rev-parse HEAD~1 2>/dev/null || echo "none")
  post_head=$(git rev-parse HEAD 2>/dev/null || echo "none")
  [[ "$pre_head" != "$post_head" ]] && head_advanced=true

  # foreign.txt must NOT appear in the resulting commit (it was subtracted)
  local committed_files
  committed_files=$(git show --name-only --format="" HEAD 2>/dev/null || true)

  teardown_repo

  [[ $rc -eq 0 ]] \
    && assert_not_contains "TF2-no-warn"           "WARN:"        "$stderr_out" \
    && assert_not_contains "TF2-foreign-not-staged" "foreign.txt" "$committed_files" \
    && assert_contains     "TF2-own-staged"         "mine.txt"    "$committed_files" \
    && [[ "$head_advanced" == true ]]
}

# TF3: Foreign overlap, COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 — subtract is skipped,
#      foreign path IS committed (full sweep), no WARN emitted, exits 0, HEAD advances.
#
# With COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 the subtract block is bypassed entirely,
# so both the foreign-accept.txt and mine2.txt land in the commit.
test_foreign_overlap_accepted_commits_foreign() {
  setup_repo
  local my_sid="blanket-mine-$$"
  local sib_sid="blanket-sib-$$"

  make_session "$my_sid" "$$"
  # Use $$ (a known-alive PID) so cs_live_session_ids treats sibling as live
  make_session "$sib_sid" "$$" "foreign-accept.txt"

  echo "shared content" > foreign-accept.txt
  echo "mine" > mine2.txt
  git add mine2.txt foreign-accept.txt

  local stderr_out rc
  rc=0
  stderr_out=$(COORDINATOR_BLANKET_ACCEPT_FOREIGN=1 \
    CLAUDE_INVOKING_COMMAND="workstream-start" CLAUDE_SESSION_ID="$my_sid" \
    bash "$HELPER" --blanket "test: accept foreign" 2>&1 >/dev/null) || rc=$?

  local head_advanced=false
  local pre_head post_head
  pre_head=$(git rev-parse HEAD~1 2>/dev/null || echo "none")
  post_head=$(git rev-parse HEAD 2>/dev/null || echo "none")
  [[ "$pre_head" != "$post_head" ]] && head_advanced=true

  # With subtract skipped, the foreign path must appear in the commit
  local committed_files
  committed_files=$(git show --name-only --format="" HEAD 2>/dev/null || true)

  teardown_repo

  [[ $rc -eq 0 ]] \
    && assert_not_contains "TF3-no-warn"           "WARN:"              "$stderr_out" \
    && assert_contains     "TF3-foreign-committed"  "foreign-accept.txt" "$committed_files" \
    && [[ "$head_advanced" == true ]]
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

echo "========================================================"
echo " coordinator-safe-commit -- blanket foreign-subtract tests"
echo "========================================================"
echo ""

run_test "TF1: no foreign overlap — silent, exits 0, HEAD advances"                           test_no_foreign_overlap_silent
run_test "TF2: foreign overlap — foreign subtracted, own committed, no WARN, exits 0"         test_foreign_overlap_subtracts_and_commits
run_test "TF3: foreign overlap + ACCEPT_FOREIGN=1 — subtract skipped, foreign committed, no WARN" test_foreign_overlap_accepted_commits_foreign

echo ""
echo "========================================================"
echo " Results: ${PASS} passed, ${FAIL} failed"
echo "========================================================"

if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
fi

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
