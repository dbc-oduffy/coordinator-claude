#!/usr/bin/env bash
# rollup-shape.sh — AC5: verify deterministic_facts present and authoritative;
# top-level freshness + input_watermark present on rollup records; narrative null-or-watermarked.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § AC5
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CLAUDE_HOME:-$HOME}/.claude"
EMISSION="$ROOT/state/cockpit-emission.json"
VALIDATE="$COORDINATOR_ROOT/bin/lib/validate-cockpit-record.mjs"

# Always re-run the emitter so we test fresh output deterministically
# regardless of run order (C-F4: stale-emission fix).
EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-emit-stderr.XXXXXX")"
if ! bash "$COORDINATOR_ROOT/bin/emit-cockpit-snapshot.sh" 2>"$EMIT_STDERR"; then
  echo "[rollup-shape] FAIL: emitter exited non-zero" >&2
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
# WeekRollup checks
# ---------------------------------------------------------------------------
WEEK="$(jq '.completion_rollup.week' "$EMISSION")"

# AC5a: grain, period, repo, coordinator_root_path present
check "week rollup: grain == 'week'" "$(echo "$WEEK" | jq '.grain == "week"')"
check "week rollup: period is string (ISO week)" "$(echo "$WEEK" | jq '.period | type == "string"')"
check "week rollup: repo is string" "$(echo "$WEEK" | jq '.repo | type == "string"')"
check "week rollup: coordinator_root_path is string" "$(echo "$WEEK" | jq '.coordinator_root_path | type == "string"')"

# AC5b: deterministic_facts present with all required sub-fields
check "week rollup: deterministic_facts present" "$(echo "$WEEK" | jq '.deterministic_facts | type == "object"')"
check "week rollup: deterministic_facts.chains_completed is integer" \
  "$(echo "$WEEK" | jq '.deterministic_facts.chains_completed | type == "number"')"
check "week rollup: deterministic_facts.tshirt_counts is object" \
  "$(echo "$WEEK" | jq '.deterministic_facts.tshirt_counts | type == "object"')"
check "week rollup: deterministic_facts.opus_dispatches is integer" \
  "$(echo "$WEEK" | jq '.deterministic_facts.opus_dispatches | type == "number"')"
check "week rollup: deterministic_facts.commits is integer" \
  "$(echo "$WEEK" | jq '.deterministic_facts.commits | type == "number"')"
# Week-only fields
check "week rollup: deterministic_facts.reviews_conducted is integer" \
  "$(echo "$WEEK" | jq '.deterministic_facts.reviews_conducted | type == "number"')"
check "week rollup: deterministic_facts.verdicts is object" \
  "$(echo "$WEEK" | jq '.deterministic_facts.verdicts | type == "object"')"

# AC5c: top-level freshness present and valid
# C-F6: replaced fragile `[ ] || [ ] && echo` (ambiguous precedence) with
# explicit if/else to make operator-precedence unambiguous.
WEEK_FRESHNESS="$(echo "$WEEK" | jq -r '.freshness')"
check "week rollup: freshness in {current, stale}" \
  "$(if [[ "$WEEK_FRESHNESS" = "current" || "$WEEK_FRESHNESS" = "stale" ]]; then echo true; else echo false; fi)"

# AC5d: top-level input_watermark present with all 3 required fields
check "week rollup: input_watermark.max_observed_at is string" \
  "$(echo "$WEEK" | jq '.input_watermark.max_observed_at | type == "string"')"
check "week rollup: input_watermark.max_commit_sha is string" \
  "$(echo "$WEEK" | jq '.input_watermark.max_commit_sha | type == "string"')"
check "week rollup: input_watermark.source_count is integer" \
  "$(echo "$WEEK" | jq '.input_watermark.source_count | type == "number"')"

# AC5e: narrative is null (v1) or object with input_watermark
WEEK_NARRATIVE="$(echo "$WEEK" | jq '.narrative')"
NARRATIVE_OK="$(echo "$WEEK_NARRATIVE" | jq '. == null or (type == "object" and .input_watermark != null)')"
check "week rollup: narrative is null or watermarked object" "$NARRATIVE_OK"

# AC5f: validate week rollup against schema
WEEK_TMP="$(mktemp /tmp/cockpit-week-XXXXXX.json)"
echo "$WEEK" > "$WEEK_TMP"
WEEK_VALID="$(node "$VALIDATE" week-rollup "$WEEK_TMP" >/dev/null 2>&1 && echo true || echo false)"
rm -f "$WEEK_TMP"
check "week rollup validates against schema" "$WEEK_VALID"

# ---------------------------------------------------------------------------
# DayRollup checks
# ---------------------------------------------------------------------------
DAY="$(jq '.completion_rollup.day' "$EMISSION")"

check "day rollup: grain in {chain, day}" \
  "$(echo "$DAY" | jq '[.grain == "chain", .grain == "day"] | any')"
check "day rollup: period is string (ISO date)" "$(echo "$DAY" | jq '.period | type == "string"')"
check "day rollup: deterministic_facts present" "$(echo "$DAY" | jq '.deterministic_facts | type == "object"')"
check "day rollup: deterministic_facts.chains_completed is integer" \
  "$(echo "$DAY" | jq '.deterministic_facts.chains_completed | type == "number"')"

# AC5c for day: top-level freshness present
# C-F6: same explicit if/else fix as week freshness check above.
DAY_FRESHNESS="$(echo "$DAY" | jq -r '.freshness')"
check "day rollup: freshness in {current, stale}" \
  "$(if [[ "$DAY_FRESHNESS" = "current" || "$DAY_FRESHNESS" = "stale" ]]; then echo true; else echo false; fi)"

# AC5d for day: input_watermark
check "day rollup: input_watermark.max_observed_at is string" \
  "$(echo "$DAY" | jq '.input_watermark.max_observed_at | type == "string"')"
check "day rollup: input_watermark.source_count is integer" \
  "$(echo "$DAY" | jq '.input_watermark.source_count | type == "number"')"

# Validate day rollup against schema
DAY_TMP="$(mktemp /tmp/cockpit-day-XXXXXX.json)"
echo "$DAY" > "$DAY_TMP"
DAY_VALID="$(node "$VALIDATE" day-rollup "$DAY_TMP" >/dev/null 2>&1 && echo true || echo false)"
rm -f "$DAY_TMP"
check "day rollup validates against schema" "$DAY_VALID"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "---"
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
