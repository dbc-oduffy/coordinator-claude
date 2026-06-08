#!/usr/bin/env bash
# coordinator/dist/oss-only-skills/coordinator-update/tests/scenarios/audit-skill-self-containment.sh
#
# Purpose: SKILL.md self-containment audit — verifies the SKILL.md carries the
# four verbatim load-bearing rules required by the C3 scaffold checklist.
#
# Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 3
#   Scaffold checklist items 1 (preservation hard-constraint + §2 out-of-scope list),
#   7a (never git add -A commit rule), 7b (preservation verbatim), 7c (offer-shape rule).
#   Covers plan AC5 (consumer_modified preservation) and AC9 (out-of-scope apply audit).
#
# Usage:
#   bash audit-skill-self-containment.sh [<path-to-SKILL.md>]
#
# Returns:
#   0   all assertions pass
#   1   one or more assertions fail (each failure printed to stderr)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD="${1:-${SCRIPT_DIR}/../../SKILL.md}"

if [[ ! -f "$SKILL_MD" ]]; then
  echo "ERROR: SKILL.md not found at: ${SKILL_MD}" >&2
  exit 1
fi

FAIL=0
PASS=0

pass() {
  echo "  PASS: $1"
  (( PASS++ )) || true
}

fail() {
  echo "  FAIL: $1" >&2
  (( FAIL++ )) || true
}

echo "=== SKILL.md self-containment audit ==="
echo "File: ${SKILL_MD}"
echo ""

# ---------------------------------------------------------------------------
# Assertion 1 — Preservation hard-constraint (AC5 / scaffold item 7b)
# The verbatim preservation rule must appear in the SKILL.md.
# ---------------------------------------------------------------------------
echo "Assertion 1: verbatim preservation hard-constraint"
if grep -q "Never overwrite a \`consumer_modified\` file without the user's Claude affirmatively judging" "$SKILL_MD" && \
   grep -q "preserved by default" "$SKILL_MD"; then
  pass "preservation hard-constraint present"
else
  fail "preservation hard-constraint missing — must quote: 'Never overwrite a consumer_modified file without the user\\'s Claude affirmatively judging ... preserved by default'"
fi

# ---------------------------------------------------------------------------
# Assertion 2 — "never git add -A" commit rule (AC9 / scaffold item 7a)
# ---------------------------------------------------------------------------
echo "Assertion 2: 'never git add -A' commit rule"
if grep -q "git add -A" "$SKILL_MD" && \
   grep -q "Never" "$SKILL_MD" && \
   grep -qE "git add -- " "$SKILL_MD"; then
  pass "commit safety rule (never git add -A + scoped explicit-path) present"
else
  fail "commit safety rule missing — must prohibit 'git add -A' and show explicit-path 'git add -- <paths>'"
fi

# ---------------------------------------------------------------------------
# Assertion 3 — Offer-shape rule (scaffold item 7c)
# The default is compute+advise; apply is explicit-consent-gated.
# ---------------------------------------------------------------------------
echo "Assertion 3: offer-shape framing (compute+advise default; apply consent-gated)"
if grep -q "explicit" "$SKILL_MD" && \
   grep -q "consent" "$SKILL_MD" && \
   grep -qiE "(compute|advise).*(default|not autonomous|explicit)" "$SKILL_MD"; then
  pass "offer-shape rule present"
else
  fail "offer-shape rule missing — must state compute+advise is default, apply is explicit-consent-gated"
fi

# ---------------------------------------------------------------------------
# Assertion 4 — §2 out-of-scope path list (scaffold item 1 / AC9)
# Must enumerate agent-owned session-continuity paths that are never touched.
# ---------------------------------------------------------------------------
echo "Assertion 4: §2 out-of-scope path list (agent-owned session-continuity surface)"
PATHS_OK=true
for required_path in "tasks/" "state/handoffs/" "lessons.md" "settings.json" "consumer_added"; do
  if ! grep -q "$required_path" "$SKILL_MD"; then
    fail "out-of-scope list missing entry: '${required_path}'"
    PATHS_OK=false
  fi
done
if $PATHS_OK; then
  pass "out-of-scope path list covers tasks/, state/handoffs/, lessons.md, settings.json, consumer_added"
fi

# ---------------------------------------------------------------------------
# Assertion 5 — marketplace.json exclusion noted (execution notes from plan)
# ---------------------------------------------------------------------------
echo "Assertion 5: marketplace.json exclusion noted"
if grep -q "marketplace.json" "$SKILL_MD"; then
  pass "marketplace.json installer-owned exclusion noted"
else
  fail "marketplace.json exclusion not mentioned — this file is always rewritten by install.sh and must be excluded from the advisory set"
fi

# ---------------------------------------------------------------------------
# Assertion 6 — verb-name collision note (scaffold item 6)
# ---------------------------------------------------------------------------
echo "Assertion 6: verb-name collision check noted"
if grep -q "fan-out" "$SKILL_MD" || grep -qiE "verb.name|collision|fan.out lesson" "$SKILL_MD"; then
  pass "verb-name collision check noted"
else
  fail "verb-name collision check not mentioned — required by scaffold checklist item 6"
fi

# ---------------------------------------------------------------------------
# Assertion 7 — No handoff/spinoff authoring (scaffold item 3)
# ---------------------------------------------------------------------------
echo "Assertion 7: no handoff/spinoff authoring (out-of-scope block)"
if grep -qiE "handoff|spinoff" "$SKILL_MD" && \
   (grep -qiE "(not|never|does not).*(handoff|spinoff)" "$SKILL_MD" || \
    grep -qiE "Author handoffs|Author spinoffs|handoffs.*spinoffs.*out.of.scope" "$SKILL_MD"); then
  pass "out-of-scope block explicitly excludes handoff/spinoff authoring"
else
  fail "out-of-scope block does not explicitly exclude handoff/spinoff authoring — must include 'Author handoffs/spinoffs' in the does-not list"
fi

# ---------------------------------------------------------------------------
# Assertion 8 — Re-stamp sentinel after apply (plan requirement)
# ---------------------------------------------------------------------------
echo "Assertion 8: post-apply sentinel re-stamp referenced"
if grep -q "install-sentinel-write" "$SKILL_MD" || grep -q "version.txt" "$SKILL_MD"; then
  pass "post-apply re-stamp (version.txt / install-sentinel-write) referenced"
else
  fail "post-apply sentinel re-stamp not referenced — required so next run has correct baseline"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [[ $FAIL -gt 0 ]]; then
  echo "AUDIT FAILED — SKILL.md missing required self-containment elements" >&2
  exit 1
else
  echo "AUDIT PASSED — SKILL.md carries all required self-containment elements"
  exit 0
fi
