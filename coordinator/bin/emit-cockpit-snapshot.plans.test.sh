#!/usr/bin/env bash
# Regression test for the PlanSummary emit section (SECTION 8.6) of
# emit-cockpit-snapshot.sh — chunk C4b of
# docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md.
#
# Two parts:
#   A. Unit — feed a synthetic query-records `--type plan` payload through the
#      SAME jq transform the emitter applies, asserting the load-bearing C4b
#      contract: IsoDateTime → date-only truncation, `#`-bearing title preserved
#      (tc-5 parseScalar dependency, AC11), 8-value status enum gate, and
#      missing-required-field / bad-status quarantine to malformed.
#   B. Integration — run the real emitter and assert the emitted `.plans` array
#      is schema-shaped: status within enum, created date-only, composite key
#      present, NO review-sidecar paths (C4a producer filter, AC9/AC12), and
#      `.malformed_records.plans` is present as an array.
#
# Run: bash bin/emit-cockpit-snapshot.plans.test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMITTER="$SCRIPT_DIR/emit-cockpit-snapshot.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok:   $*"; }

# The PlanSummary jq transform — kept byte-aligned with SECTION 8.6 of the
# emitter. If the emitter's select/map changes, update this in the same commit.
PLAN_JQ='
  [
    .[] | . as $rec | ($rec.frontmatter) as $fm | ($rec.path) as $p |
    select(
      ($fm.title | type) == "string" and
      ($fm.created | type) == "string" and
      ($fm.author | type) == "string" and
      ($fm.status | type) == "string" and
      ($fm.status | . == "draft" or . == "reviewed" or . == "approved" or . == "executing" or . == "implemented" or . == "deferred" or . == "abandoned" or . == "superseded")
    ) |
    {
      repo: "r", coordinator_root_path: ".", path: $p,
      title: $fm.title, created: ($fm.created | .[0:10]),
      author: $fm.author, status: $fm.status,
      scope_mode: ($fm.scope_mode // null), reviewer: ($fm.reviewer // null),
      branch: ($fm.branch // null), superseded_by: ($fm.superseded_by // null),
      source: ($fm.source // $fm.roadmap_id // null)
    }
  ]'

# ---- Part A: unit -----------------------------------------------------------
# Three synthetic records: a good plan with a datetime `created` and a `#` in the
# title; a plan with status outside the enum; a plan missing `author`.
SYNTH='[
  {"path":"docs/plans/2026-06-22-foo.md","frontmatter":{"title":"Borrow #4 — keep the # intact","created":"2026-06-22T08:00:00Z","author":"roadmap-planning","status":"executing","roadmap_id":"rmid"}},
  {"path":"docs/plans/2026-06-21-bad-status.md","frontmatter":{"title":"Bad status","created":"2026-06-21","author":"x","status":"execution"}},
  {"path":"docs/plans/2026-06-20-no-author.md","frontmatter":{"title":"No author","created":"2026-06-20","status":"draft"}}
]'

GOOD="$(echo "$SYNTH" | jq -c "$PLAN_JQ")"

[ "$(echo "$GOOD" | jq 'length')" -eq 1 ] || fail "expected exactly 1 conforming plan (bad-status + no-author quarantined), got $(echo "$GOOD" | jq 'length')"
ok "A: enum + required-field gate keeps only the conforming plan"

[ "$(echo "$GOOD" | jq -r '.[0].created')" = "2026-06-22" ] || fail "IsoDateTime not truncated to date-only: got $(echo "$GOOD" | jq -r '.[0].created')"
ok "A: IsoDateTime created truncated to date-only (2026-06-22T08:00:00Z -> 2026-06-22)"

[ "$(echo "$GOOD" | jq -r '.[0].title')" = "Borrow #4 — keep the # intact" ] || fail "title with # was mangled: $(echo "$GOOD" | jq -r '.[0].title')"
ok "A: '#'-bearing title preserved verbatim (tc-5 parseScalar dependency, AC11)"

[ "$(echo "$GOOD" | jq -r '.[0].source')" = "rmid" ] || fail "source did not fall back to roadmap_id"
ok "A: source falls back to roadmap_id when no explicit source"

[ "$(echo "$GOOD" | jq -r '.[0].scope_mode')" = "null" ] || fail "absent nullable not present-as-null"
ok "A: absent nullable fields are present-as-null (D9)"

# ---- Part B: integration ----------------------------------------------------
if [ ! -x "$EMITTER" ] && [ ! -f "$EMITTER" ]; then
  fail "emitter not found at $EMITTER"
fi
TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_OUT"' EXIT
# Review: code-reviewer — coupling to emitter's --out flag; defined in emit-cockpit-snapshot.sh
# at the argument-parsing block (search for `--out`): `if [[ "${1:-}" == "--out" && -n "${2:-}" ]]`.
# If the emitter renames or removes --out, this test must be updated in the same commit.
# Emitter writes to the path given after --out (else default state/cockpit-emission.json).
if ! bash "$EMITTER" --out "$TMP_OUT" >/dev/null 2>"$TMP_OUT.err"; then
  cat "$TMP_OUT.err" >&2; rm -f "$TMP_OUT.err"; fail "emitter exited non-zero"
fi
rm -f "$TMP_OUT.err"

PLANS="$(jq '.plans' "$TMP_OUT")"
[ "$(echo "$PLANS" | jq 'type')" = '"array"' ] || fail "B: .plans is not an array"
ok "B: .plans is an array ($(echo "$PLANS" | jq 'length') records)"

# Empty plans is acceptable (D9 present-but-empty); only assert shape if populated.
if [ "$(echo "$PLANS" | jq 'length')" -gt 0 ]; then
  echo "$PLANS" | jq -e 'all(.status | . == "draft" or . == "reviewed" or . == "approved" or . == "executing" or . == "implemented" or . == "deferred" or . == "abandoned" or . == "superseded")' >/dev/null \
    || fail "B: a plan status is outside the PlanStatus enum"
  ok "B: every emitted plan status within the 8-value enum"

  echo "$PLANS" | jq -e 'all(.created | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))' >/dev/null \
    || fail "B: a plan created is not date-only"
  ok "B: every emitted plan created is date-only"

  echo "$PLANS" | jq -e 'all((.repo|type=="string") and (.coordinator_root_path|type=="string") and (.path|type=="string"))' >/dev/null \
    || fail "B: composite key (repo, coordinator_root_path, path) incomplete on some record"
  ok "B: composite key present on every record"

  echo "$PLANS" | jq -e 'any(.path | test("\\.(zoli-review|plan-coverage-check|prior-art-check|patrik-review|code-review)\\.md$"))' >/dev/null \
    && fail "B: a review-sidecar leaked into .plans (C4a producer filter regression, AC12)" || true
  ok "B: no review-sidecar paths in .plans (C4a producer filter holds)"
fi

[ "$(jq '.malformed_records.plans | type' "$TMP_OUT")" = '"array"' ] || fail "B: malformed_records.plans missing or not an array"
ok "B: malformed_records.plans present as an array"

echo "ALL TESTS PASSED"
