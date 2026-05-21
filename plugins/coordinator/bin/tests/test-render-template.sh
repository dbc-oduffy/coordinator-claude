#!/usr/bin/env bash
# bin/tests/test-render-template.sh — AC2 test harness for render-template.sh
#
# Purpose: verify the AC2 cases for bin/render-template.sh.
# Runs standalone via: bash bin/tests/test-render-template.sh
# No external harness dependency.
#
# Spec backlink: docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md § C1 AC2
#
# Exit codes:
#   0  All cases PASS
#   1  One or more cases FAIL

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate render-template.sh relative to this test file
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER="$SCRIPT_DIR/../render-template.sh"

if [[ ! -x "$RENDER" ]]; then
    echo "FATAL: render-template.sh not found or not executable at: $RENDER" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TMPDIR_HARNESS="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_HARNESS"' EXIT

pass_count=0
fail_count=0

pass() {
    echo "PASS: $1"
    pass_count=$((pass_count + 1))
}

fail() {
    echo "FAIL: $1"
    fail_count=$((fail_count + 1))
}

# ---------------------------------------------------------------------------
# Case 1 — round-trip a {{FOO}} template
# ---------------------------------------------------------------------------
# Write a template with {{FOO}}, render with FOO=bar, verify output is "bar".

tmpl1="$TMPDIR_HARNESS/tmpl1.txt"
printf '{{FOO}}' > "$tmpl1"

output1="$("$RENDER" "$tmpl1" FOO=bar)"
if [[ "$output1" == "bar" ]]; then
    pass "Case 1: round-trip {{FOO}} → FOO=bar substitution"
else
    fail "Case 1: round-trip {{FOO}} → expected 'bar', got '${output1}'"
fi

# ---------------------------------------------------------------------------
# Case 1b — value with sed metacharacters round-trips
# ---------------------------------------------------------------------------
# Verifies that & and \ in values are treated as literals, not sed commands.

tmpl1b="$TMPDIR_HARNESS/tmpl1b.txt"
printf '{{FOO}}' > "$tmpl1b"

output1b="$("$RENDER" "$tmpl1b" 'FOO=a&b\c')"
if [[ "$output1b" == 'a&b\c' ]]; then
    pass "Case 1b: value with sed metacharacters (& and \\) round-trips correctly"
else
    fail "Case 1b: metacharacter round-trip → expected 'a&b\\c', got '${output1b}'"
fi

# ---------------------------------------------------------------------------
# Case 1c — trailing newline preservation
# ---------------------------------------------------------------------------
# Template ending in \n must render to output that also ends in \n.
# Captured via file (not variable) because $() strips trailing newlines.

tmpl1c="$TMPDIR_HARNESS/tmpl1c.txt"
outfile1c="$TMPDIR_HARNESS/out1c.txt"
printf 'hello {{NAME}}\n' > "$tmpl1c"

"$RENDER" "$tmpl1c" NAME=world > "$outfile1c"
# Check the last byte of the file is 0a (newline)
last_byte="$(tail -c 1 "$outfile1c" | od -An -tx1 | tr -d ' \n')"
if [[ "$last_byte" == "0a" ]]; then
    pass "Case 1c: trailing newline preserved in rendered output"
else
    fail "Case 1c: trailing newline NOT preserved — last byte was '${last_byte}', expected '0a'"
fi

# ---------------------------------------------------------------------------
# Case 2 — failure on unsubstituted {{BAR}}
# ---------------------------------------------------------------------------
# Write a template with {{BAR}}, render without supplying BAR,
# verify exit code is non-zero and stderr contains 'unsubstituted'.

tmpl2="$TMPDIR_HARNESS/tmpl2.txt"
printf '{{BAR}}' > "$tmpl2"

exit2=0; stderr2="$("$RENDER" "$tmpl2" 2>&1 1>/dev/null)" || exit2=$?
if [[ $exit2 -ne 0 ]] && printf '%s\n' "$stderr2" | grep -q "unsubstituted"; then
    pass "Case 2: unsubstituted {{BAR}} → non-zero exit + 'unsubstituted' in stderr"
else
    fail "Case 2: unsubstituted {{BAR}} → expected non-zero exit with diagnostic; got exit=${exit2} stderr='${stderr2}'"
fi

# ---------------------------------------------------------------------------
# Case 3 — rejection of {{ SPACE }} (whitespace inside braces)
# ---------------------------------------------------------------------------
# Write a template with {{ SPACE }} (space inside braces), render without
# supplying any key, verify exit code is non-zero and stderr contains 'unsubstituted'.

tmpl3="$TMPDIR_HARNESS/tmpl3.txt"
printf '{{ SPACE }}' > "$tmpl3"

exit3=0; stderr3="$("$RENDER" "$tmpl3" 2>&1 1>/dev/null)" || exit3=$?
if [[ $exit3 -ne 0 ]] && printf '%s\n' "$stderr3" | grep -q "unsubstituted"; then
    pass "Case 3: {{ SPACE }} is rejected (treated as unsubstituted) → non-zero exit + 'unsubstituted' in stderr"
else
    fail "Case 3: {{ SPACE }} should be rejected but render-template exited 0 or lacked diagnostic; exit=${exit3} stderr='${stderr3}'"
fi

# ---------------------------------------------------------------------------
# Case 4 — -o <path> writes rendered output to file
# ---------------------------------------------------------------------------
# Write a template with {{NAME}}, render with -o <outfile> NAME=world,
# verify the output file contains "hello world", stdout is empty, and stderr is clean.

tmpl4="$TMPDIR_HARNESS/tmpl4.txt"
outfile4="$TMPDIR_HARNESS/out4.txt"
printf 'hello {{NAME}}' > "$tmpl4"

exit4=0; stdout4="$("$RENDER" "$tmpl4" -o "$outfile4" NAME=world)" || exit4=$?
stderr4="$("$RENDER" "$tmpl4" -o "$outfile4" NAME=world 2>&1 1>/dev/null)" || true
if [[ $exit4 -eq 0 ]] && [[ -f "$outfile4" ]] && [[ "$(cat "$outfile4")" == "hello world" ]] && [[ -z "$stdout4" ]] && [[ -z "$stderr4" ]]; then
    pass "Case 4: -o <path> writes rendered output to file, stdout is empty, stderr is clean"
else
    fail "Case 4: -o <path> — exit=${exit4} file_content='$(cat "$outfile4" 2>/dev/null)' stdout='${stdout4}' stderr='${stderr4}'"
fi

# ---------------------------------------------------------------------------
# Case 5 — unknown positional argument exits 1 with diagnostic
# ---------------------------------------------------------------------------

exit5=0; stderr5="$("$RENDER" /dev/null --unknown 2>&1 1>/dev/null)" || exit5=$?
if [[ $exit5 -ne 0 ]] && printf '%s\n' "$stderr5" | grep -q "unexpected argument"; then
    pass "Case 5: unknown positional argument → non-zero exit + 'unexpected argument' in stderr"
else
    fail "Case 5: unknown positional argument → expected non-zero exit with 'unexpected argument'; got exit=${exit5} stderr='${stderr5}'"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: ${pass_count} passed, ${fail_count} failed"

if [[ $fail_count -gt 0 ]]; then
    exit 1
fi
exit 0
