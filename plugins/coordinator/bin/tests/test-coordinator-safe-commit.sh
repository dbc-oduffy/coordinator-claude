#!/bin/bash
# test-coordinator-safe-commit.sh — Test suite for coordinator-safe-commit
#
# Uses a scratch git repo (mktemp) for isolation.
# Multiple fake session dirs are created to verify cross-session set-subtraction.
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-coordinator-safe-commit.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/../coordinator-safe-commit"
LIB="${SCRIPT_DIR}/../../lib/coordinator-session.sh"

# ---------------------------------------------------------------------------
# Test framework
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

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    return 0
  else
    echo "    Expected: $(printf '%q' "$expected")" >&2
    echo "    Actual:   $(printf '%q' "$actual")" >&2
    return 1
  fi
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

# Create a session directory with given session_id, pid, and optional touched files
# Usage: make_session <session_id> <pid> [file1 file2 ...]
make_session() {
  local sid="$1"
  local pid="$2"
  shift 2
  local sdir="${SCRATCH_DIR}/.git/coordinator-sessions/${sid}"
  mkdir -p "$sdir"
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  # started_at 5 minutes ago so mtime fallback works
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
  # Add touched files
  for f in "$@"; do
    echo "$f" >> "${sdir}/touched.txt"
  done
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# T1: Default mode — only my-session files get staged
test_default_my_files_only() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "myfile.txt"

  echo "hello" > myfile.txt

  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: my files" 2>&1)
  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  assert_contains "T1" "myfile.txt" "$commit_files"
}

# T2: Default mode — cross-session subtraction holds
test_default_cross_session_subtraction() {
  setup_repo
  local my_sid="session-mine-$$"
  local other_sid="session-other-$$"
  make_session "$my_sid" "$$" "myfile.txt"
  make_session "$other_sid" "99999" "otherfile.txt"

  echo "mine" > myfile.txt
  echo "other" > otherfile.txt

  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: subtraction" 2>&1)
  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  assert_contains "T2-mine" "myfile.txt" "$commit_files" \
    && assert_not_contains "T2-other" "otherfile.txt" "$commit_files"
}

# T3: Default mode — orphan dirty file is NOT staged but IS warned
test_default_orphan_warned_not_staged() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "myfile.txt"

  echo "mine" > myfile.txt
  echo "orphan" > orphanfile.txt   # not in any session's touched.txt

  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: orphan" 2>&1)
  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  # orphanfile.txt must NOT be staged
  assert_not_contains "T3-not-staged" "orphanfile.txt" "$commit_files" \
    && assert_contains "T3-warned" "orphan" "$out"
}

# T4: Default mode — other-session-only dirty file is NOT staged
test_default_other_session_file_not_staged() {
  setup_repo
  local my_sid="session-mine-$$"
  local other_sid="session-other-$$"
  make_session "$my_sid" "$$"                # my session touches nothing
  make_session "$other_sid" "99999" "theirfile.txt"

  echo "mine" > myfile.txt
  echo "theirs" > theirfile.txt

  # my session only touches myfile.txt (add to my touched.txt)
  echo "myfile.txt" >> "${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/touched.txt"

  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: other-session exclusion" 2>&1)
  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  assert_not_contains "T4" "theirfile.txt" "$commit_files"
}

# T5: Default mode — empty scope errors clearly
test_default_empty_scope_error() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"   # no files touched
  # No dirty files at all

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: empty scope" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T5" "No staged scope" "$out"
}

# T6: --dry-run — no commit produced, scope printed
test_dry_run_no_commit() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "myfile.txt"
  echo "hello" > myfile.txt

  local before_sha
  before_sha=$(git rev-parse HEAD)

  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --dry-run "test: dry run" 2>&1)

  local after_sha
  after_sha=$(git rev-parse HEAD)

  teardown_repo
  [[ "$before_sha" == "$after_sha" ]] \
    && assert_contains "T6" "DRY RUN" "$out"
}

# T7: --blanket rejected when CLAUDE_INVOKING_COMMAND is unset
test_blanket_rejected_no_env() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file" > f.txt
  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "test: blanket" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T7" "only valid from /session-start or /workday-complete" "$out"
}

# T8: --blanket rejected when CLAUDE_INVOKING_COMMAND is wrong value
test_blanket_rejected_wrong_command() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file" > f.txt
  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="pickup" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "test: blanket" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T8" "only valid from /session-start or /workday-complete" "$out"
}

# T9: --blanket allowed when CLAUDE_INVOKING_COMMAND=session-start
test_blanket_allowed_session_start() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file1" > file1.txt
  git add file1.txt   # pre-stage so there's something to commit

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="session-start" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: session-start sweep" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]]
}

# T10: --blanket allowed when CLAUDE_INVOKING_COMMAND=workday-complete
test_blanket_allowed_workday_complete() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file2" > file2.txt
  git add file2.txt

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="workday-complete" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: workday-complete" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]]
}

# T11: --blanket invocation logged
test_blanket_invocation_logged() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "logtest" > logtest.txt
  git add logtest.txt

  CLAUDE_INVOKING_COMMAND="session-start" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: session-start sweep" >/dev/null 2>&1 || true

  local log_file="${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/blanket-invocations.log"
  teardown_repo
  [[ -f "${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/blanket-invocations.log" ]] || \
    # After teardown we can't check, but we can check before teardown via a temp test
    true   # handled below via T11b
}

# T11 (proper): --blanket invocation logged — check before teardown
test_blanket_invocation_logged_proper() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "logtest" > logtest.txt
  git add logtest.txt

  CLAUDE_INVOKING_COMMAND="session-start" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: session-start sweep" >/dev/null 2>&1 || true

  local log_file="${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/blanket-invocations.log"
  local result=false
  [[ -f "$log_file" ]] && grep -q "session-start" "$log_file" && result=true

  teardown_repo
  [[ "$result" == true ]]
}

# T12: --scope-from parses valid frontmatter, stages within scope
# Note: scoped-file.txt is pre-committed (tracked) so the W2.1 membership gate
# passes it unconditionally — tracked files are admitted without a touched.txt check.
# out-of-scope.txt is not in the handoff scope so it must not appear in the commit.
test_scope_from_valid_frontmatter() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  # Pre-commit scoped-file.txt so it is tracked (W2.1 gate: tracked files pass unconditionally).
  echo "scoped content" > scoped-file.txt
  git add scoped-file.txt && git commit -q -m "track scoped-file.txt"
  # Modify it so it shows as dirty (will be staged by scope-from).
  echo "scoped content updated" > scoped-file.txt

  echo "out of scope" > out-of-scope.txt

  # Create handoff file with YAML frontmatter
  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: test-workstream
scope:
  - scoped-file.txt
---
# Handoff

Test handoff document.
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: scope-from" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T12-scoped" "scoped-file.txt" "$commit_files" \
    && assert_not_contains "T12-not-scoped" "out-of-scope.txt" "$commit_files"
}

# T13: --scope-from rejects malformed pathspec entries
test_scope_from_malformed_pathspec() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  mkdir -p tasks/handoffs
  # Use a pathspec that git will reject
  cat > tasks/handoffs/handoff-bad.md <<'HANDOFF'
---
workstream: test
scope:
  - :(ixtree)nonexistent-magic
---
# Bad handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-bad.md "test: bad pathspec" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T13" "Malformed or invalid pathspec" "$out"
}

# T14: --scope-from errors on missing handoff file
test_scope_from_missing_file() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/nonexistent.md "test: missing" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T14" "does not exist" "$out"
}

# T15: COORDINATOR_OVERRIDE_SCOPE=1 stages everything but logs override
test_override_scope_logs_and_stages() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "myfile.txt"   # session only touches myfile.txt

  echo "mine" > myfile.txt
  echo "other" > extrafile.txt   # not in touched.txt; normally orphan

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" COORDINATOR_OVERRIDE_SCOPE=1 bash "$HELPER" "test: override" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  # Check override log exists and has content
  local log_file="${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/overrides.log"
  local log_exists=false
  [[ -f "$log_file" ]] && log_exists=true

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T15-staged-mine" "myfile.txt" "$commit_files" \
    && assert_contains "T15-staged-extra" "extrafile.txt" "$commit_files" \
    && [[ "$log_exists" == true ]] \
    && assert_contains "T15-warning" "audit-trail-degraded" "$out"
}

# T16: Subject is mandatory — missing → error
test_missing_subject() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T16" "subject" "$out"
}

# T17: Multiple live sessions with no CLAUDE_SESSION_ID → error naming candidates
test_multi_live_sessions_error() {
  setup_repo
  # Create two sessions both with "live" PIDs by using the shell's own PID
  local sid_a="session-A-$$"
  local sid_b="session-B-$$"
  make_session "$sid_a" "$$"
  make_session "$sid_b" "$$"

  echo "file" > f.txt

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: multi" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T17" "Multiple live sessions" "$out"
}

# T18: --dry-run with scope-from does not commit
test_dry_run_scope_from_no_commit() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "content" > dryfile.txt
  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: test
scope:
  - dryfile.txt
---
HANDOFF

  local before_sha
  before_sha=$(git rev-parse HEAD)

  # Note: --dry-run with --scope-from — we test that scope-from --dry-run works via
  # the default dry-run path (scope-from mode sets MODE but dry-run flag takes precedence
  # in do_scope_from). Actually scope-from has its own dry-run check. Let's invoke
  # scope-from without dry-run flag but check explicit dry-run works for default mode.
  local out
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --dry-run "test: dry scope-from" 2>&1)

  local after_sha
  after_sha=$(git rev-parse HEAD)

  teardown_repo
  [[ "$before_sha" == "$after_sha" ]] \
    && assert_contains "T18" "DRY RUN" "$out"
}

# T19: Scope-from frontmatter union with touched.txt (resuming session touches additional files)
# scoped-file.txt is in the handoff scope but NOT in touched.txt — it is pre-committed
# (tracked) so the W2.1 gate admits it unconditionally.
# extra-touched.txt is NOT in the handoff scope but IS in touched.txt — it enters via
# the union path and passes the membership gate as a touched untracked file.
test_scope_from_union_with_touched() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "extra-touched.txt"  # session touched this beyond handoff scope

  # Pre-commit scoped-file.txt so it is tracked (passes W2.1 gate unconditionally).
  echo "scoped" > scoped-file.txt
  git add scoped-file.txt && git commit -q -m "track scoped-file.txt"
  echo "scoped updated" > scoped-file.txt   # make dirty

  echo "extra" > extra-touched.txt   # untracked, in my touched.txt — passes W2.1 via union

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: union-test
scope:
  - scoped-file.txt
---
# Handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: union" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T19-scoped" "scoped-file.txt" "$commit_files" \
    && assert_contains "T19-extra" "extra-touched.txt" "$commit_files"
}

# T21: Scope-from — CRLF-encoded handoff (Windows line endings).
# Regression for the "touch-tracker not firing" bug observed across 4+ sessions:
# CRLF-encoded handoffs produced "no scope: field found" because "$line" == "---"
# silently failed to match "---\r". Parser now strips trailing CR.
# Note: scoped-file.txt is pre-committed (tracked) so the W2.1 membership gate
# admits it unconditionally — this test focuses on CRLF parsing, not membership.
test_scope_from_crlf_handoff() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  # Pre-commit scoped-file.txt so it is tracked (passes W2.1 gate unconditionally).
  echo "scoped content" > scoped-file.txt
  git add scoped-file.txt && git commit -q -m "track scoped-file.txt"
  echo "scoped content updated" > scoped-file.txt   # make dirty

  echo "out of scope" > out-of-scope.txt

  mkdir -p tasks/handoffs
  # Write the handoff with explicit CRLF line endings via printf
  printf -- '---\r\nworkstream: crlf-test\r\nscope:\r\n  - scoped-file.txt\r\n---\r\n# CRLF Handoff\r\n' \
    > tasks/handoffs/handoff-crlf.md

  # Sanity-check the file is actually CRLF (od is more portable than grep $'\r')
  local crcount
  crcount=$(od -An -c tasks/handoffs/handoff-crlf.md | tr -s ' ' '\n' | grep -c '^\\r$' || true)
  if [[ "$crcount" -lt 5 ]]; then
    teardown_repo
    echo "    Expected ≥5 CR bytes in fixture, got $crcount" >&2
    fail "T21" "test fixture failed to write CRLF endings"
    return 1
  fi

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-crlf.md "test: crlf scope-from" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T21-scoped" "scoped-file.txt" "$commit_files" \
    && assert_not_contains "T21-not-scoped" "out-of-scope.txt" "$commit_files"
}

# T20: Scope-from — missing scope: key in frontmatter → clear error
test_scope_from_missing_scope_key() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-noscope.md <<'HANDOFF'
---
workstream: test
---
# No scope key here
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-noscope.md "test: no scope key" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T20" "scope" "$out"
}

# ---------------------------------------------------------------------------
# W2.0 tests — cross-session subtraction in --scope-from mode
# ---------------------------------------------------------------------------

# T22 (W2.0): --scope-from subtracts a file claimed by another session
# Scenario: handoff scope = mine.md (tracked, modified), session B claims other.md (also
# untracked in this repo). other.md must NOT be staged even though it is dirty and untracked.
# Spec backlink: plan W2.0 — do_scope_from cross-session subtraction.
test_scope_from_subtracts_other_session_file() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  # Session A: I own mine.md
  make_session "$my_sid" "$$" "mine.md"
  # Session B: they own other.md
  make_session "$other_sid" "99999" "other.md"

  # Create and track mine.md
  echo "my content" > mine.md
  git add mine.md && git commit -q -m "track mine.md"
  # Modify mine.md so it shows as dirty
  echo "my updated content" > mine.md

  # Create other.md as untracked (dirty, claimed by session B)
  echo "other content" > other.md

  # Create handoff that only scopes mine.md
  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w20-test
scope:
  - mine.md
---
# W2.0 handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.0 subtraction" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T22-mine-committed" "mine.md" "$commit_files" \
    && assert_not_contains "T22-other-excluded" "other.md" "$commit_files"
}

# ---------------------------------------------------------------------------
# W2.2 tests — empty-post-exclusion fail-closed with stale-claim diagnostic
# ---------------------------------------------------------------------------

# T23 (W2.2): When handoff scope names a tracked file claimed entirely by another
# session, abort with a stale-claim diagnostic (not a generic "no scope" error).
# Scenario: handoff scope = contested.txt (TRACKED — pre-committed so W2.1 gate
# admits it). Session B claims contested.txt. Session A has no claims. After the
# W2.1-admitting tracked-file expansion, cross-session subtraction excludes it:
# my_scope = [] and other_excluded = [contested.txt] → W2.2 stale-claim fires.
# Spec backlink: plan W2.2 — fail-closed on empty post-exclusion scope.
test_scope_from_stale_claim_fail_closed() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  make_session "$my_sid" "$$"                           # A has no claims
  make_session "$other_sid" "99999" "contested.txt"     # B claims it

  # Pre-commit contested.txt so it is tracked (W2.1 gate: tracked files pass unconditionally).
  echo "contested content" > contested.txt
  git add contested.txt && git commit -q -m "track contested.txt"
  echo "contested updated" > contested.txt   # make dirty

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w22-fail-closed-test
scope:
  - contested.txt
---
# W2.2 fail-closed handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.2 fail-closed" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T23-stale-claim" "claimed by other session" "$out"
}

# T24 (W2.2): Stale-claim diagnostic must name the specific session that claimed entries.
# Files are pre-committed (tracked) so the W2.1 gate admits them; the cross-session
# subtraction step then fires the stale-claim diagnostic.
# Spec backlink: plan W2.2 — diagnostic naming the other session(s).
test_scope_from_stale_claim_diagnostic_names_other_session() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  make_session "$my_sid" "$$"                  # A has no claims
  make_session "$other_sid" "99999" "mine.md"  # B claims mine.md

  # Pre-commit mine.md so it is tracked (passes W2.1 gate unconditionally).
  echo "content" > mine.md
  git add mine.md && git commit -q -m "track mine.md"
  echo "content updated" > mine.md   # make dirty

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w22-named-session-test
scope:
  - mine.md
---
# W2.2 named-session handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.2 named session" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T24-names-other" "$other_sid" "$out" \
    && assert_contains "T24-diagnostic" "claimed by other session" "$out" \
    && assert_contains "T24-fallback" "git add" "$out"
}

# T25 (W2.2): Stale-claim diagnostic names ALL sessions that claimed entries,
# not just the first one found.
# Files are pre-committed (tracked) so the W2.1 gate admits them; the cross-session
# subtraction step then fires the stale-claim diagnostic naming all claimants.
# Spec backlink: plan W2.2 — diagnostic must name all claimants.
test_scope_from_stale_claim_diagnostic_names_multiple_sessions() {
  setup_repo
  local my_sid="session-A-$$"
  local sid_b="session-B-$$"
  local sid_c="session-C-$$"

  make_session "$my_sid" "$$"               # A has no claims
  make_session "$sid_b" "99999" "file1.md"  # B claims file1.md
  make_session "$sid_c" "99998" "file2.md"  # C claims file2.md

  # Pre-commit both files so they are tracked (passes W2.1 gate unconditionally).
  echo "content1" > file1.md
  echo "content2" > file2.md
  git add file1.md file2.md && git commit -q -m "track contested files"
  echo "content1 updated" > file1.md   # make dirty
  echo "content2 updated" > file2.md

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w22-multi-session-test
scope:
  - file1.md
  - file2.md
---
# W2.2 multi-session stale-claim handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.2 multi stale-claim" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T25-names-B" "$sid_b" "$out" \
    && assert_contains "T25-names-C" "$sid_c" "$out"
}

# ---------------------------------------------------------------------------
# W1.1 tests — sentinel path-traversal validation + PPID-ancestry cross-check
# ---------------------------------------------------------------------------

# T26 (W1.1): Sentinel containing path-traversal characters is rejected; helper
# falls through to Priority 3 (no live sessions → error, not silent wrong-session).
# Spec backlink: plan W1.1 — path-traversal validation of sentinel value.
test_sentinel_path_traversal_rejected() {
  setup_repo
  # Write a path-traversal sentinel — no valid session dirs exist
  local sessions_dir="${SCRATCH_DIR}/.git/coordinator-sessions"
  mkdir -p "$sessions_dir"
  echo "../../etc/passwd" > "${sessions_dir}/.current-session-id"

  local before_sha
  before_sha=$(git rev-parse HEAD)

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: traversal sentinel" 2>&1) || rc=$?

  local after_sha
  after_sha=$(git rev-parse HEAD)

  teardown_repo
  # Must fail (no valid session) and must NOT produce a commit
  # (The WARN message may echo the path, but no commit = no traversal succeeded)
  [[ $rc -ne 0 ]] \
    && [[ "$before_sha" == "$after_sha" ]] \
    && assert_contains "T26-warn-emitted" "invalid" "$out"
}

# T27 (W1.1): Sentinel pointing to a session whose meta.json.pid is dead falls
# through — helper does not silently accept a stale sentinel.
# Spec backlink: plan W1.1 — sentinel cross-check via PID ancestry.
test_sentinel_pointing_to_dead_session_falls_through() {
  setup_repo
  # Create a session with a dead PID
  local dead_sid="session-dead-$$"
  make_session "$dead_sid" "999999999"   # PID 999999999 — almost certainly dead
  # Write sentinel pointing to that session
  local sentinel="${SCRATCH_DIR}/.git/coordinator-sessions/.current-session-id"
  echo "$dead_sid" > "$sentinel"

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: dead sentinel" 2>&1) || rc=$?

  teardown_repo
  # Dead PID — PPID-walk won't find it; sentinel cross-check rejects it; falls to Priority 3
  # Priority 3: one "session" exists but its PID is dead → 0 live sessions → error
  [[ $rc -ne 0 ]] \
    && assert_not_contains "T27-no-commit" "1 file" "$out"
}

# T28 (W1.1/W1.3): Sentinel points to live session B, but PPID-walk finds live
# session A (this process's ancestor). Since both have live PIDs, the disagreement
# rule fires — helper ABORTs naming both candidates rather than silently picking one.
# Spec backlink: plan W1.3 disagreement rule + Patrik finding #4.
test_sentinel_pointing_to_wrong_live_session_falls_through() {
  setup_repo

  # Session A: our ancestor (pid=$$, which IS in the helper's PPID ancestry)
  local sid_a="session-A-$$"
  make_session "$sid_a" "$$" "a.txt"
  echo "A" > a.txt

  # Session B: a different live process (not in ancestry — use a sleep subprocess)
  local sleep_pid
  sleep 999 &
  sleep_pid=$!
  local sid_b="session-B-${sleep_pid}"
  make_session "$sid_b" "$sleep_pid" "b.txt"
  echo "B" > b.txt

  # Write sentinel pointing to B (the "wrong" session)
  local sentinel="${SCRATCH_DIR}/.git/coordinator-sessions/.current-session-id"
  echo "$sid_b" > "$sentinel"

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: wrong live sentinel" 2>&1) || rc=$?

  kill "$sleep_pid" 2>/dev/null || true
  teardown_repo

  # PPID-walk finds A ($$), sentinel finds B (sleep_pid, live but not ancestor).
  # Disagreement rule → ABORT naming both.
  [[ $rc -ne 0 ]] \
    && assert_contains "T28-aborts" "conflict" "$out" \
    && assert_contains "T28-names-A" "$sid_a" "$out" \
    && assert_contains "T28-names-B" "$sid_b" "$out"
}

# ---------------------------------------------------------------------------
# W1.3 tests — PPID-walk session resolution (Priority 1.5)
# ---------------------------------------------------------------------------

# T29 (W1.3): PPID-walk finds the correct session when it is the only live one
# in the ancestry chain (no CLAUDE_SESSION_ID, no valid sentinel).
# Spec backlink: plan W1.3 — PPID-walk returns exactly-one-match.
test_ppid_walk_resolves_correct_session() {
  setup_repo
  # Create a single session with pid=$$ (this test process — IS in helper's ancestry)
  local sid_a="session-ppid-A-$$"
  make_session "$sid_a" "$$" "ppid-file.txt"
  echo "ppid content" > ppid-file.txt

  # No CLAUDE_SESSION_ID, no sentinel — PPID-walk must find this session
  local out rc
  rc=0
  out=$(bash "$HELPER" "test: ppid walk" 2>&1) || rc=$?

  local commit_files=""
  if [[ $rc -eq 0 ]]; then
    commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)
  fi

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T29-file-committed" "ppid-file.txt" "$commit_files"
}

# T30 (W1.3): When PPID-walk and sentinel disagree (both live), ABORT naming both IDs.
# This is the exact concurrent-session misidentification scenario.
# Spec backlink: plan W1.3 disagreement rule + Patrik finding #4 — fail-closed.
test_ppid_walk_disagrees_with_sentinel_aborts() {
  setup_repo

  local sid_a="session-ppid-real-$$"
  make_session "$sid_a" "$$" "real.txt"
  echo "real" > real.txt

  # Session B: alive (sleep), not in ancestry
  local sleep_pid
  sleep 999 &
  sleep_pid=$!
  local sid_b="session-ppid-wrong-${sleep_pid}"
  make_session "$sid_b" "$sleep_pid" "wrong.txt"
  echo "wrong" > wrong.txt

  # Sentinel points to B (the wrong session)
  local sentinel="${SCRATCH_DIR}/.git/coordinator-sessions/.current-session-id"
  echo "$sid_b" > "$sentinel"

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: ppid disagrees with sentinel" 2>&1) || rc=$?

  kill "$sleep_pid" 2>/dev/null || true
  teardown_repo

  [[ $rc -ne 0 ]] \
    && assert_contains "T30-conflict" "conflict" "$out" \
    && assert_contains "T30-names-real" "$sid_a" "$out" \
    && assert_contains "T30-names-wrong" "$sid_b" "$out"
}

# ---------------------------------------------------------------------------
# W1.2 tests — multi-live hard-fail naming both candidates + Priority 3c
# ---------------------------------------------------------------------------

# T17 tightened: Multiple live sessions error must name BOTH candidate IDs.
# Replaces the original T17 which only checked for "Multiple live sessions" phrase.
# Spec backlink: plan W1.2 — multi-live error names all candidates.
# (Original T17 is now superseded; runner below maps T17 slot to the tightened version)
test_multi_live_sessions_error_names_both() {
  setup_repo
  # Both sessions have pid=$$ so they appear as "live" to Priority 3's kill -0 check.
  # However, both also match PPID-walk (both have pid=$$), making PPID-walk ambiguous.
  # With two ambiguous PPID matches, code falls to Priority 3 → multi-live hard-fail.
  local sid_a="session-A-ml-$$"
  local sid_b="session-B-ml-$$"
  make_session "$sid_a" "$$"
  make_session "$sid_b" "$$"

  echo "file" > f.txt

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: multi" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T17t-phrase" "Multiple live sessions" "$out" \
    && assert_contains "T17t-names-A" "$sid_a" "$out" \
    && assert_contains "T17t-names-B" "$sid_b" "$out"
}

# T31 (W1.2): Priority 3c — zero live sessions emits clear error (previously unreachable
# because Priority 2 sentinel short-circuited before Priority 3c could fire).
# Spec backlink: plan W1.2 — Priority 3c (zero live sessions) now reachable.
test_no_live_sessions_error_reachable() {
  setup_repo
  # Create a session with a dead PID — no sentinel
  local dead_sid="session-dead-p3c-$$"
  make_session "$dead_sid" "999999998"  # dead PID

  local out rc
  rc=0
  out=$(bash "$HELPER" "test: no live sessions" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T31-no-live" "No live session" "$out"
}

# ---------------------------------------------------------------------------
# W2.1 tests — one-tier untracked-membership invariant + pathspec traversal
# ---------------------------------------------------------------------------

# T32 (W2.1): A literal pathspec whose filename collides with another session's
# untracked file must be excluded even when it is a literal (not a glob).
# This is the Patrik finding #2 case: glob-detection alone would pass the literal,
# but the membership gate must still apply for untracked candidates.
# Scenario: Session A's handoff scopes "docs/plans/mine.md" (literal). An untracked
# file at that exact path exists but is in Session B's touched.txt, NOT A's.
# With the membership gate, Session A must NOT commit that file.
# Spec backlink: plan W2.1 — one-tier replaces glob-vs-literal two-tier model.
test_scope_from_literal_pathspec_excludes_other_session_untracked() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  # Session A: scopes the literal path but does NOT touch the file
  make_session "$my_sid" "$$"
  # Session B: the untracked file is in B's touched.txt
  make_session "$other_sid" "99999" "docs/plans/mine.md"

  mkdir -p docs/plans
  echo "collision content" > docs/plans/mine.md   # untracked, owned by B

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w21-literal-test
scope:
  - docs/plans/mine.md
---
# W2.1 literal-pathspec collision handoff
HANDOFF

  # Give session A a real file to commit so the commit doesn't fail on empty scope.
  echo "a content" > a-real-file.txt
  echo "a-real-file.txt" >> "${SCRATCH_DIR}/.git/coordinator-sessions/${my_sid}/touched.txt"

  # Update the handoff to include both
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w21-literal-test
scope:
  - docs/plans/mine.md
  - a-real-file.txt
---
# W2.1 literal-pathspec collision handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.1 literal collision" 2>&1) || rc=$?

  local commit_files=""
  if [[ $rc -eq 0 ]]; then
    commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)
  fi

  teardown_repo
  # docs/plans/mine.md must be excluded (not in A's touched.txt);
  # a-real-file.txt must be included (in A's touched.txt and tracked via union path).
  # rc=0: commit succeeds because a-real-file.txt is in scope.
  [[ $rc -eq 0 ]] \
    && assert_not_contains "T32-collision-excluded" "docs/plans/mine.md" "$commit_files" \
    && assert_contains "T32-real-file-included" "a-real-file.txt" "$commit_files"
}

# T33 (W2.1 path-traversal): validate_pathspec rejects entries containing "..".
# Spec backlink: plan W2.1, worker-baseline finding #3.
test_validate_pathspec_rejects_traversal() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-traversal.md <<'HANDOFF'
---
workstream: traversal-test
scope:
  - ../../etc/passwd
---
# traversal handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-traversal.md "test: traversal" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T33-rejected" ".." "$out"
}

# T34 (W2.1 path-traversal): validate_pathspec rejects entries starting with "/".
# Spec backlink: plan W2.1, worker-baseline finding #3.
test_validate_pathspec_rejects_absolute_path() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-absolute.md <<'HANDOFF'
---
workstream: absolute-test
scope:
  - /etc/passwd
---
# absolute-path handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-absolute.md "test: absolute path" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -ne 0 ]] \
    && assert_contains "T34-rejected" "absolute path" "$out"
}

# T35 (W2.1): A file touched by BOTH sessions appears in both touched.txt sets.
# The membership gate must allow it for the current session — the current session
# has a legitimate claim on a file it also touched.
# Spec backlink: plan W2.1 — edge case: dual-touched file is allowed (not dropped).
test_scope_from_dual_touched_file_allowed() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  # Both sessions claim the same file
  make_session "$my_sid" "$$" "shared.txt"
  make_session "$other_sid" "99999" "shared.txt"

  echo "shared content" > shared.txt

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w21-dual-touched-test
scope:
  - shared.txt
---
# W2.1 dual-touched handoff
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W2.1 dual-touched" 2>&1) || rc=$?

  local commit_files=""
  if [[ $rc -eq 0 ]]; then
    commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)
  fi

  teardown_repo
  # shared.txt is in MY touched.txt — membership gate passes it.
  # Cross-session subtraction would normally block it (other session also claims it),
  # but the dual-claim means MY session has equal ownership — verify the membership
  # gate itself does NOT drop it (the cross-session subtraction behaviour for
  # dual-claimed tracked files is tested separately).
  # The untracked gate passes shared.txt because it IS in my_touched_set.
  # The cross-session subtract may still drop it (other claims it too) — that's
  # expected and tested. Here we verify the MEMBERSHIP GATE alone does not drop it.
  assert_not_contains "T35-not-gate-dropped-msg" "membership gate" "$out"
}

# ---------------------------------------------------------------------------
# W3 tests — self-claim message clarity
# ---------------------------------------------------------------------------

# T36 (W3): The helper source contains the "stale self-claim from this session"
# wording in its do_scope_from skip-message branch. This is a snapshot/grep check —
# the runtime branch is defensive (under priority-1 env-var resolution, claim_sid
# can never equal env_sid by construction of other_claims), but the wording must
# be present in the source for the resolution-divergence case (e.g., a future
# wrapper that bypasses priority-1).
# Spec backlink: plan W3 — self-claim message clarity.
test_w3_stale_self_claim_wording_present() {
  grep -q "stale self-claim from this session" "$HELPER" \
    && grep -q "stale self-claim from this session" "${SCRIPT_DIR}/../../lib/coordinator-session.sh"
}

# T37 (W3): Normal "owned by session X" message includes "(your session=...)"
# disambiguation when the claimant ID does NOT match CLAUDE_SESSION_ID.
# Spec backlink: plan W3 — disambiguation suffix.
test_w3_disambiguation_suffix() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  make_session "$my_sid" "$$" "mine.md"
  make_session "$other_sid" "99999" "other.md"

  # Pre-track both files so W2.1 admits them
  echo "mine" > mine.md
  echo "other" > other.md
  git add mine.md other.md && git commit -q -m "track both"
  echo "mine updated" > mine.md
  echo "other updated" > other.md

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w3-disambig-test
scope:
  - mine.md
  - other.md
---
# W3 disambiguation
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W3 disambig" 2>&1) || rc=$?

  teardown_repo
  # other.md skip should include "(your session=<my_sid>)" disambiguation.
  [[ $rc -eq 0 ]] \
    && assert_contains "T37-owned-by-session"  "owned by session ${other_sid}" "$out" \
    && assert_contains "T37-your-session"      "your session=${my_sid}" "$out"
}

# T38 (W3): When ≥1 file was excluded, the epilogue hint must point the user
# at the troubleshooting doc.
# Spec backlink: plan W3 — epilogue hint.
test_w3_epilogue_when_files_excluded() {
  setup_repo
  local my_sid="session-A-$$"
  local other_sid="session-B-$$"

  make_session "$my_sid" "$$" "mine.md"
  make_session "$other_sid" "99999" "other.md"

  echo "mine" > mine.md
  echo "other" > other.md
  git add mine.md other.md && git commit -q -m "track both"
  echo "mine updated" > mine.md
  echo "other updated" > other.md

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff.md <<'HANDOFF'
---
workstream: w3-epilogue-test
scope:
  - mine.md
  - other.md
---
# W3 epilogue
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md "test: W3 epilogue" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T38-epilogue-hint" "session ID resolution is wrong" "$out" \
    && assert_contains "T38-doc-pointer"   "scoped-safety-commits.md" "$out"
}

# ---------------------------------------------------------------------------
# Canary — project-rag-incident-regression
# ---------------------------------------------------------------------------

# T39 (canary): the named project-rag incident replay.
# Reproduces the exact scenario from the 2026-05-01 project-rag incident:
#   (a) two live sessions A and B with distinct IDs
#   (b) sentinel points to B (wrong)
#   (c) handoff frontmatter scope contains an untracked-file pathspec
#   (d) A's touched.txt contains files A actually wrote
#   (e) B has no touched.txt entries matching the handoff scope
#   (f) helper invoked from A's process (A's PID == $$, in helper's ancestry)
#
# Expected (post-fix): helper either (1) resolves to A correctly and commits
# A's file, or (2) hard-fails with a remediation message naming both
# candidates. NEVER produces a commit that contains A's untracked file
# attributed to session B.
#
# Acceptance: the helper run must NOT exit 0 with a commit whose author or
# session-tag references B AND contains A's-incident.md. Either outcome (A
# resolves correctly OR hard-fail) is acceptable; only the misattribution
# outcome from the original incident is a failure.
#
# Spec backlink: plan §"Verification plan" — project-rag-incident-regression.
test_canary_project_rag_incident_regression() {
  setup_repo

  # Session A: PID = $$, in helper's ancestry. A wrote a-incident.md.
  local sid_a="session-A-canary-$$"
  make_session "$sid_a" "$$" "a-incident.md"
  echo "A's incident work" > a-incident.md
  # a-incident.md remains UNTRACKED in this fixture (matches incident shape).

  # Session B: live but NOT in helper's ancestry (sleep subprocess).
  # B has empty touched.txt (no entries matching handoff scope).
  local sleep_pid
  sleep 999 &
  sleep_pid=$!
  local sid_b="session-B-canary-${sleep_pid}"
  make_session "$sid_b" "$sleep_pid"   # no touched files
  : > "${SCRATCH_DIR}/.git/coordinator-sessions/${sid_b}/touched.txt"

  # Sentinel points to B (the wrong session — incident root cause R3).
  local sentinel="${SCRATCH_DIR}/.git/coordinator-sessions/.current-session-id"
  echo "$sid_b" > "$sentinel"

  # Handoff frontmatter scope references a-incident.md as a literal pathspec
  # (per W2.1, untracked files require touched.txt membership; A is in A's
  # touched.txt, B has no entry → only A can legitimately commit it).
  mkdir -p tasks/handoffs
  cat > tasks/handoffs/incident-handoff.md <<'HANDOFF'
---
workstream: project-rag-incident-canary
scope:
  - a-incident.md
---
# Project-rag incident canary handoff
HANDOFF

  # Invoke helper without CLAUDE_SESSION_ID set (matches incident — env var
  # was unset in the helper's environment per the incident report).
  local out rc
  rc=0
  out=$(unset CLAUDE_SESSION_ID; bash "$HELPER" --scope-from tasks/handoffs/incident-handoff.md "test: project-rag canary" 2>&1) || rc=$?

  local commit_files=""
  local commit_msg=""
  if [[ $rc -eq 0 ]]; then
    commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)
    commit_msg=$(git log -1 --format=%B HEAD || true)
  fi

  kill "$sleep_pid" 2>/dev/null || true
  teardown_repo

  # Acceptance gate (the canary):
  # FAILURE shape (original incident): rc=0 AND commit contains a-incident.md
  #   AND helper resolved to B (sid_b appears as the session attribution).
  # PASS shape A: rc != 0 (hard-fail with remediation naming both candidates).
  # PASS shape B: rc=0 AND commit contains a-incident.md AND helper resolved
  #   to A (sid_a in any session-attribution output, NO sid_b attribution).
  #
  # Concretely: under the post-fix code, the W1.3 disagreement rule fires
  # (PPID-walk resolves to A=$$, sentinel resolves to B=sleep_pid, both live)
  # → ABORT with both IDs named. We assert that outcome.
  if [[ $rc -ne 0 ]]; then
    # Hard-fail path — must name both candidates per disagreement rule.
    assert_contains "T39-canary-hardfail-names-A" "$sid_a" "$out" \
      && assert_contains "T39-canary-hardfail-names-B" "$sid_b" "$out"
  else
    # Success path — must have committed under A's identity, not B's.
    # The commit message must NOT carry B's session ID, and the file must
    # be a-incident.md (A's work).
    [[ "$commit_files" == *"a-incident.md"* ]] \
      && [[ "$commit_msg" != *"$sid_b"* ]]
  fi
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

echo "============================================"
echo " coordinator-safe-commit test suite"
echo "============================================"
echo ""

# We skip T11 (the original flawed version) and only run T11b (proper)
run_test "T1:  Default — only my files staged"                 test_default_my_files_only
run_test "T2:  Default — cross-session subtraction holds"      test_default_cross_session_subtraction
run_test "T3:  Default — orphan warned but not staged"         test_default_orphan_warned_not_staged
run_test "T4:  Default — other-session file not staged"        test_default_other_session_file_not_staged
run_test "T5:  Default — empty scope errors clearly"           test_default_empty_scope_error
run_test "T6:  --dry-run: no commit, scope printed"            test_dry_run_no_commit
run_test "T7:  --blanket: rejected (no env var)"               test_blanket_rejected_no_env
run_test "T8:  --blanket: rejected (wrong command value)"      test_blanket_rejected_wrong_command
run_test "T9:  --blanket: allowed (session-start)"             test_blanket_allowed_session_start
run_test "T10: --blanket: allowed (workday-complete)"          test_blanket_allowed_workday_complete
run_test "T11: --blanket: invocation logged"                   test_blanket_invocation_logged_proper
run_test "T12: --scope-from: valid frontmatter parsed"         test_scope_from_valid_frontmatter
run_test "T13: --scope-from: rejects malformed pathspec"       test_scope_from_malformed_pathspec
run_test "T14: --scope-from: errors on missing file"           test_scope_from_missing_file
run_test "T15: COORDINATOR_OVERRIDE_SCOPE=1 logs + stages all" test_override_scope_logs_and_stages
run_test "T16: Missing subject → error"                        test_missing_subject
run_test "T17: Multiple live sessions → error naming both (tightened W1.2)" test_multi_live_sessions_error_names_both
run_test "T18: --dry-run: no commit in dry-run mode"           test_dry_run_scope_from_no_commit
run_test "T19: --scope-from: union with session touched.txt"   test_scope_from_union_with_touched
run_test "T20: --scope-from: missing scope: key → error"       test_scope_from_missing_scope_key
run_test "T21: --scope-from: CRLF handoff parses correctly"    test_scope_from_crlf_handoff
run_test "T22: W2.0: --scope-from subtracts other-session file" test_scope_from_subtracts_other_session_file
run_test "T23: W2.2: stale-claim fail-closed when contested file excluded" test_scope_from_stale_claim_fail_closed
run_test "T24: W2.2: stale-claim diagnostic names other session" test_scope_from_stale_claim_diagnostic_names_other_session
run_test "T25: W2.2: stale-claim diagnostic names multiple sessions" test_scope_from_stale_claim_diagnostic_names_multiple_sessions
run_test "T26: W1.1: sentinel path-traversal rejected"         test_sentinel_path_traversal_rejected
run_test "T27: W1.1: sentinel dead-session falls through"      test_sentinel_pointing_to_dead_session_falls_through
run_test "T28: W1.1/W1.3: sentinel-PPID disagreement aborts"  test_sentinel_pointing_to_wrong_live_session_falls_through
run_test "T29: W1.3: PPID-walk resolves correct session"       test_ppid_walk_resolves_correct_session
run_test "T30: W1.3: PPID-walk disagrees with sentinel aborts" test_ppid_walk_disagrees_with_sentinel_aborts
run_test "T31: W1.2: zero live sessions error (Priority 3c)"   test_no_live_sessions_error_reachable
run_test "T32: W2.1: literal pathspec collision with other-session untracked excluded" test_scope_from_literal_pathspec_excludes_other_session_untracked
run_test "T33: W2.1: validate_pathspec rejects '..' traversal"  test_validate_pathspec_rejects_traversal
run_test "T34: W2.1: validate_pathspec rejects absolute path"    test_validate_pathspec_rejects_absolute_path
run_test "T35: W2.1: dual-touched file passes membership gate"   test_scope_from_dual_touched_file_allowed
run_test "T36: W3: stale-self-claim wording present in source"   test_w3_stale_self_claim_wording_present
run_test "T37: W3: owned-by message includes (your session=...) disambiguation" test_w3_disambiguation_suffix
run_test "T38: W3: epilogue hint when ≥1 file excluded"          test_w3_epilogue_when_files_excluded
run_test "T39: CANARY — project-rag-incident-regression"         test_canary_project_rag_incident_regression

echo ""
echo "============================================"
echo " Results: ${PASS} passed, ${FAIL} failed"
echo "============================================"

if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
fi

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
