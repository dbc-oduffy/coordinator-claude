#!/usr/bin/env bash
# routine-signals.sh — AC3: verify routine_signals contains all 6 kinds, each
# validating as a routine-signal per the contract schema, with required fields present.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § AC3
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CLAUDE_HOME:-$HOME}/.claude"
EMISSION="$ROOT/state/cockpit-emission.json"
VALIDATE="$COORDINATOR_ROOT/bin/lib/validate-cockpit-record.mjs"

# ---------------------------------------------------------------------------
# Always re-run the emitter so we test fresh output deterministically
# regardless of run order (C-F4: stale-emission fix).
# Capture stderr to a temp file and fail loud on non-zero exit.
# ---------------------------------------------------------------------------
EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-emit-stderr.XXXXXX")"
if ! bash "$COORDINATOR_ROOT/bin/emit-cockpit-snapshot.sh" 2>"$EMIT_STDERR"; then
  echo "[routine-signals] FAIL: emitter exited non-zero" >&2
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
# AC3a: routine_signals array has exactly 6 entries
# ---------------------------------------------------------------------------
RS_COUNT="$(jq '.routine_signals | length' "$EMISSION")"
check "routine_signals count == 6" "$([ "$RS_COUNT" -eq 6 ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC3b: all 6 required kinds present
# ---------------------------------------------------------------------------
KINDS="$(jq -r '[.routine_signals[].kind] | sort | join(",")' "$EMISSION")"
EXPECTED_KINDS="arch-audit,bug-sweep,distill-backlog,docs,dormant-repo,weekly"
check "all 6 kinds present" "$([ "$KINDS" = "$EXPECTED_KINDS" ] && echo true || echo false)"

# ---------------------------------------------------------------------------
# AC3c: distill-backlog record validates against schema and has required fields
# ---------------------------------------------------------------------------
DISTILL_RECORD="$(jq '.routine_signals[] | select(.kind == "distill-backlog")' "$EMISSION")"
DISTILL_TMP="$(mktemp /tmp/cockpit-distill-XXXXXX.json)"
echo "$DISTILL_RECORD" > "$DISTILL_TMP"
DISTILL_VALID="$(node "$VALIDATE" routine-signal "$DISTILL_TMP" >/dev/null 2>&1 && echo true || echo false)"
rm -f "$DISTILL_TMP"
check "distill-backlog validates as routine-signal" "$DISTILL_VALID"

# AC3c: required fields present on distill-backlog
DISTILL_KIND="$(echo "$DISTILL_RECORD" | jq -r '.kind')"
check "distill-backlog.kind == distill-backlog" "$([ "$DISTILL_KIND" = "distill-backlog" ] && echo true || echo false)"

DISTILL_PENDING="$(echo "$DISTILL_RECORD" | jq '.inputs.pending_count')"
check "distill-backlog.inputs.pending_count is integer" "$(echo "$DISTILL_PENDING" | jq 'type == "number"')"

DISTILL_STATE="$(echo "$DISTILL_RECORD" | jq -r '.computed_state')"
check "distill-backlog.computed_state in {fresh,mild,stale,unknown}" \
  "$(echo '["fresh","mild","stale","unknown"]' | jq --arg s "$DISTILL_STATE" 'map(. == $s) | any')"

check "distill-backlog.overdue present (boolean)" \
  "$(echo "$DISTILL_RECORD" | jq '.overdue | type == "boolean"')"

check "distill-backlog.observed_at present" \
  "$(echo "$DISTILL_RECORD" | jq '.observed_at | type == "string"')"

check "distill-backlog.computed_as_of present" \
  "$(echo "$DISTILL_RECORD" | jq '.computed_as_of | type == "string"')"

check "distill-backlog.threshold present" \
  "$(echo "$DISTILL_RECORD" | jq '.threshold | type == "string"')"

check "distill-backlog.provenance present" \
  "$(echo "$DISTILL_RECORD" | jq '.provenance | type == "object"')"

# ---------------------------------------------------------------------------
# AC3d: all RS_COUNT routine-signal records validate against the schema
# (C-F5: loop uses actual count, not hardcoded 6, guarded against 0-length)
# ---------------------------------------------------------------------------
ALL_VALID="true"
if [[ "$RS_COUNT" -gt 0 ]]; then
for i in $(seq 0 $((RS_COUNT - 1))); do
  REC="$(jq -c ".routine_signals[$i]" "$EMISSION")"
  KIND="$(echo "$REC" | jq -r '.kind')"
  TMP="$(mktemp /tmp/cockpit-rs-XXXXXX.json)"
  echo "$REC" > "$TMP"
  if ! node "$VALIDATE" routine-signal "$TMP" >/dev/null 2>&1; then
    echo "  FAIL: routine-signal[$i] (kind=$KIND) failed schema validation"
    ALL_VALID="false"
  fi
  rm -f "$TMP"
done
fi  # end RS_COUNT > 0 guard
check "all $RS_COUNT routine-signal records pass schema validation" "$ALL_VALID"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "---"
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
