#!/usr/bin/env bash
# test-wsc-invoke-wire-contract.sh — wire-contract smoke test for the workstream-complete
# cc_invoke seam (ceremony.wsc_resolve + ceremony.wsc_commit param surface).
#
# Purpose: durable guard against cross-repo op-param drift between DoE SKILL (Steps D-1/D-5)
# and the example-orchestration-hub ops they drive via coordinator_core.invoke. ExampleOrchestrationHub evolves on its own
# branch; this test catches drift before it silently breaks the ceremony pipeline.
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C4.3
# the Director of Engineering F3 / prior-art #4: test authors the durable wire-contract assertions.
#
# PASS:  wsc_resolve rc 0 + result carries required top-level keys; wsc_commit SKILL key
#        set is a subset of op-consumed params.
# SKIP:  EXAMPLE_ORCHESTRATION_HUB_ROOT unresolvable or coordinator_core won't import (seam absent — not a
#        failure in envs without a example-orchestration-hub checkout).
# FAIL:  Expected key missing from wsc_resolve result, or SKILL passes a key wsc_commit.py
#        does not consume (both are drift signals).
#
# Usage: bash coordinator/skills/workstream-complete/tests/test-wsc-invoke-wire-contract.sh
# Exit:  0 = PASS or SKIP; 1 = FAIL.
#
# Cross-platform: bash >=4 + BSD coreutils.
# Concurrency: stateless; wsc_resolve may write state/ceremony/wsc-receipt.json (idempotent).

# ---------------------------------------------------------------------------
# Bash >=4 guard — must parse safely on bash 3.2.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'test-wsc-invoke-wire-contract.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS: brew install bash\n' >&2
  # Review: code-reviewer F6 — bash<4 is a pre-condition failure (env can't run), not a test
  # assertion failure; per the test's own exit-code contract (0=PASS/SKIP, 1=FAIL), exit 0 (SKIP).
  exit 0
fi

set -uo pipefail

# ---------------------------------------------------------------------------
# Locate the repo root and coordinator lib.
# Resolve from the script's own path — works regardless of CWD.
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
# skills/workstream-complete/tests/ → ../../.. → coordinator root
_CC_ROOT="$(cd "${_SCRIPT_DIR}/../../.." 2>/dev/null && pwd)"

# Standard cc_root resolution (mirrors SKILL Step D-1 / D-5 verbatim pattern):
#   Priority 1: $CLAUDE_PLUGIN_ROOT (installed plugin path)
#   Priority 2: .doe-root file (fallback for non-plugin envs)
#   Priority 3: computed from this test's own path (test-only bootstrap)
_cc_root="${CLAUDE_PLUGIN_ROOT:-}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { [ -n "$_cc_root" ] && [ -d "$_cc_root" ] && echo "[coordinator] WARNING: '$_cc_root' outside trusted prefix — hook degraded" >&2; _cc_root=''; }
if [[ -z "${_cc_root}" ]]; then
  _doe_root_file="${CLAUDE_HOME:-$HOME}/.claude/.doe-root"
  if [[ -f "${_doe_root_file}" ]]; then
    _cc_root="$(cat "${_doe_root_file}" 2>/dev/null)/coordinator"
  fi
fi
if [[ -z "${_cc_root}" || ! -f "${_cc_root}/lib/coordinator-core-invoke.sh" ]]; then
  # Fallback: resolve from this test file's known position in the repo tree.
  _cc_root="${_CC_ROOT}"
fi

_INVOKE_LIB="${_cc_root}/lib/coordinator-core-invoke.sh"

PASS=0
FAIL=0
SKIP_COUNT=0

_pass() { printf 'PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
_fail() { printf 'FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }
_skip() { printf 'SKIP: %s\n' "$1"; SKIP_COUNT=$((SKIP_COUNT + 1)); }

# ---------------------------------------------------------------------------
# JSON key-presence check — jq preferred; python3 fallback.
# Usage: _json_has_key <json_string> <key>
# Returns 0 if key present at top level, 1 otherwise.
# ---------------------------------------------------------------------------
_json_has_key() {
  local json="$1"
  local key="$2"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "${json}" | jq -e --arg k "${key}" 'has($k)' >/dev/null 2>&1
  else
    printf '%s' "${json}" | python3 -c "  # popup-safe-env-suppressed
import json, sys
try:
    d = json.loads(sys.stdin.read())
    # Review: code-reviewer F8 — pass key via sys.argv[1] to avoid shell source-interpolation
    # (interpolating \${key} into Python source would break on keys containing single quotes).
    sys.exit(0 if sys.argv[1] in d else 1)
except Exception:
    sys.exit(1)
" "${key}"
  fi
}

# ---------------------------------------------------------------------------
# Guard: invoke lib must exist.
# ---------------------------------------------------------------------------
if [[ ! -f "${_INVOKE_LIB}" ]]; then
  _skip "coordinator-core-invoke.sh not found at ${_INVOKE_LIB} (case-a) — smoke test requires coordinator_core reachable"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Source cc_invoke (safe — idempotency-guarded inside).
# ---------------------------------------------------------------------------
# shellcheck disable=SC1090
source "${_INVOKE_LIB}" || {
  _skip "failed to source coordinator-core-invoke.sh — smoke test requires coordinator_core reachable"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 0
}

# ---------------------------------------------------------------------------
# Resolve repo root + test SID.
# ---------------------------------------------------------------------------
# --show-toplevel always emits an absolute path; --git-common-dir may emit a relative path
# (e.g. `../../..`) when called via `git -C <subdir>`, which breaks the invoke seam that
# requires an absolute repo_root. Use --show-toplevel unconditionally here.
REPO="$(git -C "${_SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)" || REPO=""
if [[ -z "${REPO}" ]]; then
  _skip "git repo root not resolvable from script location — smoke test requires a git repo"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 0
fi

# SID: prefer live sentinel, then env vars, then synthetic.
TEST_SID=""
_sentinel="${REPO}/.git/coordinator-sessions/.current-session-id"
if [[ -f "${_sentinel}" ]]; then
  TEST_SID="$(cat "${_sentinel}" 2>/dev/null || true)"
fi
if [[ -z "${TEST_SID}" ]]; then
  TEST_SID="${CLAUDE_CODE_SESSION_ID:-${CLAUDE_SESSION_ID:-test-wire-contract-$(date +%s | tail -c 8)}}"
fi

printf '  repo: %s\n' "${REPO}"
printf '  sid:  %s\n' "${TEST_SID}"
printf '  lib:  %s\n' "${_INVOKE_LIB}"
printf '\n'

# ---------------------------------------------------------------------------
# ASSERTION 1: wsc_resolve — rc 0 + required top-level keys present.
# ---------------------------------------------------------------------------
# Required keys per SKILL.md Step D-1 return contract (wsc_resolve section).
_WSC_RESOLVE_REQUIRED_KEYS=(
  exit_code
  disposition
  # Review: code-reviewer F4 — scope_mode / nature / idempotency_guard_fired / open_memos_count
  # were absent from the assertion list; drift on these fields silently breaks the driver flow
  # (scope_mode governs ceremony path, nature feeds lesson classification).
  scope_mode
  nature
  resolved_state
  receipt_path
  j_questions
  f_slots
  b_pre_resolved
  idempotency_guard_fired
  open_memos_count
)

_stderr_tmp="$(mktemp "${TMPDIR:-/tmp}/wsc-test-err.XXXXXX")"
_wsc_resolve_rc=0
_wsc_resolve_out="$(cc_invoke ceremony.wsc_resolve "{\"sid\":\"${TEST_SID}\"}" "${REPO}" 2>"${_stderr_tmp}")" \
  || _wsc_resolve_rc=$?
_wsc_resolve_stderr="$(cat "${_stderr_tmp}" 2>/dev/null || true)"
rm -f "${_stderr_tmp}" 2>/dev/null || true

if [[ "${_wsc_resolve_rc}" -eq 2 ]]; then
  # Distinguish seam-absent (case-a SKIP) from op-errored (case-b FAIL).
  if printf '%s\n' "${_wsc_resolve_stderr}" | grep -qiE \
      "ImportError|ModuleNotFoundError|No module named|engine will not import|engine won[']t import|spawn failure|EXAMPLE_ORCHESTRATION_HUB_ROOT"; then
    _skip "example-orchestration-hub seam absent (case-a) — smoke test requires coordinator_core reachable"
    _skip "stderr: ${_wsc_resolve_stderr}"
    printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
    exit 0
  else
    # Case-b: seam present but op errored — that IS a test failure.
    _fail "wsc_resolve rc 2 (op errored, not seam-absent) — stderr: ${_wsc_resolve_stderr}"
    printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
    exit 1
  fi
fi

if [[ "${_wsc_resolve_rc}" -ne 0 ]]; then
  _fail "wsc_resolve unexpected rc=${_wsc_resolve_rc}; stderr: ${_wsc_resolve_stderr}"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 1
fi

# rc 0 — SUCCESS ENVELOPE. Check top-level exit_code per two-signal contract.
# cc_invoke strips the jsonrpc wrapper; result is bare — NEVER .result.exit_code.
if command -v jq >/dev/null 2>&1; then
  _op_exit_code="$(printf '%s' "${_wsc_resolve_out}" | jq -r '.exit_code // "MISSING"' 2>/dev/null)"
else
  _op_exit_code="$(printf '%s' "${_wsc_resolve_out}" | python3 -c "  # popup-safe-env-suppressed
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('exit_code', 'MISSING'))
except Exception:
    print('PARSE_ERROR')
" 2>/dev/null)"
fi

if [[ "${_op_exit_code}" == "MISSING" || "${_op_exit_code}" == "PARSE_ERROR" ]]; then
  _fail "wsc_resolve result missing top-level exit_code (not a valid op result)"
  printf '  raw output: %s\n' "${_wsc_resolve_out}"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 1
fi

# Review: code-reviewer F1 — previously only MISSING/PARSE_ERROR triggered FAIL; an exit_code=2
# (case-b op-errored) emitted a false PASS. A wire-contract test requires exit_code==0 to confirm
# the seam is live and healthy.
if [[ "${_op_exit_code}" != "0" ]]; then
  _fail "wsc_resolve op exit_code=${_op_exit_code} (expected 0 — op errored, not a seam-absent condition)"
  printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
  exit 1
fi

_pass "wsc_resolve rc 0 (SUCCESS ENVELOPE received, op exit_code=${_op_exit_code})"

# Check each required top-level key.
for _key in "${_WSC_RESOLVE_REQUIRED_KEYS[@]}"; do
  if _json_has_key "${_wsc_resolve_out}" "${_key}"; then
    _pass "wsc_resolve result has required key: ${_key}"
  else
    _fail "wsc_resolve result MISSING required top-level key: ${_key} (drift signal — check example-orchestration-hub op contract)"
    _present_keys="$(printf '%s' "${_wsc_resolve_out}" | python3 -c "  # popup-safe-env-suppressed
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(list(d.keys()))
except Exception:
    print('<parse error>')
" 2>/dev/null || echo '<parse error>')"
    printf '  keys present: %s\n' "${_present_keys}"
  fi
done

# ---------------------------------------------------------------------------
# ASSERTION 2: wsc_commit param-surface — SKILL key set ⊆ op consumed set.
# ---------------------------------------------------------------------------
# Grep op's params.get() calls from wsc_commit.py.
# Grep SKILL's Step D-5 cc_invoke ceremony.wsc_commit JSON block from SKILL.md.
# Assert: every key the SKILL passes is consumed by the op (no orphan keys).

_EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY=""
# Resolve wsc_commit.py — prefer EXAMPLE_ORCHESTRATION_HUB_ROOT (already exported by cc_invoke's _cc_resolve_deps).
if [[ -n "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" ]]; then
  _candidate="${EXAMPLE_ORCHESTRATION_HUB_ROOT}/coordinator_core/ops/ceremony/wsc_commit.py"
  [[ -f "${_candidate}" ]] && _EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY="${_candidate}"
fi
# Fallback: well-known sibling-repo path.
if [[ -z "${_EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY}" ]]; then
  _sibling_candidate="$(cd "${REPO}/../example-orchestration-hub-repo" 2>/dev/null && pwd)/coordinator_core/ops/ceremony/wsc_commit.py"
  [[ -f "${_sibling_candidate}" ]] && _EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY="${_sibling_candidate}"
fi

# Review: code-reviewer F6 — use lowercase _cc_root (post env-priority resolution) so that
# when CLAUDE_PLUGIN_ROOT is set to an installed plugin path, _SKILL_MD comes from the same root
# as _INVOKE_LIB (prevents dev-tree SKILL being tested against installed-plugin invoke lib).
_SKILL_MD="${_cc_root}/skills/workstream-complete/SKILL.md"

if [[ -z "${_EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY}" ]]; then
  _skip "wsc_commit.py not found (EXAMPLE_ORCHESTRATION_HUB_ROOT=${EXAMPLE_ORCHESTRATION_HUB_ROOT:-<unset>}) — skipping param-surface sub-assertion"
elif [[ ! -f "${_SKILL_MD}" ]]; then
  _skip "SKILL.md not found at ${_SKILL_MD} — skipping param-surface sub-assertion"
else
  # Extract op-consumed key names from wsc_commit.py.
  # Review: code-reviewer F5 — split by access pattern: params["key"] (subscript — effectively
  # required, raises KeyError if absent) vs params.get("key") (optional — has safe default).
  # Subscript keys missing from SKILL D-5 are FAILs; .get() keys missing are INFO only.
  _op_required_keys="$(grep -Eo 'params\["[^"]+"' "${_EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY}" 2>/dev/null \
    | grep -Eo '"[^"]+"' | tr -d '"' | sort -u)"
  _op_optional_keys="$(grep -Eo 'params\.get\("[^"]+"' "${_EXAMPLE_ORCHESTRATION_HUB_WSC_COMMIT_PY}" 2>/dev/null \
    | grep -Eo '"[^"]+"' | tr -d '"' | sort -u)"
  # Combined set used for the SKILL-key ⊆ op-consumed direction check.
  _op_keys_raw="$(printf '%s\n%s\n' "${_op_required_keys}" "${_op_optional_keys}" | grep -v '^$' | sort -u)"

  if [[ -z "${_op_keys_raw}" ]]; then
    _skip "could not extract params keys from wsc_commit.py — skipping param-surface sub-assertion"
  else
    # Extract the wsc_commit param key set the SKILL passes in Step D-5.
    # Review: code-reviewer F3 — stale comment described the jq shorthand form '{sid,resolved_state,…}'
    # (which yields null under `jq -n`); SKILL was corrected to the explicit form (2026-07-06).
    # Review: code-reviewer F1 — old regex '[a-zA-Z_][a-zA-Z0-9_,]*' rejected ':','$', space so
    # the explicit form '{sid:$sid, resolved_state:$resolved_state, …}' never matched.
    # Post-review, Step D-5 uses the explicit form '{sid:$sid, resolved_state:$resolved_state, …}'.
    # The key set lives in the jq object-construction line as comma-separated 'key:$var' pairs.
    # Anchor on 'commit_prose' (present only on the D-5 line, not on the D-1 single-key line)
    # to avoid matching the shorter '{sid:$sid}' line first. BSD-grep compatible (-oE, no PCRE).
    _skill_keys_raw="$(grep -oE "'\{[^}]+\}'" "${_SKILL_MD}" \
      | grep 'commit_prose' \
      | head -1 \
      | tr -d "'{}" \
      | tr ',' '\n' \
      | grep -oE '[a-zA-Z_][a-zA-Z0-9_]*:' \
      | tr -d ':' \
      | sort -u)"

    if [[ -z "${_skill_keys_raw}" ]]; then
      # Review: code-reviewer F2 — SKILL.md is in-repo; extraction failure is a test defect, not
      # env absence. SKIP gives CI false-coverage confidence (exits 0 with "12 passed, 1 skipped"
      # when ~24 should run). FAIL + exit 1 makes the defect visible.
      _fail "could not extract JSON keys from SKILL.md Step D-5 wsc_commit block — regex/extraction defect (SKILL.md is in-repo, parse failure is a test bug, not env absence)"
      printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
      exit 1
    else
      _pass "op consumed keys (from wsc_commit.py): $(printf '%s' "${_op_keys_raw}" | tr '\n' ' ')"
      _pass "SKILL Step D-5 keys (from SKILL.md):   $(printf '%s' "${_skill_keys_raw}" | tr '\n' ' ')"

      # Assert SKILL key set ⊆ op consumed set (no orphan keys passed by SKILL).
      _drift_found=0
      while IFS= read -r _skill_key; do
        [[ -z "${_skill_key}" ]] && continue
        if printf '%s\n' "${_op_keys_raw}" | grep -qxF "${_skill_key}"; then
          _pass "wsc_commit param: SKILL key '${_skill_key}' IS consumed by the op"
        else
          _fail "wsc_commit param DRIFT: SKILL passes key '${_skill_key}' but op does NOT consume it"
          _drift_found=1
        fi
      done <<< "${_skill_keys_raw}"

      # Review: code-reviewer F5 — required keys (subscript access params["key"]) absent from SKILL
      # D-5 block → FAIL (raises KeyError at runtime if missing). Optional (.get()) → INFO only.
      while IFS= read -r _req_key; do
        [[ -z "${_req_key}" ]] && continue
        if ! printf '%s\n' "${_skill_keys_raw}" | grep -qxF "${_req_key}"; then
          _fail "wsc_commit required param MISSING from SKILL D-5 block: op subscripts params[\"${_req_key}\"] (raises KeyError if absent)"
          _drift_found=1
        fi
      done <<< "${_op_required_keys}"

      # Informational: optional op keys (.get()) not present in SKILL (safe defaults — not a FAIL).
      while IFS= read -r _op_key; do
        [[ -z "${_op_key}" ]] && continue
        if ! printf '%s\n' "${_skill_keys_raw}" | grep -qxF "${_op_key}"; then
          printf 'INFO: op key '\''%s'\'' not in SKILL D-5 block (optional / out-of-scope for standard call)\n' "${_op_key}"
        fi
      done <<< "${_op_optional_keys}"

      if [[ "${_drift_found}" -eq 0 ]]; then
        _pass "wsc_commit param-surface: SKILL key set ⊆ op consumed set (no drift detected)"
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
# Review: code-reviewer F4 — assertion count floor prevents silent degradation exiting 0.
# Expected: 12 (Assertion 1: 1 rc-check + 11 key-checks) + 12 (Assertion 2: 2 summary-passes
# + 9 SKILL-key-subset-checks + 1 drift-summary) = 24 total when the example-orchestration-hub seam is reachable.
# Guarded by SKIP_COUNT -eq 0 so that legitimately-absent seam runs are not false-failed.
_EXPECTED_MIN_PASS=24
if [[ "${SKIP_COUNT}" -eq 0 && "${PASS}" -lt "${_EXPECTED_MIN_PASS}" ]]; then
  _fail "assertion count below expected minimum: got ${PASS} passed, expected >=${_EXPECTED_MIN_PASS} (possible silent degradation)"
fi
printf '\nResults: %d passed, %d failed, %d skipped\n' "${PASS}" "${FAIL}" "${SKIP_COUNT}"
[[ "${FAIL}" -eq 0 ]]
