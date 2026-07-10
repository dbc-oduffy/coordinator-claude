#!/usr/bin/env bash
# coordinator-artifact-subject.test.sh — table-driven tests for
# coordinator_artifact_subject.
#
# Purpose: verifies the subject-matter classifier against the required test
# surface from the W2.2 spec. Exits non-zero on any failed case so CI and
# manual runs have an unambiguous green/red signal.
#
# Spec backlink: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.2
#
# Run: bash lib/coordinator-artifact-subject.test.sh
# Expected: one PASS line per case; summary line; exit 0 on all-pass.

# Review: code-reviewer F4 — added set -e (matches doe-root.test.sh posture) and
# ERR trap so harness-internal errors produce a distinct HARNESS ABORT exit=2
# rather than silently cascading into counted test failures.
set -euo pipefail
# Distinguish a harness abort (broken fixture, missing binary) from a counted
# test failure — both would otherwise exit 1.
trap 'echo "HARNESS ABORT (unexpected error at line $LINENO) — not a counted test failure" >&2; exit 2' ERR

# Review: code-reviewer F6 — ${BASH_SOURCE[0]} is robust when the file is
# sourced; $0 resolves to the invoking shell name in that mode.
# Locate the library relative to this test file's own directory so the test
# is runnable from any working directory.
_CAS_TEST_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Review: code-reviewer F4 — guard ensures a clean FATAL error rather than
# silent "command not found" failures for every test case.
if [[ ! -f "$_CAS_TEST_SCRIPT_DIR/coordinator-artifact-subject.sh" ]]; then
    echo "FATAL: lib not found at $_CAS_TEST_SCRIPT_DIR/coordinator-artifact-subject.sh" >&2
    exit 1
fi
# shellcheck source=./coordinator-artifact-subject.sh
source "$_CAS_TEST_SCRIPT_DIR/coordinator-artifact-subject.sh"

# ---------------------------------------------------------------------------
# Test runner state
# ---------------------------------------------------------------------------
_cas_test_failures=0
_cas_test_count=0

# ---------------------------------------------------------------------------
# _cas_assert <description> <path> <expected-token> <expected-rc>
#
# Asserts that coordinator_artifact_subject produces the expected stdout token
# and exit code for the given path. Increments failure count on mismatch.
# ---------------------------------------------------------------------------
_cas_assert() {
  local _desc="$1"
  local _path="$2"
  local _expected_token="$3"
  local _expected_rc="$4"

  _cas_test_count=$(( _cas_test_count + 1 ))

  local _got_token
  local _got_rc=0
  _got_token=$(coordinator_artifact_subject "$_path" 2>/dev/null) || _got_rc=$?

  local _pass=1
  if [[ "$_got_token" != "$_expected_token" ]]; then
    _pass=0
  fi
  if [[ "$_got_rc" -ne "$_expected_rc" ]]; then
    _pass=0
  fi

  if [[ $_pass -eq 1 ]]; then
    printf 'PASS  [%s]\n' "$_desc"
  else
    printf 'FAIL  [%s]\n' "$_desc"
    printf '      path="%s"\n' "$_path"
    printf '      expected token="%s" rc=%d\n' "$_expected_token" "$_expected_rc"
    printf '      got     token="%s" rc=%d\n' "$_got_token" "$_got_rc"
    _cas_test_failures=$(( _cas_test_failures + 1 ))
  fi
}

# ---------------------------------------------------------------------------
# _cas_assert_stderr_nonempty <description> <path>
#
# Asserts that coordinator_artifact_subject writes a non-empty remediation
# message to stderr (i.e., the cross-cutting fail-loud contract fires).
# Also verifies rc=2.
# ---------------------------------------------------------------------------
_cas_assert_stderr_nonempty() {
  local _desc="$1"
  local _path="$2"

  _cas_test_count=$(( _cas_test_count + 1 ))

  # Capture stderr; discard stdout.
  # Redirect order: 2>&1 sends stderr to the $() pipe; >/dev/null discards stdout.
  local _stderr
  local _rc=0
  _stderr=$(coordinator_artifact_subject "$_path" 2>&1 >/dev/null) || _rc=$?

  local _pass=1
  if [[ -z "$_stderr" ]]; then
    _pass=0
  fi
  if [[ "$_rc" -ne 2 ]]; then
    _pass=0
  fi

  if [[ $_pass -eq 1 ]]; then
    printf 'PASS  [%s]\n' "$_desc"
  else
    printf 'FAIL  [%s]\n' "$_desc"
    printf '      path="%s"\n' "$_path"
    printf '      rc=%d (expected 2); stderr empty=%s\n' "$_rc" "$( [[ -z "$_stderr" ]] && echo yes || echo no )"
    _cas_test_failures=$(( _cas_test_failures + 1 ))
  fi
}

# ===========================================================================
# Test cases (required by W2.2 spec)
# ===========================================================================

# ---------------------------------------------------------------------------
# Install-chain collision disambiguation (two distinct cases required by spec)
# ---------------------------------------------------------------------------
echo '--- Install-chain collision ---'
_cas_assert \
  'example-orchestration-hub install script → engine' \
  'example-orchestration-hub-repo/install.sh' \
  'engine' 0

_cas_assert \
  'coordinator commands/install.md → doctrine' \
  'plugins/coordinator/commands/install.md' \
  'doctrine' 0

# ---------------------------------------------------------------------------
# ExampleOrchestrationHub-addressed memo → engine
# ---------------------------------------------------------------------------
echo '--- ExampleOrchestrationHub-addressed memo ---'
_cas_assert \
  'to-example-orchestration-hub-repo memo → engine' \
  'state/memos/to-example-orchestration-hub-repo-pcore-roadmap-q3.md' \
  'engine' 0

# ---------------------------------------------------------------------------
# Cross-cutting: DR-207-shaped artifact (stdout + rc + stderr required)
# ---------------------------------------------------------------------------
echo '--- Cross-cutting: DR-207-shaped ---'
_cas_assert \
  'DR-207-shaped artifact → cross-cutting + rc=2' \
  'docs/decisions/DR-207-tri-plane-contract-boundary.md' \
  'cross-cutting' 2

_cas_assert_stderr_nonempty \
  'DR-207-shaped artifact emits stderr remediation' \
  'docs/decisions/DR-207-tri-plane-contract-boundary.md'

# ---------------------------------------------------------------------------
# Cross-cutting: fleet-spine emitter-binding plan (rc + stderr required)
# ---------------------------------------------------------------------------
echo '--- Cross-cutting: fleet-spine emitter-binding ---'
_cas_assert \
  'fleet-spine emitter-binding plan → cross-cutting + rc=2' \
  'docs/plans/2026-07-04-fleet-spine-emitter-binding.md' \
  'cross-cutting' 2

_cas_assert_stderr_nonempty \
  'fleet-spine emitter-binding plan emits stderr remediation' \
  'docs/plans/2026-07-04-fleet-spine-emitter-binding.md'

# ---------------------------------------------------------------------------
# Clear doctrine cases (at least one required by spec)
# ---------------------------------------------------------------------------
echo '--- Clear doctrine ---'
_cas_assert \
  'skills/** file → doctrine' \
  'plugins/coordinator/skills/handoff/SKILL.md' \
  'doctrine' 0

_cas_assert \
  'docs/wiki/** plan → doctrine' \
  'docs/plans/2026-07-04-update-state-placement-law-wiki.md' \
  'doctrine' 0

_cas_assert \
  'hooks/ file → doctrine' \
  'plugins/coordinator/hooks/block-blanket-git-add.sh' \
  'doctrine' 0

_cas_assert \
  'CLAUDE.md → doctrine' \
  'CLAUDE.md' \
  'doctrine' 0

_cas_assert \
  'agents/ file → doctrine' \
  'plugins/coordinator/agents/code-reviewer.md' \
  'doctrine' 0

# ---------------------------------------------------------------------------
# Clear engine cases (at least one required by spec)
# ---------------------------------------------------------------------------
echo '--- Clear engine ---'
_cas_assert \
  'coordinator_core/** → engine' \
  'coordinator_core/session_control/dispatcher.py' \
  'engine' 0

_cas_assert \
  'pcore roadmap → engine' \
  'docs/plans/2026-07-04-pcore-roadmap-q3.md' \
  'engine' 0

_cas_assert \
  'resident-service research → engine' \
  'docs/research/2026-07-04-resident-service-latency-model.md' \
  'engine' 0

_cas_assert \
  'mcp-server research → engine' \
  'docs/research/2026-07-03-mcp-server-load-policy.md' \
  'engine' 0

# Review: code-reviewer F1 — coordinator-doctrine mcp-server path must NOT
# misclassify as engine; Phase 2 pre-emption in coordinator_artifact_subject
# routes coordinator-plugin and docs/wiki mcp-server paths to doctrine before
# the narrowed engine MCP pattern fires.
_cas_assert \
  'coordinator-plugin mcp-server wiki → doctrine (not engine)' \
  'plugins/coordinator/docs/wiki/mcp-server-configuration.md' \
  'doctrine' 0

_cas_assert \
  'docs/wiki mcp-server → doctrine (not engine)' \
  'docs/wiki/mcp-server-configuration.md' \
  'doctrine' 0

# ---------------------------------------------------------------------------
# Additional edge cases (install-chain slug variants)
# ---------------------------------------------------------------------------
echo '--- Install-chain edge cases ---'
_cas_assert \
  'skills/repo-setup → doctrine' \
  'plugins/coordinator/skills/repo-setup/SKILL.md' \
  'doctrine' 0

_cas_assert \
  'example-orchestration-hub-install slug → engine' \
  'docs/plans/2026-07-04-example-orchestration-hub-install-chain-rewire.md' \
  'engine' 0

# ---------------------------------------------------------------------------
# Usage-error cases (rc=1 contract)
# Review: code-reviewer F3 — no-arg / empty-arg usage-error path was untested;
# consumers (W2.3 coordinator_state_root) rely on rc=1 to detect bad calls.
# ---------------------------------------------------------------------------

# Helper: asserts that coordinator_artifact_subject returns rc=1 and writes a
# non-empty stderr message containing the function name (usage hint).
_cas_assert_usage_error() {
  local _desc="$1"
  local _path="$2"

  _cas_test_count=$(( _cas_test_count + 1 ))

  local _stderr _rc
  _rc=0
  _stderr=$(coordinator_artifact_subject "$_path" 2>&1 >/dev/null) || _rc=$?

  local _pass=1
  [[ "$_rc" -eq 1 ]] || _pass=0
  printf '%s' "$_stderr" | grep -q 'coordinator_artifact_subject' || _pass=0

  if [[ $_pass -eq 1 ]]; then
    printf 'PASS  [%s]\n' "$_desc"
  else
    printf 'FAIL  [%s]\n' "$_desc"
    printf '      path="%s"\n' "$_path"
    printf '      rc=%d (expected 1); stderr="%s"\n' "$_rc" "$_stderr"
    _cas_test_failures=$(( _cas_test_failures + 1 ))
  fi
}

echo '--- Usage error ---'
# Empty string arg: triggers -z "${1:-}" guard → rc=1, empty stdout, stderr usage hint.
_cas_assert \
  'empty arg → rc=1, empty stdout' \
  '' '' 1

# Also verify stderr carries the usage message (function name present).
_cas_assert_usage_error \
  'empty arg → stderr contains function name' \
  ''

# ===========================================================================
# Summary
# ===========================================================================
echo ''
echo "Results: $(( _cas_test_count - _cas_test_failures ))/${_cas_test_count} passed"

if [[ $_cas_test_failures -gt 0 ]]; then
  printf 'FAIL: %d test(s) failed.\n' "$_cas_test_failures"
  exit 1
fi

echo 'All tests passed.'
exit 0
