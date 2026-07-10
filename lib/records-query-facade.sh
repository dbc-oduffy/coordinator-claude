#!/usr/bin/env bash
# coordinator/lib/records-query-facade.sh — strang-11 C11-12 strangler facade for records.query.
#
# Purpose: exposes cc_records_query <type> <where> <format>, a drop-in for
#   node "$QR" --type <type> --where "<where>" --format <format> --root "$(coordinator_example_orchestration_hub_root)"
# with native-primary three-state routing per DR-210/DR-215.
#
# Spec backlink: strang-11 C11-12 records.query repoint
#   Consuming scripts: coordinator/bin/audit-roadmap.sh
#                      coordinator/bin/assert-no-terminal-plans-in-live.sh
#
# Three-state contract (native-primary integrity — NON-NEGOTIABLE):
#   State 1 — seam ABSENT (_sf_seam_present returns non-zero):
#             fall back to legacy: node "$QR" --type <type> --where "<where>"
#               --format <format> --root "$(coordinator_example_orchestration_hub_root)"
#             Requires $QR to be set in the caller's scope.
#             This is the ONLY condition that triggers legacy — not transport failure.
#
#   State 2 — seam present + cc_invoke returns rc 0:
#             parse .records from the bare result object and emit to stdout:
#               format=paths: .records is a newline-joined string — emit verbatim.
#                             Empty string → emit nothing (0 lines, not a blank line
#                             that grep -c . would count as 1).
#               format=json:  .records is the array — emit as JSON array structurally equivalent to
#                             query-records.js --format json output.
#
#   State 3 — seam present + cc_invoke returns rc 2:
#             HARD ERROR: emit legible diagnostic to stderr, return non-zero.
#             NEVER fall back to legacy — that would mask a live-but-broken engine.
#             (native-primary integrity; explicit commitment in the bounce-back memo)
#
# Dependencies: sources strangler-facade.sh (which sources coordinator-core-invoke.sh
#   and coordinator-example-orchestration-hub-root.sh), obtaining _sf_seam_present, cc_invoke, and
#   coordinator_example_orchestration_hub_root. Callers need only source this file; all deps follow.
#
# Negative-spec:
#   - Does NOT reimplement _sf_seam_present or cc_invoke — sources them from
#     strangler-facade.sh per dispatch instruction.
#   - Does NOT use strangle_route — that resolves repo root from PWD (DoE repo),
#     not EXAMPLE_ORCHESTRATION_HUB_ROOT; these callers must query the MAKIMA root.
#   - Does NOT fall back to legacy after a transport failure (State 3).
#   - Does NOT change the inherited limit-50 truncation default — behavior-preserving.
#
# Cross-platform: bash >=4 + BSD coreutils (no GNU-isms). Safe to source multiple times.
# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in a
# sourced lib propagates to the caller's shell. -u and pipefail ARE set and propagate
# to callers (all callers are expected to tolerate nounset + pipefail).
set -uo pipefail

# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------
if [[ -n "${_RECORDS_QUERY_FACADE_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
_RECORDS_QUERY_FACADE_SH_LOADED=1

# ---------------------------------------------------------------------------
# Source strangler-facade.sh to obtain _sf_seam_present and cc_invoke.
# strangler-facade.sh sources coordinator-core-invoke.sh (cc_invoke) and
# transitively coordinator-example-orchestration-hub-root.sh (coordinator_example_orchestration_hub_root).
# ---------------------------------------------------------------------------
_RQF_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./strangler-facade.sh
source "${_RQF_LIB_DIR}/strangler-facade.sh" || {
  printf 'records-query-facade.sh: failed to source strangler-facade.sh\n' >&2
  return 1 2>/dev/null || exit 1
}

# ---------------------------------------------------------------------------
# Public: cc_records_query <type> <where> <format> [<limit>]
# ---------------------------------------------------------------------------
# Drop-in for:
#   node "$QR" --type <type> --where "<where>" --format <format> \
#     --root "$(coordinator_example_orchestration_hub_root)" [--limit <limit>]
#
# Parameters:
#   <type>    record type: "handoff" | "handoff-archived" | "plan"
#   <where>   equality-AND filter: "field=value AND field=value"
#             (any <, >, in, != operator → non-zero exit from the op; caller's
#             2>/dev/null || true guards preserve existing call-site behavior)
#   <format>  output format: "paths" (default) | "json"
#   [<limit>] optional result cap. When provided and non-empty: State-1 (legacy)
#             appends --limit <N> to the node call; State-2 (native) adds
#             "limit": <N> (int) to the op params. When omitted/empty: both
#             paths default to 50 (op/node default — behavior-preserving).
#             DO NOT pass 0: query-records.js treats 0 as unlimited, but the
#             example-orchestration-hub records.query op treats 0 as zero-records — divergent
#             behavior. Use a high sentinel (e.g. 100000) to uncap.
#
# State 1 requires $QR to be set in the caller's scope (the existing QR= guard
# in each calling script is the legacy target; this wrapper's legacy branch uses it).
#
# Returns:
#   State 1: exit status of the legacy node call.
#   State 2: 0 on successful native invocation and parse.
#   State 3: non-zero (rc from cc_invoke, typically 2) — legible diagnostic on
#            stderr; NEVER falls back to legacy.
cc_records_query() {
  local _type="${1:?cc_records_query: <type> required}"
  local _where="${2:?cc_records_query: <where> required}"
  local _format="${3:-paths}"
  local _limit="${4:-}"

  # State 1: disk-presence gate — route to legacy if the seam is not importable.
  # _sf_seam_present tests coordinator_core.invoke importability; we suppress its
  # own stderr notice (seam-absent is normal on machines without the native engine).
  if ! _sf_seam_present 2>/dev/null; then
    if [[ -z "${QR:-}" ]]; then
      printf 'cc_records_query: State-1 (seam absent) but $QR is not set — cannot invoke legacy\n' >&2
      return 1
    fi
    local -a _node_args=()
    _node_args+=(--type "$_type" --where "$_where" --format "$_format" --root "$(coordinator_example_orchestration_hub_root)")
    [[ -n "$_limit" ]] && _node_args+=(--limit "$_limit")
    node "$QR" "${_node_args[@]}"
    return $?
  fi

  # States 2/3: native route via cc_invoke (DR-215 spawn-per-call transport).
  # coordinator_example_orchestration_hub_root is idempotent: fast-path returns if EXAMPLE_ORCHESTRATION_HUB_ROOT already set.
  local _example_orchestration_hub_root
  _example_orchestration_hub_root=$(coordinator_example_orchestration_hub_root) || {
    printf 'cc_records_query: cannot resolve EXAMPLE_ORCHESTRATION_HUB_ROOT\n' >&2
    return 2
  }

  # Build params_json safely using python3 (never string-concat unescaped values).
  # <limit> is passed as an int when provided — "limit": 0 means zero-records in the
  # native op, so callers must pass a high sentinel (e.g. 100000) to uncap, never 0.
  local _params_json
  _params_json=$(python3 -c '  # popup-safe-env-suppressed
import json, sys
d = {"type": sys.argv[1], "where": sys.argv[2], "format": sys.argv[3]}
if len(sys.argv) > 4 and sys.argv[4]:
    d["limit"] = int(sys.argv[4])
print(json.dumps(d))
' "$_type" "$_where" "$_format" "$_limit" 2>/dev/null) || {
    printf 'cc_records_query: params_json construction failed (type=%s where=%s format=%s)\n' \
      "$_type" "$_where" "$_format" >&2
    return 2
  }

  local _result
  local _invoke_rc=0
  _result=$(cc_invoke "records.query" "$_params_json" "$_example_orchestration_hub_root") || _invoke_rc=$?

  if [[ "$_invoke_rc" -ne 0 ]]; then
    # State 3: transport/import/timeout/bad-envelope — hard error, never legacy.
    printf 'cc_records_query: records.query invocation failed (rc=%d)\n' \
      "$_invoke_rc" >&2
    printf '  op=records.query type=%s format=%s EXAMPLE_ORCHESTRATION_HUB_ROOT=%s\n' \
      "$_type" "$_format" "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-<unset>}" >&2
    printf '  Native engine broken or unreachable. NOT falling back to legacy (native-primary integrity).\n' >&2
    return "$_invoke_rc"
  fi

  # State 2: parse .records from the bare result object and emit to stdout.
  if [[ "$_format" == "json" ]]; then
    # format=json: .records is the array — emit as JSON array.
    # Downstream consumers pipe this into node -e expecting [{path,frontmatter},...].
    printf '%s\n' "$_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
raw = sys.stdin.read()
try:
    j = json.loads(raw)
    records = j.get("records", [])
    sys.stdout.write(json.dumps(records) + "\n")
except Exception as e:
    sys.stderr.write("cc_records_query: failed to parse records.query result (format=json): " + str(e) + "\n")
    sys.exit(1)
' || {
      printf 'cc_records_query: failed to parse records.query result (format=json)\n' >&2
      return 2
    }
  else
    # format=paths: .records is a newline-joined string — emit verbatim.
    # Empty string → emit nothing (0 lines); a bare newline would make grep -c . count 1.
    printf '%s\n' "$_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
raw = sys.stdin.read()
try:
    j = json.loads(raw)
    records = j.get("records", "")
    if records:
        sys.stdout.write(records)
        if not records.endswith("\n"):
            sys.stdout.write("\n")
except Exception as e:
    sys.stderr.write("cc_records_query: failed to parse records.query result (format=paths): " + str(e) + "\n")
    sys.exit(1)
' || {
      printf 'cc_records_query: failed to parse records.query result (format=paths)\n' >&2
      return 2
    }
  fi
}
