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
#   RC_UBT='<n|skipped>' RC_VALIDATE='<n|skipped|blocked|ubt-overridden|lib-missing|interp-missing>'
#   Exactly one line, shell-eval-safe (values are single-quoted — eval injection defence).
#   RC_VALIDATE feeds the Validation: field in Step 9 changelog synthesis.
#
# Stderr: all human-readable detail (UBT output, fast-test output, resolver hints).
#
# Exit codes:
#   0 — both gates ok or skipped; proceed.
#   1 — UBT resolved to blocked (override with COORDINATOR_OVERRIDE_UBT_GATE=1).
#   2 — fast-test exited non-zero AND output indicates a build failure
#        (patterns: "error:" / "BUILD FAILED" / "Compilation"), OR exited 127
#        (command-not-found — missing interpreter/binary), OR the resolver itself
#        failed with a missing-interpreter (RC_VALIDATE=interp-missing). All three
#        are blocking environment/build failures, never a silent skip.
#   3 — fast-test exited non-zero with test failures only (fix-quick or flag).
#   4 — resolver lib missing at resolved path (flagged distinctly; fast-test skipped).
#        RC_VALIDATE=lib-missing on this path (not skipped) to give Step 9 a distinct signal.
#   0 (UBT override path) — UBT blocked but COORDINATOR_OVERRIDE_UBT_GATE=1 active;
#        RC_VALIDATE=ubt-overridden (not blocked) to avoid misleading Step 9 synthesis.
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
  # Exit 127 = command-not-found (missing interpreter/binary) — an ENVIRONMENT
  # failure, not a test assertion. Surface as blocking (2), never as the
  # swallow-prone test-only (3). Runtime half of the silent-127 fix: even if a
  # bare `python` slipped past resolver normalization, a 127 here is never
  # quietly downgraded to "some tests failed, proceed".
  if [[ $rc -eq 127 ]]; then
    return 2
  fi
  # Build-failure patterns (case-insensitive scan on the captured output).
  # grep -i / -E is POSIX ERE — no grep -P (BSD portability requirement).
  # Review: code-reviewer — bare "cargo build" matched command-echo lines; rely on "error:" for rustc output.
  if echo "$output" | grep -qiE '(error:|BUILD FAILED|Compilation)'; then
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
      # Review: code-reviewer — RC_VALIDATE=blocked under override is internally inconsistent;
      # ubt-overridden signals Step 9 that the gate was bypassed, not that fast-test was blocked.
      echo "RC_UBT='${RC_UBT}' RC_VALIDATE='ubt-overridden'"
      exit 0
    else
      echo "[workday-complete-step1] UBT gate: resolved to blocked (rc=${_ubt_rc})." >&2
      echo "[workday-complete-step1] Fix the C++ compile error and re-run /workday-complete." >&2
      echo "[workday-complete-step1] Override (PM-authorized only): COORDINATOR_OVERRIDE_UBT_GATE=1" >&2
      # Review: code-reviewer — single-quote values in eval-safe stdout (eval injection defence).
      echo "RC_UBT='${RC_UBT}' RC_VALIDATE='blocked'"
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
  # Review: code-reviewer — "expected path" overstated (path is dynamically resolved via BASH_SOURCE).
  # Review: code-reviewer — lib-missing distinguishes exit 4 from unconfigured (skipped) for Step 9.
  echo "RC_UBT='${RC_UBT}' RC_VALIDATE='lib-missing'"
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

if [[ $_rc_resolve -eq 2 ]]; then
  # Exit 2 = genuine skip-with-notice (no command configured) — resolver already
  # emitted remediation hints above. This is the ONLY resolver non-zero that maps
  # to a non-blocking skip.
  RC_VALIDATE="skipped"
  # Review: code-reviewer — single-quote values in eval-safe stdout (eval injection defence).
  echo "RC_UBT='${RC_UBT}' RC_VALIDATE='${RC_VALIDATE}'"
  exit 0
elif [[ $_rc_resolve -ne 0 ]]; then
  # Any OTHER resolver non-zero is a HARD failure, NOT a skip. The canonical case
  # is exit 127: the command resolved to a bare `python` token but no python3/python
  # exists on PATH. Surfacing this as blocking (exit 2) is the resolve-time half of
  # the silent-127 fix — a python3-only machine previously fell through to a skip and
  # the day's validation never ran. RC_VALIDATE='interp-missing' gives Step 9 a
  # distinct signal from a build failure.
  echo "[workday-complete-step1] fast-test: resolver failed (rc=${_rc_resolve}) — interpreter/environment problem, NOT a skip. Validation gate is BLOCKED." >&2
  echo "RC_UBT='${RC_UBT}' RC_VALIDATE='interp-missing'"
  exit 2
fi

echo "[workday-complete-step1] fast-test: running: ${CMD}" >&2

# Capture combined stdout+stderr for classification AND forward to human stderr.
# We capture once to a temp file, then cat to stderr (tee-like, without GNU tee).
# Child-shell sandbox (bash -c): isolates child variable mutations from this shell's namespace
# (assignments in the child do not propagate back); does not restrict what the configured
# command executes. $BASH forwards the current interpreter (DR-148: never bare `bash`).
# Review: code-reviewer — tightened sandbox comment; prior comment overstated protection scope.
_ft_out=$(mktemp)
# Review: code-reviewer — trap does not accumulate; re-declare to include both temp files
# (the second call replaces the first, not appends).
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
  # Review: code-reviewer — single-quote values in eval-safe stdout (eval injection defence).
  echo "RC_UBT='${RC_UBT}' RC_VALIDATE='${RC_VALIDATE}'"
  exit 0
fi

# Non-zero: classify as build failure (exit 2) or test-only failure (exit 3).
# _classify_fast_test_output returns its verdict via exit code; capture it.
set +e
_classify_fast_test_output "$_ft_content" "$_ft_rc"
_classify_rc=$?
set -e
# Review: code-reviewer — _ft_rc is non-zero at this point (guarded above); _classify_rc will be 2 or 3.

# Review: code-reviewer — single-quote values in eval-safe stdout (eval injection defence).
echo "RC_UBT='${RC_UBT}' RC_VALIDATE='${RC_VALIDATE}'"
exit $_classify_rc
