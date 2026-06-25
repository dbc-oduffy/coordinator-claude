#!/usr/bin/env bash
# assert-no-terminal-plans-in-live.sh — AC6 gate for programmatic terminal-plan archival.
#
# Asserts that NO *movable* terminal plan remains in docs/plans/ — i.e. running
# cs_sweep_terminal_plans would move zero files. A terminal plan
# (status ∈ {implemented, superseded, abandoned}) is allowed to remain in
# docs/plans/ ONLY when it is legitimately HELD by a live reference:
#   • an active (non-consumed/superseded) handoff in state/handoffs/, or
#   • a live (non-terminal) plan body in docs/plans/.
#
# Why "movable", not "zero terminal plans": the sweep deliberately skips
# terminal plans cited by live work (cleanup-sweep-hazards §1 — don't bury an
# in-flight thread's referenced plan). Most shipped plans stay cited by some
# live plan for a while, so a literal zero-terminal-plans assertion would be
# permanently red. The operative invariant the sweep CAN guarantee is "nothing
# left that the sweep should have moved" — which is exactly what regressed when
# review sidecars were mis-counted as live plans (sidecar-self-hold bug).
#
# This predicate MIRRORS cs_sweep_terminal_plans (lib/coordinator-session.sh):
# three-status enum via query-records, active-handoff skip, live-plan skip with
# review-sidecars excluded. Keep the two in sync.
#
# Spec backlink: docs/plans/2026-06-23-programmatic-terminal-plan-archival.md § AC6 / C4.
#
# Usage:   assert-no-terminal-plans-in-live.sh [--root <dir>]
# Exit:    0 = no movable terminal plan remains; 1 = ≥1 movable (sweep owes work).

set -uo pipefail

ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  command -v git >/dev/null 2>&1 && ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
fi
[[ -z "$ROOT" ]] && exit 0                       # non-git consumer: no-op pass
[[ -d "$ROOT/docs/plans" ]] || exit 0            # no plans dir: no-op pass

QR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/query-records.js"
[[ -f "$QR" ]] || QR="${HOME}/.claude/plugins/coordinator/bin/query-records.js"
if [[ ! -f "$QR" ]] || ! command -v node >/dev/null 2>&1; then
  echo "assert-no-terminal-plans-in-live: query-records.js or node unavailable — cannot verify" >&2
  exit 0
fi

# Terminal plan set (query-records already excludes sidecars).
TERM_PATHS=$(
  {
    node "$QR" --type plan --where "status=implemented" --format paths --root "$ROOT" 2>/dev/null || true # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
    node "$QR" --type plan --where "status=superseded"  --format paths --root "$ROOT" 2>/dev/null || true # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
    node "$QR" --type plan --where "status=abandoned"   --format paths --root "$ROOT" 2>/dev/null || true # verify-no-console-flash: allow — verify/emit analysis tool, not interactive-session hot-path
  } | sort -u
)
if [[ -z "$TERM_PATHS" ]]; then
  echo "OK: docs/plans/ contains zero terminal plans"
  exit 0
fi

# Active-handoff reference corpus (status not consumed/superseded).
ACTIVE_HANDOFF_REFS=""
if [[ -d "$ROOT/state/handoffs" ]]; then
  for hfile in "$ROOT/state/handoffs/"*.md; do
    [[ -f "$hfile" ]] || continue
    hstatus=$(awk '/^---/{f++} f==1 && /^status:/{print $2; exit}' "$hfile" 2>/dev/null || true)
    [[ "$hstatus" == "consumed" || "$hstatus" == "superseded" ]] && continue
    ACTIVE_HANDOFF_REFS="${ACTIVE_HANDOFF_REFS}
$(cat "$hfile" 2>/dev/null || true)"
  done
fi

# Live-plan reference corpus (non-terminal), review sidecars EXCLUDED.
LIVE_PLAN_REFS=""
for lfile in "$ROOT/docs/plans/"*.md; do
  [[ -f "$lfile" ]] || continue
  lstem=$(basename "$lfile"); lstem="${lstem%.md}"
  [[ "$lstem" == *.* ]] && continue              # sidecar, not a plan
  lstatus=$(awk '/^---/{f++} f==1 && /^status:/{print $2; exit}' "$lfile" 2>/dev/null || true)
  [[ "$lstatus" == "implemented" || "$lstatus" == "superseded" || "$lstatus" == "abandoned" ]] && continue
  LIVE_PLAN_REFS="${LIVE_PLAN_REFS}
$(cat "$lfile" 2>/dev/null || true)"
done

MOVABLE=0
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  fname=$(basename "$rel")
  echo "$ACTIVE_HANDOFF_REFS" | grep -qF "$fname" 2>/dev/null && continue   # held by handoff
  echo "$LIVE_PLAN_REFS"      | grep -qF "$fname" 2>/dev/null && continue   # held by live plan
  MOVABLE=$((MOVABLE + 1))
  echo "MOVABLE terminal plan still in docs/plans/: $fname" >&2
done <<< "$TERM_PATHS"

if [[ "$MOVABLE" -gt 0 ]]; then
  echo "FAIL: $MOVABLE movable terminal plan(s) in docs/plans/ — cs_sweep_terminal_plans owes work" >&2
  exit 1
fi
echo "OK: no movable terminal plans in docs/plans/ (all remaining terminal plans are live-ref-held)"
exit 0
