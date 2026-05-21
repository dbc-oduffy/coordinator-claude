#!/bin/bash
# test-aggregate-chain-loe.sh — Smoke tests for bin/aggregate-chain-loe.sh.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 5 — AC: 3-session chain sums LoE; 1-session chain = single-session;
# missing-ledger degrades gracefully; multi-ledger N blocks contribute; same
# session_id deduped; missing-predecessor terminates with annotation; cycle
# terminates with annotation; archived predecessors traversed.
#
# Run: bash ~/.claude/plugins/coordinator/bin/tests/test-aggregate-chain-loe.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGG="${SCRIPT_DIR}/../aggregate-chain-loe.sh"

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
# Fixture helpers
# ---------------------------------------------------------------------------

TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t agg-chain-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

FAKE_REPO="${TMPDIR_BASE}/repo"
mkdir -p "${FAKE_REPO}/tasks/handoffs/archive/2026-05"
git -C "$FAKE_REPO" init -q 2>/dev/null || true

HANDOFFS="${FAKE_REPO}/tasks/handoffs"
ARCHIVE="${HANDOFFS}/archive/2026-05"

# Write a handoff file with given predecessor and optional Session Ledger blocks.
# Arguments:
#   $1 = path (relative to HANDOFFS or absolute)
#   $2 = predecessor value (null/none/<basename-or-absolute-path>)
#         Pass basename only (e.g. "foo.md") — write_handoff resolves it to the
#         absolute path in the fixture HANDOFFS dir so resolve_handoff_path
#         (which tries absolute paths first) can find it regardless of git root.
#         Pass "null" or "none" to terminate the chain.
#   $3 = created date (YYYY-MM-DD)
#   $4+ = ledger blocks as strings (each block = one "| field | value |" table)
#         Pass as: "session_id=S1 agent_dispatches=10 opus_dispatches=2 em_tokens=200000 commits=abc1234"
write_handoff() {
  local path="$1"
  local predecessor="$2"
  local created="$3"
  shift 3

  local full_path
  if [[ "$path" = /* ]]; then
    full_path="$path"
  else
    full_path="${HANDOFFS}/${path}"
  fi

  # Resolve predecessor to an absolute path so resolve_handoff_path (which checks
  # the as-is path first) finds it in the fixture dir, not the real repo's handoffs.
  local resolved_pred="$predecessor"
  if [[ "$predecessor" != "null" && "$predecessor" != "none" && -n "$predecessor" ]]; then
    local pred_basename; pred_basename="$(basename "$predecessor")"
    # Check HANDOFFS dir first, then ARCHIVE
    if [[ -f "${HANDOFFS}/${pred_basename}" ]]; then
      resolved_pred="${HANDOFFS}/${pred_basename}"
    elif [[ -f "${ARCHIVE}/${pred_basename}" ]]; then
      resolved_pred="${ARCHIVE}/${pred_basename}"
    elif [[ -f "$predecessor" ]]; then
      resolved_pred="$predecessor"  # already absolute
    fi
    # If none found yet, keep original — file may be written after this call
    # (in cycle tests). The test will catch the missing-link result instead.
  fi

  cat > "$full_path" <<EOFRONT
---
title: "Test handoff ${path}"
created: ${created}
branch: work/test/2026-05-01
status: consumed
kind: session-handoff
predecessor: ${resolved_pred}
---

# Test Handoff

Some body content.

EOFRONT

  # Append Session Ledger blocks for each argument
  for ledger_spec in "$@"; do
    local sid="" ad="0" od="0" tok="null" commits="" ts=""
    for kv in $ledger_spec; do
      key="${kv%%=*}"
      val="${kv#*=}"
      case "$key" in
        session_id)       sid="$val" ;;
        agent_dispatches) ad="$val" ;;
        opus_dispatches)  od="$val" ;;
        em_tokens)        tok="$val" ;;
        commits)          commits="$val" ;;
        created)          ts="$val" ;;
      esac
    done
    [[ -z "$ts" ]] && ts="${created}T12:00:00Z"
    cat >> "$full_path" <<EOLEDGER

## Session Ledger

| Field | Value |
|-------|-------|
| agent_dispatches | ${ad} |
| opus_dispatches | ${od} |
| em_tokens | ${tok} |
| commits | ${commits} |
| session_id | ${sid} |
| created | ${ts} |
EOLEDGER
  done
}

# ---------------------------------------------------------------------------
# Test 1: 1-session chain (single handoff, one ledger block)
# ---------------------------------------------------------------------------

test_single_session_chain() {
  local h1="${HANDOFFS}/single-session-root.md"
  write_handoff "single-session-root.md" "null" "2026-05-01" \
    "session_id=SID-SINGLE agent_dispatches=12 opus_dispatches=2 em_tokens=280000 commits=aabbccdd"

  out=$(bash "$AGG" --terminal-handoff "$h1" --format json 2>/dev/null)

  [[ "$out" == *'"agent_dispatches": 12'* ]] || { echo "    agent_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 2'* ]]  || { echo "    opus_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'"em_tokens": 280000'* ]]   || { echo "    em_tokens wrong: $out"; return 1; }
  [[ "$out" == *'"tshirt": "M"'* ]]         || { echo "    tshirt should be M (12>=M.ad=15? no; 2>=M.od=1? yes): $out"; return 1; }
  [[ "$out" == *'"sessions": 1'* ]]   || { echo "    chain_sessions should be 1: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 2: 3-session chain — sums all ledger blocks
# ---------------------------------------------------------------------------

test_three_session_chain() {
  # Build: h3 -> h2 -> h1(root, predecessor=null)
  local h1="${HANDOFFS}/three-chain-root.md"
  local h2="${HANDOFFS}/three-chain-mid.md"
  local h3="${HANDOFFS}/three-chain-terminal.md"

  write_handoff "three-chain-root.md" "null" "2026-05-01" \
    "session_id=SID-THREE-A agent_dispatches=10 opus_dispatches=1 em_tokens=150000 commits=aaa0001"

  write_handoff "three-chain-mid.md" "three-chain-root.md" "2026-05-03" \
    "session_id=SID-THREE-B agent_dispatches=20 opus_dispatches=3 em_tokens=400000 commits=bbb0001"

  write_handoff "three-chain-terminal.md" "three-chain-mid.md" "2026-05-07" \
    "session_id=SID-THREE-C agent_dispatches=15 opus_dispatches=2 em_tokens=250000 commits=ccc0001"

  out=$(bash "$AGG" --terminal-handoff "$h3" --format json 2>/dev/null)

  # Expected sums: ad=45, od=6, tok=800000
  [[ "$out" == *'"agent_dispatches": 45'* ]] || { echo "    agent_dispatches should be 45: $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 6'* ]]   || { echo "    opus_dispatches should be 6: $out"; return 1; }
  [[ "$out" == *'"em_tokens": 800000'* ]]    || { echo "    em_tokens should be 800000: $out"; return 1; }
  # od=6 >= XL.od_threshold=6, so tshirt is XL (not L)
  [[ "$out" == *'"tshirt": "XL"'* ]]         || { echo "    tshirt should be XL (od=6>=XL.od=6): $out"; return 1; }
  [[ "$out" == *'"sessions": 3'* ]]    || { echo "    chain_sessions should be 3: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 3: Missing ledger on predecessor — degrade gracefully
# ---------------------------------------------------------------------------

test_missing_ledger_degrades() {
  # h2 has a ledger; h1 (root) has NO ledger (pre-Phase-2 legacy handoff)
  local h1="${HANDOFFS}/legacy-root.md"
  local h2="${HANDOFFS}/legacy-terminal.md"

  # Write root without any ledger block
  cat > "$h1" <<'EOF'
---
title: "Legacy root handoff"
created: 2026-04-20
status: consumed
kind: session-handoff
predecessor: null
---

# Legacy Handoff

No Session Ledger here — this is a pre-Phase-2 handoff.
EOF

  write_handoff "legacy-terminal.md" "legacy-root.md" "2026-05-10" \
    "session_id=SID-LEGACY-T agent_dispatches=8 opus_dispatches=1 em_tokens=120000 commits=ddd0001"

  out=$(bash "$AGG" --terminal-handoff "$h2" --format json 2>/dev/null)

  # Should include the terminal's counts and degrade gracefully on the legacy root
  [[ "$out" == *'"agent_dispatches": 8'* ]]           || { echo "    agent_dispatches should be 8: $out"; return 1; }
  [[ "$out" == *'"sessions": 2'* ]]             || { echo "    chain_sessions should be 2: $out"; return 1; }
  # chain_sessions_with_ledger should reflect 1 of 2
  [[ "$out" == *'"chain_sessions_with_ledger": "1 of 2"'* ]] || { echo "    chain_sessions_with_ledger should be 1 of 2: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 4: Multi-ledger handoff — N blocks in one file, all contribute
# ---------------------------------------------------------------------------

test_multi_ledger_handoff() {
  # h1 has TWO Session Ledger blocks (re-pickup scenario)
  local h1="${HANDOFFS}/multi-ledger-terminal.md"

  write_handoff "multi-ledger-terminal.md" "null" "2026-05-05" \
    "session_id=SID-ML-FIRST agent_dispatches=10 opus_dispatches=2 em_tokens=200000 commits=e001" \
    "session_id=SID-ML-SECOND agent_dispatches=5 opus_dispatches=1 em_tokens=100000 commits=e002"

  out=$(bash "$AGG" --terminal-handoff "$h1" --format json 2>/dev/null)

  # Both ledger blocks should contribute: ad=15, od=3, tok=300000
  [[ "$out" == *'"agent_dispatches": 15'* ]] || { echo "    agent_dispatches should be 15 (both ledgers): $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 3'* ]]   || { echo "    opus_dispatches should be 3: $out"; return 1; }
  [[ "$out" == *'"em_tokens": 300000'* ]]    || { echo "    em_tokens should be 300000: $out"; return 1; }
  [[ "$out" == *'"sessions": 1'* ]]    || { echo "    chain_sessions should be 1: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 5: Same session_id across two handoffs — deduplication
# ---------------------------------------------------------------------------

test_session_id_dedup() {
  # h2 predecessor is h1; BOTH have a ledger block with the SAME session_id.
  # Scenario: session wrote h1 (mid-session save), then resumed and wrote h2.
  # Only one copy of that session's ledger should count.
  local h1="${HANDOFFS}/dedup-root.md"
  local h2="${HANDOFFS}/dedup-terminal.md"

  write_handoff "dedup-root.md" "null" "2026-05-08" \
    "session_id=SID-DEDUP agent_dispatches=12 opus_dispatches=2 em_tokens=200000 commits=f001"

  write_handoff "dedup-terminal.md" "dedup-root.md" "2026-05-08" \
    "session_id=SID-DEDUP agent_dispatches=12 opus_dispatches=2 em_tokens=200000 commits=f001"

  out=$(bash "$AGG" --terminal-handoff "$h2" --format json 2>/dev/null)

  # Only one copy of SID-DEDUP should be counted — NOT double-counted.
  [[ "$out" == *'"agent_dispatches": 12'* ]] || { echo "    agent_dispatches should be 12 (deduped, not 24): $out"; return 1; }
  [[ "$out" == *'"sessions": 2'* ]]    || { echo "    chain_sessions should be 2 (2 handoffs walked): $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 6: Missing-predecessor terminates walk with annotation
# ---------------------------------------------------------------------------

test_missing_predecessor_annotation() {
  local h1="${HANDOFFS}/missing-pred-terminal.md"

  write_handoff "missing-pred-terminal.md" "tasks/handoffs/nonexistent-handoff-ZZZZZ.md" "2026-05-11" \
    "session_id=SID-MP agent_dispatches=7 opus_dispatches=1 em_tokens=130000 commits=g001"

  out=$(bash "$AGG" --terminal-handoff "$h1" --format json 2>/dev/null)

  [[ "$out" == *'"chain_walk_terminated_early": "missing-link"'* ]] || {
    echo "    should have chain_walk_terminated_early: missing-link: $out"; return 1
  }
  # Should still output the partial aggregate from h1
  [[ "$out" == *'"agent_dispatches": 7'* ]] || { echo "    partial aggregate agent_dispatches should be 7: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 7: Cycle detection — terminates with annotation
# ---------------------------------------------------------------------------

test_cycle_detection() {
  # Create a cycle: h_a -> h_b -> h_a (cycle!)
  # Both files must reference each other by absolute path. Write h_a first with a
  # placeholder predecessor path, then write h_b pointing to h_a, then rewrite h_a
  # pointing back to h_b using the actual absolute path.
  local h_a="${HANDOFFS}/cycle-a.md"
  local h_b="${HANDOFFS}/cycle-b.md"

  # Step 1: write h_b pointing to h_a (h_a will exist by run time since we create it first)
  # Step 2: write h_a pointing to h_b (absolute path)
  # Since write_handoff resolves predecessors against already-existing files only,
  # build the cycle manually to guarantee absolute paths.

  cat > "$h_b" <<EOFRONT
---
title: "Cycle test handoff B"
created: 2026-05-12
branch: work/test/2026-05-12
status: consumed
kind: session-handoff
predecessor: ${h_a}
---

## Session Ledger

| Field | Value |
|-------|-------|
| agent_dispatches | 5 |
| opus_dispatches | 0 |
| em_tokens | 50000 |
| commits | h002 |
| session_id | SID-CYCLE-B |
| created | 2026-05-12T12:00:00Z |
EOFRONT

  cat > "$h_a" <<EOFRONT
---
title: "Cycle test handoff A"
created: 2026-05-12
branch: work/test/2026-05-12
status: consumed
kind: session-handoff
predecessor: ${h_b}
---

## Session Ledger

| Field | Value |
|-------|-------|
| agent_dispatches | 5 |
| opus_dispatches | 0 |
| em_tokens | 50000 |
| commits | h001 |
| session_id | SID-CYCLE-A |
| created | 2026-05-12T12:00:00Z |
EOFRONT

  # Start from h_b: walk is h_b -> h_a -> h_b (cycle detected at h_b revisit)
  out=$(bash "$AGG" --terminal-handoff "$h_b" --format json 2>/dev/null)

  [[ "$out" == *'"chain_walk_terminated_early": "cycle-detected"'* ]] || {
    echo "    should have chain_walk_terminated_early: cycle-detected: $out"; return 1
  }
  # Partial aggregate should include both h_b and h_a (2 unique handoffs before cycle)
  [[ "$out" == *'"sessions": 2'* ]] || { echo "    chain_sessions should be 2 (before cycle): $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 8: Archived predecessor — chain walk traverses archive directory
# ---------------------------------------------------------------------------

test_archived_predecessor() {
  # h1 lives in archive; h2 (terminal) in tasks/handoffs/ and references h1 by absolute path.
  # This simulates the real-world scenario where a predecessor has been archived and is
  # referenced via the absolute path that resolve_handoff_path will match on its first check.
  local h1="${ARCHIVE}/archived-root.md"
  local h2="${HANDOFFS}/archive-terminal.md"

  # Write h1 to archive first (so it exists when h2 is written)
  write_handoff "$h1" "null" "2026-05-02" \
    "session_id=SID-ARCH agent_dispatches=18 opus_dispatches=3 em_tokens=350000 commits=i001"

  # h2's predecessor is the absolute path to h1 in the archive.
  # write_handoff resolves this automatically via the resolved_pred logic.
  write_handoff "archive-terminal.md" "${ARCHIVE}/archived-root.md" "2026-05-14" \
    "session_id=SID-ARCH-T agent_dispatches=22 opus_dispatches=4 em_tokens=500000 commits=i002"

  out=$(bash "$AGG" --terminal-handoff "$h2" --format json 2>/dev/null)

  [[ "$out" == *'"agent_dispatches": 40'* ]] || { echo "    agent_dispatches should be 40 (18+22): $out"; return 1; }
  [[ "$out" == *'"sessions": 2'* ]]    || { echo "    chain_sessions should be 2: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 9: YAML frontmatter output shape
# ---------------------------------------------------------------------------

test_yaml_frontmatter_output() {
  local h1="${HANDOFFS}/yaml-shape-test.md"
  write_handoff "yaml-shape-test.md" "null" "2026-05-15" \
    "session_id=SID-YAML agent_dispatches=35 opus_dispatches=5 em_tokens=700000 commits=j001,j002"

  out=$(bash "$AGG" --terminal-handoff "$h1" --format yaml-frontmatter 2>/dev/null)

  [[ "$out" == *'loe:'* ]]                          || { echo "    missing loe: key: $out"; return 1; }
  [[ "$out" == *'agent_dispatches: 35'* ]]          || { echo "    agent_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'opus_dispatches: 5'* ]]            || { echo "    opus_dispatches wrong: $out"; return 1; }
  [[ "$out" == *'em_tokens: 700000'* ]]             || { echo "    em_tokens wrong: $out"; return 1; }
  [[ "$out" == *'tshirt: "L"'* ]]                   || { echo "    tshirt should be L (35>=30): $out"; return 1; }
  [[ "$out" == *'sessions: 1'* ]]             || { echo "    chain_sessions should be 1: $out"; return 1; }
  [[ "$out" == *'chain_sessions_with_ledger:'* ]]   || { echo "    missing chain_sessions_with_ledger: $out"; return 1; }
  [[ "$out" == *'chain_starting_handoff:'* ]]       || { echo "    missing chain_starting_handoff: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 10: Concurrency declarations present in script header
# ---------------------------------------------------------------------------

test_concurrency_declarations_present() {
  local script="${SCRIPT_DIR}/../aggregate-chain-loe.sh"
  # Verify the mandatory header comment block contains the three required declarations.
  grep -q "Concurrency posture" "$script"  || { echo "    missing Concurrency posture declaration"; return 1; }
  grep -q "Idempotency posture" "$script"  || { echo "    missing Idempotency posture declaration"; return 1; }
  grep -q "Resume strategy"    "$script"  || { echo "    missing Resume strategy declaration"; return 1; }
}

# ---------------------------------------------------------------------------
# Test 11: Multi-ledger + cross-handoff same session_id combined case (the Staff Engineer F5)
# Chain has 2 handoffs; h1 has 2 ledger blocks (SID-A, SID-B);
# h2 (terminal) also has SID-A again (same session touched both).
# Result: SID-A counted once, SID-B counted once.
# ---------------------------------------------------------------------------

test_multi_ledger_with_cross_handoff_dedup() {
  local h1="${HANDOFFS}/multi-cross-root.md"
  local h2="${HANDOFFS}/multi-cross-terminal.md"

  # h1 has two ledger blocks: SID-A (10 ad) and SID-B (8 ad)
  write_handoff "multi-cross-root.md" "null" "2026-05-16" \
    "session_id=SID-CROSS-A agent_dispatches=10 opus_dispatches=1 em_tokens=150000 commits=k001" \
    "session_id=SID-CROSS-B agent_dispatches=8 opus_dispatches=1 em_tokens=100000 commits=k002"

  # h2 terminal also has a SID-CROSS-A ledger (same session, re-handoff scenario)
  write_handoff "multi-cross-terminal.md" "multi-cross-root.md" "2026-05-17" \
    "session_id=SID-CROSS-A agent_dispatches=10 opus_dispatches=1 em_tokens=150000 commits=k001"

  out=$(bash "$AGG" --terminal-handoff "$h2" --format json 2>/dev/null)

  # SID-CROSS-A counted once (10 ad), SID-CROSS-B counted once (8 ad).
  # Total: 18 ad, NOT 28.
  [[ "$out" == *'"agent_dispatches": 18'* ]] || { echo "    agent_dispatches should be 18 (dedup: A+B not A+A+B): $out"; return 1; }
  [[ "$out" == *'"opus_dispatches": 2'* ]]   || { echo "    opus_dispatches should be 2: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

echo "=== aggregate-chain-loe.sh smoke tests ==="
echo ""

run_test "1-session chain returns single-session LoE"             test_single_session_chain
run_test "3-session chain sums all ledger blocks"                 test_three_session_chain
run_test "missing ledger on predecessor degrades gracefully"       test_missing_ledger_degrades
run_test "multi-ledger handoff: N blocks all contribute"          test_multi_ledger_handoff
run_test "same session_id across handoffs is deduplicated"        test_session_id_dedup
run_test "missing predecessor terminates with missing-link"        test_missing_predecessor_annotation
run_test "cycle in chain terminates with cycle-detected"          test_cycle_detection
run_test "archived predecessor is traversed correctly"             test_archived_predecessor
run_test "yaml-frontmatter output shape is complete"              test_yaml_frontmatter_output
run_test "concurrency+idempotency+resume declarations present"    test_concurrency_declarations_present
run_test "multi-ledger + cross-handoff dedup (the Staff Engineer F5)"         test_multi_ledger_with_cross_handoff_dedup

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
if [[ "${#FAIL_MSGS[@]}" -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi
exit 0
