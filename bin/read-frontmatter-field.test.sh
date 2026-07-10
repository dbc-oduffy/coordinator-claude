#!/usr/bin/env bash
# Review: code-reviewer — added set -euo pipefail; subject is always-0 but defensive posture
#         matches the subject file and prevents silent false-passes on infra errors.
set -euo pipefail
# read-frontmatter-field.test.sh — Tests for read-frontmatter-field.sh
#
# Purpose: Verifies the normalization pipeline (quoted/bare/null values,
#          trailing YAML comments, single-quoted values, absent fields)
#          and the contract for missing/unreadable files.
#
# Spec backlink: coordinator/bin/read-frontmatter-field.sh (contract)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/read-frontmatter-field.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Fixture setup
# ---------------------------------------------------------------------------
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

# ---------------------------------------------------------------------------
# T1: Double-quoted deliverable_id, no trailing comment
# ---------------------------------------------------------------------------
FIXTURE1="${TMPDIR_ROOT}/t1.md"
printf '%s\n' '---' 'deliverable_id: "dlv-abc-1"' 'title: "test"' '---' '' '# Body' > "$FIXTURE1"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE1" deliverable_id)
if [ "$OUTPUT" = "dlv-abc-1" ]; then
  pass "T1: double-quoted value (no comment) → bare value"
else
  fail "T1: expected 'dlv-abc-1', got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T2: Double-quoted initiative with trailing YAML comment (real coordinator-doc-new output)
# ---------------------------------------------------------------------------
FIXTURE2="${TMPDIR_ROOT}/t2.md"
printf '%s\n' '---' 'title: "test"' 'initiative: "init-7"  # FK to state/initiatives/<id>.yaml; null when no named initiative' '---' '' '# Body' > "$FIXTURE2"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE2" initiative)
if [ "$OUTPUT" = "init-7" ]; then
  pass "T2: double-quoted value + trailing comment → bare value without comment"
else
  fail "T2: expected 'init-7', got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T3: Null with trailing comment — null + comment → empty
# ---------------------------------------------------------------------------
FIXTURE3="${TMPDIR_ROOT}/t3.md"
printf '%s\n' '---' 'title: "test"' 'initiative: null  # FK to state/initiatives/<id>.yaml; null when no named initiative' '---' '' '# Body' > "$FIXTURE3"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE3" initiative) || true
if [ -z "$OUTPUT" ]; then
  pass "T3: null + trailing comment → empty string"
else
  fail "T3: expected empty, got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T4: Bare null (no comment) → empty
# ---------------------------------------------------------------------------
FIXTURE4="${TMPDIR_ROOT}/t4.md"
printf '%s\n' '---' 'title: "test"' 'initiative: null' '---' '' '# Body' > "$FIXTURE4"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE4" initiative) || true
if [ -z "$OUTPUT" ]; then
  pass "T4: bare null → empty string"
else
  fail "T4: expected empty, got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T5: Bare (unquoted) deliverable_id
# ---------------------------------------------------------------------------
FIXTURE5="${TMPDIR_ROOT}/t5.md"
printf '%s\n' '---' 'deliverable_id: dlv-bare-2' '---' '' '# Body' > "$FIXTURE5"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE5" deliverable_id)
if [ "$OUTPUT" = "dlv-bare-2" ]; then
  pass "T5: bare (unquoted) value → bare value"
else
  fail "T5: expected 'dlv-bare-2', got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T6: Single-quoted value
# ---------------------------------------------------------------------------
FIXTURE6="${TMPDIR_ROOT}/t6.md"
printf '%s\n' '---' "workstream: 'foo-bar'" '---' '' '# Body' > "$FIXTURE6"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE6" workstream)
if [ "$OUTPUT" = "foo-bar" ]; then
  pass "T6: single-quoted value → bare value"
else
  fail "T6: expected 'foo-bar', got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T7: Absent field in an otherwise-valid file → empty string
# ---------------------------------------------------------------------------
FIXTURE7="${TMPDIR_ROOT}/t7.md"
printf '%s\n' '---' 'title: "some plan"' 'workstream: "my-ws"' '---' '' '# Body' > "$FIXTURE7"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE7" deliverable_id) || true
if [ -z "$OUTPUT" ]; then
  pass "T7: absent field → empty string"
else
  fail "T7: expected empty for absent field, got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T8: Nonexistent file path → empty string, exit 0
# ---------------------------------------------------------------------------
NONEXISTENT="${TMPDIR_ROOT}/does-not-exist-at-all.md"
EXIT_CODE=0
OUTPUT=$(bash "$SUBJECT" "$NONEXISTENT" deliverable_id) || EXIT_CODE=$?

if [ -z "$OUTPUT" ]; then
  pass "T8a: nonexistent file → empty string"
else
  fail "T8a: expected empty for nonexistent file, got '${OUTPUT}'"
fi

if [ "$EXIT_CODE" -eq 0 ]; then
  pass "T8b: nonexistent file → exit 0"
else
  fail "T8b: expected exit 0 for nonexistent file, got ${EXIT_CODE}"
fi

# ---------------------------------------------------------------------------
# T9: Double-quoted "null" literal → empty string
# Review: code-reviewer — coordinator-doc-new may emit "null" as a quoted token; pipeline must normalise it
# ---------------------------------------------------------------------------
FIXTURE9="${TMPDIR_ROOT}/t9.md"
printf '%s\n' '---' 'initiative: "null"' '---' '' '# Body' > "$FIXTURE9"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE9" initiative) || true
if [ -z "$OUTPUT" ]; then
  pass "T9: double-quoted null → empty string"
else
  fail "T9: expected empty for quoted null, got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# T10: Explicitly empty double-quoted value → empty string
# Review: code-reviewer — empty-quoted is distinct from absent (T7) and null (T4); pipeline must handle it
# ---------------------------------------------------------------------------
FIXTURE10="${TMPDIR_ROOT}/t10.md"
printf '%s\n' '---' 'deliverable_id: ""' '---' '' '# Body' > "$FIXTURE10"

OUTPUT=$(bash "$SUBJECT" "$FIXTURE10" deliverable_id) || true
if [ -z "$OUTPUT" ]; then
  pass "T10: empty double-quoted value → empty string"
else
  fail "T10: expected empty for empty-quoted value, got '${OUTPUT}'"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
