#!/usr/bin/env bash
# gen-settings-hooks.test.sh — tests for gen-settings-hooks.sh
#
# Purpose: verifies type-filter, golden-output, idempotency, same-event preservation,
#          and fail-loud on unresolvable coordinator root.
#
# Spec backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § M1 tests (a)-(e)
# Tests are ALWAYS sandboxed — never touch the live ~/.claude/settings.json.
# Golden comparison normalises the coordinator root to a placeholder so stored fixtures
# are path-independent across machines.

# ---- bash >=4 guard (must parse on bash 3.2) ----
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: gen-settings-hooks.test.sh requires bash >= 4." >&2
  exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/gen-settings-hooks.sh"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures/gen-settings-hooks"

PASS=0
FAIL=0

pass() { printf 'PASS: %s\n' "$1"; PASS=$(( PASS + 1 )); }
fail() { printf 'FAIL: %s\n' "$1"; FAIL=$(( FAIL + 1 )); }
assert_eq() {
  local label="$1" actual="$2" expected="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    pass "${label}"
  else
    fail "${label}"
    printf '  expected: %s\n  actual:   %s\n' "${expected}" "${actual}" >&2
  fi
}

# Setup: temp dir for all sandbox outputs + test coordinator root structure
TMP_DIR="$(mktemp -d /tmp/gen-settings-hooks-test.XXXXXX)"
# Test coordinator root: a REAL directory (so the existence check passes)
TEST_COORDINATOR_ROOT="${TMP_DIR}/coordinator"
mkdir -p "${TEST_COORDINATOR_ROOT}/hooks"

cleanup() { rm -rf "${TMP_DIR}"; }
trap cleanup EXIT

FIXTURE_HOOKS="${FIXTURES_DIR}/hooks.json"
# Stored golden fixture uses placeholder "/COORD_ROOT" in paths.
# We normalise actual output the same way before comparing.
FIXTURE_EXPECTED="${FIXTURES_DIR}/expected-generated.json"
GOLDEN_PLACEHOLDER="/test/coordinator"

# ---------------------------------------------------------------------------
# Helper: run generator with the fixture hooks.json + sandbox coordinator root
# ---------------------------------------------------------------------------
run_gen() {
  local out_path="$1"; shift
  bash "${SUBJECT}" \
    --out "${out_path}" \
    --hooks-json "${FIXTURE_HOOKS}" \
    --coordinator-root "${TEST_COORDINATOR_ROOT}" \
    "$@"
}

# Normalise output: replace actual test coordinator root with the golden placeholder.
# Uses a recursive jq function (no walk/1) so tests run on jq 1.5 — matching the
# generator's own jq requirement exactly.
# Review: replaced walk/1 (jq>=1.6) with portable recursive def (F4)
normalise_paths() {
  local json_path="$1"
  jq --arg cr "${TEST_COORDINATOR_ROOT}" --arg ph "${GOLDEN_PLACEHOLDER}" \
    '
    def replace_strings($from; $to):
      if type == "string" then split($from) | join($to)
      elif type == "array" then map(replace_strings($from; $to))
      elif type == "object" then with_entries(.value |= replace_strings($from; $to))
      else . end;
    replace_strings($cr; $ph)
    ' \
    "${json_path}"
}

# ---------------------------------------------------------------------------
# Test (a) — type-filter fixture
# Only type:command entries WITH ${CLAUDE_PLUGIN_ROOT} are emitted; mcp_tool and
# non-CPR commands are skipped.
# ---------------------------------------------------------------------------
OUT_A="${TMP_DIR}/test-a-settings.json"
run_gen "${OUT_A}"

# Should have no mcp_tool entries anywhere in the hooks block
MCP_COUNT="$(jq '[ .hooks[][] | .hooks[] | select(.type == "mcp_tool") ] | length' "${OUT_A}")"
if [[ "${MCP_COUNT}" -eq 0 ]]; then
  pass "T-a: no mcp_tool entries in emitted hooks block"
else
  fail "T-a: found ${MCP_COUNT} mcp_tool entries (expected 0)"
fi

# Should have no non-CPR command (platform-localize.sh — type:command but no ${CLAUDE_PLUGIN_ROOT})
NON_CPR_COUNT="$(jq \
  --arg gen_dir "${TEST_COORDINATOR_ROOT}/hooks" \
  '[ .hooks[][] | .hooks[] |
     select(.type == "command") |
     select(.command | ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") |
            startswith($gen_dir + "/") | not)
   ] | length' \
  "${OUT_A}")"
if [[ "${NON_CPR_COUNT}" -eq 0 ]]; then
  pass "T-a: no non-CPR command entries emitted (platform-localize.sh correctly skipped)"
else
  fail "T-a: found ${NON_CPR_COUNT} non-CPR command entries (expected 0)"
fi

# PreToolUse Bash group (all mcp_tool) should be entirely absent
BASH_GROUPS="$(jq '[ (.hooks.PreToolUse // [])[] | select(.matcher == "Bash") ] | length' "${OUT_A}")"
if [[ "${BASH_GROUPS}" -eq 0 ]]; then
  pass "T-a: PreToolUse Bash group (all mcp_tool) entirely skipped"
else
  fail "T-a: PreToolUse Bash group should be absent but found ${BASH_GROUPS} group(s)"
fi

# SubagentStop group (all non-CPR type:command) should be entirely absent — exercises the
# empty-after-filter skip path where a group yields zero CPR hooks (F8).
# Review: added fixture group exercising the length==0 empty branch (F8)
SUBAGENT_GROUPS="$(jq '(.hooks.SubagentStop // []) | length' "${OUT_A}")"
if [[ "${SUBAGENT_GROUPS}" -eq 0 ]]; then
  pass "T-a: SubagentStop group (all non-CPR type:command) entirely skipped (empty-after-filter path)"
else
  fail "T-a: SubagentStop group should be absent but found ${SUBAGENT_GROUPS} group(s)"
fi

# Fixture has 4 CPR commands: session-guard.sh, bootstrap-substrate.sh, block-some-write.sh, plan-persistence-check.sh
ALL_CPR_COUNT="$(jq \
  --arg gen_dir "${TEST_COORDINATOR_ROOT}/hooks" \
  '[ .hooks[][] | .hooks[] |
     select(.type == "command") |
     select(.command | ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") |
            startswith($gen_dir + "/"))
   ] | length' \
  "${OUT_A}")"
if [[ "${ALL_CPR_COUNT}" -eq 4 ]]; then
  pass "T-a: exactly 4 CPR command entries emitted"
else
  fail "T-a: expected 4 CPR command entries, found ${ALL_CPR_COUNT}"
fi

# No literal ${CLAUDE_PLUGIN_ROOT} should remain
UNREWRITTEN="$(jq -r '.. | strings | select(contains("${CLAUDE_PLUGIN_ROOT}"))' "${OUT_A}" | wc -l | tr -d ' ')"
if [[ "${UNREWRITTEN}" -eq 0 ]]; then
  pass "T-a: no literal \${CLAUDE_PLUGIN_ROOT} remains (all rewritten)"
else
  fail "T-a: found ${UNREWRITTEN} unrewritten \${CLAUDE_PLUGIN_ROOT} occurrences"
fi

# ---------------------------------------------------------------------------
# Test (b) — golden-file test
# Generator output (normalised with path placeholder) must match the stored golden fixture.
# The stored fixture uses "${GOLDEN_PLACEHOLDER}" as the coordinator root.
# ---------------------------------------------------------------------------
OUT_B="${TMP_DIR}/test-b-settings.json"
run_gen "${OUT_B}"

ACTUAL_NORM="$(normalise_paths "${OUT_B}" | jq -c .)"
EXPECTED_NORM="$(jq -c . "${FIXTURE_EXPECTED}")"

if [[ "${ACTUAL_NORM}" == "${EXPECTED_NORM}" ]]; then
  pass "T-b: output matches golden fixture (path-normalised)"
else
  fail "T-b: output differs from golden fixture"
  printf '  EXPECTED (compact): %s\n' "${EXPECTED_NORM}" >&2
  printf '  ACTUAL   (compact): %s\n' "${ACTUAL_NORM}" >&2
fi

# ---------------------------------------------------------------------------
# Test (c) — idempotency
# Running the generator twice on its own output produces byte-identical result.
# ---------------------------------------------------------------------------
OUT_C="${TMP_DIR}/test-c-settings.json"
run_gen "${OUT_C}"
cp "${OUT_C}" "${TMP_DIR}/test-c-pass1.json"

# Second run: the input is now the first-run output (already contains generated hooks)
run_gen "${OUT_C}"

DIFF_C="$(diff "${TMP_DIR}/test-c-pass1.json" "${OUT_C}" && echo "same" || true)"
if [[ "${DIFF_C}" == "same" ]]; then
  pass "T-c: second run is byte-identical to first run (idempotent)"
else
  fail "T-c: second run differs from first run (not idempotent)"
  diff "${TMP_DIR}/test-c-pass1.json" "${OUT_C}" >&2 || true
fi

# ---------------------------------------------------------------------------
# Test (d) — same-event collision: hand hook preserved alongside generated hooks
# Pre-seed settings.json with a hand SessionStart hook that is NOT from hooks.json.
# After regenerate: BOTH the hand hook and the generated hooks survive.
# Second regenerate: no-op diff.
# ---------------------------------------------------------------------------
OUT_D="${TMP_DIR}/test-d-settings.json"

cat > "${OUT_D}" << 'SEED_EOF'
{
  "env": {"TEST_KEY": "test_value"},
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/bin/touch-session-sentinel.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/bin/portability-guard-hook",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
SEED_EOF

run_gen "${OUT_D}"

# Hand SessionStart hook must survive
HAND_SENTINEL="$(jq '
  [(.hooks.SessionStart // [])[] |
   .hooks[] |
   select(.command == "bash ~/.claude/bin/touch-session-sentinel.sh")
  ] | length' "${OUT_D}")"
if [[ "${HAND_SENTINEL}" -eq 1 ]]; then
  pass "T-d: hand SessionStart hook preserved alongside generated SessionStart hooks"
else
  fail "T-d: hand SessionStart hook missing after regenerate (found ${HAND_SENTINEL})"
fi

# Hand PostToolUse hook must survive
HAND_PORTGUARD="$(jq '
  [(.hooks.PostToolUse // [])[] |
   .hooks[] |
   select(.command == "~/.claude/bin/portability-guard-hook")
  ] | length' "${OUT_D}")"
if [[ "${HAND_PORTGUARD}" -eq 1 ]]; then
  pass "T-d: hand PostToolUse hook preserved alongside generated PostToolUse hooks"
else
  fail "T-d: hand PostToolUse hook missing after regenerate (found ${HAND_PORTGUARD})"
fi

# Generated SessionStart hooks must also be present (same-event coexistence)
GEN_DIR_D="${TEST_COORDINATOR_ROOT}/hooks"
GEN_SESSION_GROUPS="$(jq \
  --arg gen_dir "${GEN_DIR_D}" \
  '[(.hooks.SessionStart // [])[] |
    select(.hooks[] |
      .type == "command" and
      (.command | ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") | startswith($gen_dir + "/"))
    )
   ] | length' "${OUT_D}")"
if [[ "${GEN_SESSION_GROUPS}" -ge 1 ]]; then
  pass "T-d: generated SessionStart hooks also present (same-event coexistence)"
else
  fail "T-d: generated SessionStart hooks missing (same-event coexistence broken)"
fi

# Non-hooks fields must survive
ENV_VAL="$(jq -r '.env.TEST_KEY // "missing"' "${OUT_D}")"
assert_eq "T-d: non-hooks fields preserved (env.TEST_KEY)" "${ENV_VAL}" "test_value"

# Second regenerate: no-op diff
cp "${OUT_D}" "${TMP_DIR}/test-d-before-2nd.json"
run_gen "${OUT_D}"
DIFF_D="$(diff "${TMP_DIR}/test-d-before-2nd.json" "${OUT_D}" && echo "same" || true)"
if [[ "${DIFF_D}" == "same" ]]; then
  pass "T-d: second regenerate is a no-op diff (idempotent with same-event collision)"
else
  fail "T-d: second regenerate changes output (not idempotent with same-event collision)"
  diff "${TMP_DIR}/test-d-before-2nd.json" "${OUT_D}" >&2 || true
fi

# ---------------------------------------------------------------------------
# Test (e) — fail-loud on unresolvable coordinator root + no partial write
# ---------------------------------------------------------------------------
OUT_E="${TMP_DIR}/test-e-settings.json"
echo '{"marker": "original"}' > "${OUT_E}"

EXIT_CODE_E=0
STDERR_E="$(
  bash "${SUBJECT}" \
    --out "${OUT_E}" \
    --coordinator-root "/nonexistent/coordinator-$(date +%s)" \
    2>&1
)" || EXIT_CODE_E=$?

if [[ "${EXIT_CODE_E}" -ne 0 ]]; then
  pass "T-e: exits non-zero on unresolvable coordinator root"
else
  fail "T-e: expected non-zero exit, got 0"
fi

if printf '%s' "${STDERR_E}" | grep -qi "remediat"; then
  pass "T-e: error output contains remediation guidance"
else
  fail "T-e: error output lacks remediation guidance"
  printf '  stderr: %s\n' "${STDERR_E}" >&2
fi

# Settings.json must be unchanged (no partial write)
MARKER_E="$(jq -r '.marker // "missing"' "${OUT_E}")"
assert_eq "T-e: settings.json unchanged on error (no partial write)" "${MARKER_E}" "original"

# ---------------------------------------------------------------------------
# Test (e2) — fail-loud when jq absent
# ---------------------------------------------------------------------------
OUT_E2="${TMP_DIR}/test-e2-settings.json"
echo '{"marker": "original_e2"}' > "${OUT_E2}"

EXIT_CODE_E2=0
# Save current PATH, restrict to exclude jq
REAL_PATH="${PATH}"
JQ_PATH="$(command -v jq)"
JQ_DIR="$(dirname "${JQ_PATH}")"
# Build a PATH without the jq directory (but keep bash, etc.)
RESTRICTED_PATH="$(printf '%s' "${REAL_PATH}" | tr ':' '\n' | grep -vxF "${JQ_DIR}" | tr '\n' ':' | sed 's/:$//')" # Review: -vxF avoids regex-metachar hazards in jq install path (F7)

STDERR_E2="$(
  PATH="${RESTRICTED_PATH}" bash "${SUBJECT}" \
    --out "${OUT_E2}" \
    --coordinator-root "${TEST_COORDINATOR_ROOT}" \
    2>&1
)" || EXIT_CODE_E2=$?

if [[ "${EXIT_CODE_E2}" -ne 0 ]]; then
  pass "T-e2: exits non-zero when jq is absent"
else
  fail "T-e2: expected non-zero exit when jq absent, got 0"
fi

if printf '%s' "${STDERR_E2}" | grep -qi "jq"; then
  pass "T-e2: error output mentions jq"
else
  fail "T-e2: error output does not mention jq"
  printf '  stderr: %s\n' "${STDERR_E2}" >&2
fi

MARKER_E2="$(jq -r '.marker // "missing"' "${OUT_E2}")"
assert_eq "T-e2: settings.json unchanged when jq absent" "${MARKER_E2}" "original_e2"

# ---------------------------------------------------------------------------
# Test (sync) — F1 guard: both def cmd_path: blocks in gen-settings-hooks.sh must be byte-identical
# Grep for the implementation line; if they've diverged, sort -u yields >1 unique line.
# ---------------------------------------------------------------------------
# Strip leading whitespace before comparing — the two blocks have different indentation
# (6 spaces in the stray-check inline jq, 2 spaces in the main heredoc) which is intentional
# given their contexts. What matters is that the jq LOGIC (the strip-interpreter chain) is identical.
# Review: static assertion that stray-check and main-jq def cmd_path: stay in sync (F1)
CMD_PATH_IMPLS="$(grep 'ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") | ltrimstr("python ")' "${SUBJECT}" | sed 's/^[[:space:]]*//')"
CMD_PATH_UNIQUE="$(printf '%s\n' "${CMD_PATH_IMPLS}" | sort -u | wc -l | tr -d ' ')"
CMD_PATH_TOTAL="$(printf '%s\n' "${CMD_PATH_IMPLS}" | wc -l | tr -d ' ')"
if [[ "${CMD_PATH_UNIQUE}" -eq 1 && "${CMD_PATH_TOTAL}" -eq 2 ]]; then
  pass "T-sync: both def cmd_path: logic strings in gen-settings-hooks.sh are identical (modulo indentation)"
else
  fail "T-sync: def cmd_path: blocks have diverged (unique_logic_lines=${CMD_PATH_UNIQUE}, total_occurrences=${CMD_PATH_TOTAL})"
fi

# ---------------------------------------------------------------------------
# Test (f) — stray-check: hand hook under coordinator/hooks/ NOT in will-emit set → fail-loud
# Pre-seed settings.json with a hand hook whose command is under the generated hooks dir
# but is NOT one of the commands the generator will emit from hooks.json.
# Assert: exits non-zero, stderr identifies the stray detection, no output written/mutated.
# ---------------------------------------------------------------------------
OUT_F="${TMP_DIR}/test-f-settings.json"

# Unquoted heredoc so ${TEST_COORDINATOR_ROOT} expands; no other $ signs in this JSON.
cat > "${OUT_F}" << SEED_F_EOF
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${TEST_COORDINATOR_ROOT}/hooks/my-hand-authored-hook.sh"
          }
        ]
      }
    ]
  }
}
SEED_F_EOF

EXIT_CODE_F=0
STDERR_F="$(
  bash "${SUBJECT}" \
    --out "${OUT_F}" \
    --hooks-json "${FIXTURE_HOOKS}" \
    --coordinator-root "${TEST_COORDINATOR_ROOT}" \
    2>&1
)" || EXIT_CODE_F=$?

if [[ "${EXIT_CODE_F}" -ne 0 ]]; then
  pass "T-f: exits non-zero on stray hand hook under coordinator/hooks/"
else
  fail "T-f: expected non-zero exit on stray hook, got 0"
fi

# stderr must mention stray detection (any of: stray, coordinator/hooks, generator-owned)
if printf '%s' "${STDERR_F}" | grep -qiE 'stray|coordinator/hooks|generator.owned'; then
  pass "T-f: stderr identifies the stray detection"
else
  fail "T-f: stderr does not identify the stray detection"
  printf '  stderr: %s\n' "${STDERR_F}" >&2
fi

# stderr must name the offending command
if printf '%s' "${STDERR_F}" | grep -q "my-hand-authored-hook.sh"; then
  pass "T-f: stderr names the offending command"
else
  fail "T-f: stderr does not name the offending command"
  printf '  stderr: %s\n' "${STDERR_F}" >&2
fi

# stderr must name the event
if printf '%s' "${STDERR_F}" | grep -q "SessionStart"; then
  pass "T-f: stderr names the offending event"
else
  fail "T-f: stderr does not name the offending event"
  printf '  stderr: %s\n' "${STDERR_F}" >&2
fi

# Settings.json must be unchanged — no partial write on stray failure
STRAY_CMD_F="$(jq -r '(.hooks.SessionStart // [])[] | .hooks[] | .command' "${OUT_F}")"
if [[ "${STRAY_CMD_F}" == "bash ${TEST_COORDINATOR_ROOT}/hooks/my-hand-authored-hook.sh" ]]; then
  pass "T-f: settings.json unchanged on stray error (no partial write)"
else
  fail "T-f: settings.json was mutated despite stray error"
  printf '  content: %s\n' "$(cat "${OUT_F}")" >&2
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
printf '\n--- gen-settings-hooks.test.sh: %d/%d PASSED ---\n' "${PASS}" "${TOTAL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
exit 0
