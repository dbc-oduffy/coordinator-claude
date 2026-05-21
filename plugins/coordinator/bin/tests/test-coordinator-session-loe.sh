#!/bin/bash
# test-coordinator-session-loe.sh — Exercise coordinator-session-loe.sh read helper.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 2 — AC: correct three numbers + t-shirt; missing token metadata degrades
# gracefully; YAML-frontmatter output paste-ready; concurrency declarations present.
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-coordinator-session-loe.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOE="${SCRIPT_DIR}/../coordinator-session-loe.sh"

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

run_test() {
  local name="$1"
  local fn="$2"
  echo "--- $name"
  "$fn" && pass "$name" || fail "$name"
}

# ---------------------------------------------------------------------------
# Fixture setup
# ---------------------------------------------------------------------------

TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t loe-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

# Create a fake git repo so git rev-parse works
FAKE_REPO="${TMPDIR_BASE}/repo"
mkdir -p "${FAKE_REPO}/.git"
git -C "$FAKE_REPO" init -q 2>/dev/null || true

SESSIONS_BASE="${FAKE_REPO}/.git/coordinator-sessions"
mkdir -p "$SESSIONS_BASE"

# Create a fixture session
make_session() {
  local sid="$1"
  local session_dir="${SESSIONS_BASE}/${sid}"
  mkdir -p "$session_dir"
  echo "$sid" > "${SESSIONS_BASE}/.current-session-id"
  echo "$session_dir"
}

# Write fixture dispatched-agents.txt with tab-delimited records
write_agents() {
  local session_dir="$1"
  shift
  local agents_file="${session_dir}/dispatched-agents.txt"
  : > "$agents_file"
  for rec in "$@"; do
    echo -e "$rec" >> "$agents_file"
  done
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test_xs_session() {
  local sid="fixture-xs-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  # 2 dispatches, 0 opus, no tokens.
  # NOTE: XS is structurally unreachable under "any-criterion" semantics because
  # S.opus_dispatches=0, so 0>=0 qualifies every session for S.  The spec worked
  # example claims XS here but the threshold table makes it impossible — see plan F8.
  # This test verifies S (the correct result given the threshold table).
  write_agents "$sdir" \
    "aaaaaa0000000001\tsonnet\texecutor" \
    "aaaaaa0000000002\tsonnet\texecutor"

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  [[ "$out" == *'"agent_dispatches": 2'* ]] || { echo "    agent_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 0'* ]] || { echo "    opus_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"em_tokens": null'* ]]     || { echo "    em_tokens should be null: $out"; return 1; }
  [[ "$out" == *'"tshirt": "XS"'* ]]        || { echo "    tshirt should be XS (2<5 agent, 0<1 opus, null<150k tokens): $out"; return 1; }
}

test_m_session() {
  local sid="fixture-m-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  # 18 dispatches, 2 opus -> M (18>=15 on agent_dispatches, 2>=1 on opus)
  write_agents "$sdir" \
    "aaaaaa0000000001\topus\texecutor" \
    "aaaaaa0000000002\topus-3-5\texecutor" \
    "aaaaaa0000000003\tsonnet\texecutor" \
    "aaaaaa0000000004\tsonnet\texecutor" \
    "aaaaaa0000000005\tsonnet\texecutor" \
    "aaaaaa0000000006\tsonnet\texecutor" \
    "aaaaaa0000000007\tsonnet\texecutor" \
    "aaaaaa0000000008\tsonnet\texecutor" \
    "aaaaaa0000000009\tsonnet\texecutor" \
    "aaaaaa0000000010\tsonnet\texecutor" \
    "aaaaaa0000000011\tsonnet\texecutor" \
    "aaaaaa0000000012\tsonnet\texecutor" \
    "aaaaaa0000000013\tsonnet\texecutor" \
    "aaaaaa0000000014\tsonnet\texecutor" \
    "aaaaaa0000000015\tsonnet\texecutor" \
    "aaaaaa0000000016\tsonnet\texecutor" \
    "aaaaaa0000000017\tsonnet\texecutor" \
    "aaaaaa0000000018\tsonnet\texecutor"

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  [[ "$out" == *'"agent_dispatches": 18'* ]] || { echo "    agent_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 2'* ]]   || { echo "    opus_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"tshirt": "M"'* ]]          || { echo "    tshirt should be M: $out"; return 1; }
}

test_l_session_via_opus() {
  local sid="fixture-l-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  # 10 dispatches, 4 opus -> L (4>=3 on opus, but 10<30 on agent_dispatches)
  write_agents "$sdir" \
    "aaaaaa0000000001\topus\texecutor" \
    "aaaaaa0000000002\topus\texecutor" \
    "aaaaaa0000000003\topus\texecutor" \
    "aaaaaa0000000004\topus\texecutor" \
    "aaaaaa0000000005\tsonnet\texecutor" \
    "aaaaaa0000000006\tsonnet\texecutor" \
    "aaaaaa0000000007\tsonnet\texecutor" \
    "aaaaaa0000000008\tsonnet\texecutor" \
    "aaaaaa0000000009\tsonnet\texecutor" \
    "aaaaaa0000000010\tsonnet\texecutor"

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  [[ "$out" == *'"opus_dispatches": 4'* ]] || { echo "    opus_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"tshirt": "L"'* ]]        || { echo "    tshirt should be L: $out"; return 1; }
}

test_legacy_format() {
  # Legacy bare-agentId records (no tabs) — must parse without error and
  # count as dispatches with 0 Opus (model field absent -> unknown, not opus).
  local sid="fixture-legacy-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  cat > "${sdir}/dispatched-agents.txt" <<'EOF'
a1234567890abcdef
a9876543210fedcba
afedcba9876543210
a0123456789abcdef
a0987654321fedcba
a0f1e2d3c4b5a6a7
EOF

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  [[ "$out" == *'"agent_dispatches": 6'* ]] || { echo "    agent_dispatches wrong (legacy): $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 0'* ]]  || { echo "    opus_dispatches should be 0 (legacy): $out"; return 1; }
  [[ "$out" == *'"tshirt": "S"'* ]]         || { echo "    tshirt should be S (6>=5): $out"; return 1; }
}

test_empty_session() {
  local sid="fixture-empty-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  # No dispatched-agents.txt at all.
  # Post dogfood-fix 2026-05-19: S.opus=1 means 0<1 fails opus criterion, 0<5 fails
  # agent criterion, null<150k fails token criterion -> XS (floor).
  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  [[ "$out" == *'"agent_dispatches": 0'* ]] || { echo "    agent_dispatches wrong (empty): $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 0'* ]]  || { echo "    opus_dispatches wrong (empty): $out"; return 1; }
  [[ "$out" == *'"tshirt": "XS"'* ]]        || { echo "    tshirt should be XS (empty session = floor): $out"; return 1; }
}

test_yaml_frontmatter_format() {
  local sid="fixture-yaml-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  write_agents "$sdir" \
    "aaaaaa0000000001\tsonnet\texecutor" \
    "aaaaaa0000000002\tsonnet\texecutor" \
    "aaaaaa0000000003\tsonnet\texecutor" \
    "aaaaaa0000000004\tsonnet\texecutor" \
    "aaaaaa0000000005\tsonnet\texecutor"

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format yaml-frontmatter 2>/dev/null)
  # Must start with "loe:" and contain the expected keys
  [[ "$out" == loe:* ]]                        || { echo "    must start with loe:: $out"; return 1; }
  [[ "$out" == *"agent_dispatches: 5"* ]]      || { echo "    agent_dispatches missing: $out"; return 1; }
  [[ "$out" == *"opus_dispatches: 0"* ]]       || { echo "    opus_dispatches missing: $out"; return 1; }
  [[ "$out" == *"em_tokens: null"* ]]          || { echo "    em_tokens should be null: $out"; return 1; }
  [[ "$out" == *"tshirt:"* ]]                  || { echo "    tshirt missing: $out"; return 1; }
}

test_tsv_format() {
  local sid="fixture-tsv-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  write_agents "$sdir" \
    "aaaaaa0000000001\tsonnet\texecutor"

  out=$(cd "$FAKE_REPO"; bash "$LOE" --session-id "$sid" --format tsv 2>/dev/null)
  # TSV: session_id  agent_dispatches  opus_dispatches  em_tokens  tshirt
  fields=$(echo "$out" | awk -F'\t' '{print NF}')
  [[ "$fields" -eq 5 ]] || { echo "    TSV should have 5 fields, got $fields: $out"; return 1; }
  col1=$(echo "$out" | cut -f1)
  [[ "$col1" == "$sid" ]] || { echo "    col1 should be session_id: $col1"; return 1; }
}

test_concurrency_declarations_present() {
  # Verify the script header contains required concurrency/idempotency/resume declarations
  grep -q "Concurrency posture:" "$LOE" || { echo "    Missing 'Concurrency posture:' declaration"; return 1; }
  grep -q "Idempotency posture:" "$LOE" || { echo "    Missing 'Idempotency posture:' declaration"; return 1; }
  grep -q "Resume strategy:" "$LOE"     || { echo "    Missing 'Resume strategy:' declaration"; return 1; }
}

test_token_degrade_graceful() {
  # When env vars absent (default test env), em_tokens should be null, not an error
  local sid="fixture-degrade-$(date +%s)"
  local sdir; sdir=$(make_session "$sid")
  write_agents "$sdir" "aaaaaa0000000001\tsonnet\texecutor"

  # Explicitly unset the speculative env vars to simulate their absence
  out=$(cd "$FAKE_REPO"; unset CLAUDE_SESSION_INPUT_TOKENS CLAUDE_SESSION_OUTPUT_TOKENS 2>/dev/null; \
        bash "$LOE" --session-id "$sid" --format json 2>/dev/null)
  exit_code=$?
  [[ $exit_code -eq 0 ]]                  || { echo "    non-zero exit on missing tokens: $exit_code"; return 1; }
  [[ "$out" == *'"em_tokens": null'* ]]   || { echo "    em_tokens should degrade to null: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

echo "=== coordinator-session-loe.sh tests ==="
run_test "XS session (2 dispatches, 0 opus)"     test_xs_session
run_test "M session (18 dispatches, 2 opus)"     test_m_session
run_test "L session via opus count (4 opus)"     test_l_session_via_opus
run_test "Legacy bare-agentId format"            test_legacy_format
run_test "Empty session (no agents file)"        test_empty_session
run_test "yaml-frontmatter output format"        test_yaml_frontmatter_format
run_test "tsv output format"                     test_tsv_format
run_test "Concurrency declarations present"      test_concurrency_declarations_present
run_test "Token degrade graceful (em_tokens=null)" test_token_degrade_graceful

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi
exit 0
