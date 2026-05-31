#!/usr/bin/env bash
# test-depersonalize-path-rewrite.sh — regression tests for the path-rewrite
# pass in publish-time-transform.sh (Chunk 1 of
# docs/plans/2026-05-18-publish-time-path-rewriting.md).
#
# PURPOSE: Assert that publish-time-transform.sh --fix correctly rewrites
# dev-tree plugin paths to their publish-tree equivalents, protects its own
# script body from rewriting, and leaves bare coordinator-claude tokens alone.
#
# PRE-CHUNK-1 EXPECTED BEHAVIOR:
#   test_rewrites_dev_form WILL FAIL when run against the pre-Chunk-1 script
#   because the path-rewrite pass does not yet exist. That is intentional —
#   this test asserts the post-Chunk-1 behavior and acts as a regression net
#   after the extension lands.
#   test_self_protection_holds PASSES on the pre-Chunk-1 script because the
#   EXCLUDED_BASENAMES self-exclusion is already present.
#   test_bare_token_survives PASSES on the pre-Chunk-1 script because the bare
#   coordinator-claude token was never subject to any persona or path
#   substitution in the first place — the test verifies a property that must
#   continue to hold after Chunk-1 adds path-rewrite logic.
#
# SPEC BACKLINK: AC9 (bin/test/test-depersonalize-path-rewrite.sh exists and
#   exits 0 when all three test functions pass).
#
# USAGE: bash test-depersonalize-path-rewrite.sh
# EXIT: 0 if all three tests pass; 1 if any fail.

set -euo pipefail

# Locate publish-time-transform.sh: one level up from bin/test/ is bin/.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPERSONALIZE="${SCRIPT_DIR}/../publish-time-transform.sh"

if [[ ! -f "$DEPERSONALIZE" ]]; then
  echo "FATAL: publish-time-transform.sh not found at expected path: $DEPERSONALIZE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# test_rewrites_dev_form
#
# Creates a fixture file containing dev-tree-rooted path citations. Runs
# --fix. Asserts:
#   1. dev-form paths were rewritten to publish-form.
#   2. No residual plugins/coordinator-claude/ remains.
#   3. Second --fix run produces no diff (idempotency).
# ---------------------------------------------------------------------------
test_rewrites_dev_form() {
  # Review: code-reviewer — trap ... RETURN bypassed when set -e triggers exit (not return).
  # Subshell wrapper ensures trap ... EXIT fires for all exit paths, preventing tmpdir leaks.
  ( local tmpdir
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT

    # Fixture: a wiki-style .md file containing several dev-tree path citations.
    cat > "$tmpdir/fixture.md" <<'EOF'
# Example doc

See plugins/coordinator/agents/staff-eng.md for the agent prompt.
The game-dev plugin ships at plugins/game-dev/foo.md.
Also note plugins/data-science/bar.md for the DS plugin.
EOF

    bash "$DEPERSONALIZE" --fix "$tmpdir" >/dev/null 2>&1

    # Assert: coordinator path collapsed two segments correctly.
    if ! grep -q "plugins/coordinator/agents/staff-eng.md" "$tmpdir/fixture.md"; then
      echo "FAIL: test_rewrites_dev_form — plugins/coordinator/ not rewritten to plugins/coordinator/"
      exit 1
    fi

    # Assert: game-dev plugin path rewritten.
    if ! grep -q "plugins/game-dev/foo.md" "$tmpdir/fixture.md"; then
      echo "FAIL: test_rewrites_dev_form — plugins/game-dev/ not rewritten to plugins/game-dev/"
      exit 1
    fi

    # Assert: data-science plugin path rewritten.
    if ! grep -q "plugins/data-science/bar.md" "$tmpdir/fixture.md"; then
      echo "FAIL: test_rewrites_dev_form — plugins/data-science/ not rewritten to plugins/data-science/"
      exit 1
    fi

    # Assert: no residual dev-tree prefix remains.
    if grep -q "plugins/coordinator-claude/" "$tmpdir/fixture.md"; then
      echo "FAIL: test_rewrites_dev_form — residual plugins/coordinator-claude/ found after --fix"
      exit 1
    fi

    # Idempotency: capture state after first run, run again, assert no diff.
    local snapshot
    snapshot="$(cat "$tmpdir/fixture.md")"

    bash "$DEPERSONALIZE" --fix "$tmpdir" >/dev/null 2>&1

    local after_second
    after_second="$(cat "$tmpdir/fixture.md")"

    if [[ "$snapshot" != "$after_second" ]]; then
      echo "FAIL: test_rewrites_dev_form — second --fix run changed the file (not idempotent)"
      exit 1
    fi

    echo "PASS: test_rewrites_dev_form"
  )
}

# ---------------------------------------------------------------------------
# test_self_protection_holds
#
# Copies publish-time-transform.sh into a tmpdir and runs --fix on that
# dir. Asserts that the copied script body is byte-identical to the source —
# the EXCLUDED_BASENAMES self-exclusion must prevent the path-rewrite (and
# persona substitution) passes from touching the script's own content.
# ---------------------------------------------------------------------------
test_self_protection_holds() {
  # Review: code-reviewer — subshell wrapper with trap ... EXIT to handle set -e exit paths.
  (
    local tmpdir
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT

    local dest="$tmpdir/publish-time-transform.sh"
    cp "$DEPERSONALIZE" "$dest"

    bash "$DEPERSONALIZE" --fix "$tmpdir" >/dev/null 2>&1

    # Assert: copied script is byte-identical to the original source.
    if ! cmp -s "$DEPERSONALIZE" "$dest"; then
      echo "FAIL: test_self_protection_holds — script body was modified by --fix (EXCLUDED_BASENAMES self-protection failed)"
      diff "$DEPERSONALIZE" "$dest" >&2 || true
      exit 1
    fi

    echo "PASS: test_self_protection_holds"
  )
}

# ---------------------------------------------------------------------------
# test_bare_token_survives
#
# Creates a fixture file containing the standalone token `coordinator-claude`
# without a `plugins/` prefix (e.g. as a repo-name reference). Runs --fix.
# Asserts the bare token survives unchanged — the rewrite is anchored on
# `plugins/coordinator-claude/`, not the bare identifier.
# ---------------------------------------------------------------------------
test_bare_token_survives() {
  # Review: code-reviewer — subshell wrapper with trap ... EXIT to handle set -e exit paths.
  (
    local tmpdir
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT

    # Fixture: prose referencing the repo by name, not by path.
    cat > "$tmpdir/fixture.md" <<'EOF'
# Notes

See the coordinator-claude repo at github.com/dbc-oduffy/coordinator-claude for details.
The coordinator-claude project ships as a plugin.
EOF

    bash "$DEPERSONALIZE" --fix "$tmpdir" >/dev/null 2>&1

    # Assert: bare coordinator-claude token is still present.
    if ! grep -q "coordinator-claude" "$tmpdir/fixture.md"; then
      echo "FAIL: test_bare_token_survives — bare coordinator-claude token was removed"
      exit 1
    fi

    # Assert: the specific prose forms still intact (not mangled by partial rewrite).
    if ! grep -q "the coordinator-claude repo" "$tmpdir/fixture.md"; then
      echo "FAIL: test_bare_token_survives — bare coordinator-claude token was rewritten (expected to survive unchanged)"
      exit 1
    fi

    echo "PASS: test_bare_token_survives"
  )
}

# ---------------------------------------------------------------------------
# Main — run all three tests; exit 1 with summary if any fail.
# ---------------------------------------------------------------------------
main() {
  local failures=0

  test_rewrites_dev_form    || failures=$((failures + 1))
  test_self_protection_holds || failures=$((failures + 1))
  test_bare_token_survives  || failures=$((failures + 1))

  echo ""
  if (( failures == 0 )); then
    echo "All 3 tests passed."
    exit 0
  else
    echo "$failures of 3 test(s) failed."
    exit 1
  fi
}

main "$@"
