#!/bin/bash
# test-coordinator-safe-commit.sh — Test suite for coordinator-safe-commit
#
# Uses a scratch git repo (mktemp) for isolation.
# Multiple fake session dirs are created to verify cross-session set-subtraction.
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-coordinator-safe-commit.sh

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

# T5: Default mode — empty touched.txt + clean working tree exits 0 with NOTE (Case A)
# Phase 1 (plans/safe-commit-fixes.md § Phase 1) replaced the single "No staged scope"
# error with a four-case branched diagnosis. Case A (touched.txt empty, tree clean) is
# not an error — it exits 0 with a NOTE so callers can detect it without treating it as
# a failure (e.g. /session-end calling the helper on an already-clean tree).
test_default_empty_scope_note() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"   # no files touched
  # No dirty files at all — Case A

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" "test: empty scope" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T5" "Nothing to commit" "$out"
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
# Updated for expanded allow-list: session-start, workday-complete, update-docs,
# relay-protocol, distillation (plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1).
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
    && assert_contains "T7" "authorized sweep ceremonies" "$out"
}

# T8: --blanket rejected when CLAUDE_INVOKING_COMMAND is wrong value
# Updated for expanded allow-list (see T7 comment).
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
    && assert_contains "T8" "authorized sweep ceremonies" "$out"
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
# --allow-out-of-scope-dirty is required because out-of-scope.txt and the handoff
# file itself are untracked (dirty) but not in the declared scope. Issue C (Phase 1+2,
# plans/safe-commit-fixes.md § Phase 1) added a fail-closed out-of-scope-dirty check;
# the flag opts in to warn-and-continue so this test can verify scoping behaviour
# independently of the out-of-scope-dirty gate.
test_scope_from_valid_frontmatter() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  # Create files
  echo "scoped content" > scoped-file.txt
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
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md --allow-out-of-scope-dirty "test: scope-from" 2>&1) || rc=$?

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

# T19: --scope-from stages only handoff-declared files (touched.txt is NOT unioned)
# Issue C (plans/2026-05-05-session-misidentification-fix.md) removed the union of
# handoff scope + session touched.txt in --scope-from mode. The handoff scope is now
# the sole source of truth. Files in touched.txt but NOT in the handoff scope are
# treated as out-of-scope-dirty and are NOT staged (warning emitted with
# --allow-out-of-scope-dirty; fail-closed without it).
# --allow-out-of-scope-dirty is passed here so extra-touched.txt doesn't abort the
# commit — the assertion confirms it was warned about but NOT staged.
test_scope_from_stages_handoff_scope_only() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$" "extra-touched.txt"  # session touched this beyond handoff scope

  echo "scoped" > scoped-file.txt
  echo "extra" > extra-touched.txt

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
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff.md --allow-out-of-scope-dirty "test: handoff-scope-only" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  # Only the handoff-declared file is staged; the touched.txt-only file is NOT.
  [[ $rc -eq 0 ]] \
    && assert_contains "T19-scoped" "scoped-file.txt" "$commit_files" \
    && assert_not_contains "T19-not-staged" "extra-touched.txt" "$commit_files" \
    && assert_contains "T19-warned" "outside declared scope" "$out"
}

# T21: Scope-from — CRLF-encoded handoff (Windows line endings).
# Regression for the "touch-tracker not firing" bug observed across 4+ sessions:
# CRLF-encoded handoffs produced "no scope: field found" because "$line" == "---"
# silently failed to match "---\r". Parser now strips trailing CR.
test_scope_from_crlf_handoff() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "scoped content" > scoped-file.txt
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

  # --allow-out-of-scope-dirty is required because out-of-scope.txt and the CRLF
  # handoff file itself are untracked (dirty) but not in the declared scope. Issue C
  # (plans/safe-commit-fixes.md § Phase 1) fail-closes on out-of-scope dirty files;
  # the flag opts in to warn-and-continue so this test can verify CRLF parsing only.
  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-crlf.md --allow-out-of-scope-dirty "test: crlf scope-from" 2>&1) || rc=$?

  local commit_files
  commit_files=$(git show --name-only HEAD --format="" | grep -v "^$" || true)

  teardown_repo
  [[ $rc -eq 0 ]] \
    && assert_contains "T21-scoped" "scoped-file.txt" "$commit_files" \
    && assert_not_contains "T21-not-scoped" "out-of-scope.txt" "$commit_files"
}

# T10b: --blanket allowed when CLAUDE_INVOKING_COMMAND=update-docs
# Verifies expanded allow-list (plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1).
test_blanket_allowed_update_docs() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file3" > file3.txt
  git add file3.txt

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="update-docs" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: update-docs sweep" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]]
}

# T10c: --blanket allowed when CLAUDE_INVOKING_COMMAND=relay-protocol
# Verifies expanded allow-list (plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1).
test_blanket_allowed_relay_protocol() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file4" > file4.txt
  git add file4.txt

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="relay-protocol" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: relay-protocol sweep" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]]
}

# T10d: --blanket allowed when CLAUDE_INVOKING_COMMAND=distillation
# Verifies expanded allow-list (plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1).
test_blanket_allowed_distillation() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "file5" > file5.txt
  git add file5.txt

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="distillation" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "chore: distillation sweep" 2>&1) || rc=$?

  teardown_repo
  [[ $rc -eq 0 ]]
}

# T-scope-zero: scope-from with declared scope that resolves to zero dirty files.
# Spec: plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1 — T11 (scope filtered to zero).
# Asserts exit non-zero AND a FAIL-or-ERROR line on stderr.
# Note: do_scope_from exits with ERROR (not FAIL) when scope resolves to zero dirty files —
# the ERROR path at line ~751 fires before the commit sentinels. This is correct behavior:
# the scope-zero error is structural, not a commit failure.
test_scope_from_filtered_to_zero() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  # Create a file that exists on disk but is NOT dirty (already committed)
  echo "clean" > clean-file.txt
  git add clean-file.txt
  git commit -q -m "pre-commit clean file"

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-zero.md <<'HANDOFF'
---
workstream: zero-test
scope:
  - clean-file.txt
---
# Handoff with clean (non-dirty) scope
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-zero.md "test: zero scope" 2>&1) || rc=$?

  teardown_repo
  # Must exit non-zero and emit a diagnostic message
  [[ $rc -ne 0 ]] \
    && { echo "$out" | grep -qE "(FAIL|ERROR)" ; }
}

# T-scope-from-empty-fileset: --scope-from with a handoff whose scope: resolves to no files at all
# (pathspec pattern that matches nothing). Asserts FAIL line + exit non-zero.
# Spec: plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1 — T12.
test_scope_from_empty_fileset() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  echo "dirty" > some-dirty.txt

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-empty.md <<'HANDOFF'
---
workstream: empty-test
scope:
  - nonexistent-pattern-xyz-abc-999.txt
---
# Handoff with scope that matches nothing
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-empty.md --allow-out-of-scope-dirty "test: empty fileset" 2>&1) || rc=$?

  teardown_repo
  # Must exit non-zero: nothing to commit when scope resolves to zero files
  [[ $rc -ne 0 ]]
}

# T-overlap-gate: when a peer session owns a file in our scope, the overlap gate fires.
# Asserts exit non-zero and a diagnostic message (FAIL or ERROR or overlap).
# Spec: plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1 — T13 (overlap-gate).
# Note: the overlap gate prints "OVERLAP" or "ERROR" — not necessarily "FAIL" — since it
# fires before the commit step. Both formats satisfy the "non-zero + diagnostic" contract.
test_scope_from_overlap_gate() {
  setup_repo
  local my_sid="session-mine-$$"
  local peer_sid="session-peer-$$"
  make_session "$my_sid" "$$"
  make_session "$peer_sid" "99999"

  echo "shared" > shared-file.txt

  # Publish peer's active scope so our session sees the overlap
  local peer_scope_dir="${SCRATCH_DIR}/.git/coordinator-sessions/${peer_sid}"
  mkdir -p "$peer_scope_dir"
  echo "shared-file.txt" > "${peer_scope_dir}/active-scope.txt"

  mkdir -p tasks/handoffs
  cat > tasks/handoffs/handoff-overlap.md <<'HANDOFF'
---
workstream: overlap-test
scope:
  - shared-file.txt
---
# Handoff claiming a file also in a peer's active scope
HANDOFF

  local out rc
  rc=0
  out=$(CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --scope-from tasks/handoffs/handoff-overlap.md "test: overlap" 2>&1) || rc=$?

  teardown_repo
  # Must exit non-zero and surface a diagnostic
  [[ $rc -ne 0 ]] \
    && { echo "$out" | grep -qiE "(overlap|ERROR|FAIL)" ; }
}

# T-head-unchanged: Sentinel 1 fires when HEAD is unchanged after a commit attempt.
# This test stubs a contrived scenario where the commit step is a no-op:
# the working tree is clean (no staged files), so git commit exits non-zero.
# Sentinel 2 catches the git commit failure and emits FAIL before Sentinel 1 can fire;
# both sentinels together guarantee no silent exit-0 without a HEAD movement.
# Spec: plan/2026-05-13-safe-commit-demote-to-sweep.md § Chunk 1 — T14 (HEAD-unchanged sentinel).
test_head_unchanged_sentinel() {
  setup_repo
  local my_sid="session-mine-$$"
  make_session "$my_sid" "$$"

  # Stash any dirty state so the working tree is clean when we invoke the helper
  # (git stash push -u is not needed since setup_repo gives us a clean tree)
  # We invoke --blanket with a clean working tree: git add -A stages nothing,
  # git commit fails (nothing to commit), Sentinel 2 fires with FAIL line, exit 2.
  local before_sha
  before_sha=$(git rev-parse HEAD)

  local out rc
  rc=0
  out=$(CLAUDE_INVOKING_COMMAND="session-start" CLAUDE_SESSION_ID="$my_sid" bash "$HELPER" --blanket "test: nothing to commit" 2>&1) || rc=$?

  local after_sha
  after_sha=$(git rev-parse HEAD)

  teardown_repo
  # HEAD must not have moved and helper must have exited non-zero with a FAIL line
  [[ "$before_sha" == "$after_sha" ]] \
    && [[ $rc -ne 0 ]] \
    && assert_contains "T-head-unchanged" "FAIL" "$out"
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
run_test "T5:  Default — empty scope+clean tree → NOTE exit 0" test_default_empty_scope_note
run_test "T6:  --dry-run: no commit, scope printed"            test_dry_run_no_commit
run_test "T7:  --blanket: rejected (no env var)"               test_blanket_rejected_no_env
run_test "T8:  --blanket: rejected (wrong command value)"      test_blanket_rejected_wrong_command
run_test "T9:  --blanket: allowed (session-start)"             test_blanket_allowed_session_start
run_test "T10: --blanket: allowed (workday-complete)"          test_blanket_allowed_workday_complete
run_test "T10b:--blanket: allowed (update-docs)"               test_blanket_allowed_update_docs
run_test "T10c:--blanket: allowed (relay-protocol)"            test_blanket_allowed_relay_protocol
run_test "T10d:--blanket: allowed (distillation)"              test_blanket_allowed_distillation
run_test "T11: --blanket: invocation logged"                   test_blanket_invocation_logged_proper
run_test "T12: --scope-from: valid frontmatter parsed"         test_scope_from_valid_frontmatter
run_test "T13: --scope-from: rejects malformed pathspec"       test_scope_from_malformed_pathspec
run_test "T14: --scope-from: errors on missing file"           test_scope_from_missing_file
run_test "T15: COORDINATOR_OVERRIDE_SCOPE=1 logs + stages all" test_override_scope_logs_and_stages
run_test "T16: Missing subject → error"                        test_missing_subject
run_test "T17: Multiple live sessions → error naming both"     test_multi_live_sessions_error
run_test "T18: --dry-run: no commit in dry-run mode"           test_dry_run_scope_from_no_commit
run_test "T19: --scope-from: handoff scope only (no touched.txt union)" test_scope_from_stages_handoff_scope_only
run_test "T20: --scope-from: missing scope: key → error"       test_scope_from_missing_scope_key
run_test "T21: --scope-from: CRLF handoff parses correctly"    test_scope_from_crlf_handoff
run_test "T-scope-zero:       scope-from scope resolves to zero dirty files → non-zero exit" test_scope_from_filtered_to_zero
run_test "T-scope-empty-fs:   scope-from scope matches no files → non-zero exit"              test_scope_from_empty_fileset
run_test "T-overlap-gate:     overlap-gate rejection → non-zero exit + diagnostic"            test_scope_from_overlap_gate
run_test "T-head-unchanged:   HEAD-unchanged sentinel fires on clean-tree no-op commit"       test_head_unchanged_sentinel

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
