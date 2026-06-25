#!/usr/bin/env bash
# gen-step-zero-conformance.sh — regenerate step-zero-conformance.json from the LIVE emitter.
#
# The fixture is the NORMATIVE cross-language authority for the Step Zero NDJSON contract
# (docs/wiki/step-zero-emitter-contract.md). It is generated from the bash reference emitter
# (scripts/lib/step_zero_emit.sh) so the expected bytes are exactly what a conforming emitter
# must produce. Run this ONLY on an intentional contract change (then bump contract_version),
# review the diff, and commit the regenerated fixture. The runner (test_step_zero_conformance.sh)
# fails if the committed fixture drifts from the emitter — that is the regression guard.
#
# Requires: bash >= 4, jq, base64. Usage: bash tests/fixtures/gen-step-zero-conformance.sh
set -euo pipefail

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  echo "ERROR: requires bash >= 4 (brew install bash); found ${BASH_VERSION:-unknown}" >&2
  exit 78
fi
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq required" >&2; exit 1; }
command -v base64 >/dev/null 2>&1 || { echo "ERROR: base64 required" >&2; exit 1; }

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=../../scripts/lib/step_zero_emit.sh
source "$_DIR/../../scripts/lib/step_zero_emit.sh"

OUT="$_DIR/step-zero-conformance.json"
CONTRACT_VERSION="1.0"

# Cases — cover all 4 statuses, both severities, and every escape (\ " \r \n \t), CRLF,
# and empty remediation. Control chars use ANSI-C $'...' quoting.
names=(       "python"        "python"                          "uv"                 "clone_auth"                              "longpaths"        "escbug"                       "clone_auth"                                          "crlf" )
statuses=(    "pass"          "fail"                            "warn"               "inconclusive"                            "pass"             "warn"                         "warn"                                                "inconclusive" )
severities=(  "hard"          "hard"                            "advisory"           "advisory"                                "advisory"         "advisory"                     "advisory"                                            "advisory" )
details=(     "Python 3.11.5" "No functional Python 3.11+ found" "uv not found on PATH" "Network unreachable or proxy/SSL error" "n/a (non-Windows)" $'path C:\\temp said "hi"'      $'fatal: auth failed\r\nremote: denied\ttoken'        $'a\r\nb' )
remediations=( ""             "install Python 3.11+"            "brew install uv"    "ensure network connectivity"             ""                 ""                             "configure gh (gh auth login)"                        "" )

{
  for i in "${!names[@]}"; do
    exp_b64="$(_co_pp_emit "${names[$i]}" "${statuses[$i]}" "${severities[$i]}" "${details[$i]}" "${remediations[$i]}" | base64 | tr -d '\n')"
    jq -n -c \
      --arg name "${names[$i]}" \
      --arg status "${statuses[$i]}" \
      --arg severity "${severities[$i]}" \
      --arg detail "${details[$i]}" \
      --arg remediation "${remediations[$i]}" \
      --arg b64 "$exp_b64" \
      '{input:{name:$name,status:$status,severity:$severity,detail:$detail,remediation:$remediation}, expected_output_bytes:$b64}'
  done
} | jq -s --arg v "$CONTRACT_VERSION" '{contract_version:$v, cases: .}' > "$OUT"

echo "Wrote $OUT ($(jq '.cases | length' "$OUT") cases, contract_version $(jq -r .contract_version "$OUT"))"
