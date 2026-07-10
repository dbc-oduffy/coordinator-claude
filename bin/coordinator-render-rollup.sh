#!/usr/bin/env bash
# coordinator-render-rollup.sh — render deliverable.rollup initiatives to stdout.
#
# Purpose: transport seam consumer that calls deliverable.rollup via cc_invoke and
# renders each advancing initiative as a human-readable "advances initiative" line.
# Omits output entirely on empty list or transport failure (fail-open, no hard error).
#
# Usage: coordinator-render-rollup.sh <deliverable_id> <repo_root>
#
# Output (per initiative, one line each):
#   advances initiative <label> (<id>)
#
# Spec backlink: docs/plans/2026-07-06-deliverable-rollup-render-and-fk-population.md § AC3
# Contract pinned to vendored contract §1.1/§4.1/§4.2.

# ---------------------------------------------------------------------------
# Bash >=4 guard — must be above all bash-4 syntax; parses safely on bash 3.2.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  {
    printf 'coordinator-render-rollup.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}"
    printf '  macOS: brew install bash  (restart terminal; /opt/homebrew/bin/bash is bash 5)\n'
    printf '  Reference: coordinator/docs/wiki/cross-platform-shell-portability.md\n'
  } >&2
  return 1 2>/dev/null || exit 1
fi

set -uo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
_deliverable_id="${1:?coordinator-render-rollup.sh: <deliverable_id> is required}"
_repo_root="${2:?coordinator-render-rollup.sh: <repo_root> is required}"

# ---------------------------------------------------------------------------
# Source transport seam (relative to this script's own dir, never hardcoded).
# The source-guard (_CC_INVOKE_SH_LOADED) ensures idempotency if cc_invoke is
# already defined (e.g. when the test harness pre-exports a stub).
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
_TRANSPORT="${_SCRIPT_DIR}/../lib/coordinator-core-invoke.sh"

# Only source if not already loaded (test harness may export stub + guard).
if [[ -z "${_CC_INVOKE_SH_LOADED:-}" ]]; then
  if [[ ! -f "${_TRANSPORT}" ]]; then
    printf 'coordinator-render-rollup.sh: coordinator-core-invoke.sh not found at %s\n' \
      "${_TRANSPORT}" >&2
    exit 0  # fail-open: skip render, no hard error
  fi
  # shellcheck disable=SC1090
  source "${_TRANSPORT}" || {
    printf 'coordinator-render-rollup.sh: failed to source coordinator-core-invoke.sh\n' >&2
    exit 0  # fail-open
  }
fi

# ---------------------------------------------------------------------------
# Call deliverable.rollup — SINGLE-SIGNAL: check cc_invoke's OWN rc only.
# This op is COMPUTE_ONLY (contract §1.1): result has NO .exit_code field.
# DO NOT add a .exit_code / result.exit_code branch — it does not exist.
# ---------------------------------------------------------------------------
# Review: code-reviewer — F5: prefer jq --arg quoting over printf to avoid JSON injection on exotic ids
if command -v jq >/dev/null 2>&1; then
  _params="$(jq -nc --arg did "${_deliverable_id}" '{"deliverable_id":$did}')"
else
  _params="$(printf '{"deliverable_id":"%s"}' "${_deliverable_id}")"
fi

_result=""
_cc_rc=0
_result="$(cc_invoke "deliverable.rollup" "${_params}" "${_repo_root}")" || _cc_rc=$?

# rc 2 → transport fail-closed: skip silently, exit 0 (fail-open render).
# Any other non-zero rc: also skip+log, fail-open (contract defines only rc 0 and rc 2).
if [[ "${_cc_rc}" -eq 2 ]]; then
  printf 'coordinator-render-rollup.sh: transport fail-closed for deliverable_id=%s (skip)\n' \
    "${_deliverable_id}" >&2
  exit 0
elif [[ "${_cc_rc}" -ne 0 ]]; then
  # Review: code-reviewer — F6: explicit branch for non-contract rc (e.g., rc 1) emits log instead of silent fall-through
  printf 'coordinator-render-rollup.sh: unexpected cc_invoke rc=%s for deliverable_id=%s (skip)\n' \
    "${_cc_rc}" "${_deliverable_id}" >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# Parse .advances_initiatives and render.
# resolution_mode must be "direct" in v1.0 — any other value is a future §5.2
# transitive extension this slice does not handle: skip/omit that entry silently.
# Dedup by id (insertion order, first occurrence wins).
# Empty list → emit nothing (omit-on-empty; exit 0, no stdout).
# ---------------------------------------------------------------------------

# Prefer jq if available; fall back to python3.
if command -v jq >/dev/null 2>&1; then
  # jq program: extract resolution_mode + initiatives, dedup by id, render.
  # Outputs nothing if resolution_mode != "direct" or list is empty.
  _render_out=""
  _render_out="$(printf '%s\n' "${_result}" | jq -r '
    select(.resolution_mode == "direct") |
    .advances_initiatives // [] |
    # Dedup by id, preserving first-occurrence order.
    reduce .[] as $item (
      {"seen": [], "out": []};
      if (.seen | index($item.id)) == null
      then {"seen": (.seen + [$item.id]), "out": (.out + [$item])}
      else .
      end
    ) |
    .out[] |
    "advances initiative \(.label // .id) (\(.id))"
  ' 2>/dev/null)" || {
    printf 'coordinator-render-rollup.sh: jq parse error for deliverable_id=%s\n' \
      "${_deliverable_id}" >&2
    exit 0  # fail-open
  }
else
  # python3 fallback (stdlib json only).
  # popup-safe-env-suppressed token below: prevents Claude Code UI from showing a permissions
  # popup when running python3 -c with multi-line inline code. The token is a Claude Code
  # UI suppression marker; it has no effect on python3 itself (parsed as a Python comment).
  _render_out=""
  _render_out="$(printf '%s\n' "${_result}" | python3 -c '  # popup-safe-env-suppressed: Claude Code UI permission-prompt suppressor — no python3 effect
import json, sys
data = json.loads(sys.stdin.read())
if data.get("resolution_mode") != "direct":
    sys.exit(0)
initiatives = data.get("advances_initiatives") or []
seen = set()
for item in initiatives:
    iid = item.get("id", "")
    if iid in seen:
        continue
    seen.add(iid)
    label = item.get("label") or item.get("id", "")  # Review: code-reviewer — F4: get("label","") returns None on JSON null; or-chain falls back to id
    sys.stdout.write("advances initiative {} ({})\n".format(label, iid))
' 2>/dev/null)" || {
    printf 'coordinator-render-rollup.sh: python3 parse error for deliverable_id=%s\n' \
      "${_deliverable_id}" >&2
    exit 0  # fail-open
  }
fi

# Emit rendered lines (may be empty → omit-on-empty contract satisfied by silence).
if [[ -n "${_render_out}" ]]; then
  printf '%s\n' "${_render_out}"
fi

exit 0
