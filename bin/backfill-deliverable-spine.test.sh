#!/usr/bin/env bash
# backfill-deliverable-spine.test.sh — Tests for backfill-deliverable-spine.sh
#
# Purpose: Verifies corpus grouping, idempotency, ambiguity detection,
#          immutable-file protection, and --write behavior.
#
# Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § C5, AC7

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/backfill-deliverable-spine.sh"
MINT_HELPER="${SCRIPT_DIR}/mint-deliverable-id.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Fixture setup — build a minimal synthetic coordinator root
# ---------------------------------------------------------------------------
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FAKE_ROOT="${TMPDIR_ROOT}/coordinator"

# Create corpus directories
mkdir -p "${FAKE_ROOT}/bin"
mkdir -p "${FAKE_ROOT}/state/handoffs"
mkdir -p "${FAKE_ROOT}/archive/handoffs/2026-06"
mkdir -p "${FAKE_ROOT}/archive/completed/2026-06"
mkdir -p "${FAKE_ROOT}/docs/plans"
mkdir -p "${FAKE_ROOT}/state/roadmap/my-roadmap"

# Link real mint helper into fake root so the subject can find it
ln -sf "$MINT_HELPER" "${FAKE_ROOT}/bin/mint-deliverable-id.sh"

# ---------------------------------------------------------------------------
# Helper: write a minimal YAML-frontmatter markdown artifact
# ---------------------------------------------------------------------------
write_artifact() {
  local path="$1"
  shift
  # remaining args: key=value pairs to include in frontmatter
  {
    echo "---"
    for kv in "$@"; do
      echo "${kv%%=*}: ${kv#*=}"
    done
    echo "---"
    echo ""
    echo "# Body"
  } > "$path"
}

# ---------------------------------------------------------------------------
# T1: Dry-run emits a report and exits 0 when corpus is clean
# ---------------------------------------------------------------------------
# Single plan with workstream
write_artifact "${FAKE_ROOT}/docs/plans/2026-06-01-foo.md" \
  "title=Foo Plan" "created=2026-06-01" "workstream=foo-work" "status=draft"

OUTPUT="$(bash "$SUBJECT" --dry-run --root "$FAKE_ROOT" 2>/dev/null)"
EXIT_CODE=$?

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "T1a: exits 0 on clean dry-run"
else
  fail "T1a: expected exit 0, got ${EXIT_CODE}"
fi

if echo "$OUTPUT" | grep -q "GROUPING REPORT"; then
  pass "T1b: dry-run emits GROUPING REPORT header"
else
  fail "T1b: GROUPING REPORT header not found in output"
fi

if echo "$OUTPUT" | grep -q "foo-work"; then
  pass "T1c: plan's workstream appears in report"
else
  fail "T1c: workstream 'foo-work' not found in report"
fi

if echo "$OUTPUT" | grep -q "STATUS: CLEAN"; then
  pass "T1d: report says STATUS: CLEAN"
else
  fail "T1d: STATUS: CLEAN not found in report"
fi

# ---------------------------------------------------------------------------
# T2: Unknown-group artifacts (no workstream field) appear in UNKNOWN GROUP
# ---------------------------------------------------------------------------
write_artifact "${FAKE_ROOT}/docs/plans/2026-06-01-bar.md" \
  "title=Bar Plan" "created=2026-06-01" "status=draft"
  # NOTE: no workstream field → should fall into UNKNOWN group

OUTPUT2="$(bash "$SUBJECT" --dry-run --root "$FAKE_ROOT" 2>/dev/null)"

if echo "$OUTPUT2" | grep -q "UNKNOWN GROUP"; then
  pass "T2a: plan without workstream appears in UNKNOWN GROUP"
else
  fail "T2a: UNKNOWN GROUP section not found in report"
fi

if echo "$OUTPUT2" | grep -q "bar.md"; then
  pass "T2b: the no-workstream plan file is listed"
else
  fail "T2b: bar.md not found in report"
fi

# ---------------------------------------------------------------------------
# T3: Already-threaded artifacts are skipped (idempotency / carry rule D1)
# ---------------------------------------------------------------------------
write_artifact "${FAKE_ROOT}/docs/plans/2026-06-01-already-threaded.md" \
  "title=Pre-Threaded Plan" "created=2026-06-01" "workstream=pre-threaded" \
  "deliverable_id=dlv-pre-threaded-aabbcc"

OUTPUT3="$(bash "$SUBJECT" --dry-run --root "$FAKE_ROOT" 2>/dev/null)"

if echo "$OUTPUT3" | grep -q "already-threaded"; then
  pass "T3a: already-threaded artifact appears in ALREADY-THREADED section"
else
  fail "T3a: ALREADY-THREADED section not present in report"
fi

if echo "$OUTPUT3" | grep -q "dlv-pre-threaded-aabbcc"; then
  pass "T3b: existing deliverable_id shown in ALREADY-THREADED section"
else
  fail "T3b: existing deliverable_id not shown in report"
fi

# Verify the already-threaded workstream does NOT appear as a new group to stamp
if ! echo "$OUTPUT3" | grep -qE "GROUP \[OK\]:.*pre-threaded"; then
  pass "T3c: pre-threaded workstream not listed as a new group to stamp"
else
  fail "T3c: pre-threaded workstream incorrectly listed as a new group"
fi

# ---------------------------------------------------------------------------
# T4: Archived artifacts are marked immutable (derive-at-emit, no write)
# ---------------------------------------------------------------------------
write_artifact "${FAKE_ROOT}/archive/handoffs/2026-06/2026-06-01-archived.md" \
  "title=Archived Handoff" "created=2026-06-01" "workstream=archived-work" \
  "status=consumed" "kind=session-handoff"

OUTPUT4="$(bash "$SUBJECT" --dry-run --root "$FAKE_ROOT" 2>/dev/null)"

if echo "$OUTPUT4" | grep -q "immutable"; then
  pass "T4a: archived artifact tagged as immutable in report"
else
  fail "T4a: 'immutable' label not found for archived artifact"
fi

if echo "$OUTPUT4" | grep -q "derive-at-emit"; then
  pass "T4b: report notes derive-at-emit for archived artifact"
else
  fail "T4b: 'derive-at-emit' not found for archived artifact"
fi

# ---------------------------------------------------------------------------
# T5: Ambiguity detection — two distinct plans with the same workstream key
# ---------------------------------------------------------------------------
write_artifact "${FAKE_ROOT}/docs/plans/2026-06-01-collide-a.md" \
  "title=Collision Plan A" "created=2026-06-01" "workstream=collided-workstream" \
  "slug=collide-a" "status=draft"
write_artifact "${FAKE_ROOT}/docs/plans/2026-06-15-collide-b.md" \
  "title=Collision Plan B" "created=2026-06-15" "workstream=collided-workstream" \
  "slug=collide-b" "status=draft"

AMBIG_OUTPUT="$(bash "$SUBJECT" --dry-run --root "$FAKE_ROOT" 2>/dev/null)" || AMBIG_EXIT=$?
AMBIG_EXIT="${AMBIG_EXIT:-0}"

if echo "$AMBIG_OUTPUT" | grep -q "AMBIGUOUS"; then
  pass "T5a: two colliding plans detected as AMBIGUOUS"
else
  fail "T5a: AMBIGUOUS not detected for two colliding plans"
fi

if [[ "$AMBIG_EXIT" -eq 2 ]]; then
  pass "T5b: exit code 2 when ambiguities present"
else
  fail "T5b: expected exit code 2 for ambiguous groups, got ${AMBIG_EXIT}"
fi

if echo "$AMBIG_OUTPUT" | grep -q "REVIEW REQUIRED"; then
  pass "T5c: report says REVIEW REQUIRED when ambiguities present"
else
  fail "T5c: REVIEW REQUIRED not in output with ambiguous groups"
fi

# ---------------------------------------------------------------------------
# T6: --write is blocked when ambiguities exist
# ---------------------------------------------------------------------------
WRITE_BLOCK_OUTPUT="$(bash "$SUBJECT" --write --root "$FAKE_ROOT" 2>&1)" || WRITE_BLOCK_EXIT=$?
WRITE_BLOCK_EXIT="${WRITE_BLOCK_EXIT:-0}"

if [[ "$WRITE_BLOCK_EXIT" -eq 2 ]]; then
  pass "T6a: --write exits 2 (blocked) when ambiguities present"
else
  fail "T6a: --write should exit 2 on ambiguous groups, got ${WRITE_BLOCK_EXIT}"
fi

if echo "$WRITE_BLOCK_OUTPUT" | grep -qi "ambiguous\|cannot --write"; then
  pass "T6b: --write emits ambiguity error message"
else
  fail "T6b: --write did not emit ambiguity error message"
fi

# ---------------------------------------------------------------------------
# T7: --write stamps deliverable_id on mutable artifacts in clean corpus
# ---------------------------------------------------------------------------
# Build a fresh clean fake root with no ambiguities
CLEAN_ROOT="${TMPDIR_ROOT}/clean_coordinator"
mkdir -p "${CLEAN_ROOT}/bin"
mkdir -p "${CLEAN_ROOT}/state/handoffs"
mkdir -p "${CLEAN_ROOT}/archive/handoffs/2026-06"
mkdir -p "${CLEAN_ROOT}/archive/completed/2026-06"
mkdir -p "${CLEAN_ROOT}/docs/plans"
ln -sf "$MINT_HELPER" "${CLEAN_ROOT}/bin/mint-deliverable-id.sh"

write_artifact "${CLEAN_ROOT}/docs/plans/2026-06-01-alpha.md" \
  "title=Alpha Plan" "created=2026-06-01" "workstream=alpha-work" "status=draft"

write_artifact "${CLEAN_ROOT}/state/handoffs/2026-06-01_alpha_handoff.md" \
  "title=Alpha Handoff" "created=2026-06-01" "workstream=alpha-work" \
  "status=active" "kind=session-handoff"

write_artifact "${CLEAN_ROOT}/archive/handoffs/2026-06/2026-06-01-alpha-archived.md" \
  "title=Alpha Archived" "created=2026-06-01" "workstream=alpha-work" \
  "status=consumed" "kind=session-handoff"

write_artifact "${CLEAN_ROOT}/archive/completed/2026-06/2026-06-01-alpha-comp.md" \
  "title=Alpha Completion" "created=2026-06-01" "chain=alpha-work" "status=pending-release"

WRITE_OUTPUT="$(bash "$SUBJECT" --write --root "$CLEAN_ROOT" 2>/dev/null)"
WRITE_EXIT=$?

if [[ "$WRITE_EXIT" -eq 0 ]]; then
  pass "T7a: --write exits 0 on clean corpus"
else
  fail "T7a: --write expected exit 0, got ${WRITE_EXIT}"
fi

# Verify mutable plan got deliverable_id written
PLAN_ID="$(grep "^deliverable_id:" "${CLEAN_ROOT}/docs/plans/2026-06-01-alpha.md" | head -1 | awk '{print $2}')"
if [[ "$PLAN_ID" =~ ^dlv- ]]; then
  pass "T7b: plan artifact has deliverable_id stamped (${PLAN_ID})"
else
  fail "T7b: plan artifact missing deliverable_id (got: '${PLAN_ID}')"
fi

# Verify mutable handoff got deliverable_id written
HANDOFF_ID="$(grep "^deliverable_id:" "${CLEAN_ROOT}/state/handoffs/2026-06-01_alpha_handoff.md" | head -1 | awk '{print $2}')"
if [[ "$HANDOFF_ID" =~ ^dlv- ]]; then
  pass "T7c: handoff artifact has deliverable_id stamped (${HANDOFF_ID})"
else
  fail "T7c: handoff artifact missing deliverable_id (got: '${HANDOFF_ID}')"
fi

# Verify both mutable artifacts got the SAME id (same workstream group)
if [[ "$PLAN_ID" == "$HANDOFF_ID" ]]; then
  pass "T7d: plan and handoff in same group share the same deliverable_id"
else
  fail "T7d: plan and handoff got different ids (plan=${PLAN_ID}, handoff=${HANDOFF_ID})"
fi

# Verify archived handoff was NOT written
ARCHIVED_ID="$(grep "^deliverable_id:" "${CLEAN_ROOT}/archive/handoffs/2026-06/2026-06-01-alpha-archived.md" 2>/dev/null | head -1)" || true
if [[ -z "$ARCHIVED_ID" ]]; then
  pass "T7e: immutable archived handoff was NOT written (derive-at-emit preserved)"
else
  fail "T7e: archived handoff was incorrectly mutated (got: '${ARCHIVED_ID}')"
fi

# Verify archived completion was NOT written
COMP_ID="$(grep "^deliverable_id:" "${CLEAN_ROOT}/archive/completed/2026-06/2026-06-01-alpha-comp.md" 2>/dev/null | head -1)" || true
if [[ -z "$COMP_ID" ]]; then
  pass "T7f: immutable completion entry was NOT written (derive-at-emit preserved)"
else
  fail "T7f: completion entry was incorrectly mutated (got: '${COMP_ID}')"
fi

# ---------------------------------------------------------------------------
# T8: Idempotency — running --write twice does NOT re-mint or change ids
# ---------------------------------------------------------------------------
# Run --write a second time on the same clean root
bash "$SUBJECT" --write --root "$CLEAN_ROOT" 2>/dev/null

PLAN_ID_2="$(grep "^deliverable_id:" "${CLEAN_ROOT}/docs/plans/2026-06-01-alpha.md" | head -1 | awk '{print $2}')"
HANDOFF_ID_2="$(grep "^deliverable_id:" "${CLEAN_ROOT}/state/handoffs/2026-06-01_alpha_handoff.md" | head -1 | awk '{print $2}')"

if [[ "$PLAN_ID_2" == "$PLAN_ID" ]]; then
  pass "T8a: plan deliverable_id unchanged on second --write (idempotent)"
else
  fail "T8a: plan deliverable_id changed from '${PLAN_ID}' to '${PLAN_ID_2}' (not idempotent)"
fi

if [[ "$HANDOFF_ID_2" == "$HANDOFF_ID" ]]; then
  pass "T8b: handoff deliverable_id unchanged on second --write (idempotent)"
else
  fail "T8b: handoff deliverable_id changed from '${HANDOFF_ID}' to '${HANDOFF_ID_2}' (not idempotent)"
fi

# Verify only ONE deliverable_id line exists in each file (no duplicate injection)
PLAN_ID_COUNT="$(grep -c "^deliverable_id:" "${CLEAN_ROOT}/docs/plans/2026-06-01-alpha.md" || true)"
if [[ "$PLAN_ID_COUNT" -eq 1 ]]; then
  pass "T8c: plan has exactly one deliverable_id line after two --write runs"
else
  fail "T8c: plan has ${PLAN_ID_COUNT} deliverable_id lines (expected 1)"
fi

HANDOFF_ID_COUNT="$(grep -c "^deliverable_id:" "${CLEAN_ROOT}/state/handoffs/2026-06-01_alpha_handoff.md" || true)"
if [[ "$HANDOFF_ID_COUNT" -eq 1 ]]; then
  pass "T8d: handoff has exactly one deliverable_id line after two --write runs"
else
  fail "T8d: handoff has ${HANDOFF_ID_COUNT} deliverable_id lines (expected 1)"
fi

# ---------------------------------------------------------------------------
# T9: Sidecar plan files are excluded from corpus
# ---------------------------------------------------------------------------
write_artifact "${CLEAN_ROOT}/docs/plans/2026-06-01-alpha.md.prior-art-check.md" \
  "title=Sidecar" "created=2026-06-01" "workstream=should-be-excluded"

SIDECAR_OUTPUT="$(bash "$SUBJECT" --dry-run --root "$CLEAN_ROOT" 2>/dev/null)"

if ! echo "$SIDECAR_OUTPUT" | grep -q "prior-art-check"; then
  pass "T9a: sidecar .prior-art-check.md excluded from corpus"
else
  fail "T9a: sidecar file was incorrectly included in corpus"
fi

if ! echo "$SIDECAR_OUTPUT" | grep -q "should-be-excluded"; then
  pass "T9b: sidecar workstream value not visible in grouping"
else
  fail "T9b: sidecar workstream value leaked into grouping"
fi

# ---------------------------------------------------------------------------
# T10: Completion entries group by `chain:` field (not workstream:)
# ---------------------------------------------------------------------------
COMP_ROOT="${TMPDIR_ROOT}/comp_coordinator"
mkdir -p "${COMP_ROOT}/bin"
mkdir -p "${COMP_ROOT}/state/handoffs"
mkdir -p "${COMP_ROOT}/archive/completed/2026-06"
mkdir -p "${COMP_ROOT}/docs/plans"
ln -sf "$MINT_HELPER" "${COMP_ROOT}/bin/mint-deliverable-id.sh"

write_artifact "${COMP_ROOT}/docs/plans/2026-06-01-comp-test.md" \
  "title=Comp Test Plan" "created=2026-06-01" "workstream=comp-test" "status=draft"

write_artifact "${COMP_ROOT}/archive/completed/2026-06/2026-06-01-comp-test-abc123.md" \
  "title=Comp Test Completion" "created=2026-06-01" "chain=comp-test" "status=pending-release"

COMP_OUTPUT="$(bash "$SUBJECT" --dry-run --root "$COMP_ROOT" 2>/dev/null)"
COMP_EXIT=$?

if [[ "$COMP_EXIT" -eq 0 ]]; then
  pass "T10a: completion with chain= groups cleanly with plan with workstream= (exit 0)"
else
  fail "T10a: unexpected exit ${COMP_EXIT} with completion + plan sharing workstream/chain key"
fi

if echo "$COMP_OUTPUT" | grep -q "comp-test"; then
  pass "T10b: completion chain field appears in grouping report"
else
  fail "T10b: completion chain field missing from grouping report"
fi

# ---------------------------------------------------------------------------
# T11: --write on unknown-workstream artifacts does NOT write (skips them)
# ---------------------------------------------------------------------------
UNKNOWN_ROOT="${TMPDIR_ROOT}/unknown_coordinator"
mkdir -p "${UNKNOWN_ROOT}/bin"
mkdir -p "${UNKNOWN_ROOT}/state/handoffs"
mkdir -p "${UNKNOWN_ROOT}/docs/plans"
ln -sf "$MINT_HELPER" "${UNKNOWN_ROOT}/bin/mint-deliverable-id.sh"

write_artifact "${UNKNOWN_ROOT}/docs/plans/2026-06-01-noworkstream.md" \
  "title=No Workstream Plan" "created=2026-06-01" "status=draft"

bash "$SUBJECT" --write --root "$UNKNOWN_ROOT" 2>/dev/null

NO_WS_ID="$(grep "^deliverable_id:" "${UNKNOWN_ROOT}/docs/plans/2026-06-01-noworkstream.md" 2>/dev/null | head -1)" || true
if [[ -z "$NO_WS_ID" ]]; then
  pass "T11a: artifact without workstream NOT stamped by --write (unknown group skipped)"
else
  fail "T11a: artifact without workstream was incorrectly stamped (got: '${NO_WS_ID}')"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
