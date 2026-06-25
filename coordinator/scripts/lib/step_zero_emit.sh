#!/usr/bin/env bash
# step_zero_emit.sh — SSOT NDJSON emitter for the ratified Step Zero contract.
#
# Purpose: the shared, ratified "Step Zero" install-prereq emitter — the single
# source of truth for the per-probe NDJSON line shape that coordinator emits and
# that sibling repos (holodeck, project-opticon) conform their own emitters against.
# This file holds ONLY the emitter + JSON-escape primitives; it contains NO probe
# logic (probes live in prereq_probe.sh). It NEVER mutates the machine.
#
# Downstream vendors (cross-repo): project-rag-ue-addon AND deep-research both vendor this
# file BYTE-STABLE as part of the prereq_probe.sh self-sourcing unit (prereq_probe.sh sources
# this for the NDJSON emitter primitives). coordinator-claude is source_is_live, so their
# producer-side parity test's FRESHNESS leg is advisory — a breaking change here warrants a
# bump-memo to BOTH project-rag-ue-addon-em AND deep-research-em.
# See docs/wiki/cross-repo-contract-parity.md § Convention B.
# VENDOR AS A UNIT INTO A DEDICATED ISOLATED SUBDIR (cross-repo memo 2026-06-22): this file
# is self-sourced by prereq_probe.sh under the GENERIC name step_zero_emit.sh. Vendor all
# three unit files into a dedicated subdir (e.g. lib/coordinator_prereq/), never flat
# alongside a consumer lib of the same name — see prereq_probe.sh header for the full rule.
#
# Spec backlink: docs/wiki/step-zero-emitter-contract.md (canonical contract)
#   + docs/plans/2026-06-22-step-zero-emitter-contract-lib.md
# Conformance fixture: tests/fixtures/step-zero-conformance.json (the NORMATIVE
#   authority — base64-encoded expected bytes; this bash code is the worked example
#   for bash consumers, illustrative not normative for non-bash emitters).
#
# Contract — one compact NDJSON line per probe (no trailing whitespace, single \n):
#   {"name":"<probe>","status":"<pass|fail|warn|inconclusive>","severity":"<hard|semi-hard|advisory>","detail":"<short>","remediation":"<one-line|empty>"}
#
# Two enums (orthogonal, non-multiplexed — a `warn` may be `hard` OR `advisory`):
#   status   ∈ {pass, fail, warn, inconclusive}   — the verdict
#   severity ∈ {hard, semi-hard, advisory}         — the gate weight
#     hard      — blocks the preflight exit; no operator escape path
#     semi-hard — blocks the preflight exit like hard, but is escapable via a probe-specific
#                 override flag (operator consciously proceeds). Use only for prerequisites
#                 near-universal but with a legitimate alternative the probe can't always detect.
#     advisory  — surfaced to the operator but does not stop the gate
# `inconclusive` is first-class (per doctor-probe-design.md): a probe that genuinely
#   cannot determine state returns "inconclusive", never a false "pass"/"fail".
#
# JSON escaping — FIVE escapes, applied IN THIS ORDER (order is normative; backslash
# MUST be first to avoid double-escaping the substitutions that follow):
#   1. \  backslash       -> \\
#   2. "  double-quote    -> \"
#   3. \r carriage-return -> \r
#   4. \n line-feed       -> \n
#   5. \t tab             -> \t
# NOT escaped (intentional boundary): other C0 control chars, NUL, and non-ASCII —
#   they pass through raw. clone_auth captures multiline git stderr, so \r/\n/\t are
#   load-bearing (real Windows git stderr carries CRLF).
#
# Exported functions:
#   _co_pp_json_escape <string>                          — escape a string for inline JSON
#   _co_pp_emit <name> <status> <severity> <detail> <remediation>  — emit one NDJSON line
#
# Usage (sourced):
#   source scripts/lib/step_zero_emit.sh
#   _co_pp_emit "python" "pass" "hard" "Python 3.11.5" ""

# ---------------------------------------------------------------------------
# Bash version guard -- must be syntactically parseable on bash 3.2.
# Mirrors prereq_probe.sh: the coordinator install standard is bash >= 4
# (macOS ships 3.2 and is unsupported, DR-148). The emit primitives below use
# only ${v//x/y} + printf (3.2-safe), but the guard is kept for family parity
# so a sibling sourcing this lib gets the same brew-bash remediation.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'ERROR: step_zero_emit.sh requires bash >= 4 (found: %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS ships bash 3.2 -- install a modern bash via Homebrew:\n' >&2
  printf '    brew install bash\n' >&2
  printf '  Then invoke with: /usr/local/bin/bash %s\n' "${BASH_SOURCE[0]:-step_zero_emit.sh}" >&2
  # exit (not return) is intentional even though this file is sourced: a bash<4
  # environment cannot run the consumers either, so failing loud here is correct.
  exit 78  # EX_CONFIG
fi

# ---------------------------------------------------------------------------
# Idempotency guard -- safe to source multiple times.
# ---------------------------------------------------------------------------
_CO_STEP_ZERO_EMIT_LOADED="${_CO_STEP_ZERO_EMIT_LOADED:-0}"
if [[ "$_CO_STEP_ZERO_EMIT_LOADED" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_CO_STEP_ZERO_EMIT_LOADED=1

# ---------------------------------------------------------------------------
# _co_pp_json_escape <string>
#
# Purpose: escape a string for safe embedding in a hand-rolled JSON value.
# Escapes FIVE characters in order (see file header): backslash, double-quote,
# carriage-return, line-feed, tab. No jq dependency -- jq is not guaranteed at
# Step Zero. Backslash MUST be escaped first to avoid double-escaping.
# ---------------------------------------------------------------------------
_co_pp_json_escape() {
  local _s="$1"
  # Escape backslash first (must be first to avoid double-escaping quotes or control chars).
  _s="${_s//\\/\\\\}"
  # Escape double-quote.
  _s="${_s//\"/\\\"}"
  # Escape control characters — applied AFTER backslash and quote to avoid double-escaping.
  # clone_auth captures multiline git stderr; bare newlines/carriage-returns/tabs produce invalid JSON.
  _s="${_s//$'\r'/\\r}"
  _s="${_s//$'\n'/\\n}"
  _s="${_s//$'\t'/\\t}"
  printf '%s' "$_s"
}

# ---------------------------------------------------------------------------
# _co_pp_emit <name> <status> <severity> <detail> <remediation>
#
# Purpose: emit a single compact NDJSON line for one probe result.
# All string fields are escaped via _co_pp_json_escape before embedding.
#
# Enum validation is the CALLER's responsibility: this function escapes and emits but does
# NOT reject out-of-enum status/severity values. A caller passing an invalid status (e.g. a
# typo or a value carrying a quote) produces a syntactically-valid but semantically-wrong line
# rather than an error. Callers must pass status ∈ {pass,fail,warn,inconclusive} and
# severity ∈ {hard,semi-hard,advisory}. (Kept as a pass-through printer to preserve the
# byte-identical extraction from prereq_probe.sh; a validating wrapper belongs at the probe
# layer. The semi-hard value is ENV-PREREQ-PROBE-taxonomy-specific — see file header for
# the definition. Do not confuse with the manifest-dep taxonomy {hard,soft,optional} which
# is a separate, orthogonal contract.)
# ---------------------------------------------------------------------------
_co_pp_emit() {
  local _name="$1"
  local _status="$2"
  local _severity="$3"
  local _detail="$4"
  local _remediation="$5"
  printf '{"name":"%s","status":"%s","severity":"%s","detail":"%s","remediation":"%s"}\n' \
    "$(_co_pp_json_escape "$_name")" \
    "$(_co_pp_json_escape "$_status")" \
    "$(_co_pp_json_escape "$_severity")" \
    "$(_co_pp_json_escape "$_detail")" \
    "$(_co_pp_json_escape "$_remediation")"
}
