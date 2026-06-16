#!/usr/bin/env bash
# workday-complete-step1-validate.sh — /workday-complete Step 1 gate (UBT + fast-test).
#
# Encapsulates the two blocking gates from commands/workday-complete.md §Step 1:
#   1. UBT pending-record resolution (UE work only, presence-detected via
#      bin/check-ubt-build-fresh.sh in cwd).
#   2. Fast-test resolver + invocation (all repos, skipped when unconfigured).
#
# Exists so the EM cannot accidentally skip either gate when running the
# workday-complete ceremony inline — the same failure mode that prompted
# workday-start-step0.sh (2026-05-20 regression).
#
# Spec backlink: commands/workday-complete.md §Step 1 (lines 18–69)
#
# Idempotency: this script is a read-and-report wrapper. It touches no files of
# its own — state mutation is limited to what the underlying validation command
# itself does (e.g., the UBT build writes resolved records; the fast-test command
# may write test artefacts). Running this script twice from the same repo state
# produces identical stdout and the same exit code.
#
# Stdout (caller eval's this line):
#   RC_UBT=<n|skipped> RC_VALIDATE=<n|skipped|blocked>
#   Exactly one line, shell-eval-safe. RC_VALIDATE feeds the Validation: field in
#   Step 9 changelog synthesis.
#
# Stderr: all human-readable detail (UBT output, fast-test output, resolver hints).
#
# Exit codes:
#   0 — both gates ok or skipped; proceed.
#   1 — UBT resolved to blocked (override with COORDINATOR_OVERRIDE_UBT_GATE=1).
#   2 — fast-test exited non-zero AND output indicates a build failure
#        (patterns: "error:" / "BUILD FAILED" / "Compilation" / cargo build failure).
#   3 — fast-test exited non-zero with test failures only (fix-quick or flag).
#   4 — resolver lib missing at expected path (flagged distinctly; fast-test skipped).
#
# Env (optional):
#   COORDINATOR_OVERRIDE_UBT_GATE=1  — bypass exit 1 on UBT-blocked verdict.
#                                       PM-authorized only.

set -eu

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_LIB="${PLUGIN_ROOT}/lib/coordinator-resolve-validation-cmd.sh"

# ---------------------------------------------------------------------------
# _classify_fast_test_output <captured-output-string> <rc>
#
# Returns (via exit code):
#   0  — exit code was 0 (caller should not call this on rc=0)
#   2  — build failure (output contains compile/build error patterns)
#   3  — test-only failure (rc non-zero but no build error patterns found)
#
# Negative-spec: when output is ambiguous, this function prefers exit 3 (test
# failure) over exit 2 (build failure), per the interface contract above.
# ---------------------------------------------------------------------------
_classify_fast_test_output() {
  local output="$1" rc="$2"
  if [[ $rc -eq 0 ]]; then
    return 0
  fi
  # Build-failure patterns (case-insensitive scan on the captured output).
  # grep -i / -E is POSIX ERE — no grep -P (BSD portability requirement).
  if echo "$output" | grep -qiE '(error:|BUILD FAILED|Compilation|cargo build)'; then
    return 2
  fi
  return 3
}

# ---------------------------------------------------------------------------
# Gate 1 — UBT pending-record resolution (UE repos only)
# Presence-detected: script absent → silent skip.
# ---------------------------------------------------------------------------
RC_UBT="skipped"

if [[ -x "bin/check-ubt-build-fresh.sh" ]]; then
  echo "[workday-complete-step1] UBT gate: bin/check-ubt-build-fresh.sh found — running resolve pass." >&2
  set +e
  # $BASH forwards the current interpreter (DR-148: never bare `bash`).
  "$BASH" "bin/check-ubt-build-fresh.sh" --since HEAD --mode resolve >&2
  _ubt_rc=$?
  set -e
  RC_UBT=$_ubt_rc

  if [[ $_ubt_rc -ne 0 ]]; then
    if [[ "${COORDINATOR_OVERRIDE_UBT_GATE:-0}" == "1" ]]; then
      echo "[workday-complete-step1] UBT gate: resolved to blocked (rc=${_ubt_rc}) — OVERRIDE active, continuing." >&2
      echo "RC_UBT=${RC_UBT} RC_VALIDATE=blocked"
      exit 0
    else
      echo "[workday-complete-step1] UBT gate: resolved to blocked (rc=${_ubt_rc})." >&2
      echo "[workday-complete-step1] Fix the C++ compile error and re-run /workday-complete." >&2
      echo "[workday-complete-step1] Override (PM-authorized only): COORDINATOR_OVERRIDE_UBT_GATE=1" >&2
      echo "RC_UBT=${RC_UBT} RC_VALIDATE=blocked"
      exit 1
    fi
  fi

  echo "[workday-complete-step1] UBT gate: passed (rc=0)." >&2
else
  echo "[workday-complete-step1] UBT gate: bin/check-ubt-build-fresh.sh absent — skipping (non-UE repo)." >&2
fi

# ---------------------------------------------------------------------------
# Gate 2 — Fast-test resolver + invocation
# ---------------------------------------------------------------------------
RC_VALIDATE="skipped"

if [[ ! -f "$_LIB" ]]; then
  echo "[workday-complete-step1] WARN: resolver lib not found at ${_LIB} — fast-test gate skipped." >&2
  echo "RC_UBT=${RC_UBT} RC_VALIDATE=${RC_VALIDATE}"
  exit 4
fi

# shellcheck source=/dev/null
source "$_LIB"

_resolve_stderr=$(mktemp)
trap 'rm -f "$_resolve_stderr"' EXIT

# Capture resolver output without aborting on non-zero exit (set -e guard).
# The || true idiom is the canonical pattern for "capture exit code under set -e".
_rc_resolve=0
CMD=$(cs_resolve_fast_test_cmd 2>"$_resolve_stderr") || _rc_resolve=$?

# Always forward resolver stderr (step=env-var / step=local-md / step=skipped notices).
[[ -s "$_resolve_stderr" ]] && cat "$_resolve_stderr" >&2

if [[ $_rc_resolve -ne 0 ]]; then
  # No command configured — resolver already emitted remediation hints above.
  RC_VALIDATE="skipped"
  echo "RC_UBT=${RC_UBT} RC_VALIDATE=${RC_VALIDATE}"
  exit 0
fi

echo "[workday-complete-step1] fast-test: running: ${CMD}" >&2

# Capture combined stdout+stderr for classification AND forward to human stderr.
# We capture once to a temp file, then cat to stderr (tee-like, without GNU tee).
# Child-shell sandbox (bash -c): isolates child from this shell's variable namespace,
# preventing assignment-injection clobber of RC_VALIDATE / $? / other caller state.
# $BASH forwards the current interpreter (DR-148: never bare `bash`).
_ft_out=$(mktemp)
# Append _ft_out to the trap so it is cleaned up even on early exit.
trap 'rm -f "$_resolve_stderr" "$_ft_out"' EXIT

set +e
"$BASH" -c "$CMD" >"$_ft_out" 2>&1
_ft_rc=$?
set -e

# Forward the captured output to human stderr before classifying.
cat "$_ft_out" >&2

_ft_content=$(cat "$_ft_out")
RC_VALIDATE=$_ft_rc

if [[ $_ft_rc -eq 0 ]]; then
  echo "RC_UBT=${RC_UBT} RC_VALIDATE=${RC_VALIDATE}"
  exit 0
fi

# Non-zero: classify as build failure (exit 2) or test-only failure (exit 3).
# _classify_fast_test_output returns its verdict via exit code; capture it.
set +e
_classify_fast_test_output "$_ft_content" "$_ft_rc"
_classify_rc=$?
set -e

echo "RC_UBT=${RC_UBT} RC_VALIDATE=${RC_VALIDATE}"
exit $_classify_rc
