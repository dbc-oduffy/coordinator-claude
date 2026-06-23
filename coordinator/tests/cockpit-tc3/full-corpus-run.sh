#!/usr/bin/env bash
# full-corpus-run.sh — AC9: emitter runs clean against the full current archive
# (live + archived handoffs, all backlog types, full review-trail union);
# malformed_records reported but non-fatal; at least one record in each main array.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § AC9
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CLAUDE_HOME:-$HOME}/.claude"
VALIDATE="$COORDINATOR_ROOT/bin/lib/validate-cockpit-record.mjs"

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
# AC9a: emitter runs clean against the full corpus
# C-F7: use mktemp instead of hardcoded /tmp path to avoid parallel-run races.
# ---------------------------------------------------------------------------
EMISSION="$ROOT/state/cockpit-emission.json"
EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-emit-stderr.XXXXXX")"
echo "[full-corpus-run] running emitter against full corpus..." >&2
if bash "$COORDINATOR_ROOT/bin/emit-cockpit-snapshot.sh" 2>"$EMIT_STDERR"; then
  EMIT_OK="true"
  echo "PASS: emitter exited 0"
  PASS=$((PASS + 1))
else
  EMIT_OK="false"
  echo "FAIL: emitter exited non-zero"
  echo "stderr:"
  cat "$EMIT_STDERR" >&2
  FAIL=$((FAIL + 1))
fi
rm -f "$EMIT_STDERR"

if [[ "$EMIT_OK" != "true" ]]; then
  echo "Cannot proceed with further checks — emitter failed"
  exit 1
fi

# ---------------------------------------------------------------------------
# AC9b: output is valid JSON
# ---------------------------------------------------------------------------
if jq . "$EMISSION" > /dev/null 2>&1; then
  echo "PASS: cockpit-emission.json is valid JSON"
  PASS=$((PASS + 1))
else
  echo "FAIL: cockpit-emission.json is not valid JSON"
  FAIL=$((FAIL + 1))
  exit 1
fi

# ---------------------------------------------------------------------------
# AC9c: schema_version == "0.1.0"
# ---------------------------------------------------------------------------
SCHEMA_VER="$(jq -r '.schema_version' "$EMISSION")"
check "schema_version == 0.1.0" "$([ "$SCHEMA_VER" = "0.1.0" ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC9d: at least one record in each main array
# ---------------------------------------------------------------------------
HANDOFF_COUNT="$(jq '.handoffs | length' "$EMISSION")"
check "at least 1 handoff" "$([ "$HANDOFF_COUNT" -gt 0 ] && echo true || echo false)"

BACKLOG_BUG="$(jq '.backlogs.bug | length' "$EMISSION")"
BACKLOG_DEBT="$(jq '.backlogs.debt | length' "$EMISSION")"
BACKLOG_IMPROV="$(jq '.backlogs.improvement | length' "$EMISSION")"
BACKLOG_TOTAL="$(echo "$BACKLOG_BUG $BACKLOG_DEBT $BACKLOG_IMPROV" | awk '{print $1+$2+$3}')"
check "at least 1 backlog item" "$([ "$BACKLOG_TOTAL" -gt 0 ] && echo true || echo false)"

RT_COUNT="$(jq '.review_trail | length' "$EMISSION")"
check "at least 1 review_trail record" "$([ "$RT_COUNT" -gt 0 ] && echo true || echo false)"

RS_COUNT="$(jq '.routine_signals | length' "$EMISSION")"
check "at least 1 routine_signal" "$([ "$RS_COUNT" -gt 0 ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC9e: malformed_records structure present but non-fatal (emitter completed).
# C-F11: AC is "structure exists", NOT "has content" — a clean corpus would
# have an empty object and the old `keys | length > 0` check would fail.
# Assert type==object (structure present) and log the count as INFO.
# ---------------------------------------------------------------------------
check "malformed_records structure present (type==object)" \
  "$(jq '.malformed_records | type == "object"' "$EMISSION")"
MALFORMED_TOTAL="$(jq '
  .malformed_records |
  to_entries |
  map(.value | length) |
  add // 0
' "$EMISSION")"
echo "INFO: malformed_records total=$MALFORMED_TOTAL (non-fatal, expected from legacy data)"

# ---------------------------------------------------------------------------
# AC9f: every handoff in main array validates against schema
# C-F1: guard loop with [[ count > 0 ]] — on BSD, seq 0 $((0-1)) emits
# "0\n-1" causing phantom iterations that mask an empty array.
# ---------------------------------------------------------------------------
echo "[full-corpus-run] validating all handoff records..." >&2
HANDOFF_FAILURES=0
if [[ "$HANDOFF_COUNT" -gt 0 ]]; then
  for i in $(seq 0 $((HANDOFF_COUNT - 1))); do
    REC="$(jq -c ".handoffs[$i]" "$EMISSION")"
    TMP="$(mktemp "${TMPDIR:-/tmp}/cockpit-val-XXXXXX.json")"
    echo "$REC" > "$TMP"
    if ! node "$VALIDATE" handoff-summary "$TMP" >/dev/null 2>&1; then
      echo "  FAIL: handoffs[$i] failed validation"
      HANDOFF_FAILURES=$((HANDOFF_FAILURES + 1))
    fi
    rm -f "$TMP"
  done
else
  echo "  INFO: handoffs array is empty — validation trivially passes"
fi
check "all $HANDOFF_COUNT handoffs validate" "$([ "$HANDOFF_FAILURES" -eq 0 ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC9g: every review_trail record validates against schema
# C-F1: same BSD seq guard as AC9f above.
# ---------------------------------------------------------------------------
echo "[full-corpus-run] validating all review-trail records..." >&2
RT_FAILURES=0
if [[ "$RT_COUNT" -gt 0 ]]; then
  for i in $(seq 0 $((RT_COUNT - 1))); do
    REC="$(jq -c ".review_trail[$i]" "$EMISSION")"
    TMP="$(mktemp "${TMPDIR:-/tmp}/cockpit-val-XXXXXX.json")"
    echo "$REC" > "$TMP"
    if ! node "$VALIDATE" review-trail "$TMP" >/dev/null 2>&1; then
      echo "  FAIL: review_trail[$i] failed validation"
      RT_FAILURES=$((RT_FAILURES + 1))
    fi
    rm -f "$TMP"
  done
else
  echo "  INFO: review_trail array is empty — validation trivially passes"
fi
check "all $RT_COUNT review_trail records validate" "$([ "$RT_FAILURES" -eq 0 ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC9h: handoffs cover both live and archived (combined count > live-only)
# ---------------------------------------------------------------------------
LIVE_HANDOFF_COUNT="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type handoff --format json 2>/dev/null | jq 'length')"
ARCH_HANDOFF_COUNT="$(node "$COORDINATOR_ROOT/bin/query-records.js" --type handoff-archived --format json 2>/dev/null | jq 'length')"
EXPECTED_MAX="$(( LIVE_HANDOFF_COUNT + ARCH_HANDOFF_COUNT ))"
# Pass if emitted > live-only count OR if there are no archived handoffs at all
if [[ "$HANDOFF_COUNT" -gt "$LIVE_HANDOFF_COUNT" ]] || [[ "$ARCH_HANDOFF_COUNT" -eq 0 ]]; then
  _ARCH_COND="true"
else
  _ARCH_COND="false"
fi
check "handoffs include archived (emitted=$HANDOFF_COUNT, max_possible=$EXPECTED_MAX, live=$LIVE_HANDOFF_COUNT, archived=$ARCH_HANDOFF_COUNT)" \
  "$_ARCH_COND"

# ---------------------------------------------------------------------------
# AC9i: review_trail covers archived records (not live-only)
# C-F10: the assertion `RT_COUNT > LIVE_RT_COUNT` is only valid when an
# archive directory exists and is non-empty. When there are no archived
# review-trail records, we can only assert RT_COUNT >= LIVE_RT_COUNT.
# ---------------------------------------------------------------------------
LIVE_RT_COUNT="$(find "$ROOT/state/review-trail" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
ARCH_RT_COUNT="$(find "$ROOT/archive/review-trail" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$ARCH_RT_COUNT" -gt 0 ]]; then
  check "review_trail count ($RT_COUNT) > live-only count ($LIVE_RT_COUNT) — archive non-empty ($ARCH_RT_COUNT archived)" \
    "$([ "$RT_COUNT" -gt "$LIVE_RT_COUNT" ] && echo true || echo false)"
else
  # No archive exists or is empty — can only assert emitter didn't drop live records.
  check "review_trail count ($RT_COUNT) >= live-only count ($LIVE_RT_COUNT) — no archive to cover" \
    "$([ "$RT_COUNT" -ge "$LIVE_RT_COUNT" ] && echo true || echo false)"
  echo "  INFO: archive/review-trail/ is absent or empty — strict > assertion skipped"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "---"
echo "Emission: handoffs=$HANDOFF_COUNT backlogs=$BACKLOG_TOTAL review_trail=$RT_COUNT routine_signals=$RS_COUNT"
echo "Malformed (non-fatal): $MALFORMED_TOTAL"
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
