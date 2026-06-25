#!/usr/bin/env bash
# test_step_zero_conformance.sh — conformance test for the Step Zero NDJSON emitter.
#
# Runs the bash reference emitter (scripts/lib/step_zero_emit.sh) against every case in
# the normative conformance fixture (tests/fixtures/step-zero-conformance.json) and asserts
# byte-equality with the base64-encoded expected bytes. This is the regression guard: if the
# emitter drifts from the committed fixture, this fails. Sibling repos vendor the fixture and
# run their own emitter against it the same way (base64-decode expected, assert byte-equality).
#
# Contract + protocol: docs/wiki/step-zero-emitter-contract.md.
# Regenerate the fixture on an intentional contract change: tests/fixtures/gen-step-zero-conformance.sh.
#
# Requires: bash >= 4 (mapfile), jq. jq does all base64 work via @base64 / @base64d, so there is
# no `base64 -d` vs `-D` portability trap and no NUL/newline byte-handling hazard in the source.
set -uo pipefail

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'ERROR: test_step_zero_conformance.sh requires bash >= 4 (found %s). brew install bash\n' "${BASH_VERSION:-unknown}" >&2
  exit 78
fi
if ! command -v jq >/dev/null 2>&1; then
  printf 'ERROR: jq is required for the conformance runner (base64 decode + JSON parse).\n' >&2
  exit 1
fi

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
FIXTURE="$_DIR/fixtures/step-zero-conformance.json"
# shellcheck source=../scripts/lib/step_zero_emit.sh
source "$_DIR/../scripts/lib/step_zero_emit.sh"

[[ -f "$FIXTURE" ]] || { printf 'ERROR: fixture not found: %s\n' "$FIXTURE" >&2; exit 1; }

_pass=0
_fail=0
_pass_msg() { printf 'PASS: %s\n' "$1"; _pass=$((_pass + 1)); }
_fail_msg() { printf 'FAIL: %s\n' "$1"; _fail=$((_fail + 1)); }

# Decode a single base64 token to exact bytes (jq -j: no trailing newline added).
_b64d() { jq -jn --arg s "$1" '$s | @base64d'; }

# Temp-file cleanup on ANY exit/signal. set -uo (no -e) means the runner accumulates failures
# rather than exiting on the first mismatch, so a jq error or SIGINT mid-loop would otherwise
# leak the per-case mktemp pair — the trap + accumulator close that.
_tmpfiles=()
trap 'rm -f "${_tmpfiles[@]:-}"' EXIT

# --- Structural assertions (back AC3's coverage intent mechanically) ---
_cv="$(jq -r '.contract_version // empty' "$FIXTURE")"
[[ "$_cv" == "1.1" ]] && _pass_msg "contract_version present (= $_cv)" || _fail_msg "contract_version missing/unexpected (got '${_cv:-<none>}', expected 1.1)"

_n="$(jq '.cases | length' "$FIXTURE")"
[[ "$_n" -ge 1 ]] && _pass_msg "fixture has $_n cases" || _fail_msg "fixture has no cases"

# Per-value inclusion (resilient to fixture growth — no two-place hardcoded-string edit on enum change).
for _s in pass fail warn inconclusive; do
  jq -e --arg s "$_s" '[.cases[].input.status] | index($s) != null' "$FIXTURE" >/dev/null \
    && _pass_msg "status '$_s' covered" || _fail_msg "status '$_s' NOT covered"
done
for _sv in hard semi-hard advisory; do
  jq -e --arg s "$_sv" '[.cases[].input.severity] | index($s) != null' "$FIXTURE" >/dev/null \
    && _pass_msg "severity '$_sv' covered" || _fail_msg "severity '$_sv' NOT covered"
done

# --- Per-case byte-equality ---
# NOTE: the fixture contains TWO intentionally distinct clone_auth cases:
#   (1) inconclusive/advisory — network-unreachable scenario (probe can't determine auth state)
#   (2) warn/semi-hard       — auth-failure scenario (probe determined auth is absent)
# Do NOT consolidate them into one case; they exercise different status/severity combinations.
# Review: code-reviewer — doc comment added so a future fixture editor doesn't delete one.
#
# Extract the 5 input fields as base64 tokens (one per line — base64 has no embedded
# newline/NUL, so mapfile reads them cleanly and bytes survive intact through decode).
for ((i = 0; i < _n; i++)); do
  mapfile -t _b64 < <(jq -r --argjson i "$i" '.cases[$i].input | (.name, .status, .severity, .detail, .remediation) | @base64' "$FIXTURE")
  # Review: code-reviewer — guard against jq extraction failures yielding empty/short arrays
  # that would produce a misleading byte-MISMATCH rather than a parse error.
  if [[ "${#_b64[@]}" -ne 5 ]]; then
    _fail_msg "case $i: jq extraction produced ${#_b64[@]} fields (expected 5) — fixture parse error or schema mismatch"
    continue
  fi
  _name="$(_b64d "${_b64[0]}")"
  _status="$(_b64d "${_b64[1]}")"
  _severity="$(_b64d "${_b64[2]}")"
  _detail="$(_b64d "${_b64[3]}")"
  _remediation="$(_b64d "${_b64[4]}")"

  _exp_file="$(mktemp)"; _tmpfiles+=("$_exp_file")
  _act_file="$(mktemp)"; _tmpfiles+=("$_act_file")
  jq -j --argjson i "$i" '.cases[$i].expected_output_bytes | @base64d' "$FIXTURE" > "$_exp_file"
  _co_pp_emit "$_name" "$_status" "$_severity" "$_detail" "$_remediation" > "$_act_file"

  if cmp -s "$_exp_file" "$_act_file"; then
    _pass_msg "case $i byte-equal ($_status/$_severity)"
  else
    _fail_msg "case $i byte MISMATCH ($_status/$_severity):"
    printf '  expected: '; od -An -c "$_exp_file" | tr '\n' ' '; printf '\n'
    printf '  actual:   '; od -An -c "$_act_file" | tr '\n' ' '; printf '\n'
  fi
  rm -f "$_exp_file" "$_act_file"
done

echo "=== Summary ==="
printf 'PASS: %d  FAIL: %d\n' "$_pass" "$_fail"
[[ "$_fail" -eq 0 ]]
