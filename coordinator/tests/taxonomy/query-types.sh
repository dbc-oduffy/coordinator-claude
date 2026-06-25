#!/usr/bin/env bash
# AC6 — every new deliverable type is reachable via `query-records --type <type>` (no "Unknown type").
# Portable (DR-148): bash 3.2 + BSD coreutils.
set -eo pipefail
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORD_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
QR="$COORD_ROOT/bin/query-records.js"

fail() { echo "FAIL: $*" >&2; exit 1; }
[ -f "$QR" ] || fail "query-records.js not found at $QR"

NEW_TYPES="review-sidecar prior-art-check plan-coverage-check docs-check-sidecar integration-summary problem-set archived-memo"
for t in $NEW_TYPES; do
  # Reachable = the type is a known --type (not rejected as "Unknown type"). Empty result is OK.
  # Review: code-reviewer (S3-F8) — empty result is OK; AC6 tests type reachability, not that files exist.
  out="$(node "$QR" --type "$t" --format markdown-list 2>&1)"
  rc=$?
  if [ $rc -ne 0 ] || printf '%s' "$out" | grep -qi 'unknown type'; then
    fail "--type $t not reachable (rc=$rc): $(printf '%s' "$out" | head -1)"
  fi
done

echo "PASS: all 7 new types reachable via query-records --type"
exit 0
