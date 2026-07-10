#!/usr/bin/env bash
# coordinator-safe-name.test.sh — test suite for coordinator-safe-name helper
#
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § AC1, AC2
#
# Coverage:
#   (a) timestamp --now: colon-free UTC form YYYY-MM-DDTHH-MM-SSZ, no colon
#   (b) timestamp --mtime <real-file>: colon-free stamp derived from file mtime
#   (c) slug: lowercases, replaces non-alnum with '-', trims, caps at 40 chars
#   (d) check: accepts safe name; rejects : ? * < > | " \ / + trailing dot/space
#   (e) lib sources cleanly via bash -c + path (no BASH_SOURCE self-location)
#   (f) cross-impl consistency: Python _ts_for_filename / _slug_from_title outputs
#       pass csn_check (SoT-by-test, no runtime coupling)
#   (g) parse-on-3.2: bash -n passes; no unguarded bash-4 constructs in lib/CLI

set -uo pipefail

# ---------------------------------------------------------------------------
# Locate paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib/coordinator-safe-name.sh"
CLI="$SCRIPT_DIR/coordinator-safe-name"

# Source the lib for direct function invocations
# shellcheck source=lib/coordinator-safe-name.sh
. "$LIB"

# ---------------------------------------------------------------------------
# Minimal test harness
# ---------------------------------------------------------------------------
_PASS=0
_FAIL=0

_pass() {
    printf 'PASS: %s\n' "$1"
    _PASS=$((_PASS + 1))
}

_fail() {
    printf 'FAIL: %s\n' "$1"
    _FAIL=$((_FAIL + 1))
}

# Run a command; expect it to succeed (exit 0)
_expect_pass() {
    local label="$1"; shift
    if "$@" 2>/dev/null; then
        _pass "$label"
    else
        _fail "$label (expected exit 0, got non-zero)"
    fi
}

# Run a command; expect it to fail (exit non-zero)
_expect_fail() {
    local label="$1"; shift
    if "$@" 2>/dev/null; then
        _fail "$label (expected non-zero, got exit 0)"
    else
        _pass "$label"
    fi
}

# ---------------------------------------------------------------------------
# (a) timestamp --now: matches YYYY-MM-DDTHH-MM-SSZ, contains no colon
# ---------------------------------------------------------------------------
_ts_now=$(csn_timestamp --now)

if printf '%s' "$_ts_now" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$'; then
    _pass "timestamp --now: matches YYYY-MM-DDTHH-MM-SSZ format (got: $_ts_now)"
else
    _fail "timestamp --now: format mismatch (got: '$_ts_now')"
fi

if printf '%s' "$_ts_now" | grep -qF ':'; then
    _fail "timestamp --now: contains colon (got: '$_ts_now')"
else
    _pass "timestamp --now: contains no colon"
fi

# ---------------------------------------------------------------------------
# (b) timestamp --mtime <real file>: colon-free stamp
# ---------------------------------------------------------------------------
_ts_mtime=$(csn_timestamp --mtime "$LIB")

if printf '%s' "$_ts_mtime" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$'; then
    _pass "timestamp --mtime: matches YYYY-MM-DDTHH-MM-SSZ format (got: $_ts_mtime)"
else
    _fail "timestamp --mtime: format mismatch (got: '$_ts_mtime')"
fi

if printf '%s' "$_ts_mtime" | grep -qF ':'; then
    _fail "timestamp --mtime: contains colon (got: '$_ts_mtime')"
else
    _pass "timestamp --mtime: contains no colon"
fi

# ---------------------------------------------------------------------------
# (c) slug: lowercase, non-alnum → '-', trim leading/trailing '-', cap at 40
# ---------------------------------------------------------------------------

# Basic lowercase conversion
_slug_upper=$(csn_slug "UPPERCASE")
if [ "$_slug_upper" = "uppercase" ]; then
    _pass "slug: lowercases input"
else
    _fail "slug: did not lowercase; got '$_slug_upper'"
fi

# Non-alphanumeric chars replaced with '-'
_slug_special=$(csn_slug "hello world! foo")
if printf '%s' "$_slug_special" | grep -qE '^[a-z0-9-]+$'; then
    _pass "slug: output is [a-z0-9-] only"
else
    _fail "slug: output contains illegal chars: '$_slug_special'"
fi

# No leading or trailing hyphen (case statement avoids grep '-$' flag-ambiguity)
_slug_trim=$(csn_slug "  leading and trailing  ")
case "$_slug_trim" in
    -*|*-) _fail "slug: has leading/trailing hyphen: '$_slug_trim'" ;;
    *)     _pass "slug: no leading/trailing hyphen (got: '$_slug_trim')" ;;
esac

# Caps at 40 chars
_slug_long=$(csn_slug "this is a very long title that definitely exceeds the forty character limit for slugs")
_slug_len=${#_slug_long}
if [ "$_slug_len" -le 40 ]; then
    _pass "slug: length $_slug_len <= 40 chars"
else
    _fail "slug: length $_slug_len > 40 chars"
fi

# Output must not end with a hyphen even after truncation
case "$_slug_long" in
    *-) _fail "slug: trailing hyphen after truncation: '$_slug_long'" ;;
    *)  _pass "slug: no trailing hyphen after truncation" ;;
esac

# ---------------------------------------------------------------------------
# (d) check: accepts safe name; rejects each NTFS-illegal char + trailing dot/space
# ---------------------------------------------------------------------------

_expect_pass "check: accepts safe name 'safe-filename-2026'"  csn_check "safe-filename-2026"
_expect_pass "check: accepts simple word 'hello'"             csn_check "hello"
_expect_pass "check: accepts alphanumeric '2026abc'"          csn_check "2026abc"

# One assertion per illegal char (spec requirement)
_expect_fail "check: rejects colon (:)"              csn_check "file:name"
_expect_fail "check: rejects question mark (?)"      csn_check "file?name"
_expect_fail "check: rejects asterisk (*)"           csn_check "file*name"
_expect_fail "check: rejects less-than (<)"          csn_check "file<name"
_expect_fail "check: rejects greater-than (>)"       csn_check "file>name"
_expect_fail "check: rejects pipe (|)"               csn_check "file|name"
_expect_fail "check: rejects double-quote (\")"      csn_check 'file"name'
_expect_fail 'check: rejects backslash (\)'          csn_check $'file\\name'
_expect_fail "check: rejects slash (/)"              csn_check "file/name"
_expect_fail "check: rejects trailing dot (.)"       csn_check "filename."
_expect_fail "check: rejects trailing space ( )"     csn_check "filename "

# ---------------------------------------------------------------------------
# (d2) CSN_ILLEGAL_CHARS → csn_check consistency assertion (F3)
# Drives every char in the constant through csn_check to prevent silent drift
# if a char is added to CSN_ILLEGAL_CHARS but its case is omitted from csn_check.
# Review: code-reviewer F3 — ties the two enumerations by test (option a)
# ---------------------------------------------------------------------------
_csn_illegal_len="${#CSN_ILLEGAL_CHARS}"
for (( _csi=0; _csi<_csn_illegal_len; _csi++ )); do
    _c="${CSN_ILLEGAL_CHARS:_csi:1}"
    _expect_fail "CSN_ILLEGAL_CHARS[${_csi}]='${_c}': csn_check rejects it in a component" \
        csn_check "file${_c}name"
done

# ---------------------------------------------------------------------------
# (e) lib sources cleanly via bash -c; no BASH_SOURCE self-location regression
# ---------------------------------------------------------------------------
if "$BASH" -c ". '$LIB'; csn_check 'ok'" 2>/dev/null; then
    _pass "lib: sources cleanly and csn_check works (no BASH_SOURCE side-effect)"
else
    _fail "lib: failed to source or csn_check failed in subprocess"
fi

# Negative: no shell source-array variable reference ($BASH_SOURCE or ${BASH_SOURCE...})
# in the lib (contract: pure functions + constants, no path-resolution side effects).
# Check for actual variable-reference syntax, not the word in comments/docs.
if grep -qE '\$\{?BASH_SOURCE' "$LIB"; then
    _fail "lib: contains \$BASH_SOURCE variable reference (violates no-self-location contract)"
else
    _pass "lib: no \$BASH_SOURCE variable reference in lib"
fi

# ---------------------------------------------------------------------------
# (f) Cross-impl consistency: Python sanitizer outputs pass csn_check
#     (SoT-by-test, no runtime coupling — the Python impls are independent)
# ---------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then

    # _ts_for_filename (coordinator-lesson-promote:328): replaces : and + with -
    # Review: code-reviewer F8 — removed _f_fail (set but never read; failures counted via _fail()/$_FAIL)
    while IFS= read -r py_out; do
        [ -z "$py_out" ] && continue
        if csn_check "$py_out" 2>/dev/null; then
            _pass "cross-impl: _ts_for_filename output passes csn_check: '$py_out'"
        else
            _fail "cross-impl: _ts_for_filename output rejected by csn_check: '$py_out'"
        fi
    done < <(python3 - <<'PYEOF' | tr -d '\r'
import re

def _ts_for_filename(iso_ts):
    return re.sub(r'[:+]', '-', iso_ts)

adversarial = [
    '2026-06-15T10:30:00+00:00',
    '2099-12-31T23:59:59Z',
    '2000-01-01T00:00:00+05:30',
    '2026-06-15T10:30:00-08:00',
    '2026-01-01T00:00:00+00:00',
]
for inp in adversarial:
    print(_ts_for_filename(inp))
PYEOF
)

    # _slug_from_title (coordinator-doc-new:295 / coordinator-lesson-promote:311)
    while IFS= read -r py_out; do
        [ -z "$py_out" ] && continue
        if csn_check "$py_out" 2>/dev/null; then
            _pass "cross-impl: _slug_from_title output passes csn_check: '$py_out'"
        else
            _fail "cross-impl: _slug_from_title output rejected by csn_check: '$py_out'"
        fi
    done < <(python3 - <<'PYEOF' | tr -d '\r'
import re

def _slug_from_title(title):
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:40]

adversarial = [
    'Hello World: The Final Episode',
    'Plan/Spec?? For <File> Naming | System',
    'UPPER CASE title with "quotes"',
    'trailing spaces   ',
    'Multiple---hyphens and CAPS',
    'file.name.with.dots',
    '   leading spaces too',
]
for inp in adversarial:
    result = _slug_from_title(inp)
    if result:
        print(result)
PYEOF
)

else
    printf 'SKIP (f): python3 not found — cross-impl consistency test skipped\n'
fi

# ---------------------------------------------------------------------------
# (g) Parse-on-3.2: bash -n syntax check + no unguarded bash-4 constructs
# ---------------------------------------------------------------------------

# bash -n validates syntax without executing (works on bash 3.2+)
if "$BASH" -n "$LIB" 2>/dev/null; then
    _pass "parse: lib passes bash -n syntax check"
else
    _fail "parse: lib fails bash -n syntax check"
fi

if "$BASH" -n "$CLI" 2>/dev/null; then
    _pass "parse: CLI passes bash -n syntax check"
else
    _fail "parse: CLI fails bash -n syntax check"
fi

# grep-assert: no unguarded bash-4 constructs in lib or CLI
# Bash-4 patterns: ${var,,} (lowercase), ${var^^} (uppercase), mapfile, declare -A
# Exclude comment lines to avoid false positives from doc comments that name the
# forbidden constructs as "what NOT to use" examples.
_BASH4_PATTERN='\$\{[^}]*,,\}|\$\{[^}]*\^\^\}|[[:space:]]mapfile[[:space:]]|declare[[:space:]]+-[^=]*A'

if grep -Ev '^[[:space:]]*#' "$LIB" | grep -qE "$_BASH4_PATTERN" 2>/dev/null; then
    _fail "parse: unguarded bash-4 construct found in lib (non-comment line)"
else
    _pass "parse: no unguarded bash-4 constructs in lib"
fi

if grep -Ev '^[[:space:]]*#' "$CLI" | grep -qE "$_BASH4_PATTERN" 2>/dev/null; then
    _fail "parse: unguarded bash-4 construct found in CLI (non-comment line)"
else
    _pass "parse: no unguarded bash-4 constructs in CLI"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\n--- Results: %d passed, %d failed ---\n' "$_PASS" "$_FAIL"
[ "$_FAIL" -eq 0 ]
