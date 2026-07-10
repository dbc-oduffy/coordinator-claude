#!/usr/bin/env bash
# coordinator-doe-root.test.sh — unit tests for coordinator-doe-root.sh
#
# Spec backlink: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.1
#
# Coverage:
#   T1  env-var short-circuit (REPO_DOE_CLAUDE set)
#         → prints value, returns 0, machine-local NOT called
#   T2  registry resolution (machine-local stub exits 0 with known path)
#         → prints path, returns 0
#   T3  fail-loud path (machine-local stub exits 1)
#         → returns 1, stderr contains "repos.doe_claude"
#
# Self-contained: creates temp dirs and PATH-prepended machine-local stubs,
# restores env between cases. Exits 0 if all pass, 1 if any fail.

set -euo pipefail
# Distinguish a harness abort (broken fixture, missing binary) from a counted
# test failure — both would otherwise exit 1.
trap 'echo "HARNESS ABORT (unexpected error at line $LINENO) — not a counted test failure" >&2; exit 2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_FILE="$SCRIPT_DIR/coordinator-doe-root.sh"

PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
_fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

echo "=== coordinator-doe-root.test.sh ==="

if [[ ! -f "$LIB_FILE" ]]; then
    echo "FATAL: lib not found at $LIB_FILE" >&2
    exit 1
fi

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Ensure REPO_DOE_CLAUDE is clean going into T1
unset REPO_DOE_CLAUDE 2>/dev/null || true

# ---------------------------------------------------------------------------
# T1: env-var short-circuit — REPO_DOE_CLAUDE already set
# ---------------------------------------------------------------------------
echo "--- T1: REPO_DOE_CLAUDE set → short-circuit, no machine-local call"

T1_STUBDIR="$TMPROOT/t1-stub"
T1_SENTINEL="$TMPROOT/t1-machine-local-called"
mkdir -p "$T1_STUBDIR"

# Stub records its invocation so we can assert it was NOT called.
cat > "$T1_STUBDIR/machine-local" <<EOF
#!/usr/bin/env bash
touch "$T1_SENTINEL"
echo "/should-not-be-returned"
exit 0
EOF
chmod +x "$T1_STUBDIR/machine-local"

T1_OUT=$(
    REPO_DOE_CLAUDE="/tmp/fake-doe-root" \
    PATH="$T1_STUBDIR:$PATH" \
    bash -c "source '$LIB_FILE'; coordinator_doe_root"
)
T1_RC=$?

if [[ "$T1_OUT" == "/tmp/fake-doe-root" && "$T1_RC" -eq 0 ]]; then
    _pass "T1 output and return code"
else
    _fail "T1 output and return code" "got rc=$T1_RC out='$T1_OUT'"
fi

if [[ ! -f "$T1_SENTINEL" ]]; then
    _pass "T1 machine-local not called"
else
    _fail "T1 machine-local not called" "stub was invoked despite REPO_DOE_CLAUDE being set"
fi

unset REPO_DOE_CLAUDE 2>/dev/null || true

# ---------------------------------------------------------------------------
# T2: registry resolution — machine-local stub exits 0 with a known path
# ---------------------------------------------------------------------------
echo "--- T2: machine-local stub exits 0 → prints resolved path, returns 0"

T2_STUBDIR="$TMPROOT/t2-stub"
T2_EXPECTED="/x/DoE-claude"
mkdir -p "$T2_STUBDIR"

cat > "$T2_STUBDIR/machine-local" <<EOF
#!/usr/bin/env bash
# Called as: machine-local get repos.doe_claude
echo "$T2_EXPECTED"
exit 0
EOF
chmod +x "$T2_STUBDIR/machine-local"

T2_OUT=$(
    PATH="$T2_STUBDIR:$PATH" \
    bash -c "unset REPO_DOE_CLAUDE 2>/dev/null; source '$LIB_FILE'; coordinator_doe_root"
)
T2_RC=$?

if [[ "$T2_OUT" == "$T2_EXPECTED" && "$T2_RC" -eq 0 ]]; then
    _pass "T2 registry resolution output and return code"
else
    _fail "T2 registry resolution output and return code" "got rc=$T2_RC out='$T2_OUT'"
fi

# ---------------------------------------------------------------------------
# T3: fail-loud path — machine-local exits 1 (key missing)
# ---------------------------------------------------------------------------
echo "--- T3: machine-local exits 1 → returns 1, stderr contains repos.doe_claude"

T3_STUBDIR="$TMPROOT/t3-stub"
T3_STDERR="$TMPROOT/t3-stderr.txt"
mkdir -p "$T3_STUBDIR"

cat > "$T3_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T3_STUBDIR/machine-local"

# CLAUDE_HOME is pointed at a fresh, empty temp dir (no .claude/.doe-root)
# so the new Rung-2.5 pointer-file fallback also returns empty here — this
# test asserts the TRUE fail-loud floor (nothing resolves), so it must not
# accidentally pick up the real machine's ~/.claude/.doe-root pointer.
T3_FAKE_HOME="$TMPROOT/t3-empty-home"
mkdir -p "$T3_FAKE_HOME"

# Use || to capture the expected rc=1 without triggering the ERR trap.
# In bash 5.x, set +e does NOT suppress the ERR trap; || is the correct
# pattern (the ERR trap is not invoked for the left side of || per bash docs).
# PATH= must come BEFORE the command name so bash receives it as an env var.
T3_RC=0
CLAUDE_HOME="$T3_FAKE_HOME" PATH="$T3_STUBDIR:$PATH" bash -c "
    unset REPO_DOE_CLAUDE 2>/dev/null
    source '$LIB_FILE'
    coordinator_doe_root
" >"$TMPROOT/t3-stdout.txt" 2>"$T3_STDERR" || T3_RC=$?

if [[ "$T3_RC" -eq 1 ]]; then
    _pass "T3 fail-loud returns 1"
else
    _fail "T3 fail-loud returns 1" "got rc=$T3_RC"
fi

T3_STDERR_CONTENT="$(cat "$T3_STDERR")"
if printf '%s' "$T3_STDERR_CONTENT" | grep -q "repos.doe_claude"; then
    _pass "T3 stderr contains repos.doe_claude"
else
    _fail "T3 stderr contains repos.doe_claude" "got stderr: '$T3_STDERR_CONTENT'"
fi

# ---------------------------------------------------------------------------
# T4: export idempotency — second call in same process uses REPO_DOE_CLAUDE env
#     var (Rung 1 guard) and does NOT re-invoke machine-local.
# Review: code-reviewer F5 — the export side-effect (REPO_DOE_CLAUDE) was
# untested; this asserts the second same-process call short-circuits via the
# exported var, so machine-local is invoked exactly once.
# ---------------------------------------------------------------------------
echo "--- T4: second call in same process skips machine-local (export idempotency)"

T4_STUBDIR="$TMPROOT/t4-stub"
T4_SENTINEL="$TMPROOT/t4-call-count"
mkdir -p "$T4_STUBDIR"

# Stub appends one line per invocation so we can count calls.
cat > "$T4_STUBDIR/machine-local" <<EOF
#!/usr/bin/env bash
echo "called" >> "$T4_SENTINEL"
echo "/x/DoE-claude"
exit 0
EOF
chmod +x "$T4_STUBDIR/machine-local"

# Run two coordinator_doe_root calls in one bash -c subshell (same process,
# same exported environment).  Use || to prevent the ERR trap from firing on
# an unexpected non-zero exit.
T4_RC=0
PATH="$T4_STUBDIR:$PATH" bash -c "
    unset REPO_DOE_CLAUDE 2>/dev/null
    source '$LIB_FILE'
    coordinator_doe_root
    coordinator_doe_root
" >/dev/null 2>&1 || T4_RC=$?

if [[ "$T4_RC" -eq 0 ]]; then
    _pass "T4 double-call returns 0"
else
    _fail "T4 double-call returns 0" "got rc=$T4_RC"
fi

# machine-local must have been invoked exactly once; the second call must have
# hit the Rung-1 exported-var guard and skipped re-resolution.
if [[ -f "$T4_SENTINEL" ]]; then
    T4_CALL_COUNT=$(wc -l < "$T4_SENTINEL" | tr -d '[:space:]')
    if [[ "$T4_CALL_COUNT" -eq 1 ]]; then
        _pass "T4 machine-local called exactly once (second call short-circuited)"
    else
        _fail "T4 machine-local called exactly once" "called ${T4_CALL_COUNT} times — export guard not firing"
    fi
else
    _fail "T4 machine-local called exactly once" "sentinel not created — machine-local was never called at all?"
fi

# ---------------------------------------------------------------------------
# T5: Rung 2.5 — cold-readable pointer file (~/.claude/.doe-root) fallback,
#     fires only when Rung 1 (env) and Rung 2 (machine-local) both come up
#     empty. Supersedes audit C1.
# ---------------------------------------------------------------------------
echo "--- T5: REPO_DOE_CLAUDE unset, machine-local unresolvable → pointer-file rung resolves"

T5_STUBDIR="$TMPROOT/t5-stub"
T5_FAKE_HOME="$TMPROOT/t5-fake-home"
T5_FAKE_DOE_ROOT="$TMPROOT/t5-fake-doe-root"
mkdir -p "$T5_STUBDIR" "$T5_FAKE_HOME/.claude" "$T5_FAKE_DOE_ROOT/.git"

# machine-local stub mirrors T3: exits 1 (key unresolvable), forcing fallthrough
# past Rung 2 into the new Rung 2.5.
cat > "$T5_STUBDIR/machine-local" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$T5_STUBDIR/machine-local"

# Write the cold-readable pointer file: value is the fake DoE root, which has
# a .git dir so the -d "${_ptr}/.git" gate in coordinator_doe_root passes.
printf '%s' "$T5_FAKE_DOE_ROOT" > "$T5_FAKE_HOME/.claude/.doe-root"

T5_OUT=$(
    CLAUDE_HOME="$T5_FAKE_HOME" \
    PATH="$T5_STUBDIR:$PATH" \
    bash -c "unset REPO_DOE_CLAUDE 2>/dev/null; source '$LIB_FILE'; coordinator_doe_root"
)
T5_RC=$?

if [[ "$T5_OUT" == "$T5_FAKE_DOE_ROOT" && "$T5_RC" -eq 0 ]]; then
    _pass "T5 pointer-file rung resolves DoE root"
else
    _fail "T5 pointer-file rung resolves DoE root" "got rc=$T5_RC out='$T5_OUT' expected='$T5_FAKE_DOE_ROOT'"
fi

# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
