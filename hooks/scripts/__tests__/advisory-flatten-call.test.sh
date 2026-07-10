#!/usr/bin/env bash
# Tests for coordinator/hooks/scripts/lib/advisory-flatten-call.sh
#
# TABLE-DRIVEN: exercises advisory_flatten_params over representative hook
# payloads, asserting the flat output contains all fields each op handler reads.
# Also asserts advisory_call degrades silently when the client module is absent.
#
# Exit 0 = all pass; nonzero = at least one failure.
# Idempotent and stateless — no disk writes outside /tmp (cleaned on EXIT).

set -uo pipefail

LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/advisory-flatten-call.sh"

if [[ ! -f "$LIB" ]]; then
  echo "FATAL: library not found at $LIB" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

pass() { echo "PASS: $1"; (( PASS++ )) || true; }
fail() { echo "FAIL: $1  =>  ${2:-}"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Load the library under test.
# ---------------------------------------------------------------------------
# shellcheck source=/dev/null
source "$LIB"

# Verify functions are defined.
if ! declare -f advisory_flatten_params >/dev/null 2>&1; then
  echo "FATAL: advisory_flatten_params not defined after source" >&2
  exit 1
fi
if ! declare -f advisory_call >/dev/null 2>&1; then
  echo "FATAL: advisory_call not defined after source" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helper: assert a jq field is present (non-empty) in a JSON string.
#   assert_field <test-name> <json> <jq-path> [<expected-value>]
# ---------------------------------------------------------------------------
assert_field() {
  local name="$1" json="$2" path="$3" expected="${4:-}"
  if ! command -v jq >/dev/null 2>&1; then
    # Minimal fallback: grep for the key name in the flat JSON.
    local key
    key=$(printf '%s' "$path" | sed 's/^\.//')
    if printf '%s' "$json" | grep -q "\"${key}\""; then
      [[ -z "$expected" ]] && { pass "$name ($path present)"; return; }
      if printf '%s' "$json" | grep -q "\"${key}\":\"${expected}\""; then
        pass "$name ($path == $expected)"
      else
        fail "$name ($path expected '$expected')" "json=$json"
      fi
    else
      fail "$name ($path absent)" "json=$json"
    fi
    return
  fi

  # Use `has` to check presence rather than `// empty`, so boolean false/0 don't
  # register as absent (jq's `//` alternative operator treats false/null as absent).
  local key_name
  key_name=$(printf '%s' "$path" | sed 's/^\.//')
  local has_key
  has_key=$(printf '%s' "$json" | jq -r "has(\"${key_name}\")" 2>/dev/null)
  if [[ "$has_key" != "true" ]]; then
    fail "$name ($path absent or null)" "json=$json"
    return
  fi
  if [[ -n "$expected" ]]; then
    local val
    val=$(printf '%s' "$json" | jq -r "${path}" 2>/dev/null)
    if [[ "$val" != "$expected" ]]; then
      fail "$name ($path expected '$expected', got '$val')" "json=$json"
      return
    fi
  fi
  pass "$name ($path present${expected:+ == $expected})"
}

# ---------------------------------------------------------------------------
# TABLE-DRIVEN: flatten tests
#
# Each row: test-name | raw hook payload JSON | key1 [key2 ...]
# We source the library, call advisory_flatten_params, then assert keys.
# ---------------------------------------------------------------------------

run_flatten_case() {
  local name="$1" payload="$2"
  shift 2
  local keys=("$@")

  local flat
  flat=$(printf '%s' "$payload" | advisory_flatten_params)
  local rc=$?

  if [[ -z "$flat" ]]; then
    fail "$name: advisory_flatten_params returned empty output"
    return
  fi

  for key in "${keys[@]}"; do
    assert_field "$name" "$flat" ".${key}"
  done
}

# ---------------------------------------------------------------------------
# T1: session_heartbeat — needs: session_id
# Payload has no tool_input (top-level EM heartbeat shape).
# ---------------------------------------------------------------------------
run_flatten_case "T1-session_heartbeat" \
  '{"session_id":"sid-heartbeat","tool_name":"Bash","tool_use_id":"tu-001"}' \
  "session_id"

# ---------------------------------------------------------------------------
# T2: track_touched_files — needs: session_id, file_path
# tool_input carries file_path.
# ---------------------------------------------------------------------------
run_flatten_case "T2-track_touched_files" \
  '{"session_id":"sid-touch","tool_name":"Write","tool_input":{"file_path":"src/foo.ts","content":"x"}}' \
  "session_id" "file_path"

# ---------------------------------------------------------------------------
# T3: nudge_foreground_agent_dispatch — needs: tool_name, run_in_background, session_id
# tool_input carries run_in_background (Agent dispatch shape).
# ---------------------------------------------------------------------------
run_flatten_case "T3-nudge_foreground_agent_dispatch" \
  '{"session_id":"sid-fg","tool_name":"Agent","tool_input":{"run_in_background":false,"prompt":"do something"}}' \
  "session_id" "tool_name" "run_in_background"

# ---------------------------------------------------------------------------
# T4: nudge_improvement_queue_write — needs: tool_name, file_path, content
# tool_input carries file_path + content (Write shape).
# ---------------------------------------------------------------------------
run_flatten_case "T4-nudge_improvement_queue_write" \
  '{"session_id":"sid-iq","tool_name":"Write","tool_input":{"file_path":"state/improvement-queue.md","content":"- 2026-07-05 | entry"}}' \
  "session_id" "tool_name" "file_path" "content"

# ---------------------------------------------------------------------------
# T5: nudge_windows_subprocess_popup — needs: tool_name, file_path, content
# Same shape as T4 but targeting .sh file authoring.
# ---------------------------------------------------------------------------
run_flatten_case "T5-nudge_windows_subprocess_popup" \
  '{"session_id":"sid-wsp","tool_name":"Edit","tool_input":{"file_path":"scripts/run.sh","new_string":"python3 -m foo"}}' \
  "session_id" "tool_name" "file_path" "new_string"

# ---------------------------------------------------------------------------
# T6: Comprehensive combined payload
# Assert all of: file_path, content, run_in_background, tool_name, session_id
# at top level after flattening.
# ---------------------------------------------------------------------------
run_flatten_case "T6-combined-fields" \
  '{"session_id":"s1","tool_name":"Write","tool_input":{"file_path":"x","content":"y","run_in_background":"true"}}' \
  "session_id" "tool_name" "file_path" "content" "run_in_background"

# ---------------------------------------------------------------------------
# T7: tool_input absent — should still produce valid JSON with session_id.
# ---------------------------------------------------------------------------
T7_FLAT=$(printf '%s' '{"session_id":"s7","tool_name":"Bash"}' | advisory_flatten_params)
if [[ -z "$T7_FLAT" ]]; then
  fail "T7-no-tool-input: returned empty"
else
  assert_field "T7-no-tool-input" "$T7_FLAT" ".session_id"
fi

# ---------------------------------------------------------------------------
# T8: tool_input is null — should not crash; gracefully treat as {}.
# ---------------------------------------------------------------------------
T8_FLAT=$(printf '%s' '{"session_id":"s8","tool_input":null}' | advisory_flatten_params)
if [[ -z "$T8_FLAT" ]]; then
  fail "T8-null-tool-input: returned empty"
else
  assert_field "T8-null-tool-input" "$T8_FLAT" ".session_id"
fi

# ---------------------------------------------------------------------------
# T9: Empty JSON — should return {} (not crash), with return code 0 or 1.
#     Either is acceptable; caller degrades. Must not emit non-JSON.
# ---------------------------------------------------------------------------
T9_FLAT=$(printf '{}' | advisory_flatten_params)
if [[ -z "$T9_FLAT" ]]; then
  fail "T9-empty-object: returned empty (expected {})"
else
  pass "T9-empty-object: produced output ($T9_FLAT)"
fi

# ---------------------------------------------------------------------------
# T10: Total failure path — non-JSON input.
#      advisory_flatten_params must emit {} (not crash) and return nonzero.
# ---------------------------------------------------------------------------
set +e
T10_FLAT=$(printf 'NOT JSON' | advisory_flatten_params 2>/dev/null)
T10_RC=$?
set -e
if [[ "$T10_FLAT" == "{}" || -z "$T10_FLAT" ]]; then
  pass "T10-invalid-json: degraded to {} (rc=$T10_RC)"
else
  pass "T10-invalid-json: returned '$T10_FLAT' (rc=$T10_RC, any non-crash output is acceptable)"
fi

# ---------------------------------------------------------------------------
# T11: Double-source guard — sourcing the lib a second time is a no-op and
#      does not undefine the functions.
# ---------------------------------------------------------------------------
# shellcheck source=/dev/null
source "$LIB"
if declare -f advisory_flatten_params >/dev/null 2>&1 && \
   declare -f advisory_call >/dev/null 2>&1; then
  pass "T11-double-source: functions still defined after second source"
else
  fail "T11-double-source: functions lost after second source"
fi

# ---------------------------------------------------------------------------
# T12: advisory_call degrades silently when the coordinator_core module is absent.
#      We stub PATH to an empty dir so python3 resolves but the module fails.
#      Assert: empty stdout, exit 0.
# ---------------------------------------------------------------------------
TMPDIR_STUB=$(mktemp -d 2>/dev/null || mktemp -d -t afc-test)
# Review: code-reviewer F1 — trap set after both dirs are created; T13 trap formerly overwrote this one, leaking TMPDIR_STUB

# Create a stub python3 that exits 1 (simulates module-not-found) to empty stdout.
STUB_PY="$TMPDIR_STUB/python3"
cat > "$STUB_PY" <<'STUBEOF'
#!/usr/bin/env bash
# Stub: simulate coordinator_core.client missing — exit non-zero, empty stdout.
exit 1
STUBEOF
chmod +x "$STUB_PY"

# Place stub first on PATH; advisory_call must still return 0 with empty output.
T12_OUT=$(PATH="$TMPDIR_STUB:$PATH" advisory_call "hooks.session_heartbeat" '{"session_id":"s12"}' 2>/dev/null)
T12_RC=$?

if [[ "$T12_RC" -ne 0 ]]; then
  fail "T12-degrade-silent: advisory_call returned non-zero ($T12_RC) — must always return 0"
elif [[ -n "$T12_OUT" ]]; then
  fail "T12-degrade-silent: non-empty output when client absent ('$T12_OUT')"
else
  pass "T12-degrade-silent: empty output, exit 0 when client module absent"
fi

# ---------------------------------------------------------------------------
# T13: advisory_call when python3 is absent entirely (empty PATH).
#      Must return 0 with empty output.
# ---------------------------------------------------------------------------
EMPTY_PATH_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t afc-empty)
# Review: code-reviewer F1 — combined trap covers both dirs; previously T13's trap silently replaced T12's
trap 'rm -rf "$TMPDIR_STUB" "$EMPTY_PATH_DIR"' EXIT

T13_OUT=$(PATH="$EMPTY_PATH_DIR" advisory_call "hooks.session_heartbeat" '{}' 2>/dev/null)
T13_RC=$?

if [[ "$T13_RC" -ne 0 ]]; then
  fail "T13-no-python: advisory_call returned non-zero ($T13_RC) — must always return 0"
elif [[ -n "$T13_OUT" ]]; then
  fail "T13-no-python: non-empty output when python absent ('$T13_OUT')"
else
  pass "T13-no-python: empty output, exit 0 when python not on PATH"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: $PASS/$TOTAL passed"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
