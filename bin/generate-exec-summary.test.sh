#!/usr/bin/env bash
# generate-exec-summary.test.sh — Self-contained tests for generate-exec-summary.sh
#
# Purpose: Verifies MANAGED derivation, HAND-block verbatim preservation,
#   fail-loud on malformed HAND fences, --check flag, and new-file creation.
#
# Spec backlink: docs/plans/2026-07-03-exec-summary-per-repo-brief.md § C2 AC2/AC3/AC9/AC10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/generate-exec-summary.sh"

PASS=0
FAIL=0

pass() { printf 'PASS: %s\n' "$1"; PASS=$(( PASS + 1 )); }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Fixture: minimal fake git repo with README + coordinator state dir
# ---------------------------------------------------------------------------
TMPDIR_ROOT="$(mktemp -d)"
REPO="${TMPDIR_ROOT}/repo"
mkdir -p "$REPO/docs" "$REPO/state"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

# Init a bare git repo so generate-exec-summary.sh can resolve the git root.
git -C "$TMPDIR_ROOT" init "$REPO" -q 2>/dev/null || git init "$REPO" -q

# Minimal README with H1 + lead paragraph.
cat > "$REPO/README.md" <<'TEOF'
# Test Project — A Sample Repo

This is the lead paragraph describing what the project does.
It spans a single paragraph of meaningful content.

## Other section
TEOF

TARGET="$REPO/docs/exec-summary.md"

# ---------------------------------------------------------------------------
# T1: --check on a new (absent) target prints content without writing the file
# ---------------------------------------------------------------------------
OUTPUT="$(bash "$SUBJECT" --check 2>/dev/null)" || true

if echo "$OUTPUT" | grep -q 'kind: exec-summary'; then
    pass "T1a: --check emits frontmatter kind: exec-summary"
else
    fail "T1a: --check output missing 'kind: exec-summary'"
fi

if echo "$OUTPUT" | grep -q 'Test Project'; then
    pass "T1b: --check emits README H1 title in output"
else
    fail "T1b: --check output missing README H1 title"
fi

if echo "$OUTPUT" | grep -q '<!-- BEGIN HAND: special -->'; then
    pass "T1c: --check emits HAND: special fence"
else
    fail "T1c: --check output missing HAND: special fence"
fi

if echo "$OUTPUT" | grep -q '<!-- BEGIN MANAGED: identity -->'; then
    pass "T1d: --check emits MANAGED: identity fence"
else
    fail "T1d: --check output missing MANAGED: identity fence"
fi

if [[ ! -f "$TARGET" ]]; then
    pass "T1e: --check did NOT write the file"
else
    fail "T1e: --check wrote the file (should not)"
fi

# ---------------------------------------------------------------------------
# T2: New-file creation without --check
# ---------------------------------------------------------------------------
bash "$SUBJECT" 2>/dev/null

if [[ -f "$TARGET" ]]; then
    pass "T2a: new file created at docs/exec-summary.md"
else
    fail "T2a: file not created"
fi

if grep -q '<!-- BEGIN MANAGED: identity -->' "$TARGET"; then
    pass "T2b: file contains MANAGED: identity fence"
else
    fail "T2b: file missing MANAGED: identity fence"
fi

if grep -q '<!-- BEGIN HAND: special -->' "$TARGET"; then
    pass "T2c: file contains HAND: special fence"
else
    fail "T2c: file missing HAND: special fence"
fi

if grep -q '<!-- BEGIN MANAGED: progress -->' "$TARGET"; then
    pass "T2d: file contains MANAGED: progress fence"
else
    fail "T2d: file missing MANAGED: progress fence"
fi

if grep -q 'This is the lead paragraph' "$TARGET"; then
    pass "T2e: identity section contains README lead paragraph"
else
    fail "T2e: identity section missing README lead paragraph"
fi

# ---------------------------------------------------------------------------
# T3: HAND-block verbatim preservation on regen (AC3)
# ---------------------------------------------------------------------------
SENTINEL="MY_UNIQUE_SENTINEL_TEXT_7x9q"

# Edit the HAND: special block content in the generated file.
# Replace placeholder content between the fences with the sentinel.
python3 - "$TARGET" "$SENTINEL" <<'PEOF'
import sys, re

path = sys.argv[1]
sentinel = sys.argv[2]
content = open(path).read()

# Replace content between HAND: special fences.
new_content = re.sub(
    r'(<!-- BEGIN HAND: special -->).*?(<!-- END HAND: special -->)',
    r'\1\n' + sentinel + r'\n\2',
    content,
    flags=re.DOTALL
)
open(path, 'w').write(new_content)
PEOF

# Re-run the generator.
bash "$SUBJECT" 2>/dev/null

if grep -q "$SENTINEL" "$TARGET"; then
    pass "T3: HAND block edit survived regen verbatim (AC3)"
else
    fail "T3: HAND block edit was overwritten by regen"
fi

# ---------------------------------------------------------------------------
# T4: MANAGED: identity is refreshed on regen (not the old MANAGED text)
# ---------------------------------------------------------------------------
# We verify the README title still appears (MANAGED re-derived correctly).
if grep -q 'Test Project' "$TARGET"; then
    pass "T4: MANAGED: identity still contains README H1 title after regen"
else
    fail "T4: MANAGED: identity missing README H1 title after regen"
fi

# ---------------------------------------------------------------------------
# T5: Fail-loud if a HAND fence is removed from an existing file (AC9)
# ---------------------------------------------------------------------------
# Remove the END HAND: special fence from the target file.
python3 - "$TARGET" <<'PEOF'
import sys
path = sys.argv[1]
lines = open(path).readlines()
lines = [l for l in lines if '<!-- END HAND: special -->' not in l]
open(path, 'w').writelines(lines)
PEOF

EXIT_CODE=0
bash "$SUBJECT" 2>/dev/null || EXIT_CODE=$?

if [[ "$EXIT_CODE" -ne 0 ]]; then
    pass "T5a: generator exits non-zero when HAND fence is missing (AC9)"
else
    fail "T5a: generator should have exited non-zero with missing HAND fence"
fi

# Verify the file was NOT overwritten (still has sentinel from T3).
if grep -q "$SENTINEL" "$TARGET"; then
    pass "T5b: generator did NOT write to file when HAND fence malformed"
else
    fail "T5b: generator overwrote file despite missing HAND fence"
fi

# ---------------------------------------------------------------------------
# T6: git-log fallback when no week-changelog directory (AC10)
# ---------------------------------------------------------------------------
# Add a commit so git-log has something to show.
git -C "$REPO" add . 2>/dev/null || true
git -C "$REPO" -c user.email=test@test.com -c user.name=Test commit -m "initial" --allow-empty 2>/dev/null || true

# Recreate a clean target (no existing file).
rm -f "$TARGET"
bash "$SUBJECT" 2>/dev/null

if grep -q '<!-- BEGIN MANAGED: progress -->' "$TARGET"; then
    pass "T6a: progress MANAGED section present when no week-changelog"
else
    fail "T6a: progress MANAGED section missing"
fi

PROG_CONTENT="$(awk '
    /<!-- BEGIN MANAGED: progress -->/ { in_s=1; next }
    /<!-- END MANAGED: progress -->/ { exit }
    in_s { print }
' "$TARGET")"

if [[ -n "$PROG_CONTENT" ]]; then
    pass "T6b: progress section is not empty (git-log fallback or placeholder)"
else
    fail "T6b: progress section is empty — AC10 violation"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\nResults: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
