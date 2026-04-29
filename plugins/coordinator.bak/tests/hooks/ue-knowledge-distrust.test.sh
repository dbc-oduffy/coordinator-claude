#!/bin/bash
# Regression test: ue-knowledge-distrust hook format and registration.
#
# TARGET LOCATION: coordinator-claude/tests/hooks/ue-knowledge-distrust.test.sh
# This file was staged in the holodeck repo due to sandbox write restrictions on
# ~/.claude/ paths. Move to coordinator-claude and commit there.
#
# Schema test — asserts structural format (not just keyword presence).
# Six required assertions verify the hook output is machine-readable and complete.
#
# Usage:
#   bash tests/hooks/ue-knowledge-distrust.test.sh
#   Returns: exit 0 on pass, exit 1 with details on fail.
#
# BASELINE_BYTES: measured from hook stdout in X:/DroneSim (2026-04-14)
# This constant is the Phase 4 char-budget ceiling (≤ ceil(BASELINE_BYTES * 1.5)).
BASELINE_BYTES=470
BUDGET_BYTES=$(( (BASELINE_BYTES * 3 + 1) / 2 ))  # ceil(BASELINE_BYTES * 1.5) = 705

HOOKS_JSON="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/coordinator-claude}/coordinator/hooks/hooks.json"
HOOK_SCRIPT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/coordinator-claude}/coordinator/hooks/scripts/ue-knowledge-distrust.sh"

PASS=0
FAIL=0
ERRORS=()

assert_pass() {
  local label="$1"
  PASS=$((PASS + 1))
  echo "  PASS: $label"
}

assert_fail() {
  local label="$1"
  local detail="$2"
  FAIL=$((FAIL + 1))
  ERRORS+=("FAIL: $label -- $detail")
  echo "  FAIL: $label -- $detail"
}

echo "=== ue-knowledge-distrust hook regression test ==="
echo ""

# Setup: run hook in a temp .uproject directory
TMP_DIR=$(mktemp -d)
touch "$TMP_DIR/TestProject.uproject"
HOOK_OUTPUT=$(cd "$TMP_DIR" && bash "$HOOK_SCRIPT" 2>/dev/null)
rm -rf "$TMP_DIR"

if [[ -z "$HOOK_OUTPUT" ]]; then
  echo "FATAL: hook produced no output when run from a .uproject directory"
  exit 1
fi

echo "Hook output:"
echo "$HOOK_OUTPUT" | sed 's/^/  /'
echo ""
echo "--- Assertions ---"

# Assertion 1: Lead-tag prefix regex
# Must match: ^UE PROJECT DETECTED (identifier):
if echo "$HOOK_OUTPUT" | head -1 | grep -qE '^UE PROJECT DETECTED \([A-Za-z0-9_-]+\): '; then
  assert_pass "1. Lead-tag prefix: 'UE PROJECT DETECTED (<NAME>): '"
else
  assert_fail "1. Lead-tag prefix" "expected '^UE PROJECT DETECTED ([A-Za-z0-9_-]+): ', got: $(echo "$HOOK_OUTPUT" | head -1 | head -c 80)"
fi

# Assertion 2: "Verified counts:" segment with 421,935 / 73K / 197K in order
if echo "$HOOK_OUTPUT" | grep -q "Verified counts:"; then
  COUNTS_LINE=$(echo "$HOOK_OUTPUT" | grep "Verified counts:")
  if echo "$COUNTS_LINE" | grep -q "421,935" && echo "$COUNTS_LINE" | grep -q "73K" && echo "$COUNTS_LINE" | grep -q "197K"; then
    POS_421=$(echo "$COUNTS_LINE" | grep -bo "421,935" | head -1 | cut -d: -f1)
    POS_73K=$(echo "$COUNTS_LINE" | grep -bo "73K" | head -1 | cut -d: -f1)
    POS_197K=$(echo "$COUNTS_LINE" | grep -bo "197K" | head -1 | cut -d: -f1)
    if [[ -n "$POS_421" && -n "$POS_73K" && -n "$POS_197K" && "$POS_421" -lt "$POS_73K" && "$POS_73K" -lt "$POS_197K" ]]; then
      assert_pass "2. Verified counts: 421,935 / 73K / 197K in order"
    else
      assert_fail "2. Verified counts order" "421,935 / 73K / 197K present but not in expected order"
    fi
  else
    assert_fail "2. Verified counts segment" "missing one or more of: 421,935, 73K, 197K in counts line"
  fi
else
  assert_fail "2. Verified counts segment" "'Verified counts:' not found in hook output"
fi

# Assertion 3: "Verified tools:" segment non-empty, all 5 tools present
REQUIRED_TOOLS=("quick_ue_lookup" "lookup_ue_class" "check_ue_patterns" "find_symbol" "search_symbols")
if echo "$HOOK_OUTPUT" | grep -q "Verified tools:"; then
  TOOLS_LINE=$(echo "$HOOK_OUTPUT" | grep "Verified tools:")
  ALL_TOOLS=1
  MISSING_TOOLS=()
  for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! echo "$TOOLS_LINE" | grep -q "$tool"; then
      ALL_TOOLS=0
      MISSING_TOOLS+=("$tool")
    fi
  done
  if [[ $ALL_TOOLS -eq 1 ]]; then
    assert_pass "3. Verified tools: all 5 named"
  else
    assert_fail "3. Verified tools missing" "missing: ${MISSING_TOOLS[*]}"
  fi
else
  assert_fail "3. Verified tools segment" "'Verified tools:' not found in hook output"
fi

# Assertion 4: "Known hallucination risk categories:" segment with >=5 entries
if echo "$HOOK_OUTPUT" | grep -q "Known hallucination risk categories:"; then
  CATEGORIES_LINE=$(echo "$HOOK_OUTPUT" | grep "Known hallucination risk categories:")
  CATEGORIES_CONTENT=$(echo "$CATEGORIES_LINE" | sed 's/.*Known hallucination risk categories: *//')
  SEMICOLON_COUNT=$(echo "$CATEGORIES_CONTENT" | tr -cd ';' | wc -c)
  CATEGORY_COUNT=$((SEMICOLON_COUNT + 1))
  if [[ $CATEGORY_COUNT -ge 5 ]]; then
    assert_pass "4. Known hallucination risk categories: >=5 entries (found $CATEGORY_COUNT)"
  else
    assert_fail "4. Known hallucination risk categories count" "expected >=5 categories, found $CATEGORY_COUNT"
  fi
else
  assert_fail "4. Known hallucination risk categories segment" "'Known hallucination risk categories:' not found"
fi

# Assertion 5: Closing advisory phrase
if echo "$HOOK_OUTPUT" | grep -q "Treat training knowledge as unverified hypothesis"; then
  assert_pass "5. Closing advisory: 'Treat training knowledge as unverified hypothesis'"
else
  assert_fail "5. Closing advisory phrase" "phrase not found in hook output"
fi

# Assertion 6: Byte count <= ceil(BASELINE_BYTES * 1.5)
ACTUAL_BYTES=$(echo "$HOOK_OUTPUT" | wc -c)
if [[ $ACTUAL_BYTES -le $BUDGET_BYTES ]]; then
  assert_pass "6. Byte count: $ACTUAL_BYTES <= $BUDGET_BYTES (ceil($BASELINE_BYTES x 1.5))"
else
  assert_fail "6. Byte count exceeded budget" "$ACTUAL_BYTES bytes > $BUDGET_BYTES ceiling"
fi

# jq assertion: hook registered under startup|compact AND clear matcher blocks
echo ""
echo "--- Hook registration (jq) ---"

if ! command -v jq &>/dev/null; then
  echo "  SKIP: jq not available"
else
  STARTUP_HOOKS=$(jq -r '.hooks.SessionStart[] | select(.matcher | test("startup")) | .hooks[].command' "$HOOKS_JSON" 2>/dev/null)
  if echo "$STARTUP_HOOKS" | grep -q "ue-knowledge-distrust.sh"; then
    assert_pass "jq: ue-knowledge-distrust.sh registered in startup|compact block"
  else
    assert_fail "jq: startup|compact registration" "not found in startup matcher block"
  fi

  CLEAR_HOOKS=$(jq -r '.hooks.SessionStart[] | select(.matcher | test("clear")) | .hooks[].command' "$HOOKS_JSON" 2>/dev/null)
  if echo "$CLEAR_HOOKS" | grep -q "ue-knowledge-distrust.sh"; then
    assert_pass "jq: ue-knowledge-distrust.sh registered in clear block"
  else
    assert_fail "jq: clear registration" "not found in clear matcher block"
  fi
fi

# Silent test: non-UE directory produces no output
TMP_EMPTY=$(mktemp -d)
SILENT_OUTPUT=$(cd "$TMP_EMPTY" && bash "$HOOK_SCRIPT" 2>/dev/null)
rm -rf "$TMP_EMPTY"
if [[ -z "$SILENT_OUTPUT" ]]; then
  assert_pass "Silent: no output in non-UE directory"
else
  assert_fail "Silent test" "hook emitted output in non-UE directory"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for err in "${ERRORS[@]}"; do
    echo "  $err"
  done
  exit 1
fi

exit 0
