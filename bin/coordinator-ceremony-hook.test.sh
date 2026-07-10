#!/usr/bin/env bash
# coordinator-ceremony-hook.test.sh — Smoke tests for the shared post-ceremony
# command hook helper.
#
# Spec backlink: docs/plans/2026-07-08-ceremony-post-command-hook-seam.md
#   § "Acceptance Criteria" (AC1-AC5, AC12, AC13)
# Model: bin/workday-complete-step1-validate.test.sh
#
# Run: bash coordinator/bin/coordinator-ceremony-hook.test.sh
#
# Tests:
#   1. AC1  — command configured, exits 0 -> summary line + exit 0.
#   2. AC2  — key absent -> silent no-op (empty stdout), exit 0.
#   2b. AC2 — key present but empty -> silent no-op, exit 0.
#   3. AC3  — command exits non-zero -> WARN on stderr, summary line still
#             printed with (exit N), helper itself exits 0.
#   4. AC4a — command containing a secret-shaped token is redacted in the
#             summary line (never echoed raw).
#   4b. AC4b — command containing a shell metacharacter triggers the
#             _cs_metachar_warn advisory tripwire on stderr.
#   5. AC5  — command runs with repo root as cwd (pwd-echoing command).
#   6. Unknown ceremony arg -> WARN + exit 0 (no output).
#   7. AC12 — the call-site emit idiom, run as the terminal statement of a
#             `set -e` block with the key ABSENT, exits 0.
#   8. AC13 — resolver lib unsourceable (simulated path drift) -> WARN,
#             exit 0, cs_read_local_md_key never invoked.
#   9. Non-git repo_root fallback: `git rev-parse --show-toplevel || pwd` falls
#      back to $PWD in a plain (non-git) tmpdir with coordinator.local.md
#      present — the key still resolves relative to $PWD.
#   10. Metachar-warn suppression var actually suppresses the WARN end-to-end
#       through the ceremony hook.

set -eu

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/coordinator-ceremony-hook.sh"

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# Cleanup registry — accumulate mktemp dirs/files, clean them all at exit.
_TMPDIRS=()
cleanup() {
  for d in "${_TMPDIRS[@]+"${_TMPDIRS[@]}"}"; do  # safe empty-array iterate under set -u (bash 4.2+)
    rm -rf "$d"
  done
}
trap cleanup EXIT

make_tmpdir() {
  local d
  d=$(mktemp -d)
  _TMPDIRS+=("$d")
  echo "$d"
}

# make_repo_fixture <local-md-body-or-empty>
# Creates a fresh temp git repo. If a non-empty argument is given, writes it
# verbatim as coordinator.local.md (caller supplies full YAML frontmatter,
# including the --- delimiters). Echoes the repo path.
make_repo_fixture() {
  local body="${1:-}"
  local d
  d=$(make_tmpdir)
  ( cd "$d" && git init -q ) >/dev/null 2>&1
  if [[ -n "$body" ]]; then
    printf '%s\n' "$body" > "${d}/coordinator.local.md"
  fi
  echo "$d"
}

# run_helper <repo_root> <ceremony> — invokes the helper with cwd = repo_root
# (load-bearing: the helper resolves repo_root via `git rev-parse
# --show-toplevel`, which is cwd-relative). Sets _OUT (stdout), _ERR (stderr),
# _RC (exit code).
run_helper() {
  local repo_root="$1" ceremony="$2"
  local _errfile
  _errfile=$(mktemp)
  set +e
  _OUT=$(cd "$repo_root" && "$BASH" "$HELPER" "$ceremony" 2>"$_errfile")
  _RC=$?
  set -e
  _ERR=$(cat "$_errfile")
  rm -f "$_errfile"
}

# ---------------------------------------------------------------------------
# Test 1 (AC1): command configured, exits 0 -> summary line + exit 0.
# ---------------------------------------------------------------------------
echo "--- Test 1 (AC1): configured command, exit 0 -> summary line + exit 0"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "echo hi"\n---')
run_helper "$_REPO" "workday-complete"

_expected="Post-workday-complete hook: ran echo hi (exit 0)"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 1: stdout matches '$_expected'"
else
  fail "Test 1: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 1: exit 0"
else
  fail "Test 1: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 2 (AC2): key absent -> silent no-op (empty stdout), exit 0.
# ---------------------------------------------------------------------------
echo "--- Test 2 (AC2): key absent -> silent no-op, exit 0"
_REPO=$(make_repo_fixture "")
run_helper "$_REPO" "workday-complete"

if [[ -z "$_OUT" ]]; then
  pass "Test 2: stdout empty"
else
  fail "Test 2: expected empty stdout, got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 2: exit 0"
else
  fail "Test 2: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 2b (AC2): key present but empty -> silent no-op, exit 0.
# ---------------------------------------------------------------------------
echo "--- Test 2b (AC2): key present but empty -> silent no-op, exit 0"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: ""\n---')
run_helper "$_REPO" "workday-complete"

if [[ -z "$_OUT" ]]; then
  pass "Test 2b: stdout empty"
else
  fail "Test 2b: expected empty stdout, got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 2b: exit 0"
else
  fail "Test 2b: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 3 (AC3): command exits non-zero -> WARN on stderr, summary line still
# printed with (exit N), helper itself exits 0 (never gates).
# ---------------------------------------------------------------------------
echo "--- Test 3 (AC3): command exits non-zero -> WARN + summary line + exit 0"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "false"\n---')
run_helper "$_REPO" "workday-complete"

_expected="Post-workday-complete hook: ran false (exit 1)"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 3: stdout matches '$_expected'"
else
  fail "Test 3: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ "$_ERR" == *"WARN"* ]]; then
  pass "Test 3: stderr contains WARN"
else
  fail "Test 3: expected WARN on stderr, got '$_ERR'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 3: helper exits 0 (never gates)"
else
  fail "Test 3: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 4a (AC4): a command containing a secret-shaped token is redacted in
# the summary line — never echoed raw. The command is > 60 chars so
# _cs_redact_for_diag truncates it (see coordinator-resolve-validation-cmd.sh).
# ---------------------------------------------------------------------------
echo "--- Test 4a (AC4): secret-shaped command is redacted in summary line"
_secret_cmd='curl -s "https://example.com/publish?token=SUPERSECRETTOKEN1234567890abcdef"'
_REPO=$(make_repo_fixture "$(printf -- '---\nworkday_complete_post_command: "%s"\n---' "$_secret_cmd")")
run_helper "$_REPO" "workday-complete"

if [[ "$_OUT" != *"SUPERSECRETTOKEN1234567890abcdef"* ]]; then
  pass "Test 4a: secret token not present verbatim in stdout"
else
  fail "Test 4a: secret token leaked verbatim in stdout: '$_OUT'"
fi
if [[ "$_OUT" == *"truncated"* ]]; then
  pass "Test 4a: stdout carries the truncation marker (redaction applied)"
else
  fail "Test 4a: expected truncation marker in stdout, got '$_OUT'"
fi

# ---------------------------------------------------------------------------
# Test 4b (AC4): a metachar-bearing command triggers _cs_metachar_warn.
# ---------------------------------------------------------------------------
echo "--- Test 4b (AC4): metachar-bearing command triggers _cs_metachar_warn"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "echo hi; echo bye"\n---')
run_helper "$_REPO" "workday-complete"

if [[ "$_ERR" == *"shell metacharacters"* ]]; then
  pass "Test 4b: metachar WARN present on stderr"
else
  fail "Test 4b: expected metachar WARN on stderr, got '$_ERR'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 4b: exit 0"
else
  fail "Test 4b: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 5 (AC5): command runs with repo root as cwd (pwd-echoing command).
# ---------------------------------------------------------------------------
echo "--- Test 5 (AC5): command runs with repo root as cwd"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "pwd"\n---')
run_helper "$_REPO" "workday-complete"

_real_repo="$(cd "$_REPO" && pwd -P)"
if [[ "$_ERR" == *"$_real_repo"* ]]; then
  pass "Test 5: command's pwd output matches repo root"
else
  fail "Test 5: expected repo root '$_real_repo' in stderr, got '$_ERR'"
fi

# ---------------------------------------------------------------------------
# Test 6: unknown ceremony arg -> WARN + exit 0, no stdout.
# ---------------------------------------------------------------------------
echo "--- Test 6: unknown ceremony arg -> WARN + exit 0, no stdout"
_REPO=$(make_repo_fixture "")
run_helper "$_REPO" "not-a-real-ceremony"

if [[ -z "$_OUT" ]]; then
  pass "Test 6: stdout empty"
else
  fail "Test 6: expected empty stdout, got '$_OUT'"
fi
if [[ "$_ERR" == *"WARN"* && "$_ERR" == *"unknown ceremony"* ]]; then
  pass "Test 6: stderr WARNs about unknown ceremony"
else
  fail "Test 6: expected unknown-ceremony WARN on stderr, got '$_ERR'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 6: exit 0"
else
  fail "Test 6: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 7 (AC12): the pinned call-site emit idiom, run as the terminal
# statement of a `set -e` block with the key ABSENT, exits 0.
#
#   _HOOK_OUT="$(bash "$_cc_root/bin/coordinator-ceremony-hook.sh" <name>)" \
#     || echo "[<ceremony>] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
#   if [ -n "$_HOOK_OUT" ]; then printf '%s\n' "$_HOOK_OUT"; fi
#
# The `if`-form's false branch is exit 0, so the terminal statement of the
# block can never leave a non-zero exit under `set -e` when $_HOOK_OUT is
# empty (the opt-in no-op common case). A bare `[ -n "$_HOOK_OUT" ] && printf
# ...` form would fail this test — that footgun is the anti-scope item this
# AC guards against.
# ---------------------------------------------------------------------------
echo "--- Test 7 (AC12): call-site emit idiom under set -e, key ABSENT, exits 0"
_REPO=$(make_repo_fixture "")
_cc_root="$(cd "$SCRIPT_DIR/.." && pwd)"

# Run the exact pinned idiom in a fresh subshell with set -e, cd-ed to the
# fixture repo (so the helper's repo-root resolution sees the empty-key repo).
_idiom_out=$(cd "$_REPO" && bash -c '
set -e
_HOOK_OUT="$(bash "'"$_cc_root"'/bin/coordinator-ceremony-hook.sh" workday-complete)" \
  || echo "[workday-complete] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
if [ -n "$_HOOK_OUT" ]; then printf "%s\n" "$_HOOK_OUT"; fi
' 2>/dev/null)
_idiom_rc=$?

if [[ $_idiom_rc -eq 0 ]]; then
  pass "Test 7: pinned emit idiom exits 0 under set -e with key absent"
else
  fail "Test 7: pinned emit idiom exited ${_idiom_rc} (expected 0) under set -e with key absent"
fi
if [[ -z "$_idiom_out" ]]; then
  pass "Test 7: pinned emit idiom produced no output when key absent"
else
  fail "Test 7: expected no output, got '$_idiom_out'"
fi

# ---------------------------------------------------------------------------
# Test 8 (AC13): resolver lib unsourceable (simulated path drift) -> WARN,
# exit 0, cs_read_local_md_key never invoked.
#
# Fixture: copy the helper script alone into an isolated bin/ dir with NO
# sibling lib/ dir, so `source "$PLUGIN_ROOT/lib/coordinator-resolve-
# validation-cmd.sh"` fails (file does not exist at the resolved path).
# ---------------------------------------------------------------------------
echo "--- Test 8 (AC13): resolver lib unsourceable -> WARN, exit 0"
_ISOLATED=$(make_tmpdir)
mkdir -p "${_ISOLATED}/bin"
cp "$HELPER" "${_ISOLATED}/bin/coordinator-ceremony-hook.sh"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "echo should-not-run"\n---')

_errfile=$(mktemp)
set +e
_OUT=$(cd "$_REPO" && "$BASH" "${_ISOLATED}/bin/coordinator-ceremony-hook.sh" workday-complete 2>"$_errfile")
_RC=$?
set -e
_ERR=$(cat "$_errfile")
rm -f "$_errfile"

if [[ -z "$_OUT" ]]; then
  pass "Test 8: stdout empty (command never ran)"
else
  fail "Test 8: expected empty stdout (command should not have run), got '$_OUT'"
fi
if [[ "$_ERR" == *"WARN"* && "$_ERR" == *"resolver lib unavailable"* ]]; then
  pass "Test 8: stderr WARNs about unavailable resolver lib"
else
  fail "Test 8: expected resolver-lib-unavailable WARN on stderr, got '$_ERR'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 8: exit 0"
else
  fail "Test 8: expected exit 0, got $_RC"
fi
if [[ "$_OUT" != *"should-not-run"* ]]; then
  pass "Test 8: configured command never invoked (cs_read_local_md_key never reached)"
else
  fail "Test 8: configured command output leaked — cs_read_local_md_key must not have been invoked"
fi

# ---------------------------------------------------------------------------
# Test 9 (Review: code-reviewer F4): non-git repo_root falls back to $PWD.
# make_repo_fixture always `git init`s the fixture, so the `|| pwd` branch of
# `git rev-parse --show-toplevel 2>/dev/null || pwd` is never exercised by
# Tests 1-8. Build a plain (non-git) tmpdir with coordinator.local.md present
# and confirm the key still resolves relative to $PWD.
# ---------------------------------------------------------------------------
echo "--- Test 9: non-git repo_root falls back to \$PWD, key still resolves"
_PLAIN=$(make_tmpdir)
printf '%s\n' $'---\nworkday_complete_post_command: "echo hi"\n---' > "${_PLAIN}/coordinator.local.md"
run_helper "$_PLAIN" "workday-complete"

_expected="Post-workday-complete hook: ran echo hi (exit 0)"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 9: stdout matches '$_expected' (key resolved via \$PWD fallback)"
else
  fail "Test 9: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 9: exit 0"
else
  fail "Test 9: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 10 (Review: code-reviewer F5): metachar-warn suppression var actually
# suppresses the WARN end-to-end through the ceremony hook (Test 4b only
# asserts the WARN fires; this locks in that the suppress var works too).
# ---------------------------------------------------------------------------
echo "--- Test 10: metachar-warn suppression var suppresses WARN via ceremony hook"
_REPO=$(make_repo_fixture $'---\nworkday_complete_post_command: "echo hi; echo bye"\n---')
_errfile=$(mktemp)
set +e
_OUT=$(cd "$_REPO" && COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1 "$BASH" "$HELPER" "workday-complete" 2>"$_errfile")
_RC=$?
set -e
_ERR=$(cat "$_errfile")
rm -f "$_errfile"

if [[ "$_ERR" != *"shell metacharacters"* ]]; then
  pass "Test 10: metachar WARN suppressed on stderr"
else
  fail "Test 10: expected metachar WARN suppressed, got '$_ERR'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 10: exit 0"
else
  fail "Test 10: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi
exit 0
