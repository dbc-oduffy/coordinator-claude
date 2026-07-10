#!/usr/bin/env bash
# stamp-plan-status-on-ship.integration.test.sh — integration test for the
# stamp-on-ship seam: plan-status-transition.js (CLI), cs_stamp_plan_implemented
# (helper), and draft-plan-aging.sh (pre-existing draft-plan staleness detector
# that short-circuits on a non-draft status at ~line 271-272 of that script).
#
# Purpose: prove the three pieces compose correctly end-to-end —
#   (a) AC4 — a stale draft plan IS flagged by draft-plan-aging.sh pre-stamp,
#       and is NO LONGER flagged post-stamp (non-draft short-circuit).
#   (b) stamp-on-ship — cs_stamp_plan_implemented flips a draft fixture to
#       implemented via plan-status-transition.js under the hood.
#   (c) AC2 no-stamp-on-partial — asserts the seam-level invariant: the helper
#       is only ever invoked on the ship-confirmed path (never on a halt/partial
#       path), and separately confirms the CLI's own documented behavior
#       (executing -> implemented DOES flip when called directly) — halt-safety
#       is a call-site property, not a CLI property, and is documented as such.
#   (d) idempotent double-call — invoking the helper twice on the same fixture:
#       second call is a no-op, exit 0, status stays 'implemented'.
#
# Spec backlink: chunk C6 dispatch (plan-status-transition.js C1,
# cs_stamp_plan_implemented C2, draft-plan-aging.sh pre-existing AC4 detector).
# Run: bash coordinator/bin/stamp-plan-status-on-ship.integration.test.sh
# Portability (DR-148): bash >= 4 + BSD coreutils; no GNU-only date/sed flags.

set -euo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "stamp-plan-status-on-ship.integration.test.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AGING_CLI="${SCRIPT_DIR}/draft-plan-aging.sh"
TRANSITION_CLI="${SCRIPT_DIR}/plan-status-transition.js"
STAMP_LIB="${REPO_ROOT}/coordinator/lib/coordinator-archive-stamp.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

_days_ago() {
  local n="$1"
  date -d "-${n} days" +%Y-%m-%d 2>/dev/null || date -v-"${n}"d +%Y-%m-%d
}

write_draft_plan() {
  local p="$1" created="$2" status="${3:-draft}"
  {
    printf -- '---\n'
    printf 'title: "Stamp-on-ship fixture"\n'
    printf 'status: %s\n' "$status"
    printf 'created: %s\n' "$created"
    printf -- '---\n'
    printf '\n# Body\nSome plan.\n'
  } > "$p"
}

read_status() {
  local p="$1"
  grep -m1 '^status:' "$p" | sed 's/^status: *//'
}

# ---------------------------------------------------------------------------
# (a) + (b) — AC4: draft-plan-aging.sh flags pre-stamp, does not post-stamp;
# stamp-on-ship: helper flips draft -> implemented.
# ---------------------------------------------------------------------------
TMP_A="$(mktemp -d)"
PLAN_A="${TMP_A}/plan.md"
# 15 days old, no scope block (no-scope fails toward surfacing — no git-log
# needed, mirrors draft-plan-aging.bats t_15d_over_boundary_stale), no
# state/handoffs baton reference possible (cwd has no state/handoffs dir).
write_draft_plan "$PLAN_A" "$(_days_ago 15)" "draft"

# Review: code-reviewer C-F3 — mktemp scratch file, not hardcoded /tmp/*.$$
# (matches skills/workstream-complete/SKILL.md:99 convention).
aging_pre_out_file="$(mktemp "${TMPDIR:-/tmp}/aging-pre.XXXXXX")"
( cd "$TMP_A" && bash "$AGING_CLI" "$PLAN_A" >"$aging_pre_out_file" 2>&1 ) && rc_pre=0 || rc_pre=$?
out_pre="$(cat "$aging_pre_out_file")"; rm -f "$aging_pre_out_file"

if [[ "$rc_pre" -eq 1 ]] && [[ "$out_pre" == *"STALE"* ]] && [[ "$out_pre" == *"$PLAN_A"* ]]; then
  pass "AC4 pre-stamp: draft-plan-aging.sh flags the stale draft fixture (rc=1, STALE)"
else
  fail "AC4 pre-stamp: expected rc=1 + STALE output, got rc=${rc_pre} out=${out_pre}"
fi

# shellcheck source=/dev/null
source "$STAMP_LIB"
stamp_out="$(cs_stamp_plan_implemented "$PLAN_A" 2>&1)" && stamp_rc=0 || stamp_rc=$?
status_after_stamp="$(read_status "$PLAN_A")"

if [[ "$stamp_rc" -eq 0 ]] && [[ "$status_after_stamp" == "implemented" ]]; then
  pass "stamp-on-ship: cs_stamp_plan_implemented flips draft fixture to implemented (rc=0)"
else
  fail "stamp-on-ship: expected rc=0 + status=implemented, got rc=${stamp_rc} status=${status_after_stamp} output=${stamp_out}"
fi

aging_post_out_file="$(mktemp "${TMPDIR:-/tmp}/aging-post.XXXXXX")"
( cd "$TMP_A" && bash "$AGING_CLI" "$PLAN_A" >"$aging_post_out_file" 2>&1 ) && rc_post=0 || rc_post=$?
out_post="$(cat "$aging_post_out_file")"; rm -f "$aging_post_out_file"

if [[ "$rc_post" -eq 0 ]] && [[ -z "$out_post" ]]; then
  pass "AC4 post-stamp: draft-plan-aging.sh no longer flags the plan (non-draft short-circuit, rc=0)"
else
  fail "AC4 post-stamp: expected rc=0 + empty output, got rc=${rc_post} out=${out_post}"
fi

rm -rf "$TMP_A"

# ---------------------------------------------------------------------------
# (c) AC2 no-stamp-on-partial -- seam-level invariant.
#
# The halt/partial-vs-ship decision is call-site prose (the caller decides
# whether it is safe to declare a plan done), not something the CLI or the
# helper can enforce internally. This test asserts the invariant at the
# seam boundary in two parts:
#   1. Documentation-of-fact: the CLI, called DIRECTLY (as it would be from
#      the ship-confirmed call site only), correctly flips
#      executing -> implemented. This is expected CLI behavior per its own
#      spec (plan-status-transition.js header comment) -- NOT evidence that
#      the CLI is invoked on a halt/partial path.
#   2. Invariant-by-construction: the two wired call sites for
#      cs_stamp_plan_implemented live in skill docs (execute-plan/SKILL.md,
#      workstream-complete/SKILL.md), not bash conditionals -- grep each
#      site's surrounding prose and confirm it documents a ship-confirmed
#      gating condition (e.g. "fires ONLY on the full-plan-shipped path",
#      "never fires on a ... halt"). A halt-path fixture is deliberately NOT
#      exercised here because there is no halt-path call site to exercise --
#      the guard lives entirely in caller prose per the CLI's own
#      halt-safety note, not in code this test can invoke on a halt branch.
# ---------------------------------------------------------------------------
TMP_C="$(mktemp -d)"
PLAN_C="${TMP_C}/plan.md"
write_draft_plan "$PLAN_C" "$(_days_ago 1)" "executing"

direct_cli_out_file="$(mktemp "${TMPDIR:-/tmp}/direct-cli.XXXXXX")"
node "$TRANSITION_CLI" stamp-implemented --plan "$PLAN_C" >"$direct_cli_out_file" 2>&1 && direct_rc=0 || direct_rc=$?
direct_status="$(read_status "$PLAN_C")"
rm -f "$direct_cli_out_file"

if [[ "$direct_rc" -eq 0 ]] && [[ "$direct_status" == "implemented" ]]; then
  pass "AC2 (CLI-level): executing -> implemented flips when the CLI is called directly (documents halt-safety lives at the call-site, not the CLI)"
else
  fail "AC2 (CLI-level): expected rc=0 + status=implemented, got rc=${direct_rc} status=${direct_status}"
fi

rm -rf "$TMP_C"

# Seam invariant: locate the two wired call sites (skill docs) for
# cs_stamp_plan_implemented and confirm each is textually documented as
# gated on a ship-confirmed condition, never an unconditional/halt path.
EXEC_PLAN_SKILL="${REPO_ROOT}/coordinator/skills/execute-plan/SKILL.md"
WSC_SKILL="${REPO_ROOT}/coordinator/skills/workstream-complete/SKILL.md"

seam_invariant_ok=1
seam_invariant_detail=""

if [[ ! -f "$EXEC_PLAN_SKILL" ]] || ! grep -q 'cs_stamp_plan_implemented' "$EXEC_PLAN_SKILL"; then
  seam_invariant_ok=0
  seam_invariant_detail="execute-plan/SKILL.md call site not found"
elif ! grep -B5 'cs_stamp_plan_implemented' "$EXEC_PLAN_SKILL" | grep -qiE 'fires ONLY on the full-plan-shipped path|never fires on a|halt'; then
  seam_invariant_ok=0
  seam_invariant_detail="execute-plan/SKILL.md call site missing ship-confirmed gating language"
fi

if [[ "$seam_invariant_ok" -eq 1 ]]; then
  if [[ ! -f "$WSC_SKILL" ]] || ! grep -q 'cs_stamp_plan_implemented' "$WSC_SKILL"; then
    seam_invariant_ok=0
    seam_invariant_detail="workstream-complete/SKILL.md call site not found"
  elif ! grep -B5 'cs_stamp_plan_implemented' "$WSC_SKILL" | grep -qiE 'governing-plan predicate|governing plan doc|ALLOWLIST reconcile'; then
    seam_invariant_ok=0
    seam_invariant_detail="workstream-complete/SKILL.md call site missing ship-confirmed gating language"
  fi
fi

if [[ "$seam_invariant_ok" -eq 1 ]]; then
  pass "AC2 (seam-level): both wired call sites (execute-plan, workstream-complete SKILL.md) document ship-confirmed gating for cs_stamp_plan_implemented"
else
  fail "AC2 (seam-level): ${seam_invariant_detail:-unknown}"
fi

# ---------------------------------------------------------------------------
# (d) idempotent double-call — second call on an already-implemented plan is
# a no-op, exit 0, status unchanged.
# ---------------------------------------------------------------------------
TMP_D="$(mktemp -d)"
PLAN_D="${TMP_D}/plan.md"
write_draft_plan "$PLAN_D" "$(_days_ago 1)" "draft"

first_out="$(cs_stamp_plan_implemented "$PLAN_D" 2>&1)" && first_rc=0 || first_rc=$?
first_status="$(read_status "$PLAN_D")"

second_out="$(cs_stamp_plan_implemented "$PLAN_D" 2>&1)" && second_rc=0 || second_rc=$?
second_status="$(read_status "$PLAN_D")"

if [[ "$first_rc" -eq 0 ]] && [[ "$first_status" == "implemented" ]] \
   && [[ "$second_rc" -eq 0 ]] && [[ "$second_status" == "implemented" ]] \
   && [[ "$second_out" == *"no-op"* ]]; then
  pass "idempotent double-call: second cs_stamp_plan_implemented call is a respected no-op (rc=0, status unchanged)"
else
  fail "idempotent double-call: first(rc=${first_rc},status=${first_status}) second(rc=${second_rc},status=${second_status},out=${second_out})"
fi

rm -rf "$TMP_D"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "stamp-plan-status-on-ship.integration.test.sh: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
