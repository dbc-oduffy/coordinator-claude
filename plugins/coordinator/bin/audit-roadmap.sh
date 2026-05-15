#!/bin/bash
# audit-roadmap.sh — Phase 2 close cross-file audits for coordinator:roadmap-planning.
#
# Closes the gap that bin/lint-frontmatter.js cannot enforce per-file: rules that compare
# multiple stubs in the active set, or cross-reference a stub against tasks/roadmap/<run-id>/pm-gates.md.
#
# Spec backlink: docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md § Phase 5
# the Staff Engineer review finding: P1-1 (audit script must ship in v1, not be deferred to post-dogfood).
#
# Usage: audit-roadmap.sh <run-id>
#
# Exits 0 on pass; 1 on any audit failure with diagnostic output.

set -euo pipefail

RUN_ID="${1:-}"
if [ -z "$RUN_ID" ]; then
  echo "Usage: $0 <run-id>" >&2
  echo "  Audits the roadmap with roadmap_id=<run-id> for Phase 2 close gates." >&2
  exit 2
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="$PWD"
QR="${ROOT}/plugins/coordinator-claude/coordinator/bin/query-records.js"
PMG="${ROOT}/tasks/roadmap/${RUN_ID}/pm-gates.md"
RECON="${ROOT}/tasks/roadmap/${RUN_ID}/reconciliation.md"

if [ ! -f "$QR" ]; then
  echo "FAIL: query-records.js not found at $QR" >&2
  exit 2
fi

EXIT_CODE=0
fail() { echo "FAIL: $*" >&2; EXIT_CODE=1; }
pass() { echo "PASS: $*"; }

# --- Audit 1: stub-coverage (brief recommendation G) ----------------------
# Verdict-to-stub coverage: count of MERGE+KEEP verdicts in reconciliation.md
# must equal count of stubs on disk with this roadmap_id.

if [ ! -f "$RECON" ]; then
  fail "reconciliation.md not found at $RECON — Phase 1 incomplete"
else
  # Count verdicts. Format expected: lines containing "Verdict: KEEP" / "Verdict: MERGE"
  # at any indentation level (skill template uses these tokens).
  KEEP_COUNT=$(grep -ciE "verdict:\s*keep\b" "$RECON" || true)
  MERGE_COUNT=$(grep -ciE "verdict:\s*merge\b" "$RECON" || true)
  EXPECTED=$((KEEP_COUNT + MERGE_COUNT))

  STUB_COUNT=$(node "$QR" --type handoff \
    --where "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" \
    --format paths --root "$ROOT" 2>/dev/null | grep -c . || true)

  if [ "$STUB_COUNT" -ne "$EXPECTED" ]; then
    fail "Stub-coverage mismatch: ${STUB_COUNT} stubs on disk, ${EXPECTED} expected (KEEP=${KEEP_COUNT} + MERGE=${MERGE_COUNT}). See $RECON."
  else
    pass "Stub-coverage: ${STUB_COUNT} stubs match ${EXPECTED} verdicts (KEEP=${KEEP_COUNT}, MERGE=${MERGE_COUNT})."
  fi
fi

# --- Audit 2: at most one ready_to_fire per (roadmap_id, wave) -----------
# Validator pass per skill Step 2.7. Implements the rule across the active stub set.

READY_PATHS=$(node "$QR" --type handoff \
  --where "kind=spinoff-roadmap AND roadmap_id=${RUN_ID} AND deployment_state=ready_to_fire" \
  --format paths --root "$ROOT" 2>/dev/null || true)

if [ -n "$READY_PATHS" ]; then
  # Extract wave per file via frontmatter parse. Use node one-liner to keep schema-aware.
  WAVES=$(echo "$READY_PATHS" | while IFS= read -r p; do
    [ -z "$p" ] && continue
    node -e "
      const fs=require('fs');
      const path=require('path');
      const {parseFrontmatter} = require(path.join(process.argv[2], 'plugins/coordinator-claude/coordinator/bin/lib/schema.js'));
      const c = fs.readFileSync(path.join(process.argv[2], process.argv[3]),'utf8');
      const fm = parseFrontmatter(c).frontmatter || {};
      console.log((fm.wave === undefined || fm.wave === null) ? 'NO_WAVE' : fm.wave);
    " -- "$ROOT" "$p" 2>/dev/null || echo "PARSE_ERROR"
  done)

  DUPES=$(echo "$WAVES" | sort | uniq -d)
  if [ -n "$DUPES" ]; then
    fail "Multiple ready_to_fire stubs in the same (roadmap_id, wave): waves [${DUPES}]. At most one ready_to_fire per wave allowed."
  else
    READY_COUNT=$(echo "$READY_PATHS" | grep -c .)
    pass "ready_to_fire uniqueness: ${READY_COUNT} ready stubs across distinct waves."
  fi
fi

# --- Audit 3: pm-gates.md cross-reference (brief recommendation E) -------
# Every stub with gate_dependency starting "PM " MUST have a matching tc_id row in pm-gates.md.
# Every pending row in pm-gates.md MUST be referenced by at least one stub.

PM_STUBS=$(node "$QR" --type handoff \
  --where "kind=spinoff-roadmap AND roadmap_id=${RUN_ID} AND deployment_state=awaiting_gate" \
  --format paths --root "$ROOT" 2>/dev/null || true)

PM_TC_IDS=""
if [ -n "$PM_STUBS" ]; then
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    TC=$(node -e "
      const fs=require('fs');
      const path=require('path');
      const {parseFrontmatter} = require(path.join(process.argv[2], 'plugins/coordinator-claude/coordinator/bin/lib/schema.js'));
      const c = fs.readFileSync(path.join(process.argv[2], process.argv[3]),'utf8');
      const fm = parseFrontmatter(c).frontmatter || {};
      const gd = String(fm.gate_dependency || '');
      if (gd.startsWith('PM ')) console.log(fm.tc_id || '');
    " -- "$ROOT" "$p" 2>/dev/null || echo "")
    [ -n "$TC" ] && PM_TC_IDS="${PM_TC_IDS} ${TC}"
  done <<< "$PM_STUBS"
fi

if [ -n "${PM_TC_IDS// /}" ]; then
  if [ ! -f "$PMG" ]; then
    fail "pm-gates.md missing at $PMG — found PM-prefixed gate_dependency on tc_ids: ${PM_TC_IDS}"
  else
    PMG_CONTENT=$(cat "$PMG")
    for tc in $PM_TC_IDS; do
      if ! echo "$PMG_CONTENT" | grep -qF "$tc"; then
        fail "Stub ${tc} has gate_dependency starting 'PM ' but is not cross-referenced in pm-gates.md"
      fi
    done
    [ "$EXIT_CODE" -eq 0 ] && pass "pm-gates.md cross-references: all ${PM_TC_IDS} present."
  fi
fi

# --- Audit 4: pending pm-gates rows reference at least one stub ----------
# Inverse of Audit 3: every "pending" row in pm-gates.md must name a tc_id that exists.

if [ -f "$PMG" ]; then
  PENDING_TCS=$(awk -F'|' '/pending/ { gsub(/[ \t]+/,"",$3); if ($3 ~ /^tc-[0-9]+$/) print $3 }' "$PMG" 2>/dev/null || true)
  if [ -n "$PENDING_TCS" ]; then
    ALL_TCS=$(node "$QR" --type handoff \
      --where "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" \
      --format json --root "$ROOT" 2>/dev/null \
      | node -e "let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{const a=JSON.parse(d); a.forEach(r=>console.log(r.frontmatter.tc_id||''))})" 2>/dev/null \
      || true)
    for tc in $PENDING_TCS; do
      if ! echo "$ALL_TCS" | grep -qFx "$tc"; then
        fail "pm-gates.md has pending row for ${tc} but no stub with that tc_id exists in roadmap_id=${RUN_ID}"
      fi
    done
  fi
fi

# --- Summary --------------------------------------------------------------
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "audit-roadmap: all checks passed for roadmap_id=${RUN_ID}"
else
  echo "audit-roadmap: one or more checks FAILED for roadmap_id=${RUN_ID} — Phase 3 dispatch is blocked"
fi
exit "$EXIT_CODE"
