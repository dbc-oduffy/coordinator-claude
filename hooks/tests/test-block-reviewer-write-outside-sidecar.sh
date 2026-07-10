#!/usr/bin/env bash
# Test suite for block-reviewer-write-outside-sidecar.sh PreToolUse hook.
# Purpose: synthetic PreToolUse JSON payload units exercising Mode A confinement —
# agents in the confined findings-agent SET are restricted to state/review-trail/findings/;
# top-level EM writes (no agent_id) are always allowed; non-confined subagents are
# fail-open.  Mode B (agent_id-keyed marker files) is retired; those cases are deleted.
#
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
#
# AC coverage (Mode A):
#   AC3a - no agent_id (EM write) -> ALLOW regardless of agent types.
#   Mode A confined-set cases — see selfpersist/D3 sections below.
#   Traversal guard — path with .. component always denied.
#
# Harness pattern mirrors test-block-subagent-plan-body-write.sh:
#   run_case builds JSON, pipes to hook under TMP_ROOT, checks permissionDecision.

set -uo pipefail
export COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-reviewer-write-outside-sidecar.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FAIL: hook not found at $HOOK (expected RED until C1-guard lands)"
  exit 1
fi

PASS=0
FAIL=0

# Realistic agent_id value: lowercase hex, 17 chars (cs_build_canonical_agent_id lib:2026 format).
AGENT_X="af112333608948883"

# A source path that no findings-agent should be allowed to write.
SOURCE_PATH="hooks/scripts/block-reviewer-write-outside-sidecar.sh"

# ---------------------------------------------------------------------------
# Throwaway git repo so the guard can resolve GIT_ROOT via git rev-parse.
# ---------------------------------------------------------------------------
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

(
  cd "$TMP_ROOT"
  git init -q -b main
  git config user.email t@t.t
  git config user.name t
  git config commit.gpgsign false
) || { echo "FAIL: git init failed"; exit 1; }

# Verify git root resolves - lookup-dependent tests silently pass (fail-open) without it.
( cd "$TMP_ROOT" && git rev-parse --show-toplevel > /dev/null ) \
  || { echo "FAIL: git root setup failed"; exit 1; }

# ---------------------------------------------------------------------------
# run_case <desc> <json-payload> <expected: allow|deny>
# Pipes payload to the hook from within TMP_ROOT; asserts exit=0 and
# presence/absence of permissionDecision:deny.
# ---------------------------------------------------------------------------
run_case() {
  local desc="$1" payload="$2" expected="$3"
  local out actual_exit
  out=$(cd "$TMP_ROOT" && printf '%s' "$payload" | bash "$HOOK" 2>/dev/null)
  actual_exit=$?
  local has_deny=0
  echo "$out" | grep -q '"permissionDecision":"deny"' && has_deny=1
  local expected_deny=0
  [[ "$expected" == "deny" ]] && expected_deny=1
  if [[ "$actual_exit" -eq 0 && "$has_deny" -eq "$expected_deny" ]]; then
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $desc"
    echo "      expected exit=0 deny=$expected_deny, got exit=$actual_exit deny=$has_deny"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 300)"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# AC3a - No agent_id in payload (top-level EM write) -> ALLOW.
# Even if marker files exist for other agents, the EM is never blocked.
# ---------------------------------------------------------------------------
run_case "AC3a: EM Write (no agent_id) to source path -> allow" \
  "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$SOURCE_PATH\"}}" \
  "allow"
run_case "AC3a: EM Edit (no agent_id) to source path -> allow" \
  "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$SOURCE_PATH\"}}" \
  "allow"
run_case "AC3a: EM MultiEdit (no agent_id) -> allow" \
  "{\"tool_name\":\"MultiEdit\",\"tool_input\":{\"file_path\":\"$SOURCE_PATH\"}}" \
  "allow"
run_case "AC3a: Bash tool with agent_id -> allow (non-intercepted tool)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$AGENT_X\",\"tool_input\":{\"command\":\"echo hi\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Mode A: confined findings-agent (coordinator:code-reviewer) confined by type.
# Back-pointer chain so subagent_type lookup succeeds for CONFINED_AGENT.
# Mirrors the fixture pattern in test-block-subagent-plan-body-write.sh:66-80.
# ---------------------------------------------------------------------------
CONFINED_AGENT="dd334555820b60005"
_sp_em_session="fixture-em-session-sp01"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$CONFINED_AGENT"
echo "$_sp_em_session" > "$TMP_ROOT/.git/coordinator-sessions/.agents/$CONFINED_AGENT/em-session-id.txt"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/$_sp_em_session"
printf '%s\t%s\t%s\t%s\n' \
  "$CONFINED_AGENT" "claude-sonnet-4-6" "coordinator:code-reviewer" "2026-06-30T00:00:00Z" \
  > "$TMP_ROOT/.git/coordinator-sessions/$_sp_em_session/dispatched-agents.txt"

SP_FINDINGS="state/review-trail/findings/2026-06-30-confined-review.md"
SP_ABS_FINDINGS="$TMP_ROOT/$SP_FINDINGS"

# (a) confined reviewer writing under state/review-trail/findings/ → ALLOW.
run_case "confined: Write to findings dir (repo-relative) -> allow" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"$SP_FINDINGS\"}}" \
  "allow"
run_case "confined: Edit to findings dir (repo-relative) -> allow" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"$SP_FINDINGS\"}}" \
  "allow"
run_case "confined: Write to findings dir (absolute path) -> allow" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"$SP_ABS_FINDINGS\"}}" \
  "allow"

# (b) confined reviewer writing outside the allowed directory → DENY.
run_case "confined: Write to agents/foo.md -> deny" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"agents/foo.md\"}}" \
  "deny"
run_case "confined: Edit to CLAUDE.md -> deny" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"CLAUDE.md\"}}" \
  "deny"
run_case "confined: Write to hook source file -> deny" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"$SOURCE_PATH\"}}" \
  "deny"

# (d) non-confined subagent with no back-pointer → unconfined → ALLOW (fail-open).
UNCONFINED_AGENT="ee445666931c71116"
run_case "confined: unconfined agent without back-pointer -> allow (fail-open)" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$UNCONFINED_AGENT\",\"tool_input\":{\"file_path\":\"$SOURCE_PATH\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Path-traversal denial (Mode A): a path that starts with the allowed prefix but
# contains a .. component must be denied, not allowed.
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
# ---------------------------------------------------------------------------
run_case "traversal: via findings/../../../ hook script -> deny" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"state/review-trail/findings/../../../hooks/scripts/block-reviewer-write-outside-sidecar.sh\"}}" \
  "deny"

run_case "traversal: via findings/../../ into state/handoffs -> deny" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$CONFINED_AGENT\",\"tool_input\":{\"file_path\":\"state/review-trail/findings/../../state/handoffs/some-handoff.md\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# D3 P0.2 — OR-resolver two-sided deny-gate cases
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md § D3
#
# Cases 1–5 test the agent_type-primary / back-pointer-secondary OR-resolver.
# ---------------------------------------------------------------------------

# Shared fixture agent ids for the new cases (distinct from AGENT_X and CONFINED_AGENT above).
OR_UNNAMED="cc556677880011222"   # bare hex: used for primary-leg tests (no back-pointer needed)
OR_NONCONF="dd667788991122333"   # bare hex: used for non-confined-agent tests
OR_NOBACK="ee778899aa2233444"    # bare hex: used for absent agent_type + non-confined back-pointer
OR_NAMED_RAW="aSomeName-1234567890abcdef"  # aNAME-<16hex>: NAMED dispatch format

# Path that is explicitly OUTSIDE state/review-trail/findings/
OR_OFF_PATH="hooks/scripts/evil.sh"
# Path INSIDE the allowed directory prefix
OR_ON_PATH="state/review-trail/findings/2026-07-01-or-test-review.md"

# ---------------------------------------------------------------------------
# Case 1: Confined agent (agent_type=coordinator:code-reviewer, UNNAMED bare hex,
# NO back-pointer present) + off-path Edit → DENY.
# Proves the PRIMARY leg confines foreground/naked dispatch WITHOUT back-pointer.
# This was the v1 fail-open hole (the guard previously required a back-pointer).
# ---------------------------------------------------------------------------
run_case "D3-Case1: agent_type=coordinator:code-reviewer (unnamed, no back-ptr) + off-path → deny" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_UNNAMED\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"file_path\":\"$OR_OFF_PATH\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# Case 2: Confined agent (primary leg, no back-pointer) + on-path Edit → ALLOW.
# Same agent_type as Case 1, target is inside state/review-trail/findings/.
# ---------------------------------------------------------------------------
run_case "D3-Case2: agent_type=coordinator:code-reviewer (unnamed, no back-ptr) + on-path → allow" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_UNNAMED\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"file_path\":\"$OR_ON_PATH\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 3: NAMED confined dispatch — agent_type=SomeName (NOT in confined set),
# agent_id=aNAME-<16hex>, back-pointer resolves subagent_type=coordinator:code-reviewer
# → off-path Edit → expected DENY (secondary back-pointer leg).
#
# NOTE: The write guard currently exits early for aNAME-<hex> agent_ids because
# _cs_canonical_agent_id_format_ok only accepts bare-hex. This test DOCUMENTS
# the behavioral gap: named dispatch is not confined by the write guard's
# secondary leg (AGENT_ID fails format check → early exit 0 before reaching
# the back-pointer lookup). If this test produces ALLOW instead of DENY, that
# is the guard failing to confine named dispatch — report as EM escalation.
# ---------------------------------------------------------------------------
# Set up back-pointer for the NAMED agent so the test proves the fixture works.
OR_NAMED_EM_SID="fixture-named-em-sid-001"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NAMED_RAW"
echo "$OR_NAMED_EM_SID" > "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NAMED_RAW/em-session-id.txt"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/$OR_NAMED_EM_SID"
printf '%s\t%s\t%s\t%s\n' \
  "$OR_NAMED_RAW" "claude-sonnet-4-6" "coordinator:code-reviewer" "2026-07-01T00:00:00Z" \
  > "$TMP_ROOT/.git/coordinator-sessions/$OR_NAMED_EM_SID/dispatched-agents.txt"

run_case "D3-Case3: NAMED agent_type=SomeName, back-ptr=coordinator:code-reviewer + off-path → deny (secondary leg)" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_NAMED_RAW\",\"agent_type\":\"SomeName\",\"tool_input\":{\"file_path\":\"$OR_OFF_PATH\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# Case 4: NON-confined agent (agent_type=coordinator:executor) + off-path Edit
# + no marker → ALLOW.
# CRITICAL: Executors/enrichers/integrators MUST keep writing freely.
# A global-fail-closed bug would break all subagent writes; this case is the
# primary regression guard against that.
# ---------------------------------------------------------------------------
run_case "D3-Case4 (CRITICAL fail-open): agent_type=coordinator:executor + off-path + no marker → allow" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_NONCONF\",\"agent_type\":\"coordinator:executor\",\"tool_input\":{\"file_path\":\"$OR_OFF_PATH\"}}" \
  "allow"

# Also test Write and MultiEdit with non-confined type
run_case "D3-Case4b: coordinator:executor Write + off-path → allow" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$OR_NONCONF\",\"agent_type\":\"coordinator:executor\",\"tool_input\":{\"file_path\":\"$OR_OFF_PATH\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 5: agent_type ABSENT + back-pointer resolves to non-confined type
# → off-path Edit → ALLOW.
# ---------------------------------------------------------------------------
OR_NOBACK_EM_SID="fixture-noback-em-sid-002"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NOBACK"
echo "$OR_NOBACK_EM_SID" > "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NOBACK/em-session-id.txt"
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/$OR_NOBACK_EM_SID"
printf '%s\t%s\t%s\t%s\n' \
  "$OR_NOBACK" "claude-sonnet-4-6" "coordinator:enricher" "2026-07-01T00:00:00Z" \
  > "$TMP_ROOT/.git/coordinator-sessions/$OR_NOBACK_EM_SID/dispatched-agents.txt"

run_case "D3-Case5: agent_type absent, back-ptr=coordinator:enricher (non-confined) + off-path → allow" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_NOBACK\",\"tool_input\":{\"file_path\":\"$OR_OFF_PATH\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# REGRESSION: eng-director (review persona, now unconfined) off-path Edit → ALLOW.
# Proves the fix: review personas are no longer in the confined set and must NOT
# be blocked from writing outside state/review-trail/findings/.
# Model: same shape as D3-Case4 (coordinator:executor non-confined → allow).
# ---------------------------------------------------------------------------
OR_ENGDIR_AGENT="ff889900bb3344555"  # bare hex fixture
run_case "REGRESSION: eng-director (persona, now unconfined) off-path Edit → allow" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$OR_ENGDIR_AGENT\",\"agent_type\":\"coordinator:eng-director\",\"tool_input\":{\"file_path\":\"docs/plans/x.md\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 11: SSOT parity — inline-fallback SET in this hook is identical to
# the lib _cs_is_confined_findings_agent SET.
# D2 added inline fallbacks to each guard; this test fails loud if they drift.
# ---------------------------------------------------------------------------
_LIB_PATH_SSOT="$SCRIPT_DIR/../../lib/coordinator-session.sh"
[[ ! -f "$_LIB_PATH_SSOT" ]] && _LIB_PATH_SSOT="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"

# Source the lib to access _cs_is_confined_findings_agent.
if [[ ! -f "$_LIB_PATH_SSOT" ]]; then
  echo "FAIL: SSOT11: lib not found at $_LIB_PATH_SSOT — cannot verify parity"
  FAIL=$((FAIL + 1))
else
  # shellcheck source=/dev/null
  source "$_LIB_PATH_SSOT"

  # Canonical confined set as defined in the lib and expected in the inline fallback.
  # Reduced to coordinator:code-reviewer ONLY on 2026-07-01 — review personas removed
  # (trusted full-tool Opus; self-persist via snippet, not enforced tool-stripping).
  SSOT_TYPES=(
    "coordinator:code-reviewer"
  )
  SSOT_NON_MEMBERS=("coordinator:executor" "coordinator:enricher" "coordinator:review-integrator")

  # Extract the inline fallback block from this hook (between the "Lib failed to load"
  # comment and the first "esac" that closes it — the _is_confined_findings_agent body).
  _WRITE_FALLBACK=$(sed -n '/Lib failed to load/,/^[[:space:]]*esac/p' "$HOOK" 2>/dev/null || true)

  for _t in "${SSOT_TYPES[@]}"; do
    # (a) lib predicate returns 0 for each type in the set.
    if declare -f _cs_is_confined_findings_agent >/dev/null 2>&1 && _cs_is_confined_findings_agent "$_t"; then
      echo "PASS: SSOT11-lib: '$_t' is confined in lib predicate"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-lib: '$_t' is confined in lib predicate"
      FAIL=$((FAIL + 1))
    fi
    # (b) type appears in the inline fallback block of the write guard.
    if echo "$_WRITE_FALLBACK" | grep -qF "$_t"; then
      echo "PASS: SSOT11-write-guard fallback: '$_t' present"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-write-guard fallback: '$_t' missing — inline fallback has drifted from lib"
      FAIL=$((FAIL + 1))
    fi
  done

  # Non-members must NOT be in the lib predicate.
  for _t in "${SSOT_NON_MEMBERS[@]}"; do
    if declare -f _cs_is_confined_findings_agent >/dev/null 2>&1 && ! _cs_is_confined_findings_agent "$_t"; then
      echo "PASS: SSOT11-lib: '$_t' correctly NOT confined"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-lib: '$_t' is unexpectedly confined — set has grown beyond spec"
      FAIL=$((FAIL + 1))
    fi
    # Non-members must NOT appear in the inline fallback.
    if ! echo "$_WRITE_FALLBACK" | grep -qF "$_t"; then
      echo "PASS: SSOT11-write-guard fallback: '$_t' correctly absent"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-write-guard fallback: '$_t' found — fallback has an extra member"
      FAIL=$((FAIL + 1))
    fi
  done
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-reviewer-write-outside-sidecar: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
