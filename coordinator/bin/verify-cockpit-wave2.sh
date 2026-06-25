#!/usr/bin/env bash
# verify-cockpit-wave2.sh — acceptance-oracle verifier for the cockpit-contract-ext
# wave-2 plan (tc-2/tc-3/tc-4). One AC id per invocation; exit 0 == green.
#
# Purpose: pipe-free, drift-resistant AC checks bound from the plan's acceptance
# table (markdown cells cannot contain `|`, so each check lives here and the cell
# is `bash:bash <this> acN`). Assertions are invariant-shaped, not count-pinned,
# because the live improvement queue is written concurrently by other sessions.
#
# Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md
# Review: code-reviewer — added -e so jq/python failures propagate; was -uo pipefail (F4)
set -euo pipefail

ROOT="${CLAUDE_HOME:-$HOME}/.claude"
CO="$ROOT/plugins/coordinator-claude/coordinator"
IQ="$ROOT/state/improvement-queue"
EMIT="$ROOT/state/cockpit-emission.json"

fail() { echo "FAIL($1): $2" >&2; exit 1; }

# Count central improvement rows without a pipe (bash glob + counter).
count_scope() {
  local scope="$1" n=0 f
  for f in "$IQ"/*.yaml; do
    [ -e "$f" ] || continue
    grep -q "^queue_scope: ${scope}\b" "$f" 2>/dev/null && n=$((n+1))
  done
  echo "$n"
}
count_missing_scope() {
  local n=0 f
  for f in "$IQ"/*.yaml; do
    [ -e "$f" ] || continue
    grep -q '^queue_scope:' "$f" 2>/dev/null || n=$((n+1))
  done
  echo "$n"
}

run_emitter() { bash "$CO/bin/emit-cockpit-snapshot.sh" >/dev/null 2>&1; }

case "${1:-}" in
  ac1)  # every prose row migrated to a central YAML record
    # Review: code-reviewer — floor changed from 112 (count-pinned) to 1 (invariant-shaped per file header); AC2 enforces completeness via missing-scope check (F13)
    n=$(count_scope central); [ "$n" -ge 1 ] || fail ac1 "no central rows found — migration may not have run"; ;;
  ac2)  # backfill + no silent quarantine: every row carries queue_scope
    m=$(count_missing_scope); [ "$m" -eq 0 ] || fail ac2 "$m rows missing queue_scope"; ;;
  ac3)  # live readers no longer reference the archived prose file
    # Review: code-reviewer — -lq is contradictory/BSD-fragile; -q is correct for presence check (F12)
    grep -q 'coordinator-improvement-queue.md' \
      "$CO/bin/whats-next.sh" "$CO/bin/workday-complete-step2_5-dirty-tree.sh" 2>/dev/null \
      && fail ac3 "a live reader still references the archived prose file" || true; ;;
  ac4)  # prose-form sanction removed from the live doctrine surfaces (not historical plans, not this verifier)
    grep -q 'retains line-deletion' \
      "$CO/CLAUDE.md" "$CO/docs/wiki/improvement-queue-schema.md" "$CO/docs/wiki/backlog-prune-discipline.md" 2>/dev/null \
      && fail ac4 "prose-form sanction still present in doctrine" || true
    # Review: code-reviewer — positive assertion: queue_scope MUST be documented in the schema (F6)
    grep -q 'queue_scope' \
      "$CO/docs/wiki/improvement-queue-schema.md" 2>/dev/null \
      || fail ac4 "queue_scope field absent from improvement-queue-schema.md — schema doc incomplete"; ;;
  ac5)  # emitter green AND improvement records carry queue_scope (no regression)
    run_emitter || fail ac5 "emitter exited non-zero"
    # Review: code-reviewer — r.get("queue_scope") is truthy-only; require value in {"central","project"} (F7)
    python3 - "$EMIT" <<'PY' || exit 1 # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
import json,sys
j=json.load(open(sys.argv[1])); bl=j["backlogs"]
imp=bl["improvement"] if isinstance(bl,dict) else [r for r in bl if r.get("type")=="improvement"]
valid_scopes = {"central", "project"}
sys.exit(0 if imp and all(isinstance(r.get("repo"),str) and r.get("queue_scope") in valid_scopes for r in imp) else 1)
PY
    ;;
  ac6|ac7|ac8)  # LessonSummary union-dedup / parse_status / promotion_state
    # Review: code-reviewer — removed 2>&1 so failing test name surfaces on stderr (F8)
    python3 "$CO/bin/lib/emit-lesson-summaries.test.py" >/dev/null || fail "$1" "lesson-summaries test red"; ;; # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
  ac9|ac11|ac12)  # PlanSummary sourcing + sidecar exclusion + #-title round-trip
    # Review: code-reviewer — removed 2>&1 so failing test name surfaces on stderr (F8)
    node --test "$CO/bin/lib/query-records.test.js" >/dev/null || fail "$1" "query-records test red"; ;; # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
  ac10) # all three new/migrated entity arrays present and validate (emitter exit 0 == all main-array records valid)
    run_emitter || fail ac10 "emitter exited non-zero"
    # Review: code-reviewer — added no-regression assertions: handoffs non-empty, backlogs.improvement non-empty dict key (F9)
    python3 - "$EMIT" <<'PY' || exit 1 # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
import json,sys
j=json.load(open(sys.argv[1]))
bl=j.get("backlogs",{})
ok=(
  len(j.get("lessons",[]))>0 and
  len(j.get("plans",[]))>0 and
  len(j.get("handoffs",[]))>0 and
  isinstance(bl,dict) and len(bl.get("improvement",[]))>0
)
sys.exit(0 if ok else 1)
PY
    ;;
  *) echo "usage: verify-cockpit-wave2.sh ac1|ac2|...|ac12" >&2; exit 2; ;;
esac
echo "OK($1)"
