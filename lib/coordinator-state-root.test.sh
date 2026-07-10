#!/usr/bin/env bash
# coordinator-state-root.test.sh — unit tests for coordinator-state-root.sh
#
# Spec backlink: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.3
#
# Coverage:
#   T1  Regression guard: --central with no subject, EXAMPLE_ORCHESTRATION_HUB_ROOT set
#         → prints example-orchestration-hub/state, rc 0 (backward-compat proof for existing callers)
#   T2  --central --subject doctrine, REPO_DOE_CLAUDE set
#         → prints doe/state, rc 0
#   T3  --central --subject engine, EXAMPLE_ORCHESTRATION_HUB_ROOT set
#         → prints example-orchestration-hub/state, rc 0
#   T4  --central --artifact <doctrine-path>, REPO_DOE_CLAUDE set
#         → classifier maps to doctrine → doe/state, rc 0
#   T5  --central --artifact <cross-cutting-path (dr-207)>
#         → rc 2, stdout does not contain /state path, stderr non-empty
#   T6  --central --subject doctrine, REPO_DOE_CLAUDE unset, machine-local exits 1
#         → rc 1 (fail-loud propagation; NOT a fallback to example-orchestration-hub)
#   T7  Default branch (no --central) inside a temp git repo
#         → prints <tmprepo>/state, rc 0
#
# Self-contained: creates temp dirs and PATH-prepended machine-local stubs,
# isolates env between cases via bash subshells. Exits 0 if all pass, 1 if any fail.

set -euo pipefail
# Distinguish a harness abort (broken fixture, missing binary) from a counted
# test failure — both would otherwise exit 1.
trap 'echo "HARNESS ABORT (unexpected error at line $LINENO) — not a counted test failure" >&2; exit 2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_FILE="$SCRIPT_DIR/coordinator-state-root.sh"

PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
_fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

echo "=== coordinator-state-root.test.sh ==="

if [[ ! -f "$LIB_FILE" ]]; then
    echo "FATAL: lib not found at $LIB_FILE" >&2
    exit 1
fi

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# ---------------------------------------------------------------------------
# T1: REGRESSION GUARD — --central with no subject resolves to example-orchestration-hub
#     Proves backward-compat: existing --central callers are unchanged.
# ---------------------------------------------------------------------------
echo "--- T1: --central (no subject/artifact), EXAMPLE_ORCHESTRATION_HUB_ROOT set → example-orchestration-hub/state, rc 0"

T1_STUBDIR="$TMPROOT/t1-stub"
mkdir -p "$T1_STUBDIR"
# Minimal machine-local stub (not expected to be called for this path, but present
# in case any sourced dependency checks for it).
cat > "$T1_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
echo "UNEXPECTED machine-local call in T1" >&2
exit 1
EOF
chmod +x "$T1_STUBDIR/machine-local"

T1_RC=0
T1_OUT=$(
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
    PATH="$T1_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central"
) || T1_RC=$?

if [[ "$T1_OUT" == "/tmp/fake-example-orchestration-hub/state" && "$T1_RC" -eq 0 ]]; then
    _pass "T1 backward-compat: --central resolves to example-orchestration-hub/state"
else
    _fail "T1 backward-compat: --central resolves to example-orchestration-hub/state" "got rc=$T1_RC out='$T1_OUT'"
fi

# ---------------------------------------------------------------------------
# T2: --central --subject doctrine → doe/state
# ---------------------------------------------------------------------------
echo "--- T2: --central --subject doctrine, REPO_DOE_CLAUDE set → doe/state, rc 0"

T2_STUBDIR="$TMPROOT/t2-stub"
mkdir -p "$T2_STUBDIR"
cat > "$T2_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T2_STUBDIR/machine-local"

T2_RC=0
T2_OUT=$(
    REPO_DOE_CLAUDE="/tmp/fake-doe" \
    PATH="$T2_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --subject doctrine"
) || T2_RC=$?

if [[ "$T2_OUT" == "/tmp/fake-doe/state" && "$T2_RC" -eq 0 ]]; then
    _pass "T2 --subject doctrine → doe/state"
else
    _fail "T2 --subject doctrine → doe/state" "got rc=$T2_RC out='$T2_OUT'"
fi

# ---------------------------------------------------------------------------
# T3: --central --subject engine → example-orchestration-hub/state
# ---------------------------------------------------------------------------
echo "--- T3: --central --subject engine, EXAMPLE_ORCHESTRATION_HUB_ROOT set → example-orchestration-hub/state, rc 0"

T3_STUBDIR="$TMPROOT/t3-stub"
mkdir -p "$T3_STUBDIR"
cat > "$T3_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T3_STUBDIR/machine-local"

T3_RC=0
T3_OUT=$(
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
    PATH="$T3_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --subject engine"
) || T3_RC=$?

if [[ "$T3_OUT" == "/tmp/fake-example-orchestration-hub/state" && "$T3_RC" -eq 0 ]]; then
    _pass "T3 --subject engine → example-orchestration-hub/state"
else
    _fail "T3 --subject engine → example-orchestration-hub/state" "got rc=$T3_RC out='$T3_OUT'"
fi

# ---------------------------------------------------------------------------
# T4: --central --artifact <doctrine-path> → classifier maps to doctrine → doe/state
#     Uses a coordinator skills path: unambiguously doctrine, not engine or cross-cutting.
# ---------------------------------------------------------------------------
echo "--- T4: --central --artifact <doctrine-path>, REPO_DOE_CLAUDE set → doe/state, rc 0"

T4_STUBDIR="$TMPROOT/t4-stub"
mkdir -p "$T4_STUBDIR"
cat > "$T4_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T4_STUBDIR/machine-local"

T4_ARTIFACT="plugins/coordinator/skills/learn-lessons/SKILL.md"
T4_RC=0
T4_OUT=$(
    REPO_DOE_CLAUDE="/tmp/fake-doe" \
    PATH="$T4_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --artifact '$T4_ARTIFACT'"
) || T4_RC=$?

if [[ "$T4_OUT" == "/tmp/fake-doe/state" && "$T4_RC" -eq 0 ]]; then
    _pass "T4 --artifact doctrine-path → doe/state"
else
    _fail "T4 --artifact doctrine-path → doe/state" "got rc=$T4_RC out='$T4_OUT'"
fi

# ---------------------------------------------------------------------------
# T5: --central --artifact <cross-cutting path (dr-207)>
#     → rc 2, stdout does NOT contain a /state path, stderr non-empty
# ---------------------------------------------------------------------------
echo "--- T5: --central --artifact <dr-207 path> → rc 2, no state path in stdout, stderr non-empty"

T5_STUBDIR="$TMPROOT/t5-stub"
T5_STDOUT="$TMPROOT/t5-stdout.txt"
T5_STDERR="$TMPROOT/t5-stderr.txt"
mkdir -p "$T5_STUBDIR"
cat > "$T5_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T5_STUBDIR/machine-local"

T5_ARTIFACT="docs/plans/2026-07-04-dr-207-tri-plane-boundary.md"
T5_RC=0
PATH="$T5_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --central --artifact '$T5_ARTIFACT'
" >"$T5_STDOUT" 2>"$T5_STDERR" || T5_RC=$?

if [[ "$T5_RC" -eq 2 ]]; then
    _pass "T5 cross-cutting artifact → rc 2"
else
    _fail "T5 cross-cutting artifact → rc 2" "got rc=$T5_RC"
fi

T5_STDOUT_CONTENT="$(cat "$T5_STDOUT")"
if ! printf '%s' "$T5_STDOUT_CONTENT" | grep -q '/state'; then
    _pass "T5 stdout does not contain /state path"
else
    _fail "T5 stdout does not contain /state path" "stdout contained: '$T5_STDOUT_CONTENT'"
fi

T5_STDERR_CONTENT="$(cat "$T5_STDERR")"
if [[ -n "$T5_STDERR_CONTENT" ]]; then
    _pass "T5 stderr non-empty"
else
    _fail "T5 stderr non-empty" "stderr was empty"
fi

# ---------------------------------------------------------------------------
# T6: --central --subject doctrine, REPO_DOE_CLAUDE unset, machine-local exits 1
#     → rc 1 (fail-loud propagation — must NOT fall back to example-orchestration-hub)
# ---------------------------------------------------------------------------
echo "--- T6: --central --subject doctrine, REPO_DOE_CLAUDE unset, machine-local fails → rc 1"

T6_STUBDIR="$TMPROOT/t6-stub"
mkdir -p "$T6_STUBDIR"
cat > "$T6_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T6_STUBDIR/machine-local"

T6_STDOUT="$TMPROOT/t6-stdout.txt"
T6_RC=0
PATH="$T6_STUBDIR:$PATH" bash -c "
    unset REPO_DOE_CLAUDE 2>/dev/null
    source '$LIB_FILE'
    coordinator_state_root --central --subject doctrine
" >"$T6_STDOUT" 2>/dev/null || T6_RC=$?
# Review: code-reviewer F6 — capture stdout to file; assert both rc=1 AND stdout empty
# (a bug that prints a path then returns 1 would pass the rc check but violate the contract)

if [[ "$T6_RC" -eq 1 ]]; then
    _pass "T6 fail-loud propagation → rc 1 (no fallback to example-orchestration-hub)"
else
    _fail "T6 fail-loud propagation → rc 1 (no fallback to example-orchestration-hub)" "got rc=$T6_RC"
fi

T6_STDOUT_CONTENT="$(cat "$T6_STDOUT")"
if [[ -z "$T6_STDOUT_CONTENT" ]]; then
    _pass "T6 stdout empty (no spurious state path emitted before failure)"
else
    _fail "T6 stdout empty (no spurious state path emitted before failure)" "stdout contained: '$T6_STDOUT_CONTENT'"
fi

# ---------------------------------------------------------------------------
# T7: Default branch (no --central) inside a temp git repo
#     → prints <tmprepo>/state, rc 0
# ---------------------------------------------------------------------------
echo "--- T7: default branch (no --central), temp git repo → <tmprepo>/state, rc 0"

T7_GITROOT="$TMPROOT/t7-gitrepo"
mkdir -p "$T7_GITROOT"
git -C "$T7_GITROOT" init --quiet
# Canonicalize so T7_EXPECTED matches git rev-parse --show-toplevel, which
# resolves symlinks (e.g. /var → /private/var on macOS). BSD-portable: cd + pwd -P.
T7_GITROOT="$(cd "$T7_GITROOT" && pwd -P)"

T7_STUBDIR="$TMPROOT/t7-stub"
mkdir -p "$T7_STUBDIR"
# Provide a machine-local stub (sourced libs define functions but may call machine-local
# if example-orchestration-hub root is needed; for the sibling branch we never reach example-orchestration-hub root resolution).
cat > "$T7_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T7_STUBDIR/machine-local"

T7_RC=0
T7_OUT=$(
    PATH="$T7_STUBDIR:$PATH" \
    bash -c "
        cd '$T7_GITROOT'
        source '$LIB_FILE'
        coordinator_state_root
    "
) || T7_RC=$?

T7_EXPECTED="$T7_GITROOT/state"
if [[ "$T7_OUT" == "$T7_EXPECTED" && "$T7_RC" -eq 0 ]]; then
    _pass "T7 default branch sibling-repo → <tmprepo>/state"
else
    _fail "T7 default branch sibling-repo → <tmprepo>/state" "got rc=$T7_RC out='$T7_OUT' expected='$T7_EXPECTED'"
fi

# ---------------------------------------------------------------------------
# T8: Rule 3 — engine artifact → example-orchestration-hub/state, rc 0
#     Review: code-reviewer F3 — Rule 3 engine branch was untested (T4=doctrine, T5=cross-cutting)
# ---------------------------------------------------------------------------
echo "--- T8: --central --artifact <engine-path>, EXAMPLE_ORCHESTRATION_HUB_ROOT set → example-orchestration-hub/state, rc 0"

T8_STUBDIR="$TMPROOT/t8-stub"
mkdir -p "$T8_STUBDIR"
cat > "$T8_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T8_STUBDIR/machine-local"

T8_ARTIFACT="coordinator_core/state-writer.py"
T8_RC=0
T8_OUT=$(
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
    PATH="$T8_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --artifact '$T8_ARTIFACT'"
) || T8_RC=$?

if [[ "$T8_OUT" == "/tmp/fake-example-orchestration-hub/state" && "$T8_RC" -eq 0 ]]; then
    _pass "T8 --artifact engine-path → example-orchestration-hub/state"
else
    _fail "T8 --artifact engine-path → example-orchestration-hub/state" "got rc=$T8_RC out='$T8_OUT'"
fi

# ---------------------------------------------------------------------------
# T9: Rule 5 fail-loud — no-git-root → rc 1
#     Review: code-reviewer F4 — Rule 5 failure path was untested
# ---------------------------------------------------------------------------
echo "--- T9: default branch (no --central), non-repo tmpdir → rc 1"

T9_STUBDIR="$TMPROOT/t9-stub"
T9_NONGIT="$TMPROOT/t9-nongit"
mkdir -p "$T9_STUBDIR" "$T9_NONGIT"
cat > "$T9_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T9_STUBDIR/machine-local"

T9_RC=0
PATH="$T9_STUBDIR:$PATH" bash -c "
    cd '$T9_NONGIT'
    unset GIT_DIR GIT_WORK_TREE 2>/dev/null
    source '$LIB_FILE'
    coordinator_state_root
" >/dev/null 2>/dev/null || T9_RC=$?

if [[ "$T9_RC" -eq 1 ]]; then
    _pass "T9 no-git-root fail-loud → rc 1"
else
    _fail "T9 no-git-root fail-loud → rc 1" "got rc=$T9_RC"
fi

# ---------------------------------------------------------------------------
# T10: Mutual exclusion — --subject + --artifact → rc 1
#      Review: code-reviewer F5 — mutual exclusion guard was untested
# ---------------------------------------------------------------------------
echo "--- T10: --central --subject doctrine --artifact some/path → rc 1 (mutual exclusion)"

T10_STUBDIR="$TMPROOT/t10-stub"
mkdir -p "$T10_STUBDIR"
cat > "$T10_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T10_STUBDIR/machine-local"

T10_RC=0
PATH="$T10_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --central --subject doctrine --artifact some/path
" >/dev/null 2>/dev/null || T10_RC=$?

if [[ "$T10_RC" -eq 1 ]]; then
    _pass "T10 --subject + --artifact mutual exclusion → rc 1"
else
    _fail "T10 --subject + --artifact mutual exclusion → rc 1" "got rc=$T10_RC"
fi

# ---------------------------------------------------------------------------
# T11: Error-path cases (unknown flag, invalid --subject, missing args)
#      Review: code-reviewer F8 — error paths implemented but untested
# ---------------------------------------------------------------------------
echo "--- T11a: unknown flag --foobar → rc 1"

T11_STUBDIR="$TMPROOT/t11-stub"
mkdir -p "$T11_STUBDIR"
cat > "$T11_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T11_STUBDIR/machine-local"

T11A_RC=0
PATH="$T11_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --foobar
" >/dev/null 2>/dev/null || T11A_RC=$?

if [[ "$T11A_RC" -eq 1 ]]; then
    _pass "T11a unknown flag → rc 1"
else
    _fail "T11a unknown flag → rc 1" "got rc=$T11A_RC"
fi

echo "--- T11b: invalid --subject value 'foobar' → rc 1"

T11B_RC=0
PATH="$T11_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --central --subject foobar
" >/dev/null 2>/dev/null || T11B_RC=$?

if [[ "$T11B_RC" -eq 1 ]]; then
    _pass "T11b invalid --subject value → rc 1"
else
    _fail "T11b invalid --subject value → rc 1" "got rc=$T11B_RC"
fi

echo "--- T11c: --subject with no argument → rc 1"

T11C_RC=0
PATH="$T11_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --central --subject
" >/dev/null 2>/dev/null || T11C_RC=$?

if [[ "$T11C_RC" -eq 1 ]]; then
    _pass "T11c --subject with no argument → rc 1"
else
    _fail "T11c --subject with no argument → rc 1" "got rc=$T11C_RC"
fi

# ---------------------------------------------------------------------------
# T12: --print-map, both roots resolvable
#      → valid JSON with v1 schema string; doctrine path == --central --subject doctrine;
#        engine path == --central --subject engine; rc 0.
# ---------------------------------------------------------------------------
echo "--- T12: --print-map, both roots resolvable → valid JSON with v1 schema, rc 0"

T12_STUBDIR="$TMPROOT/t12-stub"
mkdir -p "$T12_STUBDIR"
cat > "$T12_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T12_STUBDIR/machine-local"

# Resolve expected paths using the existing --central --subject calls, so the
# assertion is a pure identity check rather than re-implementing the resolver logic.
T12_DOC_EXPECTED=$(
    REPO_DOE_CLAUDE="/tmp/fake-doe" \
    PATH="$T12_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --subject doctrine"
)
T12_ENG_EXPECTED=$(
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
    PATH="$T12_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --central --subject engine"
)

T12_RC=0
T12_OUT=$(
    REPO_DOE_CLAUDE="/tmp/fake-doe" \
    EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
    PATH="$T12_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_state_root --print-map"
) || T12_RC=$?

if [[ "$T12_RC" -eq 0 ]]; then
    _pass "T12 --print-map rc 0"
else
    _fail "T12 --print-map rc 0" "got rc=$T12_RC out='$T12_OUT'"
fi

if printf '%s' "$T12_OUT" | grep -q '"schema":"coordinator-state-root-map/v1"'; then
    _pass "T12 --print-map output contains v1 schema string"
else
    _fail "T12 --print-map output contains v1 schema string" "got: '$T12_OUT'"
fi

if printf '%s' "$T12_OUT" | grep -qF "\"doctrine\":\"${T12_DOC_EXPECTED}\""; then
    _pass "T12 doctrine path == --central --subject doctrine output"
else
    _fail "T12 doctrine path == --central --subject doctrine output" \
        "expected '$T12_DOC_EXPECTED' in: '$T12_OUT'"
fi

if printf '%s' "$T12_OUT" | grep -qF "\"engine\":\"${T12_ENG_EXPECTED}\""; then
    _pass "T12 engine path == --central --subject engine output"
else
    _fail "T12 engine path == --central --subject engine output" \
        "expected '$T12_ENG_EXPECTED' in: '$T12_OUT'"
fi

# ---------------------------------------------------------------------------
# T13: --print-map combined with --subject → rc 1, stderr names incompatibility
# ---------------------------------------------------------------------------
echo "--- T13: --print-map --subject engine (combined) → rc 1, stderr names incompatibility"

T13_STUBDIR="$TMPROOT/t13-stub"
T13_STDERR="$TMPROOT/t13-stderr.txt"
mkdir -p "$T13_STUBDIR"
cat > "$T13_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T13_STUBDIR/machine-local"

T13_RC=0
EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
PATH="$T13_STUBDIR:$PATH" bash -c "
    source '$LIB_FILE'
    coordinator_state_root --print-map --subject engine
" >/dev/null 2>"$T13_STDERR" || T13_RC=$?

if [[ "$T13_RC" -eq 1 ]]; then
    _pass "T13 --print-map --subject → rc 1"
else
    _fail "T13 --print-map --subject → rc 1" "got rc=$T13_RC"
fi

T13_STDERR_CONTENT="$(cat "$T13_STDERR")"
if printf '%s' "$T13_STDERR_CONTENT" | grep -qi 'print-map'; then
    _pass "T13 stderr mentions --print-map"
else
    _fail "T13 stderr mentions --print-map" "stderr was: '$T13_STDERR_CONTENT'"
fi

# ---------------------------------------------------------------------------
# T14: --print-map with doctrine unresolvable (REPO_DOE_CLAUDE unset, machine-local exits 1)
#      → JSON "doctrine":null, still rc 0, stderr carries WARN.
#      Uses same idiom as T6 to force doctrine unresolvable.
# ---------------------------------------------------------------------------
echo "--- T14: --print-map, doctrine unresolvable → JSON doctrine:null, rc 0, stderr WARN"

T14_STUBDIR="$TMPROOT/t14-stub"
T14_STDOUT="$TMPROOT/t14-stdout.txt"
T14_STDERR="$TMPROOT/t14-stderr.txt"
mkdir -p "$T14_STUBDIR"
cat > "$T14_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T14_STUBDIR/machine-local"

T14_RC=0
EXAMPLE_ORCHESTRATION_HUB_ROOT="/tmp/fake-example-orchestration-hub" \
PATH="$T14_STUBDIR:$PATH" bash -c "
    unset REPO_DOE_CLAUDE 2>/dev/null
    source '$LIB_FILE'
    coordinator_state_root --print-map
" >"$T14_STDOUT" 2>"$T14_STDERR" || T14_RC=$?

if [[ "$T14_RC" -eq 0 ]]; then
    _pass "T14 --print-map unresolvable doctrine → rc 0"
else
    _fail "T14 --print-map unresolvable doctrine → rc 0" "got rc=$T14_RC"
fi

T14_OUT="$(cat "$T14_STDOUT")"
if printf '%s' "$T14_OUT" | grep -q '"doctrine":null'; then
    _pass "T14 doctrine field is null in JSON"
else
    _fail "T14 doctrine field is null in JSON" "got: '$T14_OUT'"
fi

T14_STDERR_CONTENT="$(cat "$T14_STDERR")"
if [[ -n "$T14_STDERR_CONTENT" ]]; then
    _pass "T14 stderr carries WARN"
else
    _fail "T14 stderr carries WARN" "stderr was empty"
fi

# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
