#!/usr/bin/env bash
# test-selfpersist-reviewer-e2e.sh — End-to-end harness for the reviewer-findings
# write-guard and shared format-constant agreement.
#
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
#
# -----------------------------------------------------------------------
# What this harness covers (fully automated, no simulation):
#   S1 — Format-agreement assertion: assert that the guard sources
#         lib/coordinator-session.sh, that _cs_canonical_agent_id_format_ok accepts
#         a known-good hex id, and that it rejects a non-hex id.  Divergence between
#         the guard and the lib constant causes this section to FAIL.
#   S4 — OR-resolver primary-leg integration: confirm agent_type-based confinement
#         works without a back-pointer (Mode A, foreground/naked dispatch path).
#
# What the EM provides separately (live, not in this harness):
#   S3 (optional hook) — If CAPTURED_AGENT_ID is set in the environment, this harness
#         additionally asserts the captured id matches CS_CANONICAL_AGENT_ID_RE.
#
# Note: S2 (cs_write_review_claim marker exercise) was retired when Mode B confinement
# was removed.  See cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md.
#
# Usage:
#   bash hooks/tests/test-selfpersist-reviewer-e2e.sh           # S1 + S4 only
#   CAPTURED_AGENT_ID=<hex> bash ...                             # S1 + S4 + S3 format check
# -----------------------------------------------------------------------

set -uo pipefail
export COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-reviewer-write-outside-sidecar.sh"

if [[ ! -f "$HOOK" ]]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

# Source the lib — needed for _cs_canonical_agent_id_format_ok.
LIB_PATH="$SCRIPT_DIR/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"
if [[ ! -f "$LIB_PATH" ]]; then
  echo "FAIL: lib not found at $LIB_PATH"
  exit 1
fi
# shellcheck source=/dev/null
source "$LIB_PATH"

PASS=0
FAIL=0

pass_case() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail_case() { echo "FAIL: $1"; echo "      $2"; FAIL=$((FAIL + 1)); }

# ---------------------------------------------------------------------------
# S1 — Format-agreement assertion (closes the Staff Engineer R3-F1)
#
# Three checks:
#   S1a — guard file references coordinator-session.sh (grep-level source check)
#   S1b — _cs_canonical_agent_id_format_ok accepts a known-good 17-char hex id
#   S1c — _cs_canonical_agent_id_format_ok rejects a non-hex id
#   S1d — CS_CANONICAL_AGENT_ID_RE is set after sourcing lib
#
# If S1a fails, the guard's inline fallback is the only defence against divergence.
# If S1b or S1c fail, the predicate itself is broken.
# If S1d fails, the constant was not exported from the lib.
# ---------------------------------------------------------------------------
echo "=== S1: Format-agreement assertion ==="

# S1a: Guard references the shared lib (grep for the source stanza).
if grep -q 'coordinator-session\.sh' "$HOOK"; then
  pass_case "S1a: guard sources coordinator-session.sh"
else
  fail_case "S1a: guard sources coordinator-session.sh" \
    "guard does not reference lib — inline fallback only, divergence not caught structurally"
fi

# S1b: Predicate accepts a known-good 17-char hex id (probe-captured format).
_GOOD_HEX="af112333608948883"
if _cs_canonical_agent_id_format_ok "$_GOOD_HEX"; then
  pass_case "S1b: predicate accepts known-good hex id ($_GOOD_HEX)"
else
  fail_case "S1b: predicate accepts known-good hex id" \
    "$_GOOD_HEX was rejected by _cs_canonical_agent_id_format_ok"
fi

# S1c: Predicate rejects a non-hex id.
_BAD_ID="not-a-hex-id"
if ! _cs_canonical_agent_id_format_ok "$_BAD_ID"; then
  pass_case "S1c: predicate rejects non-hex id ($_BAD_ID)"
else
  fail_case "S1c: predicate rejects non-hex id" \
    "$_BAD_ID was accepted — predicate is too permissive"
fi

# S1d: CS_CANONICAL_AGENT_ID_RE constant is populated.
if [[ -n "${CS_CANONICAL_AGENT_ID_RE:-}" ]]; then
  pass_case "S1d: CS_CANONICAL_AGENT_ID_RE is set (${CS_CANONICAL_AGENT_ID_RE})"
else
  fail_case "S1d: CS_CANONICAL_AGENT_ID_RE is set" \
    "variable not populated after sourcing lib — constant missing or renamed"
fi

# ---------------------------------------------------------------------------
# S4 — OR-resolver integration: primary-leg (agent_type-based) confinement.
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md § D3
#
# Tests that the write guard confines agents via agent_type (primary leg) without
# requiring a back-pointer.  Feeds agent_type directly in the payload (UNNAMED
# bare-hex agent_id, no back-pointer record) and asserts confinement by type alone.
# ---------------------------------------------------------------------------
echo "=== S4: OR-resolver primary-leg integration ==="

# Throwaway git repo — guard resolves GIT_ROOT via git rev-parse from cwd.
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

(
  cd "$TMP_ROOT"
  git init -q -b main
  git config user.email t@t.t
  git config user.name t
  git config commit.gpgsign false
) || { fail_case "S4-setup: git init" "git init failed in $TMP_ROOT"; }

_GIT_ROOT_CHECK=$(cd "$TMP_ROOT" && git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$_GIT_ROOT_CHECK" ]]; then
  fail_case "S4-setup: git root resolves" "git rev-parse failed — guard will fail-open"
fi

# run_guard_case <desc> <json-payload> <expected: allow|deny>
run_guard_case() {
  local desc="$1" payload="$2" expected="$3"
  local out actual_exit
  out=$(cd "$TMP_ROOT" && printf '%s' "$payload" | bash "$HOOK" 2>/dev/null)
  actual_exit=$?
  local has_deny=0
  echo "$out" | grep -q '"permissionDecision":"deny"' && has_deny=1
  local expected_deny=0
  [[ "$expected" == "deny" ]] && expected_deny=1
  if [[ "$actual_exit" -eq 0 && "$has_deny" -eq "$expected_deny" ]]; then
    pass_case "$desc"
  else
    fail_case "$desc" \
      "expected exit=0 deny=$expected_deny, got exit=$actual_exit deny=$has_deny; out=$(printf '%s' "$out" | head -c 300)"
  fi
}

_OR_AGENT_CONFINED="ff112233aabbccdd4"   # bare hex, will carry agent_type in set
_OR_AGENT_EXECUTOR="ee998877665544332"   # bare hex, coordinator:executor (non-confined)

_FINDINGS_PATH="state/review-trail/findings/2026-07-01-s4-test.md"
_NON_FINDINGS="hooks/scripts/block-reviewer-write-outside-sidecar.sh"

# S4a: Confined agent (agent_type=coordinator:code-reviewer, no back-pointer) + off-path → DENY.
# Proves agent_type primary leg closes the foreground/naked fail-open hole.
run_guard_case "S4a: agent_type=coordinator:code-reviewer (no back-ptr) + off-path → DENY" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$_OR_AGENT_CONFINED\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"file_path\":\"$_NON_FINDINGS\"}}" \
  "deny"

# S4b: Confined agent (agent_type=coordinator:code-reviewer, no back-pointer) + on-path → ALLOW.
run_guard_case "S4b: agent_type=coordinator:code-reviewer (no back-ptr) + on-path findings/ → ALLOW" \
  "{\"tool_name\":\"Edit\",\"agent_id\":\"$_OR_AGENT_CONFINED\",\"agent_type\":\"coordinator:code-reviewer\",\"tool_input\":{\"file_path\":\"$_FINDINGS_PATH\"}}" \
  "allow"

# S4c: Non-confined agent (agent_type=coordinator:executor, no marker) + off-path → ALLOW.
# Critical regression guard: executors must never be blocked.
run_guard_case "S4c: agent_type=coordinator:executor + off-path + no marker → ALLOW (fail-open)" \
  "{\"tool_name\":\"Write\",\"agent_id\":\"$_OR_AGENT_EXECUTOR\",\"agent_type\":\"coordinator:executor\",\"tool_input\":{\"file_path\":\"$_NON_FINDINGS\"}}" \
  "allow"

# ---------------------------------------------------------------------------
# S3 — Optional: captured agent_id format check (EM live-fire hook)
#
# Set CAPTURED_AGENT_ID=<hex> after a real reviewer dispatch completes and
# the agent_id is captured from tool_response.agent_id.  Confirms it matches
# CS_CANONICAL_AGENT_ID_RE — closing the loop between the format the guard
# branches on and the format the harness actually produced.
# ---------------------------------------------------------------------------
if [[ -n "${CAPTURED_AGENT_ID:-}" ]]; then
  echo "=== S3: Captured agent_id format check (AC4 live-fire half) ==="
  if _cs_canonical_agent_id_format_ok "$CAPTURED_AGENT_ID"; then
    pass_case "S3: captured agent_id matches CS_CANONICAL_AGENT_ID_RE: $CAPTURED_AGENT_ID"
  else
    fail_case "S3: captured agent_id matches CS_CANONICAL_AGENT_ID_RE" \
      "CAPTURED_AGENT_ID='$CAPTURED_AGENT_ID' does not match '${CS_CANONICAL_AGENT_ID_RE}'"
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "test-selfpersist-reviewer-e2e: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
