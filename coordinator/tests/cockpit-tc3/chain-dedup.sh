#!/usr/bin/env bash
# chain-dedup.sh — AC4: verify completion rollup deduplicates on chain grain;
# no chain double-counted; null chains treated as distinct atoms.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § AC4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CLAUDE_HOME:-$HOME}/.claude"
EMISSION="$ROOT/state/cockpit-emission.json"

# Always re-run the emitter so we test fresh output deterministically
# regardless of run order (C-F4: stale-emission fix).
EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-emit-stderr.XXXXXX")"
if ! bash "$COORDINATOR_ROOT/bin/emit-cockpit-snapshot.sh" 2>"$EMIT_STDERR"; then
  echo "[chain-dedup] FAIL: emitter exited non-zero" >&2
  cat "$EMIT_STDERR" >&2
  rm -f "$EMIT_STDERR"
  exit 1
fi
rm -f "$EMIT_STDERR"

PASS=0
FAIL=0

check() {
  local label="$1"
  local condition="$2"
  if [[ "$condition" == "true" ]]; then
    echo "PASS: $label"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $label"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# AC4a: completion_rollup.week and .day exist with deterministic_facts
# ---------------------------------------------------------------------------
WEEK_CHAINS="$(jq '.completion_rollup.week.deterministic_facts.chains_completed' "$EMISSION")"
DAY_CHAINS="$(jq '.completion_rollup.day.deterministic_facts.chains_completed' "$EMISSION")"
check "completion_rollup.week.deterministic_facts.chains_completed is integer" \
  "$(echo "$WEEK_CHAINS" | jq 'type == "number"')"
check "completion_rollup.day.deterministic_facts.chains_completed is integer" \
  "$(echo "$DAY_CHAINS" | jq 'type == "number"')"

# ---------------------------------------------------------------------------
# AC4b: chains_completed count matches independent count from source data
# ---------------------------------------------------------------------------
# Count from source: query completions --since 30d, group by chain, distinct
# C-F9: do NOT swallow errors; assert non-empty valid JSON afterwards.
SOURCE_CHAINS="$(bash "$COORDINATOR_ROOT/bin/query-completions.sh" --since 30d --format json 2>&1)"
if ! echo "$SOURCE_CHAINS" | jq . >/dev/null 2>&1; then
  echo "FAIL: query-completions.sh returned non-JSON or empty (check script exists and path is correct)"
  echo "  output: $SOURCE_CHAINS"
  exit 1
fi

# Named chains (non-null): unique count
NAMED_UNIQUE="$(echo "$SOURCE_CHAINS" | jq '
  [.[].frontmatter.chain | select(. != null)] | unique | length
')"
# Null chains: count of entries with null chain (each is a distinct atom)
NULL_COUNT="$(echo "$SOURCE_CHAINS" | jq '
  [.[].frontmatter.chain | select(. == null)] | length
')"
EXPECTED_TOTAL="$(echo "$NAMED_UNIQUE $NULL_COUNT" | awk '{print $1 + $2}')"

check "week chains_completed == named_unique + null_count ($EXPECTED_TOTAL)" \
  "$([ "$WEEK_CHAINS" -eq "$EXPECTED_TOTAL" ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC4c: emitter collapsed duplicate chain names — NOT the tautological
# "unique <= total" check (always true by definition; zero regression value).
# Real assertion: emitter's chains_completed equals NAMED_UNIQUE+NULL_COUNT.
# If the source has duplicate chain names (named_unique < raw entries with
# non-null chains), this assertion fails on a non-deduping emitter.
# C-F2: replaced tautology with binding dedup invariant.
# ---------------------------------------------------------------------------
TOTAL_WITH_CHAINS="$(echo "$SOURCE_CHAINS" | jq '[.[].frontmatter.chain | select(. != null)] | length')"
# Sanity note (not an AC): named_unique should be <= total_with_chains by math.
# If equal, source has no duplicates; if less, emitter must have deduped.
check "emitter deduped named chains: week chains_completed == named_unique($NAMED_UNIQUE) + null_count($NULL_COUNT) = $EXPECTED_TOTAL" \
  "$([ "$WEEK_CHAINS" -eq "$EXPECTED_TOTAL" ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC4d: if there are any null chains, chains_completed is > named_unique
#        (null chains counted distinctly, not collapsed)
# ---------------------------------------------------------------------------
if [[ "$NULL_COUNT" -gt 0 ]]; then
  check "null chains distinct: week chains($WEEK_CHAINS) > named_unique($NAMED_UNIQUE) when null_count=$NULL_COUNT" \
    "$([ "$WEEK_CHAINS" -gt "$NAMED_UNIQUE" ] && echo true || echo false)"
else
  # C-F3: do NOT bump PASS on a data-dependent SKIP — track separately so
  # the summary count reflects only genuine assertions.
  SKIP=$((${SKIP:-0} + 1))
  echo "SKIP: no null chains in current corpus (null_count=0) — not counted as PASS"
fi

# ---------------------------------------------------------------------------
# AC4e: chains_completed is non-negative
# ---------------------------------------------------------------------------
check "week chains_completed >= 0" \
  "$(echo "$WEEK_CHAINS" | jq '. >= 0')"
check "day chains_completed >= 0" \
  "$(echo "$DAY_CHAINS" | jq '. >= 0')"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "---"
echo "Chain counts: named_unique=$NAMED_UNIQUE null_count=$NULL_COUNT total=$EXPECTED_TOTAL week_emitted=$WEEK_CHAINS"
echo "Results: $PASS passed, $FAIL failed, ${SKIP:-0} skipped (data-dependent, not counted as pass)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
