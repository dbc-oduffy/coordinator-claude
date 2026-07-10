#!/usr/bin/env bash
# workday-complete-backfill-inject-anchor.test.sh — smoke test for inject-anchor.sh
#
# Builds a temp git repo with fixture daily summaries and asserts each exit code path:
#   exit 0  — anchor injected
#   exit 10 — already-anchored (idempotent skip)
#   exit 20 — summary absent
#   exit 30 — content-completeness guard fired
#
# Usage: bash workday-complete-backfill-inject-anchor.test.sh
# Exits non-zero on any failure.
#
# Spec backlink: docs/plans/2026-07-02-backfill-anchor-injection-contract.md § Deliverable A

# bash >=4 guard (consistent with the script under test)
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (running ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INJECT="${SCRIPT_DIR}/workday-complete-backfill-inject-anchor.sh"

if [[ ! -f "$INJECT" ]]; then
  echo "FATAL: inject script not found at ${INJECT}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pass/fail/skip counters
# ---------------------------------------------------------------------------
_PASS=0
_FAIL=0
_SKIP=0

_assert_exit() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$actual" -eq "$expected" ]]; then
    echo "  PASS: ${desc} (exit=${actual})"
    _PASS=$(( _PASS + 1 ))
  else
    echo "  FAIL: ${desc} (expected exit=${expected}, got=${actual})"
    _FAIL=$(( _FAIL + 1 ))
  fi
}

_assert_grep() {
  local desc="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  PASS: ${desc}"
    _PASS=$(( _PASS + 1 ))
  else
    echo "  FAIL: ${desc} — pattern '${pattern}' not found in ${file}"
    _FAIL=$(( _FAIL + 1 ))
  fi
}

_assert_no_grep() {
  local desc="$1" pattern="$2" file="$3"
  if ! grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  PASS: ${desc}"
    _PASS=$(( _PASS + 1 ))
  else
    echo "  FAIL: ${desc} — pattern '${pattern}' was unexpectedly found in ${file}"
    _FAIL=$(( _FAIL + 1 ))
  fi
}

# ---------------------------------------------------------------------------
# Set up temp git repo
# ---------------------------------------------------------------------------
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

REPO="${TMPDIR_TEST}/repo"
mkdir -p "$REPO"

git init "$REPO" >/dev/null 2>&1
git -C "$REPO" config user.email "test@example.com"
git -C "$REPO" config user.name "Smoke Test"

# Initial commit on main branch
echo "root" > "${REPO}/README.md"
git -C "$REPO" add README.md
git -C "$REPO" commit -m "init" >/dev/null 2>&1
INIT_SHA="$(git -C "$REPO" rev-parse HEAD)"
# Rename default branch to main (tolerates both git init behaviours)
git -C "$REPO" branch -M main 2>/dev/null || true

# Create a work/testmachine/ branch so the machine derivation resolves to "testmachine"
git -C "$REPO" checkout -b "work/testmachine/2026-01-15" >/dev/null 2>&1
echo "work" >> "${REPO}/README.md"
git -C "$REPO" add README.md
git -C "$REPO" commit -m "work commit on testmachine" >/dev/null 2>&1
WORK_SHA="$(git -C "$REPO" rev-parse HEAD)"

# Return to main
git -C "$REPO" checkout main >/dev/null 2>&1

# Create required directory tree
mkdir -p "${REPO}/archive/daily-summaries"
mkdir -p "${REPO}/archive/completed/2026-01"

# Constants shared across cases
TEST_DATE="2026-01-15"
TODAY_OVERRIDE="2026-01-20"
ABSENT_DATE="2026-01-16"
GAP_DATE="2026-01-17"

# ---------------------------------------------------------------------------
# Case 1: exit 0 — anchor injected (flat file, no frontmatter, no completion entries)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 1: exit 0 (injected) ==="
cat > "${REPO}/archive/daily-summaries/${TEST_DATE}.md" << 'EOF'
# Daily Summary — 2026-01-15

## Work Completed

- bullet one
- bullet two
EOF

_rc=0
bash "$INJECT" "$REPO" "$TEST_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "inject returns exit 0" 0 $_rc

# Verify the anchor lines were written
_assert_grep "covered_tip_sha line present" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${TEST_DATE}.md"
_assert_grep "covered_machine line present" "^covered_machine:" "${REPO}/archive/daily-summaries/${TEST_DATE}.md"
_assert_grep "prose note present" "Record anchor injected" "${REPO}/archive/daily-summaries/${TEST_DATE}.md"
_assert_grep "machine resolved to testmachine" "covered_machine: testmachine" "${REPO}/archive/daily-summaries/${TEST_DATE}.md"

# The full SHA should be 40 chars in the anchor line
_injected_sha="$(grep '^covered_tip_sha:' "${REPO}/archive/daily-summaries/${TEST_DATE}.md" | awk '{print $2}')"
if [[ ${#_injected_sha} -eq 40 ]]; then
  echo "  PASS: injected SHA is 40 chars"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: injected SHA is '${_injected_sha}' (expected 40 chars, got ${#_injected_sha})"
  _FAIL=$(( _FAIL + 1 ))
fi

# ---------------------------------------------------------------------------
# Case 2: exit 10 — already anchored (idempotent, file unchanged)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 2: exit 10 (already-anchored) ==="
# File was anchored in Case 1 — call again on the same file
_sha_before="$(grep '^covered_tip_sha:' "${REPO}/archive/daily-summaries/${TEST_DATE}.md" | awk '{print $2}')"
_rc=0
bash "$INJECT" "$REPO" "$TEST_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "re-inject returns exit 10" 10 $_rc

# SHA should not have changed
_sha_after="$(grep '^covered_tip_sha:' "${REPO}/archive/daily-summaries/${TEST_DATE}.md" | awk '{print $2}')"
if [[ "$_sha_before" == "$_sha_after" ]]; then
  echo "  PASS: file unchanged after idempotent call"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: file was modified (sha changed from ${_sha_before} to ${_sha_after})"
  _FAIL=$(( _FAIL + 1 ))
fi

# ---------------------------------------------------------------------------
# Case Bump-1: exit 0 — stale anchor (recorded is a strict ancestor of target) is
# bumped in place to the descendant tip, not reported "already-anchored".
# ---------------------------------------------------------------------------
echo ""
echo "=== Case Bump-1: exit 0 (stale anchor bumped) ==="
BUMP1_DATE="2026-01-23"
cat > "${REPO}/archive/daily-summaries/${BUMP1_DATE}.md" << EOF
# Daily Summary — ${BUMP1_DATE}

covered_tip_sha: ${INIT_SHA}
covered_machine: testmachine

## Work Completed

- bullet one
- bullet two
EOF

_rc=0
bash "$INJECT" "$REPO" "$BUMP1_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "stale anchor bump returns exit 0" 0 $_rc

_bump1_sha_after="$(grep -m1 '^covered_tip_sha:' "${REPO}/archive/daily-summaries/${BUMP1_DATE}.md" | awk '{print $2}')"
if [[ "$_bump1_sha_after" == "$WORK_SHA" ]]; then
  echo "  PASS: covered_tip_sha bumped to WORK_SHA"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: covered_tip_sha is '${_bump1_sha_after}', expected ${WORK_SHA}"
  _FAIL=$(( _FAIL + 1 ))
fi
if [[ ${#_bump1_sha_after} -eq 40 ]]; then
  echo "  PASS: bumped SHA is 40 chars"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: bumped SHA is '${_bump1_sha_after}' (expected 40 chars, got ${#_bump1_sha_after})"
  _FAIL=$(( _FAIL + 1 ))
fi
_assert_grep "covered_machine intact after bump" "^covered_machine: testmachine" "${REPO}/archive/daily-summaries/${BUMP1_DATE}.md"

# ---------------------------------------------------------------------------
# Case Bump-2: exit 10 — a FRESH/newer anchor is never regressed when the target
# passed in is an ancestor of what's already recorded.
# ---------------------------------------------------------------------------
echo ""
echo "=== Case Bump-2: exit 10 (fresh anchor not regressed) ==="
BUMP2_DATE="2026-01-24"
cat > "${REPO}/archive/daily-summaries/${BUMP2_DATE}.md" << EOF
# Daily Summary — ${BUMP2_DATE}

covered_tip_sha: ${WORK_SHA}
covered_machine: testmachine

## Work Completed

- bullet one
- bullet two
EOF

_rc=0
bash "$INJECT" "$REPO" "$BUMP2_DATE" "$INIT_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "fresh anchor with ancestor target returns exit 10" 10 $_rc

_bump2_sha_after="$(grep -m1 '^covered_tip_sha:' "${REPO}/archive/daily-summaries/${BUMP2_DATE}.md" | awk '{print $2}')"
if [[ "$_bump2_sha_after" == "$WORK_SHA" ]]; then
  echo "  PASS: covered_tip_sha unchanged (still WORK_SHA)"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: covered_tip_sha changed to '${_bump2_sha_after}', expected unchanged ${WORK_SHA}"
  _FAIL=$(( _FAIL + 1 ))
fi

# ---------------------------------------------------------------------------
# Case 3: exit 20 — summary absent (no file for the date)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 3: exit 20 (summary-absent) ==="
# Verify no file exists for ABSENT_DATE
if [[ ! -f "${REPO}/archive/daily-summaries/${ABSENT_DATE}.md" ]]; then
  _rc=0
  bash "$INJECT" "$REPO" "$ABSENT_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
  _assert_exit "absent summary returns exit 20" 20 $_rc
else
  echo "  FAIL: ${ABSENT_DATE}.md unexpectedly exists"
  _FAIL=$(( _FAIL + 1 ))
fi

# ---------------------------------------------------------------------------
# Case 4: exit 30 — content-completeness guard (1 bullet, 5 completion entries)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 4: exit 30 (content-gap guard) ==="

# Skip if node is not available (query-completions requires node)
if ! command -v node &>/dev/null; then
  echo "  SKIP: node not available; content-gap guard requires node for query-completions"
  _SKIP=$(( _SKIP + 1 ))
else
  cat > "${REPO}/archive/daily-summaries/${GAP_DATE}.md" << 'EOF'
# Daily Summary — 2026-01-17

## Work Completed

- one bullet only (far fewer than the completion entries)
EOF

  # Create 5 completion entries for GAP_DATE to trigger the guard
  for _i in 1 2 3 4 5; do
    cat > "${REPO}/archive/completed/2026-01/entry-${GAP_DATE}-${_i}.md" << EOF
---
title: "Work item ${_i} for ${GAP_DATE}"
created: ${GAP_DATE}
nature: infra
---

Body of work item ${_i}.
EOF
  done

  _rc=0
  bash "$INJECT" "$REPO" "$GAP_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
  _assert_exit "content-gap guard returns exit 30" 30 $_rc

  # Verify no anchor was injected
  _assert_no_grep "no anchor injected when guard fires" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${GAP_DATE}.md"
fi

# ---------------------------------------------------------------------------
# Case 5: frontmatter file — anchor goes into frontmatter, note after H1
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 5: exit 0 (frontmatter file) ==="
FM_DATE="2026-01-18"
mkdir -p "${REPO}/archive/daily-summaries"
cat > "${REPO}/archive/daily-summaries/${FM_DATE}.md" << 'EOF'
---
backfilled: true
---

# Daily Summary — 2026-01-18

## Work Completed

- widget refactor
- test coverage bump
EOF

_rc=0
bash "$INJECT" "$REPO" "$FM_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "frontmatter file inject returns exit 0" 0 $_rc

_assert_grep "covered_tip_sha in frontmatter file" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${FM_DATE}.md"
_assert_grep "covered_machine in frontmatter file" "^covered_machine:" "${REPO}/archive/daily-summaries/${FM_DATE}.md"

# ---------------------------------------------------------------------------
# Case 6: bad SHA — must fail loud (exit 1)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 6: bad SHA fails loud ==="
BAD_DATE="2026-01-19"
cat > "${REPO}/archive/daily-summaries/${BAD_DATE}.md" << 'EOF'
# Daily Summary — 2026-01-19

## Work Completed

- some work
EOF

_rc=0
bash "$INJECT" "$REPO" "$BAD_DATE" "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
if [[ "$_rc" -ne 0 ]]; then
  echo "  PASS: bad SHA returns non-zero (exit=${_rc})"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: bad SHA should return non-zero, got exit 0"
  _FAIL=$(( _FAIL + 1 ))
fi

# ---------------------------------------------------------------------------
# Case 7: unclosed frontmatter exits non-zero and injects no anchor (F1/F5)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 7: unclosed frontmatter exits non-zero ==="
UNCLOSED_DATE="2026-01-21"
cat > "${REPO}/archive/daily-summaries/${UNCLOSED_DATE}.md" << 'EOF'
---
backfilled: true
(no closing ---)
# Daily Summary — 2026-01-21

## Work Completed
- some work
EOF
_rc=0
bash "$INJECT" "$REPO" "$UNCLOSED_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
if [[ "$_rc" -ne 0 ]]; then
  echo "  PASS: unclosed frontmatter returns non-zero (exit=${_rc})"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: unclosed frontmatter should fail, got exit 0"
  _FAIL=$(( _FAIL + 1 ))
fi
# Assert no anchor was written
_assert_no_grep "no anchor injected on unclosed frontmatter" "^covered_tip_sha:" \
  "${REPO}/archive/daily-summaries/${UNCLOSED_DATE}.md"

# ---------------------------------------------------------------------------
# Case 8: non-frontmatter file without # Daily Summary H1 exits non-zero (F6)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case 8: no H1 in non-frontmatter file exits non-zero ==="
NOH1_DATE="2026-01-22"
cat > "${REPO}/archive/daily-summaries/${NOH1_DATE}.md" << 'EOF'
## Work Completed

- something was done but H1 is missing
EOF
_rc=0
bash "$INJECT" "$REPO" "$NOH1_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
if [[ "$_rc" -ne 0 ]]; then
  echo "  PASS: no-H1 file returns non-zero (exit=${_rc})"
  _PASS=$(( _PASS + 1 ))
else
  echo "  FAIL: no-H1 file should fail, got exit 0"
  _FAIL=$(( _FAIL + 1 ))
fi
_assert_no_grep "no anchor injected when H1 absent" "^covered_tip_sha:" \
  "${REPO}/archive/daily-summaries/${NOH1_DATE}.md"

# ---------------------------------------------------------------------------
# Case A: exit 30 — commit-density PRIMARY guard fires (cited=1, range=6 → 1*2=2 < 6)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case A: exit 30 (commit-density guard — primary fires on cited<50%) ==="

DENSITY_DATE="2026-05-10"

# Create a branch with 6 commits all pinned to DENSITY_DATE via author/committer env
git -C "$REPO" checkout -b "density-test-branch" main >/dev/null 2>&1
_density_first_sha=""
for _i in 1 2 3 4 5 6; do
  echo "density ${_i}" >> "${REPO}/README.md"
  git -C "$REPO" add README.md
  GIT_AUTHOR_DATE="${DENSITY_DATE}T09:00:0${_i}" \
  GIT_COMMITTER_DATE="${DENSITY_DATE}T09:00:0${_i}" \
    git -C "$REPO" commit -m "density commit ${_i}" >/dev/null 2>&1
  if [[ "$_i" -eq 1 ]]; then
    _density_first_sha="$(git -C "$REPO" rev-parse HEAD)"
  fi
done
DENSITY_SHA="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" checkout main >/dev/null 2>&1

# Summary cites exactly 1 in-range SHA (cited=1, range=6 → 1*2=2 < 6 → PRIMARY fires).
# The morning-run phrase is present but range=6 < 10 so the corroborator does NOT fire.
# This case exercises the PRIMARY density guard.
cat > "${REPO}/archive/daily-summaries/${DENSITY_DATE}.md" << EOF
# Daily Summary — ${DENSITY_DATE}

## Work Completed

- morning run notes — wraps the tail of yesterday's session into today
- one feature shipped (${_density_first_sha})
- some docs updated
EOF

_rc=0
bash "$INJECT" "$REPO" "$DENSITY_DATE" "$DENSITY_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "density guard returns exit 30" 30 $_rc
_assert_no_grep "no anchor injected when density guard fires" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${DENSITY_DATE}.md"

# ---------------------------------------------------------------------------
# Case C: exit 30 — corroborator fires in isolation (primary would NOT fire)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case C: exit 30 (corroborator fires; primary abstains — cited*2 >= range) ==="

CORR_DATE="2026-06-01"

# Create 10 commits (>= the corroborator's threshold of 10) pinned to CORR_DATE
git -C "$REPO" checkout -b "corr-test-branch" main >/dev/null 2>&1
_corr_sha1="" _corr_sha2="" _corr_sha3="" _corr_sha4="" _corr_sha5=""
for _i in $(seq 1 10); do
  echo "corr ${_i}" >> "${REPO}/README.md"
  git -C "$REPO" add README.md
  printf -v _ct "%02d" "$_i"
  GIT_AUTHOR_DATE="${CORR_DATE}T09:00:${_ct}" \
  GIT_COMMITTER_DATE="${CORR_DATE}T09:00:${_ct}" \
    git -C "$REPO" commit -m "corr commit ${_i}" >/dev/null 2>&1
  case "$_i" in
    1) _corr_sha1="$(git -C "$REPO" rev-parse HEAD)" ;;
    2) _corr_sha2="$(git -C "$REPO" rev-parse HEAD)" ;;
    3) _corr_sha3="$(git -C "$REPO" rev-parse HEAD)" ;;
    4) _corr_sha4="$(git -C "$REPO" rev-parse HEAD)" ;;
    5) _corr_sha5="$(git -C "$REPO" rev-parse HEAD)" ;;
  esac
done
CORR_SHA="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" checkout main >/dev/null 2>&1

# Summary cites 5 in-range SHAs: 5*2=10 >= 10 → primary does NOT fire.
# Morning-run note present + range=10 >= 10 → CORROBORATOR fires → exit 30.
# This case exercises the CORROBORATOR guard in isolation.
cat > "${REPO}/archive/daily-summaries/${CORR_DATE}.md" << EOF
# Daily Summary — ${CORR_DATE}

morning run notes — wraps the tail of yesterday's session into today

## Work Completed

- shipped ${_corr_sha1}
- completed ${_corr_sha2}
- fixed ${_corr_sha3}
- resolved ${_corr_sha4}
- finalized ${_corr_sha5}
- additional prose work items not requiring SHA citations
EOF

_rc=0
bash "$INJECT" "$REPO" "$CORR_DATE" "$CORR_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "corroborator fires in isolation (exit 30)" 30 $_rc
_assert_no_grep "no anchor injected when corroborator fires" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${CORR_DATE}.md"

# ---------------------------------------------------------------------------
# Case B: exit 0 — lowercase H1 injects successfully (case-insensitive fix)
# ---------------------------------------------------------------------------
echo ""
echo "=== Case B: exit 0 (lowercase H1 injects) ==="

LOWER_DATE="2026-02-01"
# WORK_SHA has no commits dated LOWER_DATE (they were made 'now') → range_count=0 → density guard skipped
cat > "${REPO}/archive/daily-summaries/${LOWER_DATE}.md" << 'EOF'
# Daily summary — 2026-02-01

## Work Completed

- first bullet
- second bullet
EOF

_rc=0
bash "$INJECT" "$REPO" "$LOWER_DATE" "$WORK_SHA" "$TODAY_OVERRIDE" 2>/dev/null || _rc=$?
_assert_exit "lowercase H1 inject returns exit 0" 0 $_rc
_assert_grep "anchor injected for lowercase H1" "^covered_tip_sha:" "${REPO}/archive/daily-summaries/${LOWER_DATE}.md"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
if [[ "$_SKIP" -gt 0 ]]; then
  echo "Results: ${_PASS} passed, ${_FAIL} failed, ${_SKIP} skipped"
else
  echo "Results: ${_PASS} passed, ${_FAIL} failed"
fi
echo "========================================"

if [[ "$_FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
