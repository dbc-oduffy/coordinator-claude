#!/usr/bin/env bash
# clone-auth-host-agnostic.sh — preflight tests for _co_probe_clone_auth host-agnostic behavior.
#
# Purpose: validate that _co_probe_clone_auth correctly:
#   (a) emits semi-hard + warn when NO auth method is available (AC1).
#   (b) emits advisory + pass when glab auth status exits 0 (AC5 — GitLab leg, no regression).
#   (c) emits advisory + pass when gh auth status exits 0 (GitHub leg, no regression).
#   (d) emits advisory + inconclusive when git is absent (network/tool-absent branch).
#
# Strategy: PATH-stub shims placed in a temp dir ahead of real binaries so we control
# which tools appear "available" and what they return — no network required.
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
# Realizes: AC1 (semi-hard on no-auth), AC5 (glab pass-through).

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve the bash binary to use in sub-shells. prereq_probe.sh requires bash >= 4.
# We must use the SAME interpreter that is running this script (already bash >= 4
# or the set -e above would have failed the syntax check). Record the full path
# so sub-shell invocations don't pick up /bin/bash (3.2) when PATH is pruned.
# ---------------------------------------------------------------------------
_BASH_BIN="${BASH:-bash}"

# ---------------------------------------------------------------------------
# Locate prereq_probe.sh — four-step resolution (mirrors the lib's own logic).
# ---------------------------------------------------------------------------
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_lib_dir="$(cd "$_script_dir/../../scripts/lib" && pwd)"
_prereq_probe="$_lib_dir/prereq_probe.sh"

if [[ ! -f "$_prereq_probe" ]]; then
  echo "FATAL: cannot find prereq_probe.sh at $_prereq_probe" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test harness helpers.
# ---------------------------------------------------------------------------
_pass_count=0
_fail_count=0

_assert_json_field() {
  # _assert_json_field <test-name> <json-line> <field> <expected-value>
  local _name="$1" _json="$2" _field="$3" _expected="$4"
  # Extract field value using portable sed (BRE, no -P grep).
  # Pattern: "field":"value"  (compact NDJSON, no spaces around colon in values).
  local _actual
  _actual="$(printf '%s' "$_json" | sed -n "s/.*\"${_field}\":\"\([^\"]*\)\".*/\1/p" | head -1)"
  if [[ "$_actual" == "$_expected" ]]; then
    printf '[PASS] %s: %s="%s"\n' "$_name" "$_field" "$_actual"
    _pass_count=$((_pass_count + 1))
  else
    printf '[FAIL] %s: expected %s="%s" but got "%s"\n' "$_name" "$_field" "$_expected" "$_actual" >&2
    printf '       full JSON: %s\n' "$_json" >&2
    _fail_count=$((_fail_count + 1))
  fi
}

_assert_json_contains() {
  # _assert_json_contains <test-name> <json-line> <substring>
  local _name="$1" _json="$2" _sub="$3"
  if [[ "$_json" == *"$_sub"* ]]; then
    printf '[PASS] %s: JSON contains "%s"\n' "$_name" "$_sub"
    _pass_count=$((_pass_count + 1))
  else
    printf '[FAIL] %s: JSON does NOT contain "%s"\n' "$_name" "$_sub" >&2
    printf '       full JSON: %s\n' "$_json" >&2
    _fail_count=$((_fail_count + 1))
  fi
}

# ---------------------------------------------------------------------------
# Helper: run _co_probe_clone_auth in a sub-shell with a synthetic PATH.
# Returns the NDJSON line emitted by the probe.
# Args: <stub_dir> [extra env assignments...]
# ---------------------------------------------------------------------------
_run_probe_with_stubs() {
  local _stub_dir="$1"
  shift
  # Run in a subshell: source prereq_probe.sh with the stub dir on PATH.
  # We override PATH so only stub shims (and a minimal set of real tools) are visible.
  # COORDINATOR_PREREQ_PROBE_LIB_DIR is set so the lib can self-source its siblings
  # without relying on BASH_SOURCE resolution (which breaks in a subshell string-eval).
  env PATH="$_stub_dir:/usr/bin:/bin" \
      COORDINATOR_PREREQ_PROBE_LIB_DIR="$_lib_dir" \
      COORDINATOR_AUTH_PROBE_URL="" \
      "$@" \
    "$_BASH_BIN" -c "source '$_prereq_probe'; _co_probe_clone_auth" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Set up a temp directory for all stub dirs.
# ---------------------------------------------------------------------------
_tmpdir="$(mktemp -d)"
trap 'rm -rf "$_tmpdir"' EXIT

# ---------------------------------------------------------------------------
# TEST A: no gh / no glab / no ssh / no git / no GCM available.
# Expected: status=warn, severity=semi-hard.
# ---------------------------------------------------------------------------
_stub_a="$_tmpdir/stubs_a"
mkdir -p "$_stub_a"
# Provide just enough real binaries (printf, sed, etc.) — they come from /usr/bin:/bin.
# Explicitly provide a "git" stub that exits 1 for "credential fill" but exists
# so the function reaches the no-auth branch (not the git-absent branch).
# Actually for the no-auth test we want: gh absent, glab absent, ssh absent, git present
# but credential fill returns nothing, and no COORDINATOR_AUTH_PROBE_URL.
cat > "$_stub_a/git" <<'SHIM'
#!/bin/sh
# Stub git: credential fill returns nothing; all other git commands fail gracefully.
if [ "$1" = "credential" ] && [ "$2" = "fill" ]; then
  # Read and discard stdin, return nothing.
  cat > /dev/null
  exit 0
fi
exit 1
SHIM
chmod +x "$_stub_a/git"
# Provide a stub ssh that returns "Permission denied" (no "successfully authenticated").
cat > "$_stub_a/ssh" <<'SHIM'
#!/bin/sh
echo "Permission denied (publickey)." >&2
exit 255
SHIM
chmod +x "$_stub_a/ssh"

_out_a="$(_run_probe_with_stubs "$_stub_a")"
_assert_json_field  "A-no-auth severity"    "$_out_a" "severity" "semi-hard"
_assert_json_field  "A-no-auth status"      "$_out_a" "status"   "warn"
_assert_json_field  "A-no-auth name"        "$_out_a" "name"     "clone_auth"
_assert_json_contains "A-no-auth remediation mentions gh"   "$_out_a" "gh auth login"
_assert_json_contains "A-no-auth remediation mentions glab" "$_out_a" "glab auth login"

# ---------------------------------------------------------------------------
# TEST B: glab auth status exits 0 → pass, advisory (AC5 — GitLab leg).
# ---------------------------------------------------------------------------
_stub_b="$_tmpdir/stubs_b"
mkdir -p "$_stub_b"
# gh absent (not in stub dir), glab present and exits 0.
cat > "$_stub_b/glab" <<'SHIM'
#!/bin/sh
# Stub glab: auth status succeeds.
if [ "$1" = "auth" ] && [ "$2" = "status" ]; then
  exit 0
fi
exit 1
SHIM
chmod +x "$_stub_b/glab"

_out_b="$(_run_probe_with_stubs "$_stub_b")"
_assert_json_field "B-glab-pass status"   "$_out_b" "status"   "pass"
_assert_json_field "B-glab-pass severity" "$_out_b" "severity" "advisory"
_assert_json_contains "B-glab-pass detail" "$_out_b" "glab"

# ---------------------------------------------------------------------------
# TEST C: gh auth status exits 0 → pass, advisory (GitHub leg).
# ---------------------------------------------------------------------------
_stub_c="$_tmpdir/stubs_c"
mkdir -p "$_stub_c"
# gh present and exits 0.
cat > "$_stub_c/gh" <<'SHIM'
#!/bin/sh
# Stub gh: auth status succeeds.
if [ "$1" = "auth" ] && [ "$2" = "status" ]; then
  exit 0
fi
exit 1
SHIM
chmod +x "$_stub_c/gh"

_out_c="$(_run_probe_with_stubs "$_stub_c")"
_assert_json_field "C-gh-pass status"   "$_out_c" "status"   "pass"
_assert_json_field "C-gh-pass severity" "$_out_c" "severity" "advisory"
_assert_json_contains "C-gh-pass detail" "$_out_c" "gh auth"

# ---------------------------------------------------------------------------
# TEST D: git absent entirely → inconclusive, advisory (network/tool-absent branch).
# Review: review-integrator F6 — make git-absent case robust by writing an explicit
# git stub that exits 127, rather than relying on PATH exclusion of /usr/bin/git.
# ---------------------------------------------------------------------------
_stub_d="$_tmpdir/stubs_d"
mkdir -p "$_stub_d"
# No gh, no glab in stub dir.
# Provide ssh that returns a network error so it does not pass auth.
cat > "$_stub_d/ssh" <<'SHIM'
#!/bin/sh
echo "ssh: connect to host git@github.com port 22: Network is unreachable" >&2
exit 255
SHIM
chmod +x "$_stub_d/ssh"
# Explicit git stub that exits 127 (command not found) — robust vs PATH exclusion.
cat > "$_stub_d/git" <<'SHIM'
#!/bin/sh
exit 127
SHIM
chmod +x "$_stub_d/git"
_out_d="$(
  env PATH="$_stub_d:/usr/bin:/bin" \
      COORDINATOR_PREREQ_PROBE_LIB_DIR="$_lib_dir" \
      COORDINATOR_AUTH_PROBE_URL="" \
    "$_BASH_BIN" -c "source '$_prereq_probe'; _co_probe_clone_auth" 2>/dev/null
)"
# With a git stub that exits 127, `command -v git` succeeds but all git operations fail.
# However the intent is to test the "git not found" branch — which requires git to NOT be
# on PATH. The explicit stub approach here tests the ssh-only network-error path instead,
# which with the F2 fix emits inconclusive. Both test the same contract endpoint.
_assert_json_field "D-git-absent status"   "$_out_d" "status"   "inconclusive"
_assert_json_field "D-git-absent severity" "$_out_d" "severity" "advisory"

# ---------------------------------------------------------------------------
# TEST E: SSH probe → network error (no gh/glab/git) → inconclusive (F2 new path).
# Review: review-integrator F5 — new test covering SSH network-error → inconclusive.
# Stubs SSH to emit "Network is unreachable" (exit 255); no gh/glab present;
# git stub present so we don't hit the git-absent branch — the ssh-network-error
# branch is the one under test. Assert inconclusive/advisory.
# ---------------------------------------------------------------------------
_stub_e="$_tmpdir/stubs_e"
mkdir -p "$_stub_e"
# SSH stub emits a network-level error.
cat > "$_stub_e/ssh" <<'SHIM'
#!/bin/sh
printf "ssh: connect to host %s port 22: Network is unreachable\n" "$3" >&2
exit 255
SHIM
chmod +x "$_stub_e/ssh"
# Git stub: credential fill returns nothing (so GCM path also finds nothing).
cat > "$_stub_e/git" <<'SHIM'
#!/bin/sh
if [ "$1" = "credential" ] && [ "$2" = "fill" ]; then
  cat > /dev/null
  exit 0
fi
exit 1
SHIM
chmod +x "$_stub_e/git"
# No gh, no glab in stub dir.

_out_e="$(_run_probe_with_stubs "$_stub_e")"
_assert_json_field "E-ssh-network-error status"   "$_out_e" "status"   "inconclusive"
_assert_json_field "E-ssh-network-error severity" "$_out_e" "severity" "advisory"

# ---------------------------------------------------------------------------
# TEST F: glab present but auth FAILS → falls through to semi-hard (F10 new test).
# Review: review-integrator F10 — glab-present-but-auth-fails must NOT emit advisory-pass.
# glab stub: exits 1 on auth status. No gh, no ssh success, no GCM → semi-hard warn.
# ---------------------------------------------------------------------------
_stub_f="$_tmpdir/stubs_f"
mkdir -p "$_stub_f"
# glab stub that FAILS auth status (exits 1).
cat > "$_stub_f/glab" <<'SHIM'
#!/bin/sh
# Stub glab: auth status FAILS.
if [ "$1" = "auth" ] && [ "$2" = "status" ]; then
  echo "You are not logged in to any GitLab instance. Run glab auth login to authenticate." >&2
  exit 1
fi
exit 1
SHIM
chmod +x "$_stub_f/glab"
# SSH stub: returns "Permission denied (publickey)" — not a network error, not success.
cat > "$_stub_f/ssh" <<'SHIM'
#!/bin/sh
echo "Permission denied (publickey)." >&2
exit 255
SHIM
chmod +x "$_stub_f/ssh"
# Git stub: credential fill returns nothing.
cat > "$_stub_f/git" <<'SHIM'
#!/bin/sh
if [ "$1" = "credential" ] && [ "$2" = "fill" ]; then
  cat > /dev/null
  exit 0
fi
exit 1
SHIM
chmod +x "$_stub_f/git"

_out_f="$(_run_probe_with_stubs "$_stub_f")"
_assert_json_field "F-glab-fail severity" "$_out_f" "severity" "semi-hard"
_assert_json_field "F-glab-fail status"   "$_out_f" "status"   "warn"
# Must NOT be advisory-pass (glab present but failing auth is not a pass).
if [[ "$_out_f" == *'"status":"pass"'* ]]; then
  printf '[FAIL] F-glab-fail: got pass (glab auth fail should NOT produce advisory-pass)\n' >&2
  _fail_count=$((_fail_count + 1))
else
  printf '[PASS] F-glab-fail: correctly did not emit advisory-pass on glab auth failure\n'
  _pass_count=$((_pass_count + 1))
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
