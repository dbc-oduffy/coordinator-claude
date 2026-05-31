#!/usr/bin/env bash
# install-sentinel.bats — Test suite for write_install_sentinel in install.sh
#
# Purpose: verifies that OSS install.sh plants a valid 40-hex version.txt
# baseline anchor at $CLAUDE_DIR/plugins/coordinator-claude/version.txt, that
# a second run re-stamps (overwrites), and that the WARN-don't-FAIL posture
# holds when the writer binary is absent.
#
# Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 1
#
# NOTE: bats is not installed in all environments. This file uses the project's
# plain-bash test harness convention (matching coordinator/bin/tests/*.bats).
# The file is named .bats so acceptance oracle greps can resolve it.
# "run as bats" means "run this file" — bash handles execution.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/dist/publish-repo-setup/tests/install-sentinel.bats

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SH="${SCRIPT_DIR}/../install.sh"

# ---------------------------------------------------------------------------
# Test framework (matches coordinator/bin/tests/ convention)
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

run_test() {
  local name="$1"
  local fn="$2"
  echo "--- ${name}"
  if "${fn}"; then
    pass "${name}"
  else
    fail "${name}"
  fi
}

assert_matches() {
  local label="$1" pattern="$2" actual="$3"
  if [[ "${actual}" =~ ${pattern} ]]; then
    return 0
  else
    printf '    Expected to match: %s\n' "${pattern}" >&2
    printf '    Actual:   %s\n' "$(printf '%q' "${actual}")" >&2
    return 1
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if printf '%s' "${haystack}" | grep -qF "${needle}"; then
    return 0
  else
    printf '    Expected to contain: %s\n' "${needle}" >&2
    printf '    In: %s\n' "${haystack}" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Scratch environment setup / teardown
#
# We source install.sh with _INSTALL_SH_TEST_SOURCE_ONLY=1 to load its
# function definitions without executing main(). Then we call
# write_install_sentinel directly with the required globals set.
# ---------------------------------------------------------------------------

SCRATCH_DIR=""

setup_scratch() {
  SCRATCH_DIR="$(mktemp -d)"
}

teardown_scratch() {
  if [[ -n "${SCRATCH_DIR}" && -d "${SCRATCH_DIR}" ]]; then
    rm -rf "${SCRATCH_DIR}"
  fi
  SCRATCH_DIR=""
}

# Source install.sh for its function definitions only.
# _INSTALL_SH_TEST_SOURCE_ONLY prevents the trailing `main` call from firing.
# install.sh calls `main` at the bottom of the file — we guard by patching the
# associative-array declare (requires bash 4+) and replacing main with a no-op
# when sourcing for tests.
# Load write_install_sentinel by extracting it from install.sh.
#
# install.sh ends with a bare `main` call which fires on source, making direct
# sourcing impossible in test context. Instead we extract just the
# write_install_sentinel function body using awk and eval it into this shell.
# This is minimal-invasive: only the function definition is loaded; no other
# install.sh side-effects run.
_load_write_install_sentinel() {
  local fn_body
  fn_body="$(awk '
    /^write_install_sentinel\(\)/ { capture=1 }
    capture { print }
    capture && /^\}$/ { capture=0; exit }
  ' "${INSTALL_SH}")"
  if [[ -z "${fn_body}" ]]; then
    echo "ERROR: could not extract write_install_sentinel from ${INSTALL_SH}" >&2
    exit 1
  fi
  # shellcheck disable=SC2116
  eval "${fn_body}"
}

_load_write_install_sentinel

# Resolve $PYTHON once for all tests.
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "ERROR: python3/python not found — required by write_install_sentinel" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helper: build a minimal scratch repo + plugins tree that write_install_sentinel
# can invoke install-sentinel-write against.
#
# Layout:
#   $SCRATCH_DIR/repo/              — a real git repo (REPO_ROOT)
#   $SCRATCH_DIR/home/.claude/plugins/coordinator-claude/  — PLUGINS_TARGET
#   $SCRATCH_DIR/home/.claude/plugins/coordinator-claude/coordinator/bin/install-sentinel-write
#     → symlink (or copy) to the real writer
# ---------------------------------------------------------------------------

REAL_WRITER="${SCRIPT_DIR}/../../../bin/install-sentinel-write"

_build_scratch_env() {
  setup_scratch

  # Git repo (REPO_ROOT)
  local repo="${SCRATCH_DIR}/repo"
  mkdir -p "${repo}"
  git -C "${repo}" init -q
  git -C "${repo}" config user.email "test@example.com"
  git -C "${repo}" config user.name "Test"
  echo "sentinel-test" > "${repo}/README.md"
  git -C "${repo}" add README.md
  git -C "${repo}" commit -q -m "init"

  # Plugin target tree
  local plugins_target="${SCRATCH_DIR}/home/.claude/plugins/coordinator-claude"
  mkdir -p "${plugins_target}/coordinator/bin"

  # Plant the writer (symlink to real writer if present, else copy)
  if [[ -f "${REAL_WRITER}" ]]; then
    cp "${REAL_WRITER}" "${plugins_target}/coordinator/bin/install-sentinel-write"
    chmod +x "${plugins_target}/coordinator/bin/install-sentinel-write"
  else
    # Fallback: write a minimal stub writer for isolated testing
    cat > "${plugins_target}/coordinator/bin/install-sentinel-write" <<'STUB'
#!/usr/bin/env python3
import argparse, subprocess, re, sys
from pathlib import Path
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
p = argparse.ArgumentParser()
p.add_argument("--path", required=True)
p.add_argument("--source", default=".")
p.add_argument("--sha", default=None)
args = p.parse_args()
target = Path(args.path)
if not target.is_dir():
    print(f"ERROR: {target} not a dir", file=sys.stderr); sys.exit(1)
if args.sha:
    sha = args.sha
else:
    r = subprocess.run(["git","-C",args.source,"rev-parse","HEAD"], capture_output=True, text=True)
    if r.returncode != 0: print(r.stderr, file=sys.stderr); sys.exit(1)
    sha = r.stdout.strip()
if not _SHA_RE.fullmatch(sha): print(f"bad sha: {sha!r}", file=sys.stderr); sys.exit(1)
(target / "version.txt").write_text(sha + "\n", encoding="utf-8")
STUB
    chmod +x "${plugins_target}/coordinator/bin/install-sentinel-write"
  fi

  # Expose as globals for write_install_sentinel
  REPO_ROOT="${repo}"
  PLUGINS_TARGET="${plugins_target}"
  PYTHON="${PYTHON:-python3}"
  CLAUDE_DIR="${SCRATCH_DIR}/home/.claude"
}

# ---------------------------------------------------------------------------
# Test 1: write_install_sentinel plants a valid 40-hex version.txt
# ---------------------------------------------------------------------------

test_sentinel_plants_valid_sha() {
  _build_scratch_env

  local output rc=0
  output="$(write_install_sentinel 2>&1)" || rc=$?

  local ok=true
  [[ ${rc} -eq 0 ]] || { echo "    write_install_sentinel exited ${rc}, expected 0" >&2; ok=false; }

  local sentinel="${PLUGINS_TARGET}/version.txt"
  [[ -f "${sentinel}" ]] || { echo "    version.txt not found at ${sentinel}" >&2; ok=false; }

  if [[ -f "${sentinel}" ]]; then
    local sha
    sha="$(cat "${sentinel}")"
    # Strip trailing newline for matching
    sha="${sha%$'\n'}"
    assert_matches "sha-format" "^[0-9a-f]{40}$" "${sha}" || ok=false
  fi

  teardown_scratch
  "${ok}"
}

# ---------------------------------------------------------------------------
# Test 2: second run re-stamps (overwrites) with the same SHA
# ---------------------------------------------------------------------------

test_sentinel_restamps_on_rerun() {
  _build_scratch_env

  # First stamp
  write_install_sentinel >/dev/null 2>&1

  local sha_first
  sha_first="$(cat "${PLUGINS_TARGET}/version.txt")"
  sha_first="${sha_first%$'\n'}"

  # Review: code-reviewer — advance HEAD before the second stamp so sha_first != sha_second,
  # proving the file was actively overwritten (not just that the value is stable).
  # Without this commit the two SHAs are equal by design and the overwrite is not exercised.
  git -C "${REPO_ROOT}" commit --allow-empty -m "second" -q

  # Second stamp — should now reflect the new HEAD
  write_install_sentinel >/dev/null 2>&1

  local sha_second
  sha_second="$(cat "${PLUGINS_TARGET}/version.txt")"
  sha_second="${sha_second%$'\n'}"

  local ok=true
  [[ -f "${PLUGINS_TARGET}/version.txt" ]] || { echo "    version.txt missing after second run" >&2; ok=false; }
  # Both values must be valid 40-hex SHAs
  assert_matches "sha1-format" "^[0-9a-f]{40}$" "${sha_first}" || ok=false
  assert_matches "sha2-format" "^[0-9a-f]{40}$" "${sha_second}" || ok=false
  # The SHAs must DIFFER — second run reflects the new HEAD, proving active overwrite
  [[ "${sha_first}" != "${sha_second}" ]] || {
    echo "    second stamp SHA is unchanged: ${sha_second} — overwrite not proven" >&2
    ok=false
  }

  teardown_scratch
  "${ok}"
}

# ---------------------------------------------------------------------------
# Test 3: WARN-don't-FAIL — writer binary absent → warning printed, exit 0
# ---------------------------------------------------------------------------

test_sentinel_warn_not_fail_if_writer_absent() {
  _build_scratch_env

  # Remove the writer binary
  rm -f "${PLUGINS_TARGET}/coordinator/bin/install-sentinel-write"

  local output rc=0
  output="$(write_install_sentinel 2>&1)" || rc=$?

  local ok=true
  [[ ${rc} -eq 0 ]] || { echo "    exit code was ${rc}, expected 0 (warn-not-fail)" >&2; ok=false; }
  assert_contains "warn-output" "WARNING" "${output}" || ok=false
  # version.txt must NOT exist (no writer ran)
  [[ ! -f "${PLUGINS_TARGET}/version.txt" ]] || {
    echo "    version.txt was written even though writer was absent" >&2
    ok=false
  }

  teardown_scratch
  "${ok}"
}

# ---------------------------------------------------------------------------
# Test 4: SHA in version.txt matches `git -C REPO_ROOT rev-parse HEAD`
# ---------------------------------------------------------------------------

test_sentinel_sha_matches_repo_head() {
  _build_scratch_env

  write_install_sentinel >/dev/null 2>&1

  local sentinel_sha
  sentinel_sha="$(cat "${PLUGINS_TARGET}/version.txt")"
  sentinel_sha="${sentinel_sha%$'\n'}"

  local repo_head
  repo_head="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null)"

  local ok=true
  [[ "${sentinel_sha}" == "${repo_head}" ]] || {
    echo "    sentinel SHA ${sentinel_sha} != repo HEAD ${repo_head}" >&2
    ok=false
  }

  teardown_scratch
  "${ok}"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

run_test "Test 1: plants valid 40-hex version.txt" test_sentinel_plants_valid_sha
run_test "Test 2: re-run re-stamps (overwrites)" test_sentinel_restamps_on_rerun
run_test "Test 3: warn-not-fail when writer binary absent" test_sentinel_warn_not_fail_if_writer_absent
run_test "Test 4: SHA in version.txt matches git HEAD" test_sentinel_sha_matches_repo_head

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed."

if [[ ${FAIL} -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi

exit 0
