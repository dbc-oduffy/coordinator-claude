#!/usr/bin/env bash
# Test suite for block-reviewer-bash-outside-allowlist.sh PreToolUse(Bash) hook.
# Purpose: synthetic PreToolUse JSON payload units verifying that coordinator:code-
# reviewer subagents are confined to a single Bash command form (coordinator-doc-new
# --type review-findings only), while executors and the top-level EM remain unconfined.
#
# Spec backlink: docs/plans/2026-06-30-reviewer-findings-self-persist.md § Bash-guard
#
# AC coverage:
#   AC-EM    — no agent_id (top-level EM Bash) → ALLOW regardless of command.
#   AC-EX    — executor subagent running rm → ALLOW (not a reviewer type).
#   AC-A1    — reviewer running coordinator-doc-new --type review-findings → ALLOW.
#   AC-A2    — reviewer running path-prefixed coordinator-doc-new → ALLOW.
#   AC-A3    — reviewer running bash-invoked coordinator-doc-new → ALLOW.
#   AC-D1    — reviewer running rm -rf → DENY.
#   AC-D2    — reviewer running cat ~/.claude/... → DENY.
#   AC-D3    — reviewer chaining coordinator-doc-new with ; → DENY.
#   AC-D4    — reviewer chaining coordinator-doc-new with && → DENY.
#   AC-D5    — reviewer running curl → DENY.
#   AC-D6    — reviewer piping coordinator-doc-new output → DENY (| metacharacter).
#   AC-D7    — reviewer redirecting output → DENY (> metacharacter).
#   AC-D8    — reviewer invoking coordinator-doc-new without --type review-findings → DENY.
#   AC-MISS  — subagent with unknown type running rm → ALLOW (lookup-fail → fail-open).
#
# Harness pattern mirrors test-block-reviewer-write-outside-sidecar.sh:
#   run_case pipes JSON payload to the hook under TMP_ROOT git repo and checks
#   presence/absence of permissionDecision:deny in stdout.

set -uo pipefail
# Silence the illegal-filename nudge (unrelated to this test's concern).
export COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-reviewer-bash-outside-allowlist.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Agent ids — lowercase hex, 17 chars (cs_build_canonical_agent_id lib format).
# ---------------------------------------------------------------------------
REVIEWER_AGENT="af112333608948883"
EXECUTOR_AGENT="bc223444719a59994"
UNKNOWN_AGENT="cc334555720b59995"   # no back-pointer record → lookup fails → allow

EM_SID="test-em-session-001"

# ---------------------------------------------------------------------------
# Throwaway git repo so the hook can resolve GIT_ROOT via git rev-parse, and
# the back-pointer chain is reachable.
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

( cd "$TMP_ROOT" && git rev-parse --show-toplevel > /dev/null ) \
  || { echo "FAIL: git root setup failed"; exit 1; }

# -- Back-pointer for reviewer: REVIEWER_AGENT → EM_SID --
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$REVIEWER_AGENT"
printf '%s\n' "$EM_SID" \
  > "$TMP_ROOT/.git/coordinator-sessions/.agents/$REVIEWER_AGENT/em-session-id.txt"

# -- Back-pointer for executor: EXECUTOR_AGENT → EM_SID --
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$EXECUTOR_AGENT"
printf '%s\n' "$EM_SID" \
  > "$TMP_ROOT/.git/coordinator-sessions/.agents/$EXECUTOR_AGENT/em-session-id.txt"

# NOTE: UNKNOWN_AGENT intentionally has no back-pointer directory.

# -- Dispatched-agents.txt: reviewer + executor records --
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/$EM_SID"
{
  printf '%s\tclaude-sonnet-4-5\tcoordinator:code-reviewer\t2026-06-30T12:00:00Z\n' "$REVIEWER_AGENT"
  printf '%s\tclaude-sonnet-4-5\tcoordinator:executor\t2026-06-30T12:01:00Z\n' "$EXECUTOR_AGENT"
} > "$TMP_ROOT/.git/coordinator-sessions/$EM_SID/dispatched-agents.txt"

# ---------------------------------------------------------------------------
# run_case <desc> <json-payload> <expected: allow|deny>
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
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 400)"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# AC-EM — top-level EM (no agent_id) → ALLOW regardless of command.
# ---------------------------------------------------------------------------
run_case "AC-EM: EM rm -rf /tmp/x → allow (no agent_id)" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}' \
  "allow"

run_case "AC-EM: EM non-Bash tool → allow" \
  '{"tool_name":"Write","tool_input":{"file_path":"foo.md","content":"hi"}}' \
  "allow"

# ---------------------------------------------------------------------------
# AC-EX — executor subagent running rm → ALLOW (not a reviewer type).
# ---------------------------------------------------------------------------
run_case "AC-EX: executor rm -rf → allow (subagent_type=coordinator:executor)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$EXECUTOR_AGENT\",\"tool_input\":{\"command\":\"rm -rf /tmp/x\"}}" \
  "allow"

run_case "AC-EX: executor git commit → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$EXECUTOR_AGENT\",\"tool_input\":{\"command\":\"git commit -m 'chunk: update'\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# AC-MISS — unknown agent (no back-pointer) → fail-open → ALLOW.
# ---------------------------------------------------------------------------
run_case "AC-MISS: unknown agent rm → allow (lookup fails → fail-open)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$UNKNOWN_AGENT\",\"tool_input\":{\"command\":\"rm -rf /\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# AC-A1 — reviewer running coordinator-doc-new --type review-findings → ALLOW.
# ---------------------------------------------------------------------------
run_case "AC-A1: reviewer coordinator-doc-new --type review-findings → allow (basic)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings\"}}" \
  "allow"

run_case "AC-A1: reviewer coordinator-doc-new with --plan and --chunk → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings --plan docs/plans/2026-06-30-foo.md --chunk C1\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# AC-A2 — path-prefixed coordinator-doc-new → ALLOW.
# ---------------------------------------------------------------------------
run_case "AC-A2: reviewer bin/coordinator-doc-new --type review-findings → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"bin/coordinator-doc-new --type review-findings --plan docs/plans/foo.md\"}}" \
  "allow"

run_case "AC-A2: reviewer absolute path coordinator-doc-new → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"/home/user/.claude/bin/coordinator-doc-new --type review-findings\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# AC-A3 — bash-invoked coordinator-doc-new → ALLOW.
# ---------------------------------------------------------------------------
run_case "AC-A3: reviewer bash /path/coordinator-doc-new --type review-findings → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"bash /home/user/.claude/bin/coordinator-doc-new --type review-findings --chunk C2\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# AC-D1 — reviewer running rm -rf → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D1: reviewer rm -rf → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"rm -rf /tmp/evil\"}}" \
  "deny"

run_case "AC-D1b: reviewer rm -rf / (root) → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"rm -rf /\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D2 — reviewer running cat on private file → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D2: reviewer cat ~/.claude/CLAUDE.md → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"cat ~/.claude/CLAUDE.md\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D3 — reviewer chaining with semicolon → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D3: reviewer coordinator-doc-new; rm x → deny (semicolon chaining)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings; rm x\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D4 — reviewer chaining with && → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D4: reviewer coordinator-doc-new && rm x → deny (&& chaining)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings && rm x\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D5 — reviewer running curl → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D5: reviewer curl https://evil.com → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"curl https://evil.com\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D6 — reviewer piping output → DENY (| metacharacter).
# ---------------------------------------------------------------------------
run_case "AC-D6: reviewer coordinator-doc-new | tee log → deny (pipe)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings | tee /tmp/log\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D7 — reviewer redirecting output → DENY (> metacharacter).
# ---------------------------------------------------------------------------
run_case "AC-D7: reviewer coordinator-doc-new > /dev/null → deny (redirect)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings > /dev/null\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D8 — reviewer running coordinator-doc-new without --type review-findings → DENY.
# ---------------------------------------------------------------------------
run_case "AC-D8: reviewer coordinator-doc-new --type flight-recorder → deny (wrong type)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type flight-recorder\"}}" \
  "deny"

run_case "AC-D8: reviewer coordinator-doc-new (no --type at all) → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D9 — missing metacharacters: < (stdin redirect) and bare & (background fork).
# Review: code-reviewer-selfpersist — F4 adding < and & deny cases.
# ---------------------------------------------------------------------------
run_case "AC-D9: reviewer stdin redirect < → deny (< metacharacter)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings < /etc/passwd\"}}" \
  "deny"

run_case "AC-D9: reviewer background fork & → deny (bare & metacharacter)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings &\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# AC-D10 — --type word-boundary: --type review-findingsXYZ must not pass.
# Review: code-reviewer-selfpersist — F5 tighten --type to word-boundary.
# ---------------------------------------------------------------------------
run_case "AC-D10: reviewer --type review-findingsXYZ → deny (type prefix, not exact)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$REVIEWER_AGENT\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findingsXYZ\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# D3 P0.2 — OR-resolver two-sided deny-gate cases for Bash guard
# Spec backlink: docs/plans/2026-07-01-findings-agents-self-persist.md § D3
#
# Cases 7–10 test the new agent_type-primary / back-pointer-secondary OR-resolver.
# Cases 7–9 use PRIMARY leg (agent_type present in payload, no back-pointer needed).
# Case 10 uses SECONDARY leg (NAMED dispatch: back-pointer resolves confined type).
# Case 11 tests SSOT parity between inline fallback and lib.
# ---------------------------------------------------------------------------

# Shared fixture agents for the new cases.
# OR_PRIMARY_AGENT: confined via agent_type primary leg, bare hex, no separate back-pointer record needed.
OR_PRIMARY_AGENT="cc556677880011222"
# OR_NONCONF_AGENT: explicitly non-confined type, bare hex, no marker.
OR_NONCONF_AGENT="dd667788991122333"

# Payload for named dispatch (SECONDARY leg / Case 10).
# agent_id uses the aNAME-<16hex> harness format.
# session_id used by resolve_subagent_identity: short = session_id[:8] = "test-ses"
# canonical_id = "SomeName@session-test-ses"
OR_NAMED_RAW_ID="aSomeName-1234567890abcdef"
OR_NAMED_SESSION_ID="test-session-abc12345"
OR_NAMED_CANONICAL="SomeName@session-test-ses"
OR_NAMED_EM_SID="fixture-named-bash-em-001"

# Set up back-pointer chain for Case 10: NAMED confined via back-pointer.
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NAMED_CANONICAL"
printf '%s\n' "$OR_NAMED_EM_SID" \
  > "$TMP_ROOT/.git/coordinator-sessions/.agents/$OR_NAMED_CANONICAL/em-session-id.txt"
# Dispatch record: canonical_id → coordinator:code-reviewer (the confined type).
# Note: dispatched-agents.txt records live in a DIFFERENT em_sid than the existing
# $EM_SID to avoid collision. The bash guard looks up back-pointer by AGENT_ID
# (which is the resolved canonical id, not the raw aNAME-<hex>).
mkdir -p "$TMP_ROOT/.git/coordinator-sessions/$OR_NAMED_EM_SID"
printf '%s\t%s\t%s\t%s\n' \
  "$OR_NAMED_CANONICAL" "claude-sonnet-4-6" "coordinator:code-reviewer" "2026-07-01T00:00:00Z" \
  > "$TMP_ROOT/.git/coordinator-sessions/$OR_NAMED_EM_SID/dispatched-agents.txt"

# ---------------------------------------------------------------------------
# Case 7: Confined agent (agent_type IN confined set, PRIMARY leg) + non-scaffolder
# command → DENY.
# This uses the primary leg only (agent_type present, no back-pointer set up for
# OR_PRIMARY_AGENT — proves agent_type alone confines the Bash call).
# ---------------------------------------------------------------------------
run_case "D3-Case7: agent_type=coordinator:code-reviewer (primary leg) + rm -rf x → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_PRIMARY_AGENT\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"command\":\"rm -rf x\"}}" \
  "deny"

run_case "D3-Case7b: agent_type=coordinator:code-reviewer (primary leg) + cat /etc/passwd → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_PRIMARY_AGENT\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"command\":\"cat /etc/passwd\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# Case 8: Confined agent (agent_type IN confined set, PRIMARY leg) + clean
# coordinator-doc-new --type review-findings → ALLOW.
# ---------------------------------------------------------------------------
run_case "D3-Case8: agent_type=coordinator:code-reviewer (primary leg) + coordinator-doc-new --type review-findings → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_PRIMARY_AGENT\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings\"}}" \
  "allow"

run_case "D3-Case8b: agent_type=coordinator:code-reviewer (primary leg) + coordinator-doc-new --type review-findings --plan p.md → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_PRIMARY_AGENT\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"command\":\"coordinator-doc-new --type review-findings --plan docs/plans/p.md\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 9: NON-confined agent (coordinator:executor) + arbitrary command → ALLOW
# (fail-open: executors/enrichers/integrators MUST keep Bash freedom).
# ---------------------------------------------------------------------------
run_case "D3-Case9 (CRITICAL fail-open): agent_type=coordinator:executor + rm -rf → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_NONCONF_AGENT\",\"agent_type\":\"coordinator:executor\",\"tool_input\":{\"command\":\"rm -rf /tmp/work\"}}" \
  "allow"

run_case "D3-Case9b: agent_type=coordinator:enricher + git commit → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_NONCONF_AGENT\",\"agent_type\":\"coordinator:enricher\",\"tool_input\":{\"command\":\"git commit -m 'test'\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 10: NAMED confined dispatch via SECONDARY back-pointer leg.
# agent_id=aNAME-<16hex>, agent_type=SomeName (NOT in confined set by name),
# session_id drives canonical id derivation, back-pointer resolves
# subagent_type=coordinator:code-reviewer → non-scaffolder command → DENY.
# ---------------------------------------------------------------------------
run_case "D3-Case10: NAMED agent (agent_type=SomeName, back-ptr=coordinator:code-reviewer) + rm x → deny" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_NAMED_RAW_ID\",\"agent_type\":\"SomeName\",\"session_id\":\"$OR_NAMED_SESSION_ID\",\"tool_input\":{\"command\":\"rm x\"}}" \
  "deny"

run_case "D3-Case10b: NAMED confined + curl evil.com → deny (secondary leg)" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_NAMED_RAW_ID\",\"agent_type\":\"SomeName\",\"session_id\":\"$OR_NAMED_SESSION_ID\",\"tool_input\":{\"command\":\"curl https://evil.com\"}}" \
  "deny"

# ---------------------------------------------------------------------------
# REGRESSION: eng-director (review persona, now unconfined) arbitrary Bash → ALLOW.
# Proves the fix: review personas are no longer confined and must NOT be blocked
# from running arbitrary Bash commands.
# Model: same shape as D3-Case9 (coordinator:executor non-confined → allow).
# ---------------------------------------------------------------------------
OR_ENGDIR_BASH_AGENT="gg990011cc4455666"  # bare hex fixture
run_case "REGRESSION: eng-director (persona, now unconfined) arbitrary Bash → allow" \
  "{\"tool_name\":\"Bash\",\"agent_id\":\"$OR_ENGDIR_BASH_AGENT\",\"agent_type\":\"coordinator:eng-director\",\"tool_input\":{\"command\":\"ls docs/plans/\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# Case 11: SSOT parity — inline-fallback SET in this hook is identical to
# the lib _cs_is_confined_findings_agent SET.
# ---------------------------------------------------------------------------
_LIB_PATH_SSOT="$SCRIPT_DIR/../../lib/coordinator-session.sh"
[[ ! -f "$_LIB_PATH_SSOT" ]] && _LIB_PATH_SSOT="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"

if [[ ! -f "$_LIB_PATH_SSOT" ]]; then
  echo "FAIL: SSOT11: lib not found at $_LIB_PATH_SSOT"
  FAIL=$((FAIL + 1))
else
  # shellcheck source=/dev/null
  source "$_LIB_PATH_SSOT"

  # Reduced to coordinator:code-reviewer ONLY on 2026-07-01 — review personas removed
  # (trusted full-tool Opus; self-persist via snippet, not enforced tool-stripping).
  SSOT_TYPES=(
    "coordinator:code-reviewer"
  )
  SSOT_NON_MEMBERS=("coordinator:executor" "coordinator:enricher" "coordinator:review-integrator")

  # Extract the inline fallback block from this hook.
  _BASH_FALLBACK=$(sed -n '/Lib failed to load — inline fallback/,/^[[:space:]]*esac/p' "$HOOK" 2>/dev/null || true)

  for _t in "${SSOT_TYPES[@]}"; do
    # (a) lib predicate returns 0.
    if declare -f _cs_is_confined_findings_agent >/dev/null 2>&1 && _cs_is_confined_findings_agent "$_t"; then
      echo "PASS: SSOT11-lib: '$_t' is confined in lib predicate"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-lib: '$_t' is confined in lib predicate"
      FAIL=$((FAIL + 1))
    fi
    # (b) type present in inline fallback.
    if echo "$_BASH_FALLBACK" | grep -qF "$_t"; then
      echo "PASS: SSOT11-bash-guard fallback: '$_t' present"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-bash-guard fallback: '$_t' missing — inline fallback has drifted from lib"
      FAIL=$((FAIL + 1))
    fi
  done

  for _t in "${SSOT_NON_MEMBERS[@]}"; do
    if declare -f _cs_is_confined_findings_agent >/dev/null 2>&1 && ! _cs_is_confined_findings_agent "$_t"; then
      echo "PASS: SSOT11-lib: '$_t' correctly NOT confined"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-lib: '$_t' is unexpectedly confined"
      FAIL=$((FAIL + 1))
    fi
    if ! echo "$_BASH_FALLBACK" | grep -qF "$_t"; then
      echo "PASS: SSOT11-bash-guard fallback: '$_t' correctly absent"
      PASS=$((PASS + 1))
    else
      echo "FAIL: SSOT11-bash-guard fallback: '$_t' found — fallback has extra member"
      FAIL=$((FAIL + 1))
    fi
  done
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-reviewer-bash-outside-allowlist: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
