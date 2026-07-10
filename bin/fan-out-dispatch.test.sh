#!/usr/bin/env bash
# bin/fan-out-dispatch.test.sh — Self-contained test suite for fan-out-dispatch.sh
#
# Purpose: Validate the fan-out helper's overlap detection, malformed-row rejection,
# clean-spec emission, no-commit-verb guarantee, cap-breach warning, and non-git-repo
# hard-error. All tests use temp directories for fixtures; cleanup is guaranteed.
#
# Spec backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md §Chunk 1
# Spec backlink (organic-ramp — D3 update, Test E, Test H): docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §C4
#
# Usage: bash bin/fan-out-dispatch.test.sh
# Exit 0 = all tests pass; non-zero = at least one failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/fan-out-dispatch.sh"

PASS=0
FAIL=0
TMPDIR_ROOT=""

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
_setup() {
    TMPDIR_ROOT="$(mktemp -d)"
}

_teardown() {
    if [[ -n "$TMPDIR_ROOT" ]] && [[ -d "$TMPDIR_ROOT" ]]; then
        rm -rf "$TMPDIR_ROOT"
    fi
}

trap _teardown EXIT

_setup

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

_assert_exit_nonzero() {
    local label="$1" exit_code="$2"
    if [[ "$exit_code" -ne 0 ]]; then
        _pass "$label — exited non-zero (${exit_code})"
    else
        _fail "$label — expected non-zero exit, got 0"
    fi
}

_assert_exit_zero() {
    local label="$1" exit_code="$2"
    if [[ "$exit_code" -eq 0 ]]; then
        _pass "$label — exited zero"
    else
        _fail "$label — expected zero exit, got ${exit_code}"
    fi
}

_assert_stdout_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _pass "$label — stdout contains: ${needle}"
    else
        _fail "$label — stdout missing: ${needle}"
        echo "    (actual stdout first 400 chars: ${haystack:0:400})"
    fi
}

_assert_stdout_not_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _fail "$label — stdout unexpectedly contains: ${needle}"
        echo "    (actual stdout first 400 chars: ${haystack:0:400})"
    else
        _pass "$label — stdout does not contain: ${needle}"
    fi
}

_assert_stderr_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _pass "$label — stderr contains: ${needle}"
    else
        _fail "$label — stderr missing: ${needle}"
        echo "    (actual stderr first 400 chars: ${haystack:0:400})"
    fi
}

_assert_stderr_not_contains() {
    local label="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF -- "$needle"; then
        _fail "$label — stderr unexpectedly contains: ${needle}"
        echo "    (actual stderr first 400 chars: ${haystack:0:400})"
    else
        _pass "$label — stderr does not contain: ${needle}"
    fi
}

_assert_count_in_stdout() {
    local label="$1" needle="$2" expected_count="$3" haystack="$4"
    local actual
    actual="$(echo "$haystack" | grep -cF -- "$needle" || true)"
    if [[ "$actual" -eq "$expected_count" ]]; then
        _pass "$label — '${needle}' appears exactly ${expected_count} time(s)"
    else
        _fail "$label — '${needle}' appears ${actual} time(s), expected ${expected_count}"
    fi
}

# Build a minimal git repo for tests that need one
_make_git_repo() {
    local dir="$1"
    mkdir -p "$dir"
    cd "$dir"
    git init -q || { echo "FATAL: git setup failed in $dir" >&2; exit 1; }
    git config user.email "test@example.com" || { echo "FATAL: git setup failed in $dir" >&2; exit 1; }
    git config user.name "Test" || { echo "FATAL: git setup failed in $dir" >&2; exit 1; }
    git commit -q --allow-empty -m "init" || { echo "FATAL: git setup failed in $dir" >&2; exit 1; }
    cd - >/dev/null
}

# ---------------------------------------------------------------------------
# Test A — Overlap spec: two chunks claiming the same file → non-zero + collision listed
# ---------------------------------------------------------------------------
echo ""
echo "=== Test A: file-overlap detection ==="

REPO_A="${TMPDIR_ROOT}/repo_a"
_make_git_repo "$REPO_A"

SPEC_A="${TMPDIR_ROOT}/spec_a.tsv"
printf 'chunk-1\tFix auth module\tauth.py,shared.py\n' > "$SPEC_A"
printf 'chunk-2\tFix billing module\tbilling.py,shared.py\n' >> "$SPEC_A"

STDOUT_A=""
STDERR_A=""
EXIT_A=0
cd "$REPO_A"
STDOUT_A="$(bash "$HELPER" --spec "$SPEC_A" 2>${TMPDIR_ROOT}/stderr_a.txt)" || EXIT_A=$?
STDERR_A="$(cat ${TMPDIR_ROOT}/stderr_a.txt)"
cd - >/dev/null

_assert_exit_nonzero "A1: overlap → non-zero exit" "$EXIT_A"
_assert_stderr_contains "A2: overlap → names colliding file" "shared.py" "$STDERR_A"
_assert_stderr_contains "A3: overlap → names chunk-1" "chunk-1" "$STDERR_A"
_assert_stderr_contains "A4: overlap → names chunk-2" "chunk-2" "$STDERR_A"
_assert_stdout_not_contains "A5: overlap → no partial output emitted" "EXECUTOR DISPATCH BLOCK" "$STDOUT_A"

# ---------------------------------------------------------------------------
# Test B — Malformed rows: wrong field count, empty field, would-be embedded newline
# ---------------------------------------------------------------------------
echo ""
echo "=== Test B: malformed-row detection ==="

REPO_B="${TMPDIR_ROOT}/repo_b"
_make_git_repo "$REPO_B"

# B1: wrong field count (only 2 tabs, so 3 fields but spec says format wrong — test with 2 fields)
SPEC_B1="${TMPDIR_ROOT}/spec_b1.tsv"
printf 'chunk-1\tFix something\n' > "$SPEC_B1"   # only 2 fields

STDOUT_B1=""
STDERR_B1=""
EXIT_B1=0
cd "$REPO_B"
STDOUT_B1="$(bash "$HELPER" --spec "$SPEC_B1" 2>${TMPDIR_ROOT}/stderr_b1.txt)" || EXIT_B1=$?
STDERR_B1="$(cat ${TMPDIR_ROOT}/stderr_b1.txt)"
cd - >/dev/null

_assert_exit_nonzero "B1: wrong-field-count → non-zero exit" "$EXIT_B1"
_assert_stderr_contains "B1: wrong-field-count → names row" "row 1" "$STDERR_B1"
_assert_stdout_not_contains "B1: wrong-field-count → no partial output" "EXECUTOR DISPATCH BLOCK" "$STDOUT_B1"

# B2: empty chunk-id field
SPEC_B2="${TMPDIR_ROOT}/spec_b2.tsv"
printf '\tFix something\tfile.py\n' > "$SPEC_B2"  # empty chunk-id

STDOUT_B2=""
STDERR_B2=""
EXIT_B2=0
cd "$REPO_B"
STDOUT_B2="$(bash "$HELPER" --spec "$SPEC_B2" 2>${TMPDIR_ROOT}/stderr_b2.txt)" || EXIT_B2=$?
STDERR_B2="$(cat ${TMPDIR_ROOT}/stderr_b2.txt)"
cd - >/dev/null

_assert_exit_nonzero "B2: empty-chunk-id → non-zero exit" "$EXIT_B2"
_assert_stderr_contains "B2: empty-chunk-id → names row" "row 1" "$STDERR_B2"
_assert_stdout_not_contains "B2: empty-chunk-id → no partial output" "EXECUTOR DISPATCH BLOCK" "$STDOUT_B2"

# B3: empty files field
SPEC_B3="${TMPDIR_ROOT}/spec_b3.tsv"
printf 'chunk-1\tFix something\t\n' > "$SPEC_B3"  # empty files

STDOUT_B3=""
STDERR_B3=""
EXIT_B3=0
cd "$REPO_B"
STDOUT_B3="$(bash "$HELPER" --spec "$SPEC_B3" 2>${TMPDIR_ROOT}/stderr_b3.txt)" || EXIT_B3=$?
STDERR_B3="$(cat ${TMPDIR_ROOT}/stderr_b3.txt)"
cd - >/dev/null

_assert_exit_nonzero "B3: empty-files-field → non-zero exit" "$EXIT_B3"
_assert_stderr_contains "B3: empty-files-field → names chunk" "chunk-1" "$STDERR_B3"
_assert_stdout_not_contains "B3: empty-files-field → no partial output" "EXECUTOR DISPATCH BLOCK" "$STDOUT_B3"

# B4: 4-field row with a pinned-interface column — now VALID (optional 4th column accepted).
# The 4th field 'extra-field' is not a well-formed <symbol>@<path> pin, so the helper
# emits a NOTE about the malformed pin on stderr but still exits 0 and emits the block.
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md §C2 (AC2)
SPEC_B4="${TMPDIR_ROOT}/spec_b4.tsv"
printf 'chunk-1\tBrief\tfile.py\textra-field\n' > "$SPEC_B4"

STDOUT_B4=""
STDERR_B4=""
EXIT_B4=0
cd "$REPO_B"
STDOUT_B4="$(bash "$HELPER" --spec "$SPEC_B4" 2>${TMPDIR_ROOT}/stderr_b4.txt)" || EXIT_B4=$?
STDERR_B4="$(cat ${TMPDIR_ROOT}/stderr_b4.txt)"
cd - >/dev/null

_assert_exit_zero "B4: 4-field row (optional pin column) → zero exit (backward-compat: 4 fields now valid)" "$EXIT_B4"
_assert_stdout_contains "B4: 4-field row → dispatch block still emitted" "EXECUTOR DISPATCH BLOCK" "$STDOUT_B4"

# B5: embedded newline in a field — breaks the row into fragments whose field-count
# won't be 3, so the line-based parser catches it via field-count mismatch.
# Construct: chunk-id contains an embedded newline (yields two lines when parsed).
# We printf a literal newline inside the chunk-id field using $'...' syntax.
SPEC_B5="${TMPDIR_ROOT}/spec_b5.tsv"
# The embedded newline splits "chunk\nid" across two lines; neither line has 3 fields.
printf 'chunk\nid\tBrief here\tfile.py\n' > "$SPEC_B5"

STDOUT_B5=""
STDERR_B5=""
EXIT_B5=0
cd "$REPO_B"
STDOUT_B5="$(bash "$HELPER" --spec "$SPEC_B5" 2>${TMPDIR_ROOT}/stderr_b5.txt)" || EXIT_B5=$?
STDERR_B5="$(cat ${TMPDIR_ROOT}/stderr_b5.txt)"
cd - >/dev/null

_assert_exit_nonzero "B5: embedded-newline → non-zero exit" "$EXIT_B5"
_assert_stdout_not_contains "B5: embedded-newline → no dispatch block emitted" "EXECUTOR DISPATCH BLOCK" "$STDOUT_B5"

# B6: comma-in-path is a documented format limitation (NOT a detectable error).
# Comma is the field-3 delimiter, so "a,b" in the path field produces TWO path entries.
# This test asserts the DOCUMENTED behaviour so it isn't mistaken for a bug later.
# The helper exits zero and emits a block listing both "a" and "b" as separate file entries.
SPEC_B6="${TMPDIR_ROOT}/spec_b6.tsv"
printf 'chunk-x\tBrief\ta,b\n' > "$SPEC_B6"

STDOUT_B6=""
EXIT_B6=0
cd "$REPO_B"
STDOUT_B6="$(bash "$HELPER" --spec "$SPEC_B6" 2>/dev/null)" || EXIT_B6=$?
cd - >/dev/null

_assert_exit_zero "B6: comma-in-path → zero exit (known limitation, not detectable error)" "$EXIT_B6"
_assert_stdout_contains "B6: comma-in-path → path 'a' appears as separate entry" "- a" "$STDOUT_B6"
_assert_stdout_contains "B6: comma-in-path → path 'b' appears as separate entry" "- b" "$STDOUT_B6"

# ---------------------------------------------------------------------------
# Test C — Clean 3-chunk spec → 3 blocks, each with required tokens, correct peer blocks
# ---------------------------------------------------------------------------
echo ""
echo "=== Test C: clean 3-chunk spec → 3 blocks with all required tokens ==="

REPO_C="${TMPDIR_ROOT}/repo_c"
_make_git_repo "$REPO_C"

SPEC_C="${TMPDIR_ROOT}/spec_c.tsv"
printf 'alpha\tImplement the alpha feature\talpha.py,alpha_test.py\n' > "$SPEC_C"
printf 'beta\tImplement the beta feature\tbeta.py,beta_test.py\n' >> "$SPEC_C"
printf 'gamma\tImplement the gamma feature\tgamma.py,gamma_test.py\n' >> "$SPEC_C"

STDOUT_C=""
STDERR_C=""
EXIT_C=0
cd "$REPO_C"
STDOUT_C="$(bash "$HELPER" --spec "$SPEC_C" 2>${TMPDIR_ROOT}/stderr_c.txt)" || EXIT_C=$?
STDERR_C="$(cat ${TMPDIR_ROOT}/stderr_c.txt)"
cd - >/dev/null

_assert_exit_zero "C0: clean spec → zero exit" "$EXIT_C"

# Three blocks emitted
_assert_count_in_stdout "C1: exactly 3 dispatch blocks" "EXECUTOR DISPATCH BLOCK" 3 "$STDOUT_C"
_assert_count_in_stdout "C2: exactly 3 end-block markers" "END BLOCK" 3 "$STDOUT_C"

# Each chunk's ID appears in its own block header
_assert_stdout_contains "C3a: alpha block present" "EXECUTOR DISPATCH BLOCK: alpha" "$STDOUT_C"
_assert_stdout_contains "C3b: beta block present" "EXECUTOR DISPATCH BLOCK: beta" "$STDOUT_C"
_assert_stdout_contains "C3c: gamma block present" "EXECUTOR DISPATCH BLOCK: gamma" "$STDOUT_C"

# Briefs present
_assert_stdout_contains "C4a: alpha brief present" "Implement the alpha feature" "$STDOUT_C"
_assert_stdout_contains "C4b: beta brief present" "Implement the beta feature" "$STDOUT_C"
_assert_stdout_contains "C4c: gamma brief present" "Implement the gamma feature" "$STDOUT_C"

# In-scope files
_assert_stdout_contains "C5a: alpha.py in alpha block" "alpha.py" "$STDOUT_C"
_assert_stdout_contains "C5b: beta.py in beta block" "beta.py" "$STDOUT_C"
_assert_stdout_contains "C5c: gamma.py in gamma block" "gamma.py" "$STDOUT_C"

# Peer blocks: alpha's block must name beta and gamma as peers
# (We check that beta and gamma appear as out-of-scope — each appears in 2 peer blocks = 2 times total)
_assert_count_in_stdout "C6a: beta named as peer 2 times" "beta (files:" 2 "$STDOUT_C"
_assert_count_in_stdout "C6b: gamma named as peer 2 times" "gamma (files:" 2 "$STDOUT_C"
_assert_count_in_stdout "C6c: alpha named as peer 2 times" "alpha (files:" 2 "$STDOUT_C"

# Destructive-action prohibition present in each block (appears 3 times)
_assert_count_in_stdout "C7: destructive-action prohibition in all blocks" "Destructive-action prohibition" 3 "$STDOUT_C"

# Disk-first preamble present — assert section heading AND a unique body token from the snippet
_assert_stdout_contains "C8a: disk-first preamble section heading present" "Disk-first verification preamble" "$STDOUT_C"
_assert_stdout_contains "C8b: disk-first preamble body token 'TEXT ONLY' present (from snippet)" "TEXT ONLY" "$STDOUT_C"

# Out-of-scope header present 3 times (one per block)
_assert_count_in_stdout "C9: out-of-scope header in all blocks" "Out-of-scope" 3 "$STDOUT_C"

# expected_branch present in all blocks (3 times)
_assert_count_in_stdout "C10: expected_branch in all blocks" "expected_branch:" 3 "$STDOUT_C"

# In-scope section header present 3 times (one per block)
_assert_count_in_stdout "C11: in-scope section header in all blocks" "### In-scope" 3 "$STDOUT_C"

# ---------------------------------------------------------------------------
# Test D — No commit verb in emitted blocks + cap reminder on stderr
# ---------------------------------------------------------------------------
echo ""
echo "=== Test D: no commit verb in executor blocks; cap reminder on stderr ==="

# Reuse stdout from Test C (clean 3-chunk, same repo)
# The reminder is on stderr; check there are no commit-action verbs in stdout blocks

# "executors do NOT commit" is the allowed phrasing (it's a prohibition, not an instruction)
# We check that active commit-instruction forms don't appear in executor blocks
# Specifically: "git commit" as an instruction to the executor should not appear
# The preamble on stderr says "Executors do NOT commit" — but that's stderr not stdout

# Check stdout blocks don't contain "git commit" as an executor instruction.
# The emitted prohibition text uses "Do NOT stage, push, or commit" — it never contains
# the literal string "git commit". Absence of "git commit" is the correct, portable check.
# (GNU-grep -P Perl lookbehind was used here before; replaced with a portable -F check.)
_assert_stdout_not_contains "D1: no active 'git commit' instruction in executor blocks" "git commit" "$STDOUT_C"

# Simpler check: stdout blocks should not contain "git add" as a positive instruction
# (the only git add belongs in the EM reminders section which goes to stderr)
_assert_stdout_not_contains "D2: no 'git add' executor instruction in stdout" "git add --" "$STDOUT_C"

# Ramp reminder present on stderr (from Test C run) — must contain 'pilot' AND 'ramp', must NOT contain '6-8'
_assert_stderr_contains "D3a: ramp reminder on stderr contains 'pilot'" "pilot" "$STDERR_C"
_assert_stderr_contains "D3b: ramp reminder on stderr contains 'ramp'" "ramp" "$STDERR_C"
_assert_stderr_not_contains "D3c: ramp reminder on stderr does not contain '6-8'" "6-8" "$STDERR_C"
_assert_stdout_not_contains "D3d: small wave (below threshold) → no large-wave NOTE on stdout" "large wave" "$STDOUT_C"
_assert_stderr_contains "D4: commit discipline reminder on stderr" "Executors do NOT commit" "$STDERR_C"
_assert_stderr_contains "D5: EM commit instruction on stderr" "git add --" "$STDERR_C"

# ---------------------------------------------------------------------------
# Test E — Large-wave NOTE boundary: exactly LARGE_WAVE_THRESHOLD chunks fires NOTE;
#           LARGE_WAVE_THRESHOLD-1 chunks does not. No WARNING or PM call in either case.
#
# Pin LARGE_WAVE_THRESHOLD=12 explicitly so the test is independent of the runner's
# core count and the machine-local registry (spec: § "The pinned cap-breach contract", C4).
# ---------------------------------------------------------------------------
echo ""
echo "=== Test E: large-wave NOTE boundary at LARGE_WAVE_THRESHOLD=12 ==="

export LARGE_WAVE_THRESHOLD=12

REPO_E="${TMPDIR_ROOT}/repo_e"
_make_git_repo "$REPO_E"

# E-at: exactly 12 chunks (N == threshold) → NOTE fires
SPEC_E_AT="${TMPDIR_ROOT}/spec_e_at.tsv"
for n in $(seq 1 12); do
    printf "chunk-%s\tBrief for chunk %s\tfile%s.py\n" "$n" "$n" "$n"
done > "$SPEC_E_AT"

STDOUT_E_AT=""
EXIT_E_AT=0
cd "$REPO_E"
STDOUT_E_AT="$(LARGE_WAVE_THRESHOLD=12 bash "$HELPER" --spec "$SPEC_E_AT" 2>/dev/null)" || EXIT_E_AT=$?
cd - >/dev/null

_assert_exit_zero "E1: 12-chunk spec → zero exit (NOTE, not error)" "$EXIT_E_AT"
_assert_stdout_contains "E2: 12 chunks → NOTE contains 'large wave'" "large wave" "$STDOUT_E_AT"
_assert_stdout_not_contains "E3: 12-chunk output does not contain WARNING" "WARNING" "$STDOUT_E_AT"
_assert_stdout_not_contains "E4: 12-chunk output does not reference PM call" "PM call" "$STDOUT_E_AT"

# E-below: 11 chunks (N-1 == threshold-1) → NOTE does NOT fire
SPEC_E_BELOW="${TMPDIR_ROOT}/spec_e_below.tsv"
for n in $(seq 1 11); do
    printf "chunk-%s\tBrief for chunk %s\tfile%s.py\n" "$n" "$n" "$n"
done > "$SPEC_E_BELOW"

STDOUT_E_BELOW=""
EXIT_E_BELOW=0
cd "$REPO_E"
STDOUT_E_BELOW="$(LARGE_WAVE_THRESHOLD=12 bash "$HELPER" --spec "$SPEC_E_BELOW" 2>/dev/null)" || EXIT_E_BELOW=$?
cd - >/dev/null

_assert_exit_zero "E5: 11-chunk spec → zero exit" "$EXIT_E_BELOW"
_assert_stdout_not_contains "E6: 11 chunks (N-1) → no large-wave NOTE" "large wave" "$STDOUT_E_BELOW"
_assert_stdout_not_contains "E7: 11-chunk output does not contain WARNING" "WARNING" "$STDOUT_E_BELOW"
_assert_stdout_not_contains "E8: 11-chunk output does not reference PM call" "PM call" "$STDOUT_E_BELOW"

# ---------------------------------------------------------------------------
# Test F — Non-repo directory → clear non-zero error (AC8)
# ---------------------------------------------------------------------------
echo ""
echo "=== Test F: non-git-repo directory → clear error ==="

NONREPO_DIR="${TMPDIR_ROOT}/not_a_repo"
mkdir -p "$NONREPO_DIR"

SPEC_F="${TMPDIR_ROOT}/spec_f.tsv"
printf 'chunk-1\tSome brief\tsome_file.py\n' > "$SPEC_F"

STDOUT_F=""
STDERR_F=""
EXIT_F=0
cd "$NONREPO_DIR"
STDOUT_F="$(bash "$HELPER" --spec "$SPEC_F" 2>${TMPDIR_ROOT}/stderr_f.txt)" || EXIT_F=$?
STDERR_F="$(cat ${TMPDIR_ROOT}/stderr_f.txt)"
cd - >/dev/null

_assert_exit_nonzero "F1: non-git-repo → non-zero exit" "$EXIT_F"
_assert_stderr_contains "F2: non-git-repo → mentions git repository" "git repository" "$STDERR_F"
_assert_stderr_contains "F3: non-git-repo → provides remediation" "Remediation" "$STDERR_F"
_assert_stdout_not_contains "F4: non-git-repo → no partial output" "EXECUTOR DISPATCH BLOCK" "$STDOUT_F"

# ---------------------------------------------------------------------------
# Test G — @file brief form
# ---------------------------------------------------------------------------
echo ""
echo "=== Test G: @file brief form ==="

REPO_G="${TMPDIR_ROOT}/repo_g"
_make_git_repo "$REPO_G"

BRIEF_FILE="${TMPDIR_ROOT}/brief_g.txt"
echo "This is a longer brief read from a file" > "$BRIEF_FILE"

SPEC_G="${TMPDIR_ROOT}/spec_g.tsv"
printf "chunk-g\t@${BRIEF_FILE}\tsome_file.py\n" > "$SPEC_G"

STDOUT_G=""
EXIT_G=0
cd "$REPO_G"
STDOUT_G="$(bash "$HELPER" --spec "$SPEC_G" 2>/dev/null)" || EXIT_G=$?
cd - >/dev/null

_assert_exit_zero "G0: @file brief → zero exit" "$EXIT_G"
_assert_stdout_contains "G1: @file brief content present in output" "longer brief read from a file" "$STDOUT_G"

# ---------------------------------------------------------------------------
# Test H — Large-wave threshold resolution order (AC8): env → machine-local → 16
# Hermetic via MACHINE_LOCAL_REGISTRY_DIR so it never reads the real registry, and
# proves the fallback floor is 16, NOT the old 8. Each case unsets both the short
# script-level var (LARGE_WAVE_THRESHOLD) and the machine-local env escape hatch
# (MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD) except where it is the variable under test.
# ---------------------------------------------------------------------------
echo ""
echo "=== Test H: large-wave threshold resolution (env → machine-local → fallback 16) ==="
# Clear any LARGE_WAVE_THRESHOLD exported by an earlier test (Test E exports it) at script
# scope, so the per-case subshell unsets are not the only line of defense (ordering fragility).
unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD

REPO_H="${TMPDIR_ROOT}/repo_h"
_make_git_repo "$REPO_H"

# Build an N-chunk spec with disjoint file scopes (no overlap collisions).
_make_n_chunk_spec() {
    local n="$1" out="$2" i
    : > "$out"
    for (( i = 1; i <= n; i++ )); do
        printf 'chunk-%d\tbrief %d\tfile_%d.py\n' "$i" "$i" "$i" >> "$out"
    done
}

NOTE_PHRASE="large wave"
for n in 16 15 8 5 4 3 2; do _make_n_chunk_spec "$n" "${TMPDIR_ROOT}/spec_h${n}.tsv"; done

# --- H1: no env, empty registry → fallback 16 (and floor is 16, not 8) ---
REG_H1="$(mktemp -d "${TMPDIR_ROOT}/regH1.XXXXXX")"
cd "$REPO_H"
OUT_H16="$(unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; MACHINE_LOCAL_REGISTRY_DIR="$REG_H1" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h16.tsv" 2>/dev/null)"
OUT_H15="$(unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; MACHINE_LOCAL_REGISTRY_DIR="$REG_H1" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h15.tsv" 2>/dev/null)"
OUT_H8="$(unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; MACHINE_LOCAL_REGISTRY_DIR="$REG_H1" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h8.tsv" 2>/dev/null)"
cd - >/dev/null
_assert_stdout_contains "H1a: fallback 16 → NOTE at 16 chunks" "$NOTE_PHRASE" "$OUT_H16"
_assert_stdout_not_contains "H1b: fallback 16 → no NOTE at 15 chunks" "$NOTE_PHRASE" "$OUT_H15"
_assert_stdout_not_contains "H1c: fallback floor is 16 NOT 8 → no NOTE at 8 chunks" "$NOTE_PHRASE" "$OUT_H8"

# --- H2: machine-local registry value (5) wins over the fallback ---
REG_H2="$(mktemp -d "${TMPDIR_ROOT}/regH2.XXXXXX")"
MACHINE_LOCAL_REGISTRY_DIR="$REG_H2" machine-local set fan_out.large_wave_threshold 5 >/dev/null
cd "$REPO_H"
OUT_H5="$(unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; MACHINE_LOCAL_REGISTRY_DIR="$REG_H2" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h5.tsv" 2>/dev/null)"
OUT_H4="$(unset LARGE_WAVE_THRESHOLD MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; MACHINE_LOCAL_REGISTRY_DIR="$REG_H2" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h4.tsv" 2>/dev/null)"
cd - >/dev/null
_assert_stdout_contains "H2a: machine-local=5 → NOTE at 5 chunks" "$NOTE_PHRASE" "$OUT_H5"
_assert_stdout_not_contains "H2b: machine-local=5 → no NOTE at 4 chunks" "$NOTE_PHRASE" "$OUT_H4"

# --- H3: short env var LARGE_WAVE_THRESHOLD wins over the registry value ---
cd "$REPO_H"
OUT_H3="$(unset MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; LARGE_WAVE_THRESHOLD=3 MACHINE_LOCAL_REGISTRY_DIR="$REG_H2" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h3.tsv" 2>/dev/null)"
OUT_H2="$(unset MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD; LARGE_WAVE_THRESHOLD=3 MACHINE_LOCAL_REGISTRY_DIR="$REG_H2" bash "$HELPER" --spec "${TMPDIR_ROOT}/spec_h2.tsv" 2>/dev/null)"
cd - >/dev/null
_assert_stdout_contains "H3a: env=3 beats registry=5 → NOTE at 3 chunks" "$NOTE_PHRASE" "$OUT_H3"
_assert_stdout_not_contains "H3b: env=3 → no NOTE at 2 chunks" "$NOTE_PHRASE" "$OUT_H2"

# ---------------------------------------------------------------------------
# Test I — Pinned-interface column, symbol IS present in producer write-target
#           → no NOTE on stderr, exit 0, dispatch blocks emitted.
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md §C2 (AC1)
# ---------------------------------------------------------------------------
echo ""
echo "=== Test I: pinned-interface pin present → silent, exit 0, blocks emitted ==="

REPO_I="${TMPDIR_ROOT}/repo_i"
_make_git_repo "$REPO_I"

# Create the producer write-target containing the pinned symbol.
PRODUCER_FILE_I="${TMPDIR_ROOT}/producer_i.py"
cat > "$PRODUCER_FILE_I" <<'PYEOF'
def my_pinned_function(x):
    """The interface the consumer chunk expects."""
    return x
PYEOF

SPEC_I="${TMPDIR_ROOT}/spec_i.tsv"
printf "chunk-producer\tAuthor the producer\t${PRODUCER_FILE_I}\n" > "$SPEC_I"
printf "chunk-consumer\tAuthor the consumer\tconsumer.py\tmy_pinned_function@${PRODUCER_FILE_I}\n" >> "$SPEC_I"

STDOUT_I=""
STDERR_I=""
EXIT_I=0
cd "$REPO_I"
STDOUT_I="$(bash "$HELPER" --spec "$SPEC_I" 2>${TMPDIR_ROOT}/stderr_i.txt)" || EXIT_I=$?
STDERR_I="$(cat "${TMPDIR_ROOT}/stderr_i.txt")"
cd - >/dev/null

_assert_exit_zero "I1: symbol present → exit 0" "$EXIT_I"
_assert_stdout_contains "I2: symbol present → producer block emitted" "EXECUTOR DISPATCH BLOCK: chunk-producer" "$STDOUT_I"
_assert_stdout_contains "I3: symbol present → consumer block emitted" "EXECUTOR DISPATCH BLOCK: chunk-consumer" "$STDOUT_I"
_assert_stderr_not_contains "I4: symbol present → no NOTE about missing interface" "NOT found" "$STDERR_I"
_assert_stderr_not_contains "I5: symbol present → no NOTE about file not existing" "does not exist" "$STDERR_I"

# ---------------------------------------------------------------------------
# Test J — Pinned-interface column, symbol is ABSENT from producer write-target
#           → offer NOTE on stderr naming serial-fallback + exit 0 + dispatch blocks present.
# Negative-spec: exit code MUST be 0 (not 1 like the overlap pass). NOTE on stderr, not stdout.
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md §C2 (AC1)
# ---------------------------------------------------------------------------
echo ""
echo "=== Test J: pinned-interface pin absent → offer NOTE on stderr, exit 0, blocks present ==="

REPO_J="${TMPDIR_ROOT}/repo_j"
_make_git_repo "$REPO_J"

# Producer file exists but does NOT contain the pinned symbol.
PRODUCER_FILE_J="${TMPDIR_ROOT}/producer_j.py"
cat > "$PRODUCER_FILE_J" <<'PYEOF'
def some_other_function():
    """This file exists but does not define the expected interface."""
    pass
PYEOF

SPEC_J="${TMPDIR_ROOT}/spec_j.tsv"
printf "chunk-producer\tAuthor the producer\t${PRODUCER_FILE_J}\n" > "$SPEC_J"
printf "chunk-consumer\tAuthor the consumer\tconsumer.py\tmissing_symbol@${PRODUCER_FILE_J}\n" >> "$SPEC_J"

STDOUT_J=""
STDERR_J=""
EXIT_J=0
cd "$REPO_J"
STDOUT_J="$(bash "$HELPER" --spec "$SPEC_J" 2>${TMPDIR_ROOT}/stderr_j.txt)" || EXIT_J=$?
STDERR_J="$(cat "${TMPDIR_ROOT}/stderr_j.txt")"
cd - >/dev/null

# AC1 — exit 0 (observer, not gate)
_assert_exit_zero "J1: symbol absent → exit 0 (offer, not gate)" "$EXIT_J"

# AC1 — NOTE on stderr naming serial-fallback
_assert_stderr_contains "J2: symbol absent → NOTE on stderr" "NOTE:" "$STDERR_J"
_assert_stderr_contains "J3: symbol absent → names the missing symbol" "missing_symbol" "$STDERR_J"
_assert_stderr_contains "J4: symbol absent → names serial-fallback as remediation" "serial" "$STDERR_J"

# Dispatch blocks still present in stdout (concurrent dispatch proceeds)
_assert_stdout_contains "J5: symbol absent → producer block still emitted" "EXECUTOR DISPATCH BLOCK: chunk-producer" "$STDOUT_J"
_assert_stdout_contains "J6: symbol absent → consumer block still emitted" "EXECUTOR DISPATCH BLOCK: chunk-consumer" "$STDOUT_J"

# The NOTE must be on STDERR, not STDOUT — check stdout is clean of the NOTE
_assert_stdout_not_contains "J7: NOTE goes to stderr, not stdout" "serial predecessor" "$STDOUT_J"

# ---------------------------------------------------------------------------
# Test J2 — Pinned-interface column, producer file does NOT exist (file-absent NOTE path)
#            → offer NOTE on stderr, exit 0, dispatch blocks present.
# Review: code-reviewer — exercises fan-out-dispatch.sh:298-300 (file-absent branch), which
# was previously untested. Negative-spec: exit 0 (observer, not gate); NOTE on stderr.
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md §C2 (AC1)
# ---------------------------------------------------------------------------
echo ""
echo "=== Test J2: pinned-interface pin, producer file absent → offer NOTE on stderr, exit 0, blocks present ==="

REPO_J2="${TMPDIR_ROOT}/repo_j2"
_make_git_repo "$REPO_J2"

# Producer file does NOT exist at all (not created on disk).
PRODUCER_FILE_J2="${TMPDIR_ROOT}/nonexistent_producer.py"

SPEC_J2="${TMPDIR_ROOT}/spec_j2.tsv"
printf "chunk-producer\tAuthor the producer\t${PRODUCER_FILE_J2}\n" > "$SPEC_J2"
printf "chunk-consumer\tAuthor the consumer\tconsumer.py\tsome_symbol@${PRODUCER_FILE_J2}\n" >> "$SPEC_J2"

STDOUT_J2=""
STDERR_J2=""
EXIT_J2=0
cd "$REPO_J2"
STDOUT_J2="$(bash "$HELPER" --spec "$SPEC_J2" 2>${TMPDIR_ROOT}/stderr_j2.txt)" || EXIT_J2=$?
STDERR_J2="$(cat "${TMPDIR_ROOT}/stderr_j2.txt")"
cd - >/dev/null

# AC1 — exit 0 (observer, not gate)
_assert_exit_zero "J2a: file absent → exit 0 (offer, not gate)" "$EXIT_J2"

# File-absent NOTE on stderr
_assert_stderr_contains "J2b: file absent → NOTE on stderr" "NOTE:" "$STDERR_J2"
_assert_stderr_contains "J2c: file absent → names the missing file" "does not exist" "$STDERR_J2"
_assert_stderr_contains "J2d: file absent → names serial-fallback as remediation" "serial" "$STDERR_J2"

# Dispatch blocks still present in stdout (concurrent dispatch proceeds)
_assert_stdout_contains "J2e: file absent → producer block still emitted" "EXECUTOR DISPATCH BLOCK: chunk-producer" "$STDOUT_J2"
_assert_stdout_contains "J2f: file absent → consumer block still emitted" "EXECUTOR DISPATCH BLOCK: chunk-consumer" "$STDOUT_J2"

# ---------------------------------------------------------------------------
# Test K — Legacy 3-field row → parses unchanged, exit 0.
#           Backward-compat guard: 3-field rows must continue to work exactly as before.
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md §C2 (AC2)
# ---------------------------------------------------------------------------
echo ""
echo "=== Test K: legacy 3-field row → backward-compat, exit 0 ==="

REPO_K="${TMPDIR_ROOT}/repo_k"
_make_git_repo "$REPO_K"

SPEC_K="${TMPDIR_ROOT}/spec_k.tsv"
printf 'legacy-chunk-1\tFix the legacy module\tlegacy.py,legacy_test.py\n' > "$SPEC_K"
printf 'legacy-chunk-2\tFix another legacy module\tother.py\n' >> "$SPEC_K"

STDOUT_K=""
STDERR_K=""
EXIT_K=0
cd "$REPO_K"
STDOUT_K="$(bash "$HELPER" --spec "$SPEC_K" 2>${TMPDIR_ROOT}/stderr_k.txt)" || EXIT_K=$?
STDERR_K="$(cat "${TMPDIR_ROOT}/stderr_k.txt")"
cd - >/dev/null

_assert_exit_zero "K1: 3-field rows → exit 0" "$EXIT_K"
_assert_stdout_contains "K2: 3-field rows → chunk-1 block emitted" "EXECUTOR DISPATCH BLOCK: legacy-chunk-1" "$STDOUT_K"
_assert_stdout_contains "K3: 3-field rows → chunk-2 block emitted" "EXECUTOR DISPATCH BLOCK: legacy-chunk-2" "$STDOUT_K"
_assert_stderr_not_contains "K4: 3-field rows → no interface-pin NOTE" "pinned interface" "$STDERR_K"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "========================================"

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
