#!/usr/bin/env bash
# completeness-checklist.bats — plain-bash harness for bin/parse-completeness-item.sh
#
# Purpose: prove the parser seam classifies valid items correctly, extracts assertion + probe
# text faithfully (including escaped "\]" sequences), fails loud on malformed input (AC13),
# and emits classification output that callers can use to hoist restart-gated items first.
# This is the round-trip-contract test that makes the parser a tested seam rather than an
# inline micro-parser (AC9, AC13).
#
# NOTE: bats-framework is not assumed in the acceptance-oracle environment. Per the oracle's
# `bats:` semantics (= run the file under plain `bash`; see check-acceptance-oracle.sh:808-811)
# and the handoff-transition.bats convention, this is a PLAIN-BASH harness — named .bats so
# the AC grep resolves it.
#
# Spec backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C9
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/tests/completeness-checklist.bats
# Portability (DR-148): bash >= 3.2 + BSD coreutils; no grep -P / date -d / sed -i.
# (Parser-under-test is Bash-3.2 safe; harness matches that floor, not the bash-4 default.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARSER="${SCRIPT_DIR}/../bin/parse-completeness-item.sh"

PASS=0
FAIL=0
FAIL_MSGS=()
pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; FAIL_MSGS+=("$1"); (( FAIL++ )) || true; }
run_test() {
    local name="$1" fn="$2"
    echo "--- ${name}"
    if "${fn}"; then pass "${name}"; else fail "${name}"; fi
}

# ---------------------------------------------------------------------------
# Test 1 — valid `live:` item without a probe
# AC9: valid items classify correctly; exit 0; probe field empty.
# ---------------------------------------------------------------------------
t_live_no_probe() {
    local out rc
    out="$(bash "$PARSER" 'live: claude mcp list shows holodeck-native-mcp connected' 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ]                                                                        || return 1
    echo "$out" | grep -q '^class=live$'                                                   || return 1
    echo "$out" | grep -q '^assertion=claude mcp list shows holodeck-native-mcp connected$' || return 1
    echo "$out" | grep -q '^probe=$'                                                       || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 2 — valid `restart-gated:` item WITH a `[probe: …]`
# AC9: restart-gated class extracted, assertion trimmed, probe command extracted; exit 0.
# ---------------------------------------------------------------------------
t_restart_gated_with_probe() {
    local out rc
    out="$(bash "$PARSER" 'restart-gated: holodeck MCP connects after restart [probe: claude mcp list | grep -q holodeck-native-mcp]' 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ]                                                                              || return 1
    echo "$out" | grep -q '^class=restart-gated$'                                               || return 1
    echo "$out" | grep -q '^assertion=holodeck MCP connects after restart$'                      || return 1
    echo "$out" | grep -q '^probe=claude mcp list | grep -q holodeck-native-mcp$'               || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 3 — unknown class prefix → malformed → exit non-zero (AC13)
# ---------------------------------------------------------------------------
t_unknown_class_nonzero() {
    local rc
    set +e
    bash "$PARSER" 'pending: coordinator plugin enabled in settings.json' >/dev/null 2>&1
    rc=$?
    set -e
    [ "$rc" -ne 0 ] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 4 — missing class prefix entirely → malformed → exit non-zero (AC13)
# ---------------------------------------------------------------------------
t_missing_class_nonzero() {
    local rc
    set +e
    bash "$PARSER" 'coordinator plugin enabled in settings.json' >/dev/null 2>&1
    rc=$?
    set -e
    [ "$rc" -ne 0 ] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 5 — unterminated [probe: (no closing ]) → malformed → exit non-zero (AC13)
# ---------------------------------------------------------------------------
t_unterminated_probe_nonzero() {
    local rc
    set +e
    bash "$PARSER" 'live: coordinator running [probe: claude mcp list | grep -q coordinator' >/dev/null 2>&1
    rc=$?
    set -e
    [ "$rc" -ne 0 ] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 6 — probe containing an escaped \] preserves the literal ] in output
# Grammar: \] inside the probe command is an escape for a literal ].
# The parser must unescape \] → ] before emitting the probe= line.
# ---------------------------------------------------------------------------
t_escaped_bracket_in_probe() {
    local out rc
    # Item: live: check jq output [probe: jq '.[0\]' /tmp/data.json]
    # The \] in the probe is the escape; the parser should emit a literal ] in probe=
    # Review: code-reviewer — inside double-quotes, bash only escapes \\ \$ \" \` \newline;
    # \] is NOT a recognised escape so bash passes the two characters \ and ] literally to
    # the parser, which is exactly what the grammar requires for an escaped bracket.
    out="$(bash "$PARSER" "live: check jq output [probe: jq '.[0\]' /tmp/data.json]" 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ]                              || return 1
    echo "$out" | grep -q '^class=live$'         || return 1
    echo "$out" | grep -q '^assertion=check jq output$' || return 1
    # probe= must contain a literal ] (the unescaped form); use grep -F for fixed-string match
    echo "$out" | grep -qF "probe=jq '.[0]' /tmp/data.json" || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 7 — restart-gated hoisting: classification is correct so callers can hoist
#
# The pickup skill (C4), not the parser, does the actual hoisting. This test
# asserts that when a small fixture list is processed item-by-item, every
# restart-gated item's class= line is "restart-gated" and every live item's
# class= line is "live" — giving callers the signal they need to sort/hoist.
# ---------------------------------------------------------------------------
t_classification_for_hoist() {
    local out rc live1_class live2_class rg1_class rg2_class

    out="$(bash "$PARSER" 'live: coordinator hooks are registered' 2>&1)"
    rc=$?; [ "$rc" -eq 0 ] || return 1
    live1_class="$(echo "$out" | grep '^class=' | cut -d= -f2)"
    [ "$live1_class" = "live" ] || return 1

    out="$(bash "$PARSER" 'live: skills discovery preconditions met [probe: grep -q description skills/pickup/SKILL.md]' 2>&1)"
    rc=$?; [ "$rc" -eq 0 ] || return 1
    live2_class="$(echo "$out" | grep '^class=' | cut -d= -f2)"
    [ "$live2_class" = "live" ] || return 1

    out="$(bash "$PARSER" 'restart-gated: holodeck MCP connects [probe: claude mcp list | grep holodeck]' 2>&1)"
    rc=$?; [ "$rc" -eq 0 ] || return 1
    rg1_class="$(echo "$out" | grep '^class=' | cut -d= -f2)"
    [ "$rg1_class" = "restart-gated" ] || return 1

    out="$(bash "$PARSER" 'restart-gated: LSP server starts on project open' 2>&1)"
    rc=$?; [ "$rc" -eq 0 ] || return 1
    rg2_class="$(echo "$out" | grep '^class=' | cut -d= -f2)"
    [ "$rg2_class" = "restart-gated" ] || return 1

    # Sanity: same-group items share a class; groups are distinct
    [ "$rg1_class" = "$rg2_class" ]    || return 1
    [ "$live1_class" = "$live2_class" ] || return 1
    [ "$rg1_class" != "$live1_class" ]  || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 8 — STDIN input path: `echo "live: x" | bash "$PARSER"` (F8)
# Parser accepts piped stdin when no $1 is given; class=live, assertion=x, exit 0.
# ---------------------------------------------------------------------------
t_stdin_input() {
    local out rc
    out="$(echo "live: x" | bash "$PARSER" 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ]                       || return 1
    echo "$out" | grep -q '^class=live$'  || return 1
    echo "$out" | grep -q '^assertion=x$' || return 1
    echo "$out" | grep -q '^probe=$'      || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 9 — trailing whitespace on assertion is stripped (F10)
# `live: coordinator running   ` (trailing spaces) → assertion=coordinator running (no spaces).
# Parser must strip trailing whitespace when no [probe:] suffix is present (YAML SSOT hygiene).
# ---------------------------------------------------------------------------
t_trailing_whitespace_stripped() {
    local out rc
    out="$(bash "$PARSER" "live: coordinator running   " 2>&1)"
    rc=$?
    [ "$rc" -eq 0 ]                                           || return 1
    echo "$out" | grep -q '^class=live$'                      || return 1
    echo "$out" | grep -q '^assertion=coordinator running$'   || return 1
    echo "$out" | grep -q '^probe=$'                          || return 1
    # Belt-and-suspenders: assert no trailing space on the assertion= line
    local assertion_line
    assertion_line="$(echo "$out" | grep '^assertion=')"
    [ "$assertion_line" = "assertion=coordinator running" ]   || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 10 — empty probe command: `live: some assertion [probe: ]` → malformed (F7, AC13)
# An empty command between "probe: " and "]" is a parse error; parser must exit non-zero.
# ---------------------------------------------------------------------------
t_empty_probe_command_nonzero() {
    local rc
    set +e
    bash "$PARSER" 'live: some assertion [probe: ]' >/dev/null 2>&1
    rc=$?
    set -e
    [ "$rc" -ne 0 ] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Test 11 — degenerate `live:` form (class + colon, no space/content) → malformed (F12, AC13)
# `live:` with nothing after the colon must exit non-zero.
# ---------------------------------------------------------------------------
t_bare_class_colon_nonzero() {
    local rc
    set +e
    bash "$PARSER" 'live:' >/dev/null 2>&1
    rc=$?
    set -e
    [ "$rc" -ne 0 ] || return 1
    return 0
}

echo "=== completeness-checklist plain-bash harness ==="
run_test "live item: class=live, correct assertion, no probe, exit 0"                      t_live_no_probe
run_test "restart-gated item with probe: class/assertion/probe extracted, exit 0"          t_restart_gated_with_probe
run_test "unknown class prefix is malformed: exit non-zero (AC13)"                         t_unknown_class_nonzero
run_test "missing class prefix is malformed: exit non-zero (AC13)"                         t_missing_class_nonzero
run_test "unterminated [probe: (no closing ]) is malformed: exit non-zero (AC13)"          t_unterminated_probe_nonzero
run_test "escaped \\] in probe preserved as literal ] in extracted probe"                  t_escaped_bracket_in_probe
run_test "classification for hoisting: restart-gated vs live correctly distinguished"      t_classification_for_hoist
run_test "stdin input path: live item piped via stdin parsed correctly, exit 0 (F8)"      t_stdin_input
run_test "trailing whitespace stripped from assertion when no probe present (F10)"        t_trailing_whitespace_stripped
run_test "empty probe command [probe: ] is malformed: exit non-zero (F7, AC13)"           t_empty_probe_command_nonzero
run_test "bare 'live:' (no space/content after colon) is malformed: exit non-zero (F12)" t_bare_class_colon_nonzero

echo "=== PASS=${PASS} FAIL=${FAIL} ==="
if [ "${FAIL}" -ne 0 ]; then
    printf 'FAILED: %s\n' "${FAIL_MSGS[@]}"
    exit 1
fi
exit 0
