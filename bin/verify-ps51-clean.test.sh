#!/usr/bin/env bash
# verify-ps51-clean.test.sh — Tests for bin/verify-ps51-clean.sh
#
# Spec backlink: state/handoffs/2026-06-22_215618_windows-clean-install-verification.md
# (Part B). Path is relative to the ~/.claude meta-repo root; not present in distributed installs.
#
# Test cases:
#   TC1  No args → usage error, exit 2
#   TC2  Clean PS 5.1-valid script → OK verdict, exit 0 (or SKIP on non-Windows)
#   TC3  Script with deliberate parse error (unclosed brace) → FAIL verdict, exit 1
#        (skipped gracefully when powershell.exe absent)
#   TC4  Script with pwsh7-advisory syntax in a string literal (|| inside string) →
#        WARN from bash static scan, still exit 0 (advisory, not parse failure)
#   TC5  Directory arg with multiple .ps1 files — finds and checks them
#   TC6  Missing path emits a WARN to stderr, does not crash
#   TC7  Non-.ps1 file in a .ps1 directory is ignored
#   TC8  Script declaring #requires -Version 7.0 with a PS7-only operator (??) →
#        EXPECTED-PS7 verdict (not FAIL), exit 0
#   TC9  Empty directory (only .sh/.txt files, no .ps1) → exit 0, "No .ps1 files found"
#   TC10 Script declaring #requires -Version 7 (no minor) + ?? → EXPECTED-PS7
#   TC11 Script declaring #requires -Version 6.0 + parse error → FAIL (major<7 boundary)
#   TC12 BOM-encoded file with #requires -Version 7.0 + ?? → EXPECTED-PS7 (BOM must not mask #requires)
#
# Note on TC4: ??, ?. and pipeline && || ARE PS 5.1 parse errors when used as
# operators. The WARN path tests the bash static scan catching these patterns in
# contexts the PS 5.1 parser doesn't see (e.g. inside a string literal), which is
# intentionally conservative/advisory. On platforms without powershell.exe the
# script SKIPs and all TCs collapse to SKIP assertion.
#
# Usage: bash <this-file>
# Exit:  0 if all tests pass, non-zero on any failure.

set -euo pipefail

if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/verify-ps51-clean.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "ERROR: subject not found: $SUBJECT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pass/fail tally
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Temp-dir + cleanup
# ---------------------------------------------------------------------------
TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# ---------------------------------------------------------------------------
# Detect PS 5.1 availability (command -v: PATH check only, no window).
# popup-safe-env-suppressed
# ---------------------------------------------------------------------------
HAS_PS51=0
if command -v powershell.exe >/dev/null 2>&1; then  # popup-safe-env-suppressed
  HAS_PS51=1
fi

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# A clean PS 5.1-valid script (no parse errors, no pwsh7-only syntax)
CLEAN_PS1="${TMPDIR_BASE}/clean.ps1"
cat > "$CLEAN_PS1" <<'PSEOF'
# Clean PowerShell 5.1 script
param(
    [string]$Path = "C:\Temp"
)

function Get-Status {
    param([string]$Name)
    Write-Host "Checking: $Name"
    if (Test-Path $Name) {
        Write-Host "Exists"
    } else {
        Write-Host "Missing"
    }
}

Get-Status -Name $Path
PSEOF

# A script with a deliberate parse error: unclosed brace
BAD_PS1="${TMPDIR_BASE}/bad_parse.ps1"
cat > "$BAD_PS1" <<'PSEOF'
# Script with unclosed brace — parse error
function Broken {
    param([string]$X)
    if ($X -eq "test") {
        Write-Host "ok"
    # missing closing brace for function
PSEOF

# A script using || inside a string literal — bash static scan flags this as
# advisory WARN (conservative: || is a pwsh7 pipeline chain operator pattern),
# but PS 5.1 parses it fine (it's string content, not an operator).
# This tests the WARN path of the static scan while remaining PS 5.1-parseable.
WARN_PS1="${TMPDIR_BASE}/pwsh7_advisory.ps1"
cat > "$WARN_PS1" <<'PSEOF'
# Script with || inside a string — advisory static scan WARN, valid PS 5.1 parse
$cmdHint = "Try: apt-get install foo || apt-get install bar"
Write-Host $cmdHint
PSEOF

# A script that explicitly declares #requires -Version 7.0 and uses ?? as an
# operator. PS 5.1 will reject ?? as a parse error, but since the script declares
# a PS7 floor, the failure is expected (EXPECTED-PS7, not FAIL).
PS7_FLOORED_PS1="${TMPDIR_BASE}/ps7_floored.ps1"
cat > "$PS7_FLOORED_PS1" <<'PSEOF'
#requires -Version 7.0
# Script requiring PS7+ — uses null-coalescing operator
param([string]$Value = $null)
$result = $Value ?? "default-value"
Write-Host $result
PSEOF

# TC10 fixture: #requires -Version 7 (no minor version) + ?? operator.
# Tests the version-capture regex when there is no .minor component.
PS7_NO_MINOR_PS1="${TMPDIR_BASE}/ps7_no_minor.ps1"
cat > "$PS7_NO_MINOR_PS1" <<'PSEOF'
#requires -Version 7
# PS7 floor declared without minor version; ?? is a PS 5.1 parse error
param([string]$Value = $null)
$result = $Value ?? "default"
Write-Host $result
PSEOF

# TC11 fixture: #requires -Version 6.0 (major < 7) + deliberate parse error.
# A requires floor of major version < 7 should NOT set is_ps7_floored; the
# parse error must route to FAIL, not EXPECTED-PS7.
PS6_FLOORED_PS1="${TMPDIR_BASE}/ps6_floored.ps1"
cat > "$PS6_FLOORED_PS1" <<'PSEOF'
#requires -Version 6.0
# Requires PS6 — NOT a PS7 floor; parse error must be FAIL
param([string]$Value = $null)
$result = $Value ?? "default"
Write-Host $result
PSEOF

# TC12 fixture: BOM-encoded file with #requires -Version 7.0 on line 1 + a real PS7 operator.
# The UTF-8 BOM (EF BB BF) immediately precedes the #requires directive. Tests that the
# BOM-strip in the #requires detection loop correctly classifies this as EXPECTED-PS7 (not FAIL).
BOM_FLOORED_PS1="${TMPDIR_BASE}/bom_floored.ps1"
printf '\xef\xbb\xbf#requires -Version 7.0\n$x = $a ?? $b\n' > "$BOM_FLOORED_PS1"

# ---------------------------------------------------------------------------
# TC1 — No args → exit 2 (usage error)
# ---------------------------------------------------------------------------
RC=0
bash "$SUBJECT" 2>/dev/null || RC=$?
if [[ "$RC" -eq 2 ]]; then
  _pass "TC1: no-args → exit 2 (usage)"
else
  _fail "TC1: no-args usage error" "expected exit 2, got $RC"
fi

# ---------------------------------------------------------------------------
# TC2 — Clean script: OK verdict + exit 0, OR SKIP on non-Windows
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc2-err"
OUT=$(bash "$SUBJECT" "$CLEAN_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  # Non-Windows: expect SKIP line and exit 0
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC2: no powershell.exe → SKIP line + exit 0"
  else
    _fail "TC2: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Windows: expect OK verdict and exit 0
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -qE "^OK "; then
    _pass "TC2: clean script → OK verdict, exit 0"
  else
    _fail "TC2: clean script" "expected OK + exit 0; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC3 — Bad parse script (no PS7 floor): FAIL verdict + exit 1
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc3-err"
OUT=$(bash "$SUBJECT" "$BAD_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  # Non-Windows: SKIP behaviour
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC3: no powershell.exe → SKIP (parse-error test skipped gracefully)"
  else
    _fail "TC3: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Windows: expect FAIL verdict and exit 1
  if [[ "$RC" -eq 1 ]] && echo "$OUT" | grep -qE "^FAIL "; then
    _pass "TC3: script with parse error (no PS7 floor) → FAIL verdict, exit 1"
  else
    _fail "TC3: parse error script" "expected FAIL verdict + exit 1; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC4 — Script with || in string literal: WARN from bash scan, exit 0.
#
# The || is inside a string so PS 5.1 parses it fine. The bash static scan
# conservatively flags any || line as advisory WARN. Exit must be 0
# (WARN does not fail).
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc4-err"
OUT=$(bash "$SUBJECT" "$WARN_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC4: no powershell.exe → SKIP (warn test skipped gracefully)"
  else
    _fail "TC4: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # WARN should appear and exit should be 0 (warn doesn't fail)
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -qE "^WARN "; then
    _pass "TC4: || in string literal → WARN from bash scan, exit 0 (advisory, not parse fail)"
  else
    _fail "TC4: bash static scan warn" "expected WARN + exit 0; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC5 — Directory arg: finds multiple .ps1 files
# ---------------------------------------------------------------------------
DIR5="${TMPDIR_BASE}/tc5dir"
mkdir -p "$DIR5"
cp "$CLEAN_PS1" "$DIR5/script_a.ps1"
cp "$WARN_PS1"  "$DIR5/script_b.ps1"

RC=0
OUT=""
ERR_F="${TMPDIR_BASE}/tc5-err"
OUT=$(bash "$SUBJECT" "$DIR5" 2>"$ERR_F") || RC=$?

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC5: no powershell.exe → SKIP on directory arg"
  else
    _fail "TC5: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Both scripts parse-clean (clean + warn-only); summary should show 2/2
  if echo "$OUT" | grep -q "2/2 parse-clean"; then
    _pass "TC5: directory arg finds 2 .ps1 files, 2/2 parse-clean (one with WARN)"
  else
    _fail "TC5: directory arg" "expected 2/2 parse-clean in summary; got: out=$OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC6 — Non-existent path emits a WARN to stderr, does not crash
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc6-err"
# Pass one valid file and one non-existent path; should not crash
OUT=$(bash "$SUBJECT" "$CLEAN_PS1" "/nonexistent/path/that/does/not/exist.ps1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC6: no powershell.exe → SKIP (missing-path test skipped gracefully)"
  else
    _fail "TC6: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Should not crash (exit 0 since the clean script is valid)
  # Missing path should produce a WARN on stderr
  if [[ "$RC" -eq 0 ]] && echo "$ERR" | grep -q "WARN"; then
    _pass "TC6: missing path → WARN on stderr, no crash, exit 0"
  else
    _fail "TC6: missing path handling" "expected WARN on stderr + exit 0; got RC=$RC err=$ERR out=$OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC7 — Non-.ps1 files in a directory are ignored
# ---------------------------------------------------------------------------
DIR7="${TMPDIR_BASE}/tc7dir"
mkdir -p "$DIR7"
cp "$CLEAN_PS1" "$DIR7/good.ps1"
echo "this is not a ps1 file" > "$DIR7/ignored.sh"
echo "also not ps1" > "$DIR7/ignored.txt"

RC=0
OUT=""
ERR_F="${TMPDIR_BASE}/tc7-err"
OUT=$(bash "$SUBJECT" "$DIR7" 2>"$ERR_F") || RC=$?

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC7: no powershell.exe → SKIP"
  else
    _fail "TC7: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Only 1 file should be processed (the .ps1)
  if echo "$OUT" | grep -q "1/1 parse-clean"; then
    _pass "TC7: non-.ps1 files in directory are ignored; only .ps1 counted"
  else
    _fail "TC7: non-.ps1 ignored" "expected 1/1 parse-clean; got: out=$OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC8 — Script declaring #requires -Version 7.0 with a PS7-only operator (??):
#        yields EXPECTED-PS7 (not FAIL) and exit 0.
#
# This tests that a deliberate PS7 floor is distinguished from accidental
# incompatibility. The script has a real PS 5.1 parse error (??) but the
# #requires directive signals the error is by-design.
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc8-err"
OUT=$(bash "$SUBJECT" "$PS7_FLOORED_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC8: no powershell.exe → SKIP (EXPECTED-PS7 test skipped gracefully)"
  else
    _fail "TC8: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # Expect: EXPECTED-PS7 verdict line AND exit 0 (not FAIL, not exit 1)
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -qE "^EXPECTED-PS7 "; then
    _pass "TC8: #requires -Version 7.0 + ?? parse error → EXPECTED-PS7 verdict, exit 0"
  else
    _fail "TC8: EXPECTED-PS7 classification" "expected EXPECTED-PS7 verdict + exit 0; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC9 — Empty directory (only .sh / .txt files, no .ps1): exit 0 + "No .ps1 files found"
# This check is platform-agnostic: the script exits before any PS engine call.
# ---------------------------------------------------------------------------
DIR9="${TMPDIR_BASE}/tc9dir"
mkdir -p "$DIR9"
echo "#!/bin/bash" > "$DIR9/ignored.sh"
echo "plain text" > "$DIR9/ignored.txt"

RC=0
OUT=""
ERR_F="${TMPDIR_BASE}/tc9-err"
OUT=$(bash "$SUBJECT" "$DIR9" 2>"$ERR_F") || RC=$?

if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "No .ps1 files found"; then
  _pass "TC9: empty dir (no .ps1) → exit 0 + 'No .ps1 files found'"
else
  _fail "TC9: empty dir" "expected exit 0 + 'No .ps1 files found'; got RC=$RC out=$OUT"
fi

# ---------------------------------------------------------------------------
# TC10 — #requires -Version 7 (no minor version) + ?? → EXPECTED-PS7, exit 0
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc10-err"
OUT=$(bash "$SUBJECT" "$PS7_NO_MINOR_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC10: PS51 absent → SKIP (#requires -Version 7 no-minor test)"
  else
    _fail "TC10: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -qE "^EXPECTED-PS7 "; then
    _pass "TC10: #requires -Version 7 (no minor) + ?? → EXPECTED-PS7, exit 0"
  else
    _fail "TC10: version-no-minor EXPECTED-PS7" "expected EXPECTED-PS7 + exit 0; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC11 — #requires -Version 6.0 (major < 7) + parse error → FAIL, exit 1
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc11-err"
OUT=$(bash "$SUBJECT" "$PS6_FLOORED_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC11: PS51 absent → SKIP (#requires -Version 6.0 test)"
  else
    _fail "TC11: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  if [[ "$RC" -eq 1 ]] && echo "$OUT" | grep -qE "^FAIL "; then
    _pass "TC11: #requires -Version 6.0 + parse error → FAIL (major<7 boundary), exit 1"
  else
    _fail "TC11: version-6-not-ps7-floor" "expected FAIL verdict + exit 1; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# TC12 — BOM-encoded file with #requires -Version 7.0 + ?? operator → EXPECTED-PS7, exit 0
#
# A UTF-8 BOM (EF BB BF) at the very start of the file must not mask the #requires
# directive. The BOM-strip in the #requires scan loop removes it before regex matching,
# so the file is correctly classified as EXPECTED-PS7 (not FAIL).
# ---------------------------------------------------------------------------
RC=0
OUT=""
ERR=""
ERR_F="${TMPDIR_BASE}/tc12-err"
OUT=$(bash "$SUBJECT" "$BOM_FLOORED_PS1" 2>"$ERR_F") || RC=$?
ERR=$(cat "$ERR_F")

if [[ $HAS_PS51 -eq 0 ]]; then
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -q "^SKIP:"; then
    _pass "TC12: PS51 absent → SKIP (BOM-floored EXPECTED-PS7 test skipped gracefully)"
  else
    _fail "TC12: SKIP path (no ps51)" "expected SKIP + exit 0; got RC=$RC out=$OUT"
  fi
else
  # BOM must not prevent #requires -Version 7.0 detection → EXPECTED-PS7, not FAIL
  if [[ "$RC" -eq 0 ]] && echo "$OUT" | grep -qE "^EXPECTED-PS7 "; then
    _pass "TC12: BOM + #requires -Version 7.0 + ?? → EXPECTED-PS7 verdict, exit 0 (BOM stripped correctly)"
  else
    _fail "TC12: BOM-floored EXPECTED-PS7" "expected EXPECTED-PS7 verdict + exit 0; got RC=$RC out=$OUT err=$ERR"
  fi
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL (${TOTAL} total)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
