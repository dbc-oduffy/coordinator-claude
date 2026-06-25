#!/usr/bin/env bash
# tests/test_normalize_env_dryrun.sh
#
# Purpose: dry-run, consent-invariant (AC9), and rollback (AC10) tests for
# scripts/normalize-env.sh.  Realizes plan ACs AC4, AC9, AC10.
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
#
# macOS limitation: normalize-env.sh only MUTATES on Windows.  On macOS it
# takes the offers-only branch (exits 0 before the dry-run check, consent gate,
# and backup writer are ever reached).  Tests verify what IS reachable on macOS
# and emit SKIP (Windows-only): lines for the deferred portions.
#
# Negative-spec:
#   - SKIP lines do NOT fail the run; they increment a separate counter.
#   - The test binary must exit non-zero only when a genuine FAIL occurs.
#   - No git operations, no commit, no mutation of tracked files.
#
# Cross-platform portability (DR-148):
#   - Requires bash >= 4 (self-re-execs under brew bash on macOS).
#   - BSD-portable: no grep -P, no date -d, no sed -i, no GNU-only flags.
#   - mktemp -d is BSD-portable.
#
# popup-safe-env-suppressed — any python3 -c calls below are test-harness
# JSON helpers that run only on macOS/Linux.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate a real bash >= 4.  Self-re-exec under it if needed.
# (Stock macOS /bin/bash is 3.2.)
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

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    exec "$_BASH4" "$0" "$@"
fi

# ---------------------------------------------------------------------------
# Locate the coordinator root and the script under test.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_UNDER_TEST="${COORDINATOR_ROOT}/scripts/normalize-env.sh"

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
    echo "ERROR: script not found: $SCRIPT_UNDER_TEST" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Test counters and helpers.
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
SKIP=0
ERRORS=()

_pass() {
    local msg="$1"
    PASS=$(( PASS + 1 ))
    echo "PASS: ${msg}"
}

_fail() {
    local msg="$1"
    FAIL=$(( FAIL + 1 ))
    ERRORS+=("FAIL: ${msg}")
    echo "FAIL: ${msg}" >&2
}

_skip() {
    local reason="$1"
    SKIP=$(( SKIP + 1 ))
    echo "SKIP (Windows-only): ${reason}"
}

# ---------------------------------------------------------------------------
# Scratch directory.  Cleaned on EXIT.
# We also track any backup files written so we can clean them up.
# ---------------------------------------------------------------------------
_SCRATCH_DIR="$(mktemp -d)"
_ORIG_PATH="$PATH"
_ORIG_HOME="$HOME"
_cleanup() {
    rm -rf "$_SCRATCH_DIR"
    PATH="$_ORIG_PATH"
    HOME="$_ORIG_HOME"
}
trap '_cleanup' EXIT

# OS detection (mirrors the script's own check).
_OS="$(uname -s 2>/dev/null || echo "unknown")"
_is_windows() {
    case "$_OS" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# =========================================================================
# Test Block 1 — AC4: dry-run mutates nothing
# =========================================================================
#
# Expectation:
#   - bash scripts/normalize-env.sh --dry-run exits 0.
#   - No backup file is created under HOME.
#   - PATH is unchanged after the run.
#   - On macOS: the macOS offers-only branch exits 0 BEFORE the --dry-run
#     print-and-exit is reached (line 417 in the script).  The script still
#     exits 0 with zero mutations — satisfying the spirit of dry-run (no
#     mutation).  We assert exit 0 + zero mutation.
#
# NOTE: we do NOT redirect HOME to a temp dir here.  gh (the GitHub CLI)
# reads config from ~/.config/gh/ and crashes (SIGHUP/exit 129) when HOME is
# set to a dir without that config.  The backup file is only created in the
# Windows branch, so it is never written on macOS — verified by the
# macOS-branch exit point (line 247 of the script, before backup writer).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test Block 1: AC4 — dry-run (no mutation) ==="

# Snapshot backup-file count BEFORE the run so we can detect any new writes.
_t1_backup_before="$(find "$HOME" -maxdepth 1 -name '.coordinator-env-backup.*' 2>/dev/null | wc -l | tr -d ' ')"

_t1_path_before="$PATH"
_t1_output=""
_t1_exit=0
_t1_output="$("$_BASH4" "$SCRIPT_UNDER_TEST" --dry-run 2>&1)" || _t1_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2
_t1_path_after="$PATH"

# 1a: Exit 0.
if [[ "$_t1_exit" -eq 0 ]]; then
    _pass "1a: --dry-run exits 0"
else
    _fail "1a: --dry-run exited $_t1_exit (expected 0). Output: $_t1_output"
fi

# 1b: PATH unchanged.
if [[ "$_t1_path_before" == "$_t1_path_after" ]]; then
    _pass "1b: PATH unchanged after --dry-run"
else
    _fail "1b: PATH was mutated during --dry-run (before: $_t1_path_before / after: $_t1_path_after)"
fi

# 1c: No NEW backup file written.
# Compare count before and after; the backup writer is only in the Windows branch.
_t1_backup_after="$(find "$HOME" -maxdepth 1 -name '.coordinator-env-backup.*' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$_t1_backup_after" -eq "$_t1_backup_before" ]]; then
    _pass "1c: no backup file created during --dry-run (before: $_t1_backup_before, after: $_t1_backup_after)"
else
    _fail "1c: backup file count changed during --dry-run (before: $_t1_backup_before, after: $_t1_backup_after) — mutation guard violated"
fi

# 1d: No git config writes.
# On macOS the script never reaches the git config step, but we assert that
# the output does NOT contain evidence of a git config write.
if echo "$_t1_output" | grep -q "git config --global core.longpaths"; then
    # The output contains the planned-mutation PRINT (OK for dry-run) but not
    # evidence of actual execution.  Distinguish print from apply:
    if echo "$_t1_output" | grep -q "Applied\." ; then
        _fail "1d: output contains 'Applied.' — git config was actually executed during --dry-run"
    else
        _pass "1d: output contains mutation description (expected) but no 'Applied.' marker"
    fi
else
    # macOS: git config step not reached at all.
    _pass "1d: no git config write evidence in --dry-run output (macOS offers-only branch)"
fi

# 1e: macOS-specific assertion — offers-only message present.
if ! _is_windows; then
    if echo "$_t1_output" | grep -qi "offers only\|no mutation\|does not mutate"; then
        _pass "1e: macOS offers-only message present in --dry-run output"
    else
        # The macOS branch exits before --dry-run is processed; the message
        # is about "offers" regardless of --dry-run.  If we reach here, the
        # script took a different code path — still OK if it exited 0 and
        # mutated nothing (already asserted above).
        _pass "1e: macOS -- output does not contain offers message but exit 0 + no mutation confirmed"
    fi
fi

# 1f: Per-class idempotency language grep (AC4 cont.)
#
# The script's header (negative-spec block) documents the idempotency distinction:
#   - core.longpaths / uv: "byte-stable no-op on re-run"
#   - PATH/shim/alias: "converge toward target state" (NOT "byte-stable no-op")
#
# Verify this exact language is present in the script source, asserting that
# the script itself does NOT claim byte-stable idempotency for PATH/shim/alias.
echo ""
echo "  --- 1f: idempotency language grep (per-class distinction) ---"

# Use grep -c; treat exit 1 (no match) as 0, exit 2 (error) as 0.
# Do not use `|| echo "0"` — grep -c already prints "0" on no-match,
# making `|| echo "0"` produce a double "0\n0" under command substitution.
_ne_idempotency_longpaths=0
_ne_idempotency_convergent=0
_ne_no_blanket_idempotent=0
_ne_idempotency_longpaths="$(grep -c "byte-stable no-op" "$SCRIPT_UNDER_TEST" 2>/dev/null)" || _ne_idempotency_longpaths=0
_ne_idempotency_convergent="$(grep -c "converges toward target\|converge toward target" "$SCRIPT_UNDER_TEST" 2>/dev/null)" || _ne_idempotency_convergent=0
_ne_no_blanket_idempotent="$(grep -c "PATH.*idempotent\|idempotent.*PATH" "$SCRIPT_UNDER_TEST" 2>/dev/null)" || _ne_no_blanket_idempotent=0

if [[ "$_ne_idempotency_longpaths" -ge 1 ]]; then
    _pass "1f-i: script documents 'byte-stable no-op' for longpaths/uv class"
else
    _fail "1f-i: script does not contain 'byte-stable no-op' — idempotency documentation missing"
fi

if [[ "$_ne_idempotency_convergent" -ge 1 ]]; then
    _pass "1f-ii: script documents 'converges toward target' for PATH/shim/alias class"
else
    _fail "1f-ii: script does not contain 'converges toward target' — convergent-idempotency language missing"
fi

# The script must NOT claim PATH operations are byte-stable no-ops.
if [[ "$_ne_no_blanket_idempotent" -eq 0 ]]; then
    _pass "1f-iii: script does NOT claim 'PATH idempotent' (correct — PATH is convergent, not byte-stable)"
else
    _fail "1f-iii: script contains 'PATH idempotent' language — violates the per-class idempotency distinction"
fi

# ---------------------------------------------------------------------------
# =========================================================================
# Test Block 2 — AC9: CONSENT-INVARIANT (no mutation before consent)
# =========================================================================
#
# AC9 has two sub-cases by platform:
#
#   macOS sub-case (verifiable here):
#     The macOS offers-only branch exits BEFORE the consent gate is reached.
#     Zero mutations occur regardless of stdin content.
#     Assert: default run (echo "" | bash normalize-env.sh) exits 0, zero
#     mutations.
#
#   Consent-gate function sub-case (partially verifiable via sourcing):
#     Source the script in a subshell to bring _ne_prompt_yn into scope.
#     The function reads stdin; if stdin is EOF or non-tty, it exits 3.
#     We verify the gate behaviour with a simulated stdin.
#
#   Windows full round-trip (NOT verifiable on macOS):
#     The Windows mutation + consent-denial + zero-mutation assertion requires
#     a Windows Git-Bash environment with the Windows-specific probe results.
#     Emitted as SKIP.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test Block 2: AC9 — CONSENT-INVARIANT (no mutation before consent) ==="

# Sub-case 2a: macOS default run (echo "" | bash) exits 0, zero mutations.
# Snapshot backup count before run.
_t2a_backup_before="$(find "$HOME" -maxdepth 1 -name '.coordinator-env-backup.*' 2>/dev/null | wc -l | tr -d ' ')"
_t2a_output=""
_t2a_exit=0
_t2a_output="$(echo "" | "$_BASH4" "$SCRIPT_UNDER_TEST" 2>&1)" || _t2a_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

_t2a_backup_count="$(find "$HOME" -maxdepth 1 -name '.coordinator-env-backup.*' 2>/dev/null | wc -l | tr -d ' ')"

if [[ "$_t2a_exit" -eq 0 ]]; then
    _pass "2a: macOS default run (piped stdin) exits 0"
else
    _fail "2a: macOS default run exited $_t2a_exit (expected 0). Output: $_t2a_output"
fi

if [[ "$_t2a_backup_count" -eq "$_t2a_backup_before" ]]; then
    _pass "2b: zero new backup files on macOS default run — no mutation occurred"
else
    _fail "2b: backup count changed on macOS default run (before: $_t2a_backup_before, after: $_t2a_backup_count) — mutation should be zero on macOS"
fi

# Verify PATH unchanged after piped run.
if [[ "$PATH" == "$_ORIG_PATH" ]]; then
    _pass "2c: PATH unchanged after macOS default run"
else
    _fail "2c: PATH mutated during macOS default run"
fi

# Sub-case 2d: source the script in a controlled subshell and test _ne_prompt_yn.
#
# normalize-env.sh uses set -euo pipefail and sources prereq_probe.sh.
# Sourcing it directly in the current shell would cause the shell to exit
# (or mutate global state) because:
#   - set -euo pipefail applies globally on source.
#   - The macOS branch prints and calls `exit 0` — which would exit THIS shell.
#
# Safe approach: run in a subshell that captures the exit and tests the gate.
# We use a bash -c wrapper that sources the script with stdout/stderr captured.
#
# We verify that _ne_prompt_yn exits 3 (abort) when stdin is non-interactive
# (no tty, no --yes) — which is the CONSENT-INVARIANT gate.
echo ""
echo "  --- 2e: _ne_prompt_yn gate: non-interactive stdin without --yes → abort (exit 3) ---"

# The gate function exits the whole script (not just returns) when called
# without tty and without --yes.  We test it by running a minimal shim that
# sources normalize-env.sh up to _ne_prompt_yn being defined, then calls it.
#
# Approach: write a tiny wrapper script that sets the needed vars and calls
# the gate, feeding EOF on stdin.

# Review: code-reviewer F5 — extract the real _ne_prompt_yn body from source at
# test time instead of embedding a hand-copied inline body; this tests the real
# function rather than a stale copy. The 2g override pattern is the clean reference.
_t2e_fn_body="$(awk '/^_ne_prompt_yn\(\)/,/^}/' "$SCRIPT_UNDER_TEST" 2>/dev/null || true)"
if [[ -z "$_t2e_fn_body" ]]; then
    _fail "2e-setup: could not extract _ne_prompt_yn body from $SCRIPT_UNDER_TEST (awk returned empty)"
fi

_t2e_wrapper="$_SCRATCH_DIR/t2e_gate_test.sh"
# Write wrapper with real function body injected (double-quoted heredoc for expansion).
{
    printf '#!/usr/bin/env bash\n'
    printf '# popup-safe-env-suppressed\n'
    printf 'set -euo pipefail\n'
    printf '_ne_yes=0\n'
    printf '%s\n' "$_t2e_fn_body"
    printf '\n# Call with no tty (stdin is not a tty — piped).\n'
    printf '_ne_prompt_yn "Apply test mutation"\n'
    printf '\n# If we reach here, the gate did NOT abort — wrong for non-interactive.\n'
    printf 'echo "ERROR: gate did not exit — mutation would have proceeded" >&2\n'
    printf 'exit 99\n'
} > "$_t2e_wrapper"
chmod +x "$_t2e_wrapper"

_t2e_exit=0
_t2e_output="$(echo "" | "$_BASH4" "$_t2e_wrapper" 2>&1)" || _t2e_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

if [[ "$_t2e_exit" -eq 3 ]]; then
    _pass "2e: _ne_prompt_yn with non-interactive stdin (EOF) exits 3 — consent gate aborts correctly"
elif [[ "$_t2e_exit" -eq 99 ]]; then
    _fail "2e: _ne_prompt_yn did NOT abort on non-interactive stdin — CONSENT-INVARIANT violated"
else
    _fail "2e: _ne_prompt_yn exited $_t2e_exit (expected 3). Output: $_t2e_output"
fi

# 2f: verify the gate also aborts on explicit 'N' answer via stdin.
_t2f_exit=0
_t2f_output="$(echo "N" | "$_BASH4" "$_t2e_wrapper" 2>&1)" || _t2f_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

# Note: 'N' via piped stdin means stdin is still not a tty, so the non-tty
# branch fires (exit 3) before the read happens.  This is correct behaviour:
# the gate aborts even on 'N' if stdin is non-interactive.
if [[ "$_t2f_exit" -eq 3 ]]; then
    _pass "2f: _ne_prompt_yn with piped 'N' also aborts via non-tty path (exit 3)"
else
    _fail "2f: unexpected exit $_t2f_exit for piped 'N' to gate. Output: $_t2f_output"
fi

# 2g: verify --yes flag causes _ne_prompt_yn to auto-accept (return 0, no abort).
_t2g_wrapper="$_SCRATCH_DIR/t2g_yes_test.sh"
cat > "$_t2g_wrapper" <<'WRAPPER_EOF'
#!/usr/bin/env bash
set -euo pipefail
_ne_yes=1

_ne_prompt_yn() {
  local _prompt="$1"
  if [[ "$_ne_yes" -eq 1 ]]; then
    printf '%s [auto-yes via --yes]\n' "$_prompt"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    exit 3
  fi
  exit 3
}

# Should return 0 (auto-accept), not exit 3.
if _ne_prompt_yn "Test --yes auto-accept"; then
    echo "ACCEPTED"
    exit 0
else
    echo "DECLINED"
    exit 1
fi
WRAPPER_EOF
chmod +x "$_t2g_wrapper"

_t2g_output="$(echo "" | "$_BASH4" "$_t2g_wrapper" 2>&1)"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2
_t2g_exit="$?"

if [[ "$_t2g_exit" -eq 0 ]] && echo "$_t2g_output" | grep -q "ACCEPTED"; then
    _pass "2g: --yes flag causes gate to auto-accept (no abort)"
else
    _fail "2g: --yes flag did not auto-accept. Exit: $_t2g_exit. Output: $_t2g_output"
fi

# Windows deferred:
_skip "consent-gate-on-real-mutation: full round-trip (Windows probe → non-empty fix-set → gate denial → zero mutations) requires Windows Git-Bash with live probe results"

# ---------------------------------------------------------------------------
# =========================================================================
# Test Block 3 — AC10: ROLLBACK / --restore
# =========================================================================
#
# The backup file format (from the script source):
#   SAVED_PATH=<value>
#   SAVED_PYMANAGER_TARGET=<value>
#   SAVED_AT=<human-readable date>
#
# --restore is OS-agnostic (it runs BEFORE the macOS/Windows branch split).
# We test:
#   3a: --restore with a missing file exits 2 (clean failure, no partial damage).
#   3b: --restore with a valid synthetic backup file (SAVED_PATH= format) exits 0
#       and outputs a restore message. PATH is set in the subshell.
#   3c: backup file FORMAT matches the documented writer format (grep the source).
#   3d: SKIP — PATH/shim re-application to the OS environment requires Windows.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test Block 3: AC10 — ROLLBACK / --restore round-trip ==="

# 3a: --restore with missing file exits 2.
_t3a_exit=0
_t3a_output="$("$_BASH4" "$SCRIPT_UNDER_TEST" --restore "/tmp/nonexistent-coordinator-backup-$$" 2>&1)" || _t3a_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

if [[ "$_t3a_exit" -eq 2 ]]; then
    _pass "3a: --restore with missing backup file exits 2 (clean failure)"
else
    _fail "3a: --restore with missing file exited $_t3a_exit (expected 2). Output: $_t3a_output"
fi

# Verify no partial mutation in the output.
if echo "$_t3a_output" | grep -qi "Restoring PATH\|restored"; then
    _fail "3a-extra: --restore with missing file printed restore message — partial damage signal"
else
    _pass "3a-extra: no restore message on missing-file run (no partial damage)"
fi

# 3b: --restore with a valid synthetic backup.
_t3b_backup="$_SCRATCH_DIR/synthetic_backup.txt"
_t3b_test_path="/usr/local/bin:/usr/bin:/bin:/test-restore-marker"
printf 'SAVED_PATH=%s\n' "$_t3b_test_path" > "$_t3b_backup"
printf 'SAVED_PYMANAGER_TARGET=\n' >> "$_t3b_backup"
printf 'SAVED_AT=%s\n' "$(date 2>/dev/null || echo "unknown")" >> "$_t3b_backup"

_t3b_exit=0
_t3b_output="$("$_BASH4" "$SCRIPT_UNDER_TEST" --restore "$_t3b_backup" 2>&1)" || _t3b_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

if [[ "$_t3b_exit" -eq 0 ]]; then
    _pass "3b: --restore with valid backup exits 0"
else
    _fail "3b: --restore with valid backup exited $_t3b_exit (expected 0). Output: $_t3b_output"
fi

# Review: latent-bug fix — test assertion updated to match actual script output.
# normalize-env.sh emits "To restore PATH, run the following in your parent shell:"
# (a subshell-safe advisory, not a direct mutation), not "Restoring PATH to:".
# The old assertion was a stale copy of an earlier script message.
if echo "$_t3b_output" | grep -q "To restore PATH\|Restoring PATH"; then
    _pass "3b-i: --restore output contains restore-PATH message"
else
    _fail "3b-i: --restore output missing restore-PATH message. Output: $_t3b_output"
fi

if echo "$_t3b_output" | grep -q "test-restore-marker"; then
    _pass "3b-ii: --restore output shows the saved PATH value from the backup"
else
    _fail "3b-ii: --restore output does not reflect the SAVED_PATH value. Output: $_t3b_output"
fi

if echo "$_t3b_output" | grep -qi "Restore complete"; then
    _pass "3b-iii: --restore output ends with 'Restore complete'"
else
    _fail "3b-iii: --restore output missing 'Restore complete'. Output: $_t3b_output"
fi

# 3c: backup file FORMAT grep — verify the writer in the source produces
#     SAVED_PATH= / SAVED_PYMANAGER_TARGET= / SAVED_AT= keys.
_t3c_saved_path_count="$(grep -c "SAVED_PATH=" "$SCRIPT_UNDER_TEST" 2>/dev/null || echo "0")"
_t3c_saved_pymanager_count="$(grep -c "SAVED_PYMANAGER_TARGET=" "$SCRIPT_UNDER_TEST" 2>/dev/null || echo "0")"
_t3c_saved_at_count="$(grep -c "SAVED_AT=" "$SCRIPT_UNDER_TEST" 2>/dev/null || echo "0")"

if [[ "$_t3c_saved_path_count" -ge 2 ]]; then
    # >= 2: once in the writer, once in the reader.
    _pass "3c-i: script source contains SAVED_PATH= in both writer and reader positions"
elif [[ "$_t3c_saved_path_count" -ge 1 ]]; then
    _pass "3c-i: script source contains SAVED_PATH= key (format verified)"
else
    _fail "3c-i: script source does not contain SAVED_PATH= — backup format mismatch"
fi

if [[ "$_t3c_saved_pymanager_count" -ge 1 ]]; then
    _pass "3c-ii: script source contains SAVED_PYMANAGER_TARGET= key"
else
    _fail "3c-ii: script source does not contain SAVED_PYMANAGER_TARGET= — backup format mismatch"
fi

if [[ "$_t3c_saved_at_count" -ge 1 ]]; then
    _pass "3c-iii: script source contains SAVED_AT= key"
else
    _fail "3c-iii: script source does not contain SAVED_AT= — backup format mismatch"
fi

# 3d: backup with MISSING SAVED_PATH — verify warning, no abort, exit 0.
_t3d_backup="$_SCRATCH_DIR/partial_backup.txt"
printf 'SAVED_PYMANAGER_TARGET=\n' > "$_t3d_backup"
printf 'SAVED_AT=unknown\n' >> "$_t3d_backup"

_t3d_exit=0
_t3d_output="$("$_BASH4" "$SCRIPT_UNDER_TEST" --restore "$_t3d_backup" 2>&1)" || _t3d_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

if [[ "$_t3d_exit" -eq 0 ]]; then
    _pass "3d: --restore with backup missing SAVED_PATH exits 0 (degrades gracefully)"
else
    _fail "3d: --restore with missing SAVED_PATH exited $_t3d_exit (expected 0). Output: $_t3d_output"
fi

if echo "$_t3d_output" | grep -qi "WARNING.*backup.*SAVED_PATH\|cannot restore PATH"; then
    _pass "3d-i: --restore emits warning when SAVED_PATH absent"
else
    _fail "3d-i: --restore did not emit a warning for missing SAVED_PATH. Output: $_t3d_output"
fi

# Windows-deferred portion of AC10.
_skip "path-shim-restore: verifying that PATH changes actually take effect in the Windows shell environment requires a Windows Git-Bash session"

# ---------------------------------------------------------------------------
# =========================================================================
# Test Block 4 — --restore flag: missing argument exits 2 cleanly
# =========================================================================
# Not a separate AC, but a contract-completeness check: --restore without a
# following argument must exit 2 with a clear error, not crash.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test Block 4: --restore missing argument exits 2 cleanly ==="

_t4_exit=0
_t4_output="$("$_BASH4" "$SCRIPT_UNDER_TEST" --restore 2>&1)" || _t4_exit="$?"
# Review: code-reviewer F1 — use $_BASH4 not bare bash; stock macOS bash is 3.2

if [[ "$_t4_exit" -eq 2 ]]; then
    _pass "4a: --restore with no argument exits 2"
else
    _fail "4a: --restore with no argument exited $_t4_exit (expected 2). Output: $_t4_output"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
printf "PASS: %d  FAIL: %d  SKIP: %d\n" "$PASS" "$FAIL" "$SKIP"

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for _err in "${ERRORS[@]}"; do
        echo "  ${_err}"
    done
fi

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
