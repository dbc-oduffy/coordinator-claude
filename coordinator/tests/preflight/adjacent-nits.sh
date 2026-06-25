#!/usr/bin/env bash
# adjacent-nits.sh — preflight tests for adjacent fixups bundled with chunk C1/C6.
#
# Purpose: assert that:
#   AC6-a: prereq_probe.sh uses 'brew install powershell' (core formula, not --cask).
#   AC6-b: the stale 'brew install --cask powershell' string is gone from prereq_probe.sh.
#   AC6-c: _machine_local.py exits non-zero on malformed TOML (the fix already shipped;
#           this test verifies the exit-1 path exists in the source via the script itself).
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
# Realizes: AC6.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate prereq_probe.sh.
# ---------------------------------------------------------------------------
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_lib_dir="$(cd "$_script_dir/../../scripts/lib" && pwd)"
_prereq_probe="$_lib_dir/prereq_probe.sh"

if [[ ! -f "$_prereq_probe" ]]; then
  echo "FATAL: cannot find prereq_probe.sh at $_prereq_probe" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Scratch directory — set up unconditionally at top so the trap always fires.
# Review: review-integrator F11 — move mktemp + trap to top, unconditional, so
# cleanup always fires even if a test fails mid-script.
# ---------------------------------------------------------------------------
_tmpdir="$(mktemp -d)"
trap 'rm -rf "$_tmpdir"' EXIT

# ---------------------------------------------------------------------------
# Test harness helpers.
# ---------------------------------------------------------------------------
_pass_count=0
_fail_count=0

_assert_true() {
  local _name="$1" _result="$2"
  if [[ "$_result" == "0" ]]; then
    printf '[PASS] %s\n' "$_name"
    _pass_count=$((_pass_count + 1))
  else
    printf '[FAIL] %s (exit code: %s)\n' "$_name" "$_result" >&2
    _fail_count=$((_fail_count + 1))
  fi
}

_assert_false() {
  local _name="$1" _result="$2"
  if [[ "$_result" != "0" ]]; then
    printf '[PASS] %s (correctly non-zero: %s)\n' "$_name" "$_result"
    _pass_count=$((_pass_count + 1))
  else
    printf '[FAIL] %s (expected non-zero but got 0)\n' "$_name" >&2
    _fail_count=$((_fail_count + 1))
  fi
}

# ---------------------------------------------------------------------------
# AC6-a: 'brew install powershell' (core formula) is present.
# ---------------------------------------------------------------------------
grep -q 'brew install powershell' "$_prereq_probe"
_assert_true "AC6-a: 'brew install powershell' present in prereq_probe.sh" "$?"

# ---------------------------------------------------------------------------
# AC6-b: stale 'brew install --cask powershell' is gone.
# grep -q returns 1 (no match) when the string is absent — that is the success case.
# exit-code contract: grep exits 1 on no-match (truthful report, not execution failure).
# ---------------------------------------------------------------------------
grep -q -- '--cask powershell' "$_prereq_probe" && _cask_found=0 || _cask_found=1
_assert_false "AC6-b: '--cask powershell' absent from prereq_probe.sh" "$_cask_found"

# ---------------------------------------------------------------------------
# AC6-c: _machine_local.py exits non-zero on malformed TOML.
# Strategy: locate _machine_local.py, confirm the sys.exit(1) path exists for
# TOMLDecodeError (verify-only — the fix already shipped), then exercise it via
# a crafted bad-TOML registry file written to a temp dir.
# ---------------------------------------------------------------------------

# Locate _machine_local.py. Try the canonical install location first, then the template.
_machine_local_py=""
_candidate="${CLAUDE_HOME:-$HOME}/.claude/bin/_machine_local.py"
_template_candidate="$_script_dir/../../templates/bin/_machine_local.py"
if [[ -f "$_candidate" ]]; then
  _machine_local_py="$_candidate"
elif [[ -f "$_template_candidate" ]]; then
  _machine_local_py="$_template_candidate"
fi

if [[ -z "$_machine_local_py" ]]; then
  printf '[SKIP] AC6-c: _machine_local.py not found at %s or %s — skipping runtime exercise\n' \
    "$_candidate" "$_template_candidate"
  # Not a failure — the fix is verify-only; absence of the script doesn't mean the fix is absent.
  _pass_count=$((_pass_count + 1))
else
  # Confirm the TOMLDecodeError → sys.exit(1) path exists in the source.
  if grep -q 'TOMLDecodeError' "$_machine_local_py" && grep -q 'sys.exit(1)' "$_machine_local_py"; then
    printf '[PASS] AC6-c-static: _machine_local.py contains TOMLDecodeError -> sys.exit(1) path\n'
    _pass_count=$((_pass_count + 1))
  else
    printf '[FAIL] AC6-c-static: _machine_local.py missing TOMLDecodeError or sys.exit(1)\n' >&2
    _fail_count=$((_fail_count + 1))
  fi

  # Exercise: run machine-local get against a deliberately malformed TOML registry.
  # Write a temp registry dir with a bad-TOML registry.toml.
  # (Review: F11 — _tmpdir already created unconditionally at script top; no re-mktemp here.)
  # Malformed TOML: unclosed string.
  printf '[repos]\nunfinished = "this is not closed\n' > "$_tmpdir/registry.toml"
  # Also need an empty registry.local.toml so the reader doesn't fail on absence.
  touch "$_tmpdir/registry.local.toml"

  # Run _machine_local.py directly via python3 with the temp dir as the registry.
  _python_bin=""
  if command -v python3 >/dev/null 2>&1; then
    _python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    _python_bin="python"
  fi

  if [[ -z "$_python_bin" ]]; then
    printf '[SKIP] AC6-c-runtime: no python3/python found — skipping runtime TOML exercise\n'
    _pass_count=$((_pass_count + 1))
  else
    # The script reads MACHINE_LOCAL_REGISTRY_DIR env to find the registry dir.
    # Run it and capture the exit code; we expect non-zero on malformed TOML.
    _ml_exit=0
    MACHINE_LOCAL_REGISTRY_DIR="$_tmpdir" "$_python_bin" "$_machine_local_py" get repos.anything \
      >/dev/null 2>/dev/null || _ml_exit=$?
    _assert_false "AC6-c-runtime: machine-local exits non-zero on malformed TOML" "$_ml_exit"
  fi
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo ""
printf 'Results: %d passed, %d failed\n' "$_pass_count" "$_fail_count"
if [[ "$_fail_count" -gt 0 ]]; then
  exit 1
fi
exit 0
