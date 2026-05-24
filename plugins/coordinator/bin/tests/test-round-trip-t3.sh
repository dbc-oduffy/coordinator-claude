#!/usr/bin/env bash
# test-round-trip-t3.sh — AC-7 T3 round-trip integration test
#
# Spec: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § AC-7,
#       § Correctness Traps T3 (four-way coupled path declarations).
#
# Chains the four T3-coupled path declarations end-to-end:
#   1. CLI write target (bin/cross-repo-memo:_write_file)
#   2. Schema applies_to glob (schemas/cross-repo-memo.yaml)
#   3. Own-inbox guard regex (validate-frontmatter-schema.js — unit-tested via the JS suite;
#      structurally exercised here by writing a path that matches the same glob shape)
#   4. Surface query glob (bin/workday-start-cross-repo-memo-surface.sh)
#
# Each declaration is unit-tested independently in its own suite; THIS test catches
# the case where any one drifts from the others — the silent-death mode T3 exists to
# prevent (e.g. a future edit changes the surface script's INBOX_DIR but forgets the
# CLI write target, and memos write to one path but surface queries another).
#
# Pass the chain: T3 four declarations agree. Fail the chain: declarations have drifted.

set -euo pipefail

PASS=0
FAIL=0
FAILS=()

assert() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd"; then
        echo "  PASS: $name"
        PASS=$((PASS+1))
    else
        echo "  FAIL: $name"
        echo "    cmd: $cmd"
        FAIL=$((FAIL+1))
        FAILS+=("$name")
    fi
}

repo_root=$(git rev-parse --show-toplevel)
cli="$repo_root/plugins/coordinator/bin/cross-repo-memo"
surface="$repo_root/plugins/coordinator/bin/workday-start-cross-repo-memo-surface.sh"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "== AC-7 T3 round-trip integration test =="
echo "fixture: $tmp"
echo ""

# ---------------------------------------------------------------------------
# Stage 1 — CLI write target lands in cross-repo/inbox/
#
# CLAUDE_HOME isolation makes `--to claude-central-em` resolve to $tmp/.claude
# (mirrors the central-receiver CLI test cases B2/AC-11).
# ---------------------------------------------------------------------------

fixture_home="$tmp/.claude"
mkdir -p "$fixture_home"
git -C "$fixture_home" init -q
git -C "$fixture_home" config user.email "test@example.com"
git -C "$fixture_home" config user.name "Test"

set +e
CLAUDE_HOME="$fixture_home" python "$cli" \
    --to claude-central-em \
    --topic t3-round-trip \
    --title "T3 round-trip integration test" <<<"AC-7 chain integration body" \
    > "$tmp/cli.stdout" 2> "$tmp/cli.stderr"
cli_exit=$?
set -e

if [[ $cli_exit -ne 0 ]]; then
    echo "  CLI invocation failed (exit $cli_exit):"
    echo "  --- stdout ---"
    cat "$tmp/cli.stdout"
    echo "  --- stderr ---"
    cat "$tmp/cli.stderr"
    exit 1
fi

today=$(date -u +%Y-%m-%d)
expected="$fixture_home/cross-repo/inbox/${today}-t3-round-trip.md"

# Stage 1 assertions
assert "Stage 1: CLI write target lands at cross-repo/inbox/<date>-<topic>.md" "[[ -f '$expected' ]]"
assert "Stage 1: CLI did NOT write to flat cross-repo/<topic>.md (legacy shape)" \
    "[[ ! -f '$fixture_home/cross-repo/${today}-t3-round-trip.md' ]]"

# ---------------------------------------------------------------------------
# Stage 2 — Schema applies_to glob "cross-repo/inbox/[0-9]*.md" matches structurally
#
# The CLI's filename is YYYY-MM-DD-<topic>.md → starts with a digit. If the CLI
# ever shifted to a non-digit prefix (a rename, a refactor), the applies_to glob
# would silently stop matching and schema validation would skip — this catches it.
# ---------------------------------------------------------------------------

fname=$(basename "$expected")
assert "Stage 2: filename starts with digit (matches applies_to '[0-9]*.md')" \
    "[[ '$fname' =~ ^[0-9] ]]"
assert "Stage 2: file landed exactly under cross-repo/inbox/ (matches applies_to glob path)" \
    "[[ '$expected' == */cross-repo/inbox/[0-9]*.md ]]"

# ---------------------------------------------------------------------------
# Stage 3 — Surface script reads cross-repo/inbox/, surfaces status: open memos
#
# CROSS_REPO_INBOX_DIR env var override (Chunk D) points the surface script at
# the fixture inbox. The script must enumerate the memo we just wrote.
# ---------------------------------------------------------------------------

set +e
out=$(CROSS_REPO_INBOX_DIR="$fixture_home/cross-repo/inbox" bash "$surface" 2>&1)
surface_exit=$?
set -e

assert "Stage 3: surface script exits 0 on a populated inbox" \
    "[[ $surface_exit -eq 0 ]]"
assert "Stage 3: surface output mentions the memo's title (which is in the parsed frontmatter)" \
    "echo \"\$out\" | grep -q 'T3 round-trip'"

# ---------------------------------------------------------------------------
# Stage 4 — Status filter: actioned memos do NOT surface
#
# The receiver-side lifecycle (status: open → actioned via Edit + commit) means
# an actioned memo should drop out of the surface immediately. Flips the status
# in place and re-queries.
# ---------------------------------------------------------------------------

if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' 's/^status: open$/status: actioned/' "$expected"
else
    sed -i 's/^status: open$/status: actioned/' "$expected"
fi

# Confirm the edit landed (cheap pre-assertion)
if ! grep -q '^status: actioned$' "$expected"; then
    echo "  WARN: status flip didn't apply; the memo file may have unexpected shape"
    echo "  --- memo file ---"
    head -20 "$expected"
fi

set +e
out2=$(CROSS_REPO_INBOX_DIR="$fixture_home/cross-repo/inbox" bash "$surface" 2>&1)
surface_exit2=$?
set -e

assert "Stage 4: surface script still exits 0 after status flip" \
    "[[ $surface_exit2 -eq 0 ]]"
assert "Stage 4: actioned memo NOT surfaced (status filter is active)" \
    "! echo \"\$out2\" | grep -q 'T3 round-trip'"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
    echo "Failed cases:"
    for f in "${FAILS[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
exit 0
