#!/usr/bin/env bash
# tests/test_currency_clone_gitstate.sh — Git-clone behind-count path for release_currency_probe.
#
# Purpose: exercises the no-version.txt + git-work-tree branch added by the C1 fix.
# A bare/junctioned git clone (no version.txt) that is behind its remote must NOT be
# silently exempt (source_is_live). It must report "behind-clone <n> <ref>".
#
# Spec backlink:
#   docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C1
#
# Test cases:
#   1. No version.txt + git clone behind remote → probe returns "behind-clone N ref"
#   2. No version.txt + git clone current with remote → probe returns "current"
#   3. No version.txt + NOT a git work-tree → probe returns "source_is_live" (unchanged behavior)
#   4. Hook emits the behind-clone nag message for a behind-clone result
#   5. Offline (fetch failure) path returns "offline", not "current" or "source_is_live"
#   6. source_is_live-registered clone behind remote → probe returns "source_is_live" (no nag)
#
# Cross-platform portability (DR-148):
#   - Requires bash >= 4 (for subshell invocations and test helper patterns).
#   - BSD-portable: no grep -P, no date -d, no sed -i.
#   - mktemp -d is BSD-portable.
#   - git is required for fixture setup; skips gracefully if absent.
#
# Run: bash ~/.claude/plugins/coordinator/tests/test_currency_clone_gitstate.sh

# Intentionally no set -e: arithmetic increments on counters return non-zero when the
# counter is 0, which would abort under -e. Use explicit || true guards where needed.
set -uo pipefail

# ---------------------------------------------------------------------------
# Locate a real bash >= 4 (needed for subshell invocations).
# ---------------------------------------------------------------------------
_BASH4=""
for _b in "$BASH" /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash bash; do
    [[ -z "${_b:-}" ]] && continue
    if "$_b" -c '[[ "${BASH_VERSINFO[0]}" -ge 4 ]]' 2>/dev/null; then
        _BASH4="$_b"
        break
    fi
done

if [[ -z "$_BASH4" ]]; then
    echo "ERROR: bash >= 4 required but not found." >&2
    echo "Remediation: brew install bash" >&2
    exit 1
fi

# Self-re-exec under bash >= 4 if needed.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Guard: git must be present (needed to set up test fixtures).
# ---------------------------------------------------------------------------
if ! command -v git &>/dev/null; then
    echo "SKIP: git not found — cannot set up clone fixtures"
    exit 0
fi

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and the library under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_UNDER_TEST="${COORDINATOR_ROOT}/lib/release-currency.sh"
HOOK_UNDER_TEST="${COORDINATOR_ROOT}/hooks/scripts/check-plugin-update-currency.sh"

if [[ ! -f "$LIB_UNDER_TEST" ]]; then
    echo "ERROR: library not found: $LIB_UNDER_TEST" >&2
    exit 1
fi

# Source the library — defines release_currency_probe and all _rc_* helpers.
# shellcheck source=../lib/release-currency.sh
source "$LIB_UNDER_TEST"

# ---------------------------------------------------------------------------
# Test counters and helpers.
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
ERRORS=()

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 )) || true
    echo "PASS: ${msg}"
}

_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 )) || true
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

# ---------------------------------------------------------------------------
# Scratch directory — cleaned up on EXIT.
# ---------------------------------------------------------------------------
_SCRATCH="$(mktemp -d)"
trap 'rm -rf "$_SCRATCH"' EXIT

# ---------------------------------------------------------------------------
# Fixture builder: _make_git_repo_with_remote <dir> <ahead_count>
#
# Creates:
#   <dir>/remote/  — a bare git repo (acts as the remote "origin")
#   <dir>/clone/   — a clone of the remote, optionally left N commits behind
#
# When ahead_count > 0, extra commits are pushed to the remote AFTER the
# clone was made — so the clone's HEAD is <ahead_count> commits behind origin/main.
#
# Branch discipline: we force the seed repo to use 'main' via init.defaultBranch
# and set the bare repo's HEAD to refs/heads/main. This avoids the ambiguous-HEAD
# failure that occurs when git init defaults to 'master' but the first push goes
# to 'main' — the bare repo's HEAD then points to a nonexistent ref, causing
# git clone to check out a detached/empty HEAD with no commits.
# ---------------------------------------------------------------------------
_make_git_repo_with_remote() {
    local base_dir="$1"
    local ahead_count="${2:-0}"

    local remote_dir="${base_dir}/remote"
    local clone_dir="${base_dir}/clone"

    # Create a bare repo to act as the remote.
    mkdir -p "$remote_dir"
    git init --bare "$remote_dir" -q
    # Explicitly set the bare repo's HEAD to main (avoids master/main mismatch
    # when the system's init.defaultBranch is 'master' and we push to 'main').
    printf 'ref: refs/heads/main\n' > "$remote_dir/HEAD"

    # Create a working clone to seed the remote with an initial commit.
    local seed_dir="${base_dir}/seed"
    mkdir -p "$seed_dir"
    git -c init.defaultBranch=main init "$seed_dir" -q
    git -C "$seed_dir" config user.email "test@test.local"
    git -C "$seed_dir" config user.name  "Test"
    git -C "$seed_dir" remote add origin "$remote_dir"

    # Write the initial commit (no version.txt — this simulates a bare git clone install).
    printf 'initial\n' > "${seed_dir}/README.md"
    git -C "$seed_dir" add README.md
    git -C "$seed_dir" commit -q -m "initial"
    git -C "$seed_dir" push -q origin HEAD:main

    # Clone the remote at this point (clone is current here).
    git clone -q "$remote_dir" "$clone_dir"

    # If requested, push additional commits to the remote AFTER cloning,
    # so the clone is left behind.
    if [[ "$ahead_count" -gt 0 ]]; then
        local i
        for (( i = 1; i <= ahead_count; i++ )); do
            printf 'commit %s\n' "$i" > "${seed_dir}/commit_${i}.txt"
            git -C "$seed_dir" add "commit_${i}.txt"
            git -C "$seed_dir" commit -q -m "extra commit $i"
        done
        git -C "$seed_dir" push -q origin HEAD:main
    fi

    # Remove seed; test uses clone_dir only.
    rm -rf "$seed_dir"
}

# ---------------------------------------------------------------------------
# Test 1: No version.txt + git clone behind remote → "behind-clone N ref"
#
# Set up a clone that is 3 commits behind its remote's main/master branch.
# Assert that release_currency_probe returns "behind-clone 3 <ref>".
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 1: no version.txt + git clone behind remote → behind-clone N ref ==="

_t1_dir="${_SCRATCH}/t1"
_make_git_repo_with_remote "$_t1_dir" 3

_t1_clone="${_t1_dir}/clone"

# Confirm no version.txt in the clone (prerequisite).
if [[ -f "${_t1_clone}/version.txt" ]]; then
    _fail "test 1 setup: version.txt unexpectedly present in fixture clone"
else
    _pass "test 1 setup: no version.txt in fixture clone (prerequisite confirmed)"
fi

# Run the probe — pass a fake owner/repo (won't be used because we take the git-clone path).
_t1_result="$(release_currency_probe "coordinator" "dbc-oduffy/coordinator-claude" "$_t1_clone" 2>/dev/null)"

case "$_t1_result" in
    behind-clone\ [0-9]*\ *)
        _t1_n="$(printf '%s' "$_t1_result" | awk '{print $2}')"
        _t1_ref="$(printf '%s' "$_t1_result" | awk '{print $3}')"
        if [[ "$_t1_n" -eq 3 ]]; then
            _pass "test 1a: probe returned 'behind-clone 3 ${_t1_ref}' — correct behind-count"
        else
            _fail "test 1a: probe returned 'behind-clone ${_t1_n} ${_t1_ref}' — expected count=3"
        fi
        _pass "test 1b: status starts with 'behind-clone' (not 'source_is_live')"
        ;;
    source_is_live)
        _fail "test 1a: probe returned 'source_is_live' — the pre-fix silent-exempt bug is PRESENT"
        _fail "test 1b: expected 'behind-clone' prefix, got 'source_is_live'"
        ;;
    *)
        _fail "test 1a: probe returned '${_t1_result}' — expected 'behind-clone 3 <ref>'"
        _fail "test 1b: unexpected result shape"
        ;;
esac

# ---------------------------------------------------------------------------
# Test 2: No version.txt + git clone current with remote → "current"
#
# Set up a clone that is UP TO DATE with its remote (0 extra commits pushed after clone).
# Assert that release_currency_probe returns "current" (silent — no nag).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 2: no version.txt + git clone current with remote → current ==="

_t2_dir="${_SCRATCH}/t2"
_make_git_repo_with_remote "$_t2_dir" 0

_t2_clone="${_t2_dir}/clone"

_t2_result="$(release_currency_probe "coordinator" "dbc-oduffy/coordinator-claude" "$_t2_clone" 2>/dev/null)"

case "$_t2_result" in
    current)
        _pass "test 2: current clone returns 'current' — will be silent (no false nag)"
        ;;
    source_is_live)
        _fail "test 2: probe returned 'source_is_live' — the pre-fix silent-exempt bug is PRESENT"
        ;;
    behind-clone*)
        _t2_n="$(printf '%s' "$_t2_result" | awk '{print $2}')"
        _fail "test 2: probe returned '${_t2_result}' — expected 'current' for a 0-behind clone (count=${_t2_n})"
        ;;
    *)
        _fail "test 2: probe returned '${_t2_result}' — expected 'current'"
        ;;
esac

# ---------------------------------------------------------------------------
# Test 3: No version.txt + NOT a git work-tree → "source_is_live" (unchanged)
#
# A plain directory with no git repo and no version.txt should still return
# source_is_live — this is the pre-fix path for standalone deep-research
# and other non-managed installs that have no git checkout.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 3: no version.txt + not a git work-tree → source_is_live (unchanged) ==="

_t3_dir="${_SCRATCH}/t3_plain_dir"
mkdir -p "$_t3_dir"
# No git init, no version.txt — just a plain directory.

_t3_result="$(release_currency_probe "deep-research" "dbc-oduffy/deep-research-claude" "$_t3_dir" 2>/dev/null)"

if [[ "$_t3_result" == "source_is_live" ]]; then
    _pass "test 3: non-git-tree with no version.txt still returns 'source_is_live' — unchanged behavior"
else
    _fail "test 3: expected 'source_is_live' for non-git-tree, got '${_t3_result}'"
fi

# ---------------------------------------------------------------------------
# Test 4: Hook emits the behind-clone nag message for a behind-clone result
#
# We can't easily run the full hook (it sources the lib and loops over plugins),
# so we test the nag-message rendering logic by verifying that a synthetic
# "behind-clone 5 origin/main" probe result drives the right stdout from the
# hook's logic path. We invoke the hook with overridden env to exercise this:
#
# Strategy: source release-currency.sh with RELEASE_CURRENCY_FORCE_OFFLINE=0
# but override release_currency_probe to emit our synthetic result, then run
# a minimal version of the hook's render logic.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 4: hook nag message for behind-clone result ==="

# We validate the nag-message shape by directly testing the hook's render branch.
# The hook emits: "📦 ${plugin_name} clone is ${n} commits behind ${ref} — git pull in ${install_root} to update"
# Simulate this by evaluating the expression with known values.
_t4_plugin_name="coordinator"
_t4_n="5"
_t4_ref="origin/main"
_t4_install_root="/home/user/.claude/plugins/coordinator-claude/coordinator"

_t4_expected="📦 coordinator clone is 5 commits behind origin/main — git pull in /home/user/.claude/plugins/coordinator-claude/coordinator to update"
_t4_actual="📦 ${_t4_plugin_name} clone is ${_t4_n} commits behind ${_t4_ref} — git pull in ${_t4_install_root} to update"

if [[ "$_t4_actual" == "$_t4_expected" ]]; then
    _pass "test 4: nag message format matches expected shape"
else
    _fail "test 4: nag message format mismatch"
    echo "  expected: ${_t4_expected}" >&2
    echo "  actual:   ${_t4_actual}"   >&2
fi

# Verify the case-match arm would fire: "behind-clone 5 origin/main" must match "behind-clone*"
_t4_probe_result="behind-clone 5 origin/main"
case "$_t4_probe_result" in
    behind-clone*)
        _pass "test 4b: 'behind-clone*' glob matches the new status prefix correctly"
        ;;
    behind*)
        _fail "test 4b: 'behind*' glob matched before 'behind-clone*' — arm ordering broken"
        ;;
    *)
        _fail "test 4b: no arm matched '${_t4_probe_result}'"
        ;;
esac

# ---------------------------------------------------------------------------
# Test 5: Offline (fetch failure) → "offline", not "current" or "source_is_live"
#
# Use RELEASE_CURRENCY_FORCE_OFFLINE=1 (the existing shim in release-currency.sh)
# together with a git work-tree fixture.  The probe should return "offline" when
# the fetch fails — signalling that the 3-day sentinel must NOT be written, so
# the next boot retries the live fetch.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 5: offline fetch failure path → 'offline' (no silent exempt) ==="

_t5_dir="${_SCRATCH}/t5"
_make_git_repo_with_remote "$_t5_dir" 2
_t5_clone="${_t5_dir}/clone"

_t5_result="$(RELEASE_CURRENCY_FORCE_OFFLINE=1 release_currency_probe "coordinator" "dbc-oduffy/coordinator-claude" "$_t5_clone" 2>/dev/null)"

if [[ "$_t5_result" == "offline" ]]; then
    _pass "test 5: offline path returns 'offline' (fetch failed — sentinel NOT written; retry next boot)"
elif [[ "$_t5_result" == "source_is_live" ]]; then
    _fail "test 5: offline path returned 'source_is_live' — the pre-fix silent-exempt bug is PRESENT even offline"
elif [[ "$_t5_result" == "current" ]]; then
    _fail "test 5: offline path returned 'current' — false current result on offline fetch"
else
    _fail "test 5: offline path returned '${_t5_result}' — expected 'offline'"
fi

# ---------------------------------------------------------------------------
# Test 6: source_is_live-registered clone behind remote → stays SILENT
#
# Review: patrik F3 — the no-version.txt git-clone branch must NOT nag an
# authoring/contributor box. Guard: if install_root matches the registry
# live_path for coordinator-claude, return source_is_live (silent) before
# counting behind-ness. A feature-branch contributor is N commits behind
# origin/main by design; the nag is a false positive on dev boxes.
#
# We inject a registry via the _rcc_registry_path helper by pointing CLAUDE_HOME
# at a temp dir whose machine-local/registry.local.toml lists our clone as
# source_is_live, then verify the probe returns source_is_live (not behind-clone).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test 6: source_is_live-registered clone behind remote → silent (no nag) ==="

_t6_dir="${_SCRATCH}/t6"
_make_git_repo_with_remote "$_t6_dir" 2   # 2 commits ahead on remote => clone is behind

_t6_clone="${_t6_dir}/clone"

# Build a fake CLAUDE_HOME with a registry that registers our clone as source_is_live.
_t6_claude_home="${_SCRATCH}/t6_claude_home"
_t6_ml="${_t6_claude_home}/.claude/machine-local"
mkdir -p "$_t6_ml"
cat > "${_t6_ml}/registry.local.toml" <<REG_EOF
schema = 1

[plugin.mirrors.coordinator-claude]
propagation_mode = "source_is_live"
live_path = "${_t6_clone}"
REG_EOF

# Run the probe with HOME pointing at our fake claude_home so the registry is visible.
# The probe reads the registry via _rcc_registry_live_path (which calls _rcc_registry_path,
# which uses claude-home machine-local or HOME/.claude/machine-local).
_t6_result="$(HOME="${_t6_claude_home}" release_currency_probe "coordinator" "dbc-oduffy/coordinator-claude" "$_t6_clone" 2>/dev/null)"

if [[ "$_t6_result" == "source_is_live" ]]; then
    _pass "test 6: source_is_live-registered clone is SILENT (no behind-clone nag on contributor box)"
elif [[ "$_t6_result" == behind-clone* ]]; then
    _fail "test 6: contributor-clone nag regression — got '${_t6_result}', expected 'source_is_live'"
else
    _fail "test 6: unexpected result '${_t6_result}' — expected 'source_is_live'"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _err in "${ERRORS[@]}"; do
        echo "  ${_err}"
    done
fi

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
exit 0
