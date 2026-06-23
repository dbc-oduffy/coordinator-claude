#!/usr/bin/env bash
# provenance.sh — AC6: every record in every main array carries a valid provenance
# envelope with all 6 required keys: source_kind, repo, ref, path, observed_at, derivation.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § AC6
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CLAUDE_HOME:-$HOME}/.claude"
EMISSION="$ROOT/state/cockpit-emission.json"

# Always re-run the emitter so we test fresh output deterministically
# regardless of run order (C-F4: stale-emission fix).
EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-emit-stderr.XXXXXX")"
if ! bash "$COORDINATOR_ROOT/bin/emit-cockpit-snapshot.sh" 2>"$EMIT_STDERR"; then
  echo "[provenance] FAIL: emitter exited non-zero" >&2
  cat "$EMIT_STDERR" >&2
  rm -f "$EMIT_STDERR"
  exit 1
fi
rm -f "$EMIT_STDERR"

PASS=0
FAIL=0
SKIP=0
TOTAL_CHECKED=0

# ---------------------------------------------------------------------------
# Helper: check provenance on all records in a jq path (returns array)
# Args: label jq-expression
# ---------------------------------------------------------------------------
check_provenance_array() {
  local label="$1"
  local jq_expr="$2"
  local records
  records="$(jq -c "$jq_expr // []" "$EMISSION")"
  local count
  count="$(echo "$records" | jq 'length')"
  local invalid=0
  local i
  for i in $(seq 0 $((count - 1))); do
    [[ "$count" -eq 0 ]] && break
    local rec prov
    rec="$(echo "$records" | jq -c ".[$i]")"
    prov="$(echo "$rec" | jq -c '.provenance // empty')"
    if [[ -z "$prov" ]]; then
      echo "  FAIL: $label[$i] — provenance absent"
      invalid=$((invalid + 1))
      continue
    fi
    # Check all 6 required keys
    local checks
    checks="$(echo "$prov" | jq '
      [
        (.source_kind | type == "string"),
        (.repo | type == "string"),
        (.ref | type == "object" and .branch != null and .sha != null),
        (.path | type == "string"),
        (.observed_at | type == "string"),
        (.derivation | type == "string")
      ] | all
    ')"
    if [[ "$checks" != "true" ]]; then
      echo "  FAIL: $label[$i] — provenance missing required field"
      echo "    provenance: $prov"
      invalid=$((invalid + 1))
    fi
    TOTAL_CHECKED=$((TOTAL_CHECKED + 1))
  done
  if [[ "$invalid" -eq 0 ]]; then
    echo "PASS: $label ($count records all have valid provenance)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $label — $invalid/$count records have invalid provenance"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# Check all main arrays
# ---------------------------------------------------------------------------
check_provenance_array "handoffs" '.handoffs'
check_provenance_array "backlogs.bug" '.backlogs.bug'
check_provenance_array "backlogs.debt" '.backlogs.debt'
check_provenance_array "backlogs.improvement" '.backlogs.improvement'
check_provenance_array "review_trail" '.review_trail'
check_provenance_array "routine_signals" '.routine_signals'
check_provenance_array "goals_current" '.goals_current'

# ---------------------------------------------------------------------------
# Check singleton records (coordinator_root, branch)
# ---------------------------------------------------------------------------
check_singleton_provenance() {
  local label="$1"
  local jq_expr="$2"
  local rec prov
  rec="$(jq -c "$jq_expr // empty" "$EMISSION")"
  if [[ -z "$rec" || "$rec" == "null" ]]; then
    # C-F3: do NOT bump PASS on a data-dependent SKIP — use SKIP counter so
    # summary count reflects only genuine assertions.
    SKIP=$((SKIP + 1))
    echo "SKIP: $label — not present in emission (likely in malformed_records) — not counted as PASS"
    return
  fi
  prov="$(echo "$rec" | jq -c '.provenance // empty')"
  if [[ -z "$prov" ]]; then
    echo "FAIL: $label — provenance absent"
    FAIL=$((FAIL + 1))
    return
  fi
  local checks
  checks="$(echo "$prov" | jq '
    [
      (.source_kind | type == "string"),
      (.repo | type == "string"),
      (.ref | type == "object" and .branch != null and .sha != null),
      (.path | type == "string"),
      (.observed_at | type == "string"),
      (.derivation | type == "string")
    ] | all
  ')"
  if [[ "$checks" == "true" ]]; then
    echo "PASS: $label — valid provenance"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $label — provenance missing required field; got: $prov"
    FAIL=$((FAIL + 1))
  fi
  TOTAL_CHECKED=$((TOTAL_CHECKED + 1))
}

check_singleton_provenance "coordinator_root" '.coordinator_root'
check_singleton_provenance "branch" '.branch'

# ---------------------------------------------------------------------------
# Check derivation values are valid enum members
# ---------------------------------------------------------------------------
# C-F8: removed 2>/dev/null (was swallowing jq errors); extended head to 50
# so violation diagnostics aren't silently truncated.
INVALID_DERIVATIONS="$(jq -r '
  [
    .handoffs,
    .backlogs.bug, .backlogs.debt, .backlogs.improvement,
    .review_trail,
    .routine_signals,
    .goals_current
  ] |
  flatten |
  map(.provenance.derivation) |
  map(select(. != "raw" and . != "parsed" and . != "rolled_up")) |
  .[]
' "$EMISSION" | head -50)"

if [[ -z "$INVALID_DERIVATIONS" ]]; then
  echo "PASS: all derivation values are valid enum members (raw|parsed|rolled_up)"
  PASS=$((PASS + 1))
else
  echo "FAIL: invalid derivation values found:"
  echo "$INVALID_DERIVATIONS"
  FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "---"
echo "Total records with provenance checked: $TOTAL_CHECKED"
echo "Results: $PASS passed, $FAIL failed, $SKIP skipped (data-dependent, not counted as pass)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
