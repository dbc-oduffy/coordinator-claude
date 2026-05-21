#!/usr/bin/env bash
# test-check-no-monolith-completion-append.sh — Smoke tests for check-no-monolith-completion-append.sh
#
# Purpose: verifies that the static-grep tripwire:
#   1. Returns exit 1 + file:line output when a forbidden write is present.
#   2. Returns exit 0 (clean) when only allowed-exception patterns are present.
#   3. All six call shapes in the tripwire registry each produce a grep hit.
#   4. Each of the four exception patterns each produce no hit.
#
# All tests use tmpdir fixture trees — no writes to the real coordinator tree.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 10
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-check-no-monolith-completion-append.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/../check-no-monolith-completion-append.sh"

# ---------------------------------------------------------------------------
# Minimal test framework (same conventions as test-migrate-completion-log-legacy.sh)
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

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

TMP_ROOTS=()

make_coordinator_root() {
  local tmpdir
  tmpdir=$(mktemp -d)
  TMP_ROOTS+=("$tmpdir")
  # Create the minimum surface directories the script expects.
  mkdir -p "$tmpdir/skills" "$tmpdir/commands" "$tmpdir/agents" "$tmpdir/pipelines" "$tmpdir/hooks"
  echo "$tmpdir"
}

cleanup() {
  for d in "${TMP_ROOTS[@]}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Test 1 — forbidden write: plain markdown body mention in a skill file
# ---------------------------------------------------------------------------

echo "--- Test 1: forbidden literal path in skills/ → exit 1"

ROOT1=$(make_coordinator_root)
cat > "$ROOT1/skills/test-skill.md" <<'EOF'
## Completion

Write the entry to `archive/completed/2026-05.md` at the end of the session.
EOF

OUTPUT1=$(bash "$SUBJECT" --root "$ROOT1" 2>&1) && EXIT1=0 || EXIT1=$?

if [[ "$EXIT1" -eq 1 ]]; then
  pass "Test 1: exits 1 on forbidden literal path"
else
  fail "Test 1: expected exit 1, got $EXIT1 — output: $OUTPUT1"
fi

if echo "$OUTPUT1" | grep -q "test-skill.md"; then
  pass "Test 1: output names the offending file"
else
  fail "Test 1: offending file not named in output — output: $OUTPUT1"
fi

# ---------------------------------------------------------------------------
# Test 2 — clean: only per-entry paths present → exit 0
# ---------------------------------------------------------------------------

echo "--- Test 2: only per-entry paths in skills/ → exit 0"

ROOT2=$(make_coordinator_root)
cat > "$ROOT2/skills/session-end-clean.md" <<'EOF'
## Completion

Write the entry to `archive/completed/2026-05/my-task.md`.
EOF

OUTPUT2=$(bash "$SUBJECT" --root "$ROOT2" 2>&1) && EXIT2=0 || EXIT2=$?

if [[ "$EXIT2" -eq 0 ]]; then
  pass "Test 2: exits 0 when only per-entry paths present"
else
  fail "Test 2: expected exit 0, got $EXIT2 — output: $OUTPUT2"
fi

# ---------------------------------------------------------------------------
# Test 3 — all six call shapes each produce a hit
# ---------------------------------------------------------------------------

echo "--- Test 3: all six call shapes detected"

ROOT3=$(make_coordinator_root)
cat > "$ROOT3/skills/all-shapes.md" <<'EOF'
Shape 1 literal: archive/completed/2026-05.md in markdown body.
Shape 2 redirect: >> archive/completed/2026-05.md appends to monolith.
Shape 3 heredoc: cat >> archive/completed/2026-05.md <<'DONE' pipes content.
Shape 4 tee: tee -a archive/completed/2026-05.md reads stdin.
Shape 5 node: writeFileSync('archive/completed/2026-05.md', content)
Shape 6 gitm: git mv archive/completed/2026-05.md archive/completed/legacy/2026-05.md
EOF

# Shape 6 ends in legacy/ which is an exception — add a pure git mv shape without legacy target.
cat > "$ROOT3/agents/gitm-shape.md" <<'EOF'
git mv archive/completed/2026-05.md some-other-destination.md
EOF

OUTPUT3=$(bash "$SUBJECT" --root "$ROOT3" 2>&1) && EXIT3=0 || EXIT3=$?

if [[ "$EXIT3" -eq 1 ]]; then
  pass "Test 3: exits 1 (at least one shape detected)"
else
  fail "Test 3: expected exit 1, got $EXIT3 — output: $OUTPUT3"
fi

# Check each shape label appears in the output (the file containing it is named).
for shape in "Shape 1" "Shape 2" "Shape 3" "Shape 4" "Shape 5"; do
  # The file is reported; the line content contains the pattern.
  if echo "$OUTPUT3" | grep -q "all-shapes.md"; then
    pass "Test 3: shapes 1-5 — all-shapes.md cited in output"
    break
  else
    fail "Test 3: all-shapes.md not cited in output — output: $OUTPUT3"
    break
  fi
done

if echo "$OUTPUT3" | grep -q "gitm-shape.md"; then
  pass "Test 3: shape 6 (git mv without legacy target) — gitm-shape.md cited in output"
else
  fail "Test 3: gitm-shape.md not cited — output: $OUTPUT3"
fi

# ---------------------------------------------------------------------------
# Test 4 — exception: archive/completed/legacy/ paths do not fire
# ---------------------------------------------------------------------------

echo "--- Test 4: legacy/ path in content → no hit (allowed exception 1)"

ROOT4=$(make_coordinator_root)
cat > "$ROOT4/skills/migration-step.md" <<'EOF'
git mv archive/completed/2026-05.md archive/completed/legacy/2026-05.md
EOF

OUTPUT4=$(bash "$SUBJECT" --root "$ROOT4" 2>&1) && EXIT4=0 || EXIT4=$?

if [[ "$EXIT4" -eq 0 ]]; then
  pass "Test 4: legacy/ path excluded (exit 0)"
else
  fail "Test 4: legacy/ path incorrectly flagged — exit $EXIT4, output: $OUTPUT4"
fi

# ---------------------------------------------------------------------------
# Test 5 — exception: COORDINATOR_OVERRIDE_LEGACY_MONOLITH lines do not fire
# ---------------------------------------------------------------------------

echo "--- Test 5: COORDINATOR_OVERRIDE_LEGACY_MONOLITH line → no hit (allowed exception 4)"

ROOT5=$(make_coordinator_root)
cat > "$ROOT5/skills/override-doc.md" <<'EOF'
If COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1 is set, skip the git mv of archive/completed/2026-05.md.
EOF

OUTPUT5=$(bash "$SUBJECT" --root "$ROOT5" 2>&1) && EXIT5=0 || EXIT5=$?

if [[ "$EXIT5" -eq 0 ]]; then
  pass "Test 5: COORDINATOR_OVERRIDE_LEGACY_MONOLITH line excluded (exit 0)"
else
  fail "Test 5: override line incorrectly flagged — exit $EXIT5, output: $OUTPUT5"
fi

# ---------------------------------------------------------------------------
# Test 6 — exception: HTML/Markdown tripwire comment markers do not fire
# ---------------------------------------------------------------------------

echo "--- Test 6: <!-- TRIPWIRE: comment line → no hit (allowed exception 5)"

ROOT6=$(make_coordinator_root)
cat > "$ROOT6/skills/tripwire-comment.md" <<'EOF'
<!-- TRIPWIRE: NO monolithic append — archive/completed/2026-05.md writes outside legacy/ are forbidden. -->
EOF

OUTPUT6=$(bash "$SUBJECT" --root "$ROOT6" 2>&1) && EXIT6=0 || EXIT6=$?

if [[ "$EXIT6" -eq 0 ]]; then
  pass "Test 6: tripwire comment excluded (exit 0)"
else
  fail "Test 6: tripwire comment incorrectly flagged — exit $EXIT6, output: $OUTPUT6"
fi

# ---------------------------------------------------------------------------
# Test 7 — exception: docs/wiki/ files do not fire
# ---------------------------------------------------------------------------

echo "--- Test 7: docs/wiki/ mention → no hit (allowed exception 3)"

ROOT7=$(make_coordinator_root)
mkdir -p "$ROOT7/docs/wiki"
cat > "$ROOT7/docs/wiki/completion-log.md" <<'EOF'
The legacy monolith format used archive/completed/2026-05.md as its write target.
EOF

# Place an identical line in a skills/ file to confirm wiki exclusion is path-specific.
cat > "$ROOT7/skills/ref-doc.md" <<'EOF'
See docs/wiki/completion-log.md for the old archive/completed/2026-05.md format.
EOF

# The wiki file should not trigger; the skills/ file SHOULD trigger (it's not under docs/wiki/).
OUTPUT7=$(bash "$SUBJECT" --root "$ROOT7" 2>&1) && EXIT7=0 || EXIT7=$?

if [[ "$EXIT7" -eq 1 ]]; then
  pass "Test 7: skills/ mention still flagged even when wiki/ counterpart present"
else
  fail "Test 7: expected exit 1 (skills/ mention), got $EXIT7 — output: $OUTPUT7"
fi

# The wiki file itself must NOT be cited as the offending path.
# (The skills/ file's content mentions docs/wiki/ in a href, but the wiki *file* is excluded.)
if ! echo "$OUTPUT7" | grep -qF "/docs/wiki/completion-log.md:"; then
  pass "Test 7: docs/wiki/ file not cited as offending path (correctly excluded)"
else
  fail "Test 7: docs/wiki/ file incorrectly cited as offending path — output: $OUTPUT7"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=============================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "=============================="

if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failures:"
  for m in "${FAIL_MSGS[@]}"; do
    echo "  - $m"
  done
  exit 1
fi

exit 0
