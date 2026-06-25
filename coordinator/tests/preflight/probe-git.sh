#!/usr/bin/env bash
# tests/preflight/probe-git.sh
#
# Purpose: verify _co_probe_git emits correct NDJSON and that _co_prereq_probe_all
# emits exactly 10 lines with git as the first probe.
#
# Test cases:
#   T1 — _co_probe_git emits name="git", severity="hard", status="pass" when git is present.
#   T2 — _co_prereq_probe_all emits exactly 10 NDJSON lines.
#   T3 — The FIRST line of _co_prereq_probe_all output has name="git".
#
# Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md § C2 (AC3)
#
# Cross-platform portability (DR-148):
#   Requires bash >= 4 (self-re-exec if needed).
#   BSD-portable: no grep -P, no date -d, no sed -i.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate bash >= 4 and self-re-exec if needed.
# ---------------------------------------------------------------------------
_BASH4=""
for _b in "$BASH" /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash bash; do
    [[ -z "${_b:-}" ]] && continue
    if "$_b" -c '[[ "${BASH_VERSINFO[0]}" -ge 4 ]]' 2>/dev/null; then
        _BASH4="$_b"
        break
    fi
done

if [[ -z "$_BASH4" ]]; then
    echo "ERROR: bash >= 4 required but not found." >&2
    echo "Remediation: brew install bash" >&2
    exit 1
fi

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Resolve paths.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "${SCRIPT_DIR}/../../scripts/lib" && pwd)"
PREREQ_PROBE_SH="${LIB_DIR}/prereq_probe.sh"

if [[ ! -f "${PREREQ_PROBE_SH}" ]]; then
    echo "ERROR: prereq_probe.sh not found at ${PREREQ_PROBE_SH}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Test counters and helpers.
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
ERRORS=()

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

# Extract a JSON field value from a compact NDJSON line.
# _json_field <json-line> <field>
_json_field() {
    local _json="$1" _field="$2"
    printf '%s' "$_json" | sed -n "s/.*\"${_field}\":\"\([^\"]*\)\".*/\1/p" | head -1
}

# ---------------------------------------------------------------------------
# Source prereq_probe.sh via COORDINATOR_PREREQ_PROBE_LIB_DIR so the lib-dir
# resolution inside prereq_probe.sh finds manifest_reader.sh and step_zero_emit.sh.
# ---------------------------------------------------------------------------
export COORDINATOR_PREREQ_PROBE_LIB_DIR="${LIB_DIR}"
# shellcheck source=../../scripts/lib/prereq_probe.sh
source "${PREREQ_PROBE_SH}"

# ---------------------------------------------------------------------------
# T1: _co_probe_git emits name="git", severity="hard", status="pass" when git present.
# ---------------------------------------------------------------------------
echo ""
echo "--- T1: _co_probe_git emits pass/hard when git is present ---"

_t1_out="$(_co_probe_git)"

_t1_name="$(_json_field "$_t1_out" "name")"
_t1_status="$(_json_field "$_t1_out" "status")"
_t1_severity="$(_json_field "$_t1_out" "severity")"

if [[ "$_t1_name" == "git" ]]; then
    _pass "T1: name field is 'git'"
else
    _fail "T1: expected name='git', got '${_t1_name}' (full JSON: ${_t1_out})"
fi

if [[ "$_t1_severity" == "hard" ]]; then
    _pass "T1: severity field is 'hard'"
else
    _fail "T1: expected severity='hard', got '${_t1_severity}' (full JSON: ${_t1_out})"
fi

if [[ "$_t1_status" == "pass" ]]; then
    _pass "T1: status field is 'pass' (git is present)"
else
    _fail "T1: expected status='pass', got '${_t1_status}' (full JSON: ${_t1_out})"
fi

# Verify detail is non-empty (should contain version string).
_t1_detail="$(_json_field "$_t1_out" "detail")"
if [[ -n "$_t1_detail" ]]; then
    _pass "T1: detail is non-empty ('${_t1_detail}')"
else
    _fail "T1: detail field is empty (expected version string)"
fi

# ---------------------------------------------------------------------------
# T2: _co_prereq_probe_all emits exactly 10 NDJSON lines.
# ---------------------------------------------------------------------------
echo ""
echo "--- T2: _co_prereq_probe_all emits exactly 10 NDJSON lines ---"

_all_out="$(_co_prereq_probe_all)"
_line_count="$(printf '%s\n' "$_all_out" | grep -c '.')"

if [[ "$_line_count" -eq 10 ]]; then
    _pass "T2: _co_prereq_probe_all emitted exactly 10 lines"
else
    _fail "T2: expected 10 lines, got ${_line_count}"
fi

# ---------------------------------------------------------------------------
# T3: The FIRST line of _co_prereq_probe_all output has name="git".
# ---------------------------------------------------------------------------
echo ""
echo "--- T3: first line of _co_prereq_probe_all output has name='git' ---"

_first_line="$(printf '%s\n' "$_all_out" | head -1)"
_first_name="$(_json_field "$_first_line" "name")"

if [[ "$_first_name" == "git" ]]; then
    _pass "T3: first probe line has name='git' (git probe runs first)"
else
    _fail "T3: expected first probe name='git', got '${_first_name}' (first line: ${_first_line})"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  probe-git.sh results"
echo "========================================"
echo "  Results: ${PASS} passed, ${FAIL} failed"
if [[ "${#ERRORS[@]}" -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _e in "${ERRORS[@]}"; do
        echo "  ${_e}"
    done
fi
echo "========================================"

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
