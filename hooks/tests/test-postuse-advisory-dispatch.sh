#!/usr/bin/env bash
# Test suite: hooks/scripts/postuse-advisory-dispatch.sh — PostToolUse advisory dispatcher.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md § Phase 3
#
# Exercises:
#   TC-1: empty stdin → exit 0 with no output
#   TC-2: context-pressure advisory fires through the dispatcher
#          (CONTEXT_ADVISORY_THRESHOLD=1 + non-empty transcript file)
#   TC-3: neither advisory fires → empty output, exit 0
#   TC-4: merge case — both stubs emit known texts → ONE JSON with both texts
#          (temp-copy technique: replace both check scripts with stubs, run
#          temp-copy dispatcher, assert merged single-JSON output)
#
# Self-contained: builds throwaway temp files; never modifies any live repo or
# the meta-repo working tree. Run from the repo root or from this directory —
# paths resolve via BASH_SOURCE so neither cwd matters.
#
# JSON parsing: jq-only. If jq is absent, JSON-shape assertions are [SKIP]ped
# (counted as pass) so the suite remains green on minimal environments.
# The critical boolean assertions (has_ctx, has_cp, has_rt) use grep and do
# not require jq.
#
# Pass/fail idiom follows test-preuse-bash-dispatch.sh (same assertion style).
# Exit codes: 0 all passed, 1 one or more failed.

set -uo pipefail

# ---------------------------------------------------------------------------
# Path resolution — BASH_SOURCE-rooted so the test is cwd-independent.
# Layout: tests/ → hooks/ → coordinator/ → coordinator-claude/ → plugins/ → ~/.claude/
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCHER="$SCRIPT_DIR/../scripts/postuse-advisory-dispatch.sh"

if [[ ! -f "$DISPATCHER" ]]; then
  echo "FATAL: dispatcher not found: $DISPATCHER" >&2; exit 1
fi

# Detect jq availability once; used by assertions that need JSON parsing.
JQ_AVAILABLE=0
command -v jq &>/dev/null && JQ_AVAILABLE=1 || true

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# pass_fail <description> <ok:0|1> [detail]
# ---------------------------------------------------------------------------
pass_fail() {
  local desc="$1" ok="$2" detail="${3:-}"
  if [[ "$ok" == "1" ]]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc"
    [[ -n "$detail" ]] && echo "      $detail"
  fi
}

# ---------------------------------------------------------------------------
# skip_pass <description>
# Count as PASS and print a [SKIP] notice (used when no jq is available).
# ---------------------------------------------------------------------------
skip_pass() {
  PASS=$((PASS+1))
  echo "  [SKIP] $1 (counted as pass)"
}

# ---------------------------------------------------------------------------
# emit_postuse SESSION_ID TRANSCRIPT_PATH [AGENT_ID]
# Produces a PostToolUse-shaped JSON payload for piping to the dispatcher.
# Uses jq when available; sed-constructed fallback otherwise.
# ---------------------------------------------------------------------------
emit_postuse() {
  local sid="$1" tp="$2" aid="${3:-}"
  if [[ "$JQ_AVAILABLE" -eq 1 ]]; then
    jq -nc --arg s "$sid" --arg t "$tp" --arg a "$aid" \
      '{session_id:$s,transcript_path:$t,agent_id:$a,tool_name:"Write"}'
  else
    local se="${sid//\"/\\\"}"; local te="${tp//\"/\\\"}"; local ae="${aid//\"/\\\"}"
    te="${te//\\/\\\\}"  # backslash-escape path separators
    printf '{"session_id":"%s","transcript_path":"%s","agent_id":"%s","tool_name":"Write"}' \
      "$se" "$te" "$ae"
  fi
}

# ---------------------------------------------------------------------------
# count_json_objects_jq <text>
# Counts how many top-level JSON objects appear in text using jq slurp mode.
# Returns "" when jq is absent (caller must [SKIP] the assertion).
# Used to assert the dispatcher emits exactly ONE JSON object, not two.
# ---------------------------------------------------------------------------
count_json_objects_jq() {
  local text="$1"
  [[ "$JQ_AVAILABLE" -eq 0 ]] && { echo ""; return 0; }
  [[ -z "$text" ]] && { echo 0; return 0; }
  printf '%s' "$text" | jq -s 'length' 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# Shared temp directory — cleaned on EXIT.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# TC-1: empty stdin → exit 0 with no output.
#
# The dispatcher must handle the empty-stdin case via the early-exit guard
# (`[ -z "$INPUT" ] && exit 0`). Validates the simplest production path
# (hook system probes hooks with empty/minimal input on startup).
# ---------------------------------------------------------------------------
{
  out=$(printf '' | bash "$DISPATCHER" 2>/dev/null) || true

  exit_ok=0
  printf '' | bash "$DISPATCHER" >/dev/null 2>&1; [[ $? -eq 0 ]] && exit_ok=1 || true

  pass_fail "TC-1: empty stdin → no output" \
    "$([[ -z "$out" ]] && echo 1 || echo 0)" \
    "expected empty, got: $(printf '%s' "$out" | head -c 80)"

  pass_fail "TC-1: empty stdin → exit 0" \
    "$exit_ok" \
    "dispatcher exited non-zero on empty stdin"
}

# ---------------------------------------------------------------------------
# TC-2: context-pressure advisory fires through the dispatcher.
#
# CONTEXT_ADVISORY_THRESHOLD=1 lowers the advisory byte threshold to 1 so any
# non-empty transcript file triggers the advisory on the very first check
# (fresh session_id → no throttle or bark-once sentinel exists).
#
# Assertions:
#   (a) output contains "additionalContext" key (grep-based, no jq needed)
#   (b) output is valid JSON (jq-based; [SKIP] when jq absent)
#   (c) output is exactly ONE JSON object via jq slurp ([SKIP] when jq absent)
# ---------------------------------------------------------------------------
{
  SID_CP="sid-cp-$$-${RANDOM}"
  TRANSCRIPT="$TMP/transcript-${SID_CP}.jsonl"
  # Non-empty file so file_size >= CONTEXT_ADVISORY_THRESHOLD=1
  printf '"fake transcript content — context pressure test payload"\n' > "$TRANSCRIPT"

  out=$(emit_postuse "$SID_CP" "$TRANSCRIPT" "" \
    | CONTEXT_ADVISORY_THRESHOLD=1 bash "$DISPATCHER" 2>/dev/null) || out=""

  # (a) grep for additionalContext key — no jq required
  has_ctx=0
  printf '%s' "$out" | grep -q '"additionalContext"' && has_ctx=1 || true
  pass_fail "TC-2a: context-pressure fires → output contains additionalContext" \
    "$has_ctx" \
    "out: $(printf '%s' "$out" | head -c 300)"

  # (b) valid JSON via jq
  if [[ "$JQ_AVAILABLE" -eq 1 && -n "$out" ]]; then
    is_json=0
    printf '%s' "$out" | jq '.' &>/dev/null && is_json=1 || true
    pass_fail "TC-2b: context-pressure fires → output is valid JSON" \
      "$is_json" \
      "out: $(printf '%s' "$out" | head -c 300)"
  else
    skip_pass "TC-2b: valid-JSON assertion (no jq available or empty output)"
  fi

  # (c) exactly ONE JSON object via jq slurp
  json_count=$(count_json_objects_jq "$out")
  if [[ -n "$json_count" ]]; then
    pass_fail "TC-2c: context-pressure fires → exactly ONE JSON object emitted" \
      "$([[ "$json_count" -eq 1 ]] && echo 1 || echo 0)" \
      "json_count=$json_count | out: $(printf '%s' "$out" | head -c 300)"
  else
    skip_pass "TC-2c: one-JSON-object assertion (no jq available)"
  fi
}

# ---------------------------------------------------------------------------
# TC-3: neither advisory fires → empty output, exit 0.
#
# Conditions that prevent firing:
#   - No transcript_path → check_context_pressure returns 0 silently
#   - CONTEXT_ADVISORY_THRESHOLD not overridden → default threshold is large
#   - Fresh unique session_id with no .agents/ entry → runtime-tripwire
#     returns 0 (not a recognized subagent session_id)
# ---------------------------------------------------------------------------
{
  SID_NONE="sid-none-$$-${RANDOM}"

  out=$(emit_postuse "$SID_NONE" "" "" | bash "$DISPATCHER" 2>/dev/null) || out=""

  exit_ok=0
  emit_postuse "$SID_NONE" "" "" | bash "$DISPATCHER" >/dev/null 2>&1
  [[ $? -eq 0 ]] && exit_ok=1 || true

  pass_fail "TC-3: neither fires → empty output" \
    "$([[ -z "$out" ]] && echo 1 || echo 0)" \
    "expected empty, got: $(printf '%s' "$out" | head -c 200)"

  pass_fail "TC-3: neither fires → exit 0" \
    "$exit_ok" \
    "dispatcher exited non-zero when neither advisory fired"
}

# ---------------------------------------------------------------------------
# TC-4: merge case — both stubs emit known texts → ONE JSON containing both.
#
# Technique (mirrors AC12 fail-closed test in test-preuse-bash-dispatch.sh):
#   1. Copy dispatcher to a temp dir (STUB_DIR).
#   2. Write stub context-pressure-advisory.sh next to it: defines
#      check_context_pressure() to always emit a known additionalContext JSON.
#   3. Write stub runtime-tripwire-advisory.sh next to it: defines
#      check_runtime_tripwire() to always emit a different known text.
#   4. Run the temp-copy dispatcher (it sources siblings by BASH_SOURCE[0]
#      resolution, so it sources the stubs instead of the real scripts).
#   5. Assert: output contains BOTH stub texts AND is ONE JSON object.
# ---------------------------------------------------------------------------
{
  STUB_DIR="$TMP/stub-dispatcher"
  mkdir -p "$STUB_DIR"
  cp "$DISPATCHER" "$STUB_DIR/postuse-advisory-dispatch.sh"

  # Stub A: check_context_pressure always emits a fixed additionalContext JSON.
  # Intentionally minimal — no set -uo, no lib sourcing, just the function.
  cat > "$STUB_DIR/context-pressure-advisory.sh" <<'STUB_A'
#!/usr/bin/env bash
# TC-4 stub: check_context_pressure always emits a known additionalContext JSON.
check_context_pressure() {
  printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"STUB-CP-TEXT-UNIQUE-MARKER"}}\n'
  return 0
}
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  check_context_pressure "$@"; exit 0
fi
STUB_A

  # Stub B: check_runtime_tripwire always emits a different known text.
  cat > "$STUB_DIR/runtime-tripwire-advisory.sh" <<'STUB_B'
#!/usr/bin/env bash
# TC-4 stub: check_runtime_tripwire always emits a known additionalContext JSON.
check_runtime_tripwire() {
  printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"STUB-RT-TEXT-UNIQUE-MARKER"}}\n'
  return 0
}
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  check_runtime_tripwire "$@"; exit 0
fi
STUB_B

  STUB_DISP="$STUB_DIR/postuse-advisory-dispatch.sh"
  SID_MERGE="sid-merge-$$-${RANDOM}"

  merged_out=$(emit_postuse "$SID_MERGE" "" "" | bash "$STUB_DISP" 2>/dev/null) || merged_out=""

  # (a) STUB-CP-TEXT-UNIQUE-MARKER must appear in output (grep, no jq)
  has_cp=0
  printf '%s' "$merged_out" | grep -q 'STUB-CP-TEXT-UNIQUE-MARKER' && has_cp=1 || true
  pass_fail "TC-4a: merge → output contains STUB-CP-TEXT-UNIQUE-MARKER" \
    "$has_cp" \
    "out: $(printf '%s' "$merged_out" | head -c 400)"

  # (b) STUB-RT-TEXT-UNIQUE-MARKER must appear in output (grep, no jq)
  has_rt=0
  printf '%s' "$merged_out" | grep -q 'STUB-RT-TEXT-UNIQUE-MARKER' && has_rt=1 || true
  pass_fail "TC-4b: merge → output contains STUB-RT-TEXT-UNIQUE-MARKER" \
    "$has_rt" \
    "out: $(printf '%s' "$merged_out" | head -c 400)"

  # (c) exactly ONE JSON object (jq slurp; [SKIP] when jq absent)
  merged_count=$(count_json_objects_jq "$merged_out")
  if [[ -n "$merged_count" ]]; then
    pass_fail "TC-4c: merge → exactly ONE JSON object emitted (not two)" \
      "$([[ "$merged_count" -eq 1 ]] && echo 1 || echo 0)" \
      "json_count=$merged_count | out: $(printf '%s' "$merged_out" | head -c 400)"
  else
    skip_pass "TC-4c: one-JSON-object assertion (no jq available)"
  fi

  # (d) .hookSpecificOutput.additionalContext is non-empty (jq; [SKIP] when absent)
  if [[ "$JQ_AVAILABLE" -eq 1 && -n "$merged_out" ]]; then
    ctx_val=$(printf '%s' "$merged_out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
    pass_fail "TC-4d: merge → .hookSpecificOutput.additionalContext is non-empty" \
      "$([[ -n "$ctx_val" ]] && echo 1 || echo 0)" \
      "out: $(printf '%s' "$merged_out" | head -c 400)"
  else
    skip_pass "TC-4d: additionalContext field assertion (no jq available or empty output)"
  fi
}

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "postuse-advisory-dispatch: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
