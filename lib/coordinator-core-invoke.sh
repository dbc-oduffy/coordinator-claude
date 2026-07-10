#!/usr/bin/env bash
# coordinator-core-invoke.sh — single command-type transport seam for coordinator_core ops.
#
# Purpose: exposes cc_invoke <op> <params_json> <repo_root>, the ONLY site that shells
# out to `python3 -m coordinator_core.invoke`. All DoE consumers (facade, fleet wrappers,
# gate veneers) source this file and call cc_invoke rather than inline-parsing the
# JSON-RPC envelope each in their own way.
#
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § KD-0 / AC0
# DR-215: replaces the retired coordinator_core.client / UDS transport.
#
# - stdlib-only direct imports — coordinator_core is spawned as a subprocess, not imported.
# - Does NOT open any UDS/AF_UNIX socket — the daemon and socket path are retired (DR-215).
# - Does NOT read or require any auth token — the command path bypasses IPC auth.
#
# Public API:
#   cc_invoke <op> <params_json> <repo_root>
#
#   Returns:
#     0 — success envelope; bare result JSON object emitted to stdout (no jsonrpc/id wrapper).
#         Callers MUST inspect top-level .exit_code / .acted[] / .verdict_line etc.
#         NEVER .result.exit_code — there is no double-nesting; cc_invoke strips the wrapper.
#     2 — fail-CLOSED (transport error): nonzero process exit / empty stdout /
#         unparseable JSON / error-envelope / timeout.
#         Legible diagnostic on stderr DISTINGUISHES "engine won't import/start"
#         (ImportError / spawn failure / timeout) from "op errored" (error-envelope).
#
#   TWO-SIGNAL contract: callers MUST (1) check cc_invoke's OWN return code — rc 2 means
#   transport-fail-closed; (2) on rc 0, parse the result object's top-level .exit_code for
#   the op's own verdict. The BANNED signal is the raw `invoke`-process $? — always 0 on
#   a success envelope even when result.exit_code==2; cc_invoke owns that gate internally.
#
# Timeout: ${CC_INVOKE_TIMEOUT_SECS:-10} — env-overridable; mirrors _INVOKE_TIMEOUT_SECS.
#
# Cross-platform: bash >=4 + BSD coreutils. BASH_VERSINFO<4 fails loud with brew remediation.
# Safe to source multiple times (idempotency guard at bottom).

# ---------------------------------------------------------------------------
# Bash >=4 guard — MUST be above all bash-4 syntax; parses safely on bash 3.2.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  {
    printf 'coordinator-core-invoke.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}"
    printf '  macOS: brew install bash  (restart terminal; /opt/homebrew/bin/bash is bash 5)\n'
    printf '  Reference: coordinator/docs/wiki/cross-platform-shell-portability.md\n'
  } >&2
  # In sourced context, return propagates to caller. Standalone falls through to exit.
  return 1 2>/dev/null || exit 1
fi

# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------
if [[ -n "${_CC_INVOKE_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
_CC_INVOKE_SH_LOADED=1

# NOTE: deliberately no set -e (would propagate errexit to caller) — -uo pipefail ARE propagated,
# matching coordinator-example-orchestration-hub-root.sh / coordinator-currency.sh convention; callers are expected
# to tolerate nounset + pipefail.
set -uo pipefail

# ---------------------------------------------------------------------------
# Internal: resolve EXAMPLE_ORCHESTRATION_HUB_ROOT and set PYTHONPATH for the invoke spawn.
# Also sources coordinator-watchdog.sh for the portable cs_timeout primitive.
# Idempotent per call: coordinator_example_orchestration_hub_root rung 1 exits fast when EXAMPLE_ORCHESTRATION_HUB_ROOT is already
# exported; PYTHONPATH prepend is guarded by substring test. Re-sourcing watchdog/resolver is
# safe (both source-guarded).
# ---------------------------------------------------------------------------
_cc_resolve_deps() {
  # Fast-path: all deps already resolved on a prior cc_invoke call in this shell session.
  [[ -n "${_CC_DEPS_RESOLVED:-}" ]] && return 0

  local _lib_dir
  _lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"

  # Source watchdog lib for portable cs_timeout (handles timeout vs gtimeout vs fallback).
  local _watchdog="${_lib_dir}/coordinator-watchdog.sh"
  if [[ ! -f "${_watchdog}" ]]; then
    printf 'cc_invoke: coordinator-watchdog.sh not found at %s\n' "${_watchdog}" >&2
    return 2
  fi
  # shellcheck disable=SC1090
  source "${_watchdog}" || {
    printf 'cc_invoke: failed to source coordinator-watchdog.sh\n' >&2
    return 2
  }

  # Source EXAMPLE_ORCHESTRATION_HUB_ROOT resolver (idempotent — just redefines coordinator_example_orchestration_hub_root).
  local _resolver="${_lib_dir}/coordinator-example-orchestration-hub-root.sh"
  if [[ ! -f "${_resolver}" ]]; then
    printf 'cc_invoke: coordinator-example-orchestration-hub-root.sh not found at %s\n' "${_resolver}" >&2
    return 2
  fi
  # shellcheck disable=SC1090
  source "${_resolver}" || {
    printf 'cc_invoke: failed to source coordinator-example-orchestration-hub-root.sh\n' >&2
    return 2
  }

  # Resolve EXAMPLE_ORCHESTRATION_HUB_ROOT via the documented four-rung ladder (rung 1: already exported → fast).
  local _example_orchestration_hub_root
  _example_orchestration_hub_root=$(coordinator_example_orchestration_hub_root) || {
    printf 'cc_invoke: EXAMPLE_ORCHESTRATION_HUB_ROOT resolution failed — see above for remediation\n' >&2
    return 2
  }
  EXAMPLE_ORCHESTRATION_HUB_ROOT="${_example_orchestration_hub_root}"
  export EXAMPLE_ORCHESTRATION_HUB_ROOT

  # Prepend EXAMPLE_ORCHESTRATION_HUB_ROOT to PYTHONPATH only if not already present (idempotency).
  if [[ ":${PYTHONPATH:-}:" != *":${EXAMPLE_ORCHESTRATION_HUB_ROOT}:"* ]]; then
    export PYTHONPATH="${EXAMPLE_ORCHESTRATION_HUB_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
  fi
  _CC_DEPS_RESOLVED=1
  return 0
}

# ---------------------------------------------------------------------------
# Public: cc_invoke <op> <params_json> <repo_root>
# ---------------------------------------------------------------------------
# See file-header for full contract.  KD-0 / AC0 implementation.
#
# Bash port of the Python fail-open idiom at example-orchestration-hub/bin/example-orchestration-hub-commit-anchors:157-207,
# translated to bash FAIL-CLOSED (rc 2 instead of None/proceed) per the DoE veneers'
# guard contract.  Reference: veneer-substrate-map.md §2.
cc_invoke() {
  local _op _params _repo _t _rc _out _stderr_tmp _stderr_content
  local _parse_tmp _result_json _parse_diag

  _op="${1:?cc_invoke: <op> is required}"
  _params="${2:?cc_invoke: <params_json> is required}"
  _repo="${3:?cc_invoke: <repo_root> is required}"
  _t="${CC_INVOKE_TIMEOUT_SECS:-10}"
  _rc=0

  # Resolve deps (EXAMPLE_ORCHESTRATION_HUB_ROOT / PYTHONPATH / cs_timeout) — idempotent on subsequent calls.
  _cc_resolve_deps || return 2

  # Spawn invoke with timeout cap.  Redirect stderr to a temp file so we can inspect it
  # for diagnostics (distinguishes ImportError from op-error).
  # `|| _rc=$?` idiom: tolerates nonzero exit under the caller's set -e; the deliberate
  # exit-1 error-envelope case must not abort the caller's script.
  # BSD mktemp discipline: Xs at the END, no trailing extension suffix.
  _stderr_tmp="$(mktemp "${TMPDIR:-/tmp}/cc-invoke-err.XXXXXX")"
  _out="$(cs_timeout "${_t}" -- python3 -m coordinator_core.invoke "${_op}" "${_params}" --repo "${_repo}" 2>"${_stderr_tmp}")" || _rc=$?  # popup-safe-env-suppressed
  _stderr_content="$(cat "${_stderr_tmp}" 2>/dev/null || true)"
  rm -f "${_stderr_tmp}" 2>/dev/null || true

  # --- Fail-CLOSED ladder ---

  # (1) Timeout — cs_timeout exits 124 (mirrors GNU timeout contract).
  if [[ "${_rc}" -eq 124 ]]; then
    printf 'cc_invoke: engine timeout after %ss (op=%s) — coordinator_core.invoke did not respond\n' \
      "${_t}" "${_op}" >&2
    printf '  Verify EXAMPLE_ORCHESTRATION_HUB_ROOT (%s) and coordinator_core installation\n' \
      "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-<unset>}" >&2
    return 2
  fi

  # (2) Nonzero process exit — distinguish engine-start failure from op-level error.
  if [[ "${_rc}" -ne 0 ]]; then
    if printf '%s\n' "${_stderr_content}" | grep -qiE "ImportError|ModuleNotFoundError|No module named"; then
      # Engine won't start: Python cannot import coordinator_core (wrong PYTHONPATH / missing checkout).
      printf 'cc_invoke: engine will not import/start (op=%s, rc=%d)\n' "${_op}" "${_rc}" >&2
      printf '  ImportError — verify EXAMPLE_ORCHESTRATION_HUB_ROOT and coordinator_core installation:\n' >&2
      printf '    EXAMPLE_ORCHESTRATION_HUB_ROOT=%s\n'  "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-<unset>}"  >&2
      printf '    PYTHONPATH=%s\n'   "${PYTHONPATH:-<unset>}"   >&2
    else
      # Likely op-level JSON-RPC error envelope on stdout (invoke exits 1 on error response).
      printf 'cc_invoke: invoke process exited %d (op=%s) — op or dispatch error\n' \
        "${_rc}" "${_op}" >&2
    fi
    [[ -n "${_stderr_content}" ]] && printf '  stderr: %s\n' "${_stderr_content}" >&2
    return 2
  fi

  # (3) Empty stdout — invoke always produces output on success; absence means something failed.
  if [[ -z "${_out}" ]]; then
    printf 'cc_invoke: empty stdout from invoke (op=%s) — invoke produced no output\n' \
      "${_op}" >&2
    return 2
  fi

  # (4) Parse the whole-stdout JSON-RPC envelope and extract the bare result object.
  #     On error envelope: process exits 0 but has "error" key instead of "result".
  #     Python errors written to stderr of the inline python3 subprocess (captured via parse_tmp).
  _parse_tmp="$(mktemp "${TMPDIR:-/tmp}/cc-invoke-parse.XXXXXX")"
  _result_json="$(printf '%s' "${_out}" | python3 -c '  # popup-safe-env-suppressed
import json, sys
raw = sys.stdin.read()
try:
    j = json.loads(raw)
except Exception as e:
    sys.stderr.write("json-parse-error: " + str(e) + "\n")
    sys.exit(1)
if not isinstance(j, dict) or "result" not in j:
    if isinstance(j, dict) and "error" in j:
        err = j.get("error", {})
        sys.stderr.write("op-error: code=" + str(err.get("code", "?")) + " message=" + str(err.get("message", "?")) + "\n")
    else:
        top_keys = list(j.keys()) if isinstance(j, dict) else type(j).__name__
        sys.stderr.write("envelope-missing-result: top-level keys=" + repr(top_keys) + "\n")
    sys.exit(1)
sys.stdout.write(json.dumps(j["result"]) + "\n")
' 2>"${_parse_tmp}")" || {
    _parse_diag="$(cat "${_parse_tmp}" 2>/dev/null || true)"
    rm -f "${_parse_tmp}" 2>/dev/null || true
    if printf '%s\n' "${_parse_diag}" | grep -q "^op-error:"; then
      printf 'cc_invoke: op returned JSON-RPC error envelope (op=%s): %s\n' \
        "${_op}" "${_parse_diag}" >&2
    elif printf '%s\n' "${_parse_diag}" | grep -q "^json-parse-error:"; then
      printf 'cc_invoke: invoke stdout is not valid JSON (op=%s): %s\n' \
        "${_op}" "${_parse_diag}" >&2
    elif [[ -z "${_parse_diag}" ]]; then
      # Parser subprocess crashed with no stderr (e.g. Python segfault / OOM kill).
      printf 'cc_invoke: JSON parse subprocess exited nonzero with no stderr (op=%s)\n' \
        "${_op}" >&2
    else
      printf 'cc_invoke: envelope missing "result" key (op=%s): %s\n' \
        "${_op}" "${_parse_diag}" >&2
    fi
    return 2
  }
  rm -f "${_parse_tmp}" 2>/dev/null || true

  # SUCCESS — emit bare result JSON object to stdout, return 0.
  # Callers parse top-level .exit_code / .acted[] / .verdict_line / .children[] etc.
  # NEVER .result.X — there is no wrapper; cc_invoke already stripped it.
  printf '%s\n' "${_result_json}"
  return 0
}
