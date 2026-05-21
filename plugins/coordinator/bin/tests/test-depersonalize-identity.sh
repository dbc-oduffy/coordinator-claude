#!/usr/bin/env bash
# test-depersonalize-identity.sh — Fixture tests for identity-vocabulary
# substitutions in depersonalize-for-publish.sh.
#
# Spec backlink: docs/plans/2026-05-08-coordinator-claude-publish-sanitization.md § Task 1
#
# Tests:
#   1. --check against a fixture containing identity strings returns exit 1.
#   2. --fix rewrites the fixture in-place.
#   3. --check after --fix returns exit 0.
#   4. Post-fix fixture contains canonical forms (dbc-oduffy, the Coordinator Authors).
#   5. Post-fix fixture does NOT contain original identity strings.
#   6. Existing persona substitutions still work (Patrik → the Staff Engineer).
#   7. Canonical-form strings (dbc-oduffy/...) are NOT flagged by --check.
#
# All fixtures live in a mktemp directory cleaned up on EXIT.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/../depersonalize-for-publish.sh"

# ---------------------------------------------------------------------------
# Test framework
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

assert_exit() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then return 0
  else
    echo "    Expected exit $expected, got $actual" >&2
    return 1
  fi
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then return 0
  else
    echo "    Expected to contain: ${needle}" >&2
    echo "    In: ${haystack}" >&2
    return 1
  fi
}

assert_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  if ! echo "$haystack" | grep -qF "$needle"; then return 0
  else
    echo "    Expected NOT to contain: ${needle}" >&2
    echo "    In: ${haystack}" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Fixture setup — tempdir cleaned on EXIT
# ---------------------------------------------------------------------------

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FIXTURE_JSON="${TMPDIR_ROOT}/plugin.json"
FIXTURE_PERSONA_MD="${TMPDIR_ROOT}/reviewer.md"
FIXTURE_CANONICAL_JSON="${TMPDIR_ROOT}/canonical-already.json"

# Fixture 1: synthetic plugin.json with identity strings that must be replaced.
cat > "$FIXTURE_JSON" <<'FIXTURE'
{
  "name": "coordinator",
  "version": "1.0.0",
  "author": {
    "name": "Dónal O'Duffy & Claude"
  },
  "author_ascii": "Donal O'Duffy & Claude",
  "collab": "Donal + Claude",
  "pm_name": "Dónal",
  "repository": "https://github.com/oduffy-delphi/coordinator-claude",
  "related": "https://github.com/oduffy-delphi/deep-research-claude"
}
FIXTURE

# Fixture 2: markdown file with a persona name — verifies persona behavior unchanged.
cat > "$FIXTURE_PERSONA_MD" <<'FIXTURE'
# Review notes

Patrik flagged a potential issue here.
FIXTURE

# Fixture 3: JSON that already uses the canonical org — must NOT be flagged.
cat > "$FIXTURE_CANONICAL_JSON" <<'FIXTURE'
{
  "repository": "https://github.com/dbc-oduffy/coordinator-claude"
}
FIXTURE

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

echo "=== test-depersonalize-identity ==="

# Test 1: --check on fixture with identity strings returns exit 1
echo "--- 1. --check flags identity strings"
check_out=$("$SCRIPT" --check "$FIXTURE_JSON" 2>&1; echo "EXIT:$?") || true
check_exit="${check_out##*EXIT:}"
check_out="${check_out%EXIT:*}"
if assert_exit "exit code" 1 "$check_exit"; then
  pass "1. --check exits 1 on identity strings"
else
  fail "1. --check exits 1 on identity strings (got exit $check_exit)"
fi

# Test 2: --fix rewrites the fixture (exits 0)
echo "--- 2. --fix rewrites fixture"
fix_out=$("$SCRIPT" --fix "$FIXTURE_JSON" 2>&1; echo "EXIT:$?") || true
fix_exit="${fix_out##*EXIT:}"
fix_out="${fix_out%EXIT:*}"
if assert_exit "exit code" 0 "$fix_exit"; then
  pass "2. --fix exits 0"
else
  fail "2. --fix exits 0 (got exit $fix_exit, output: $fix_out)"
fi

# Test 3: --check after --fix returns exit 0
echo "--- 3. --check is clean after --fix"
recheck_out=$("$SCRIPT" --check "$FIXTURE_JSON" 2>&1; echo "EXIT:$?") || true
recheck_exit="${recheck_out##*EXIT:}"
recheck_out="${recheck_out%EXIT:*}"
if assert_exit "exit code" 0 "$recheck_exit"; then
  pass "3. --check exits 0 after --fix"
else
  fail "3. --check exits 0 after --fix (got exit $recheck_exit, output: $recheck_out)"
fi

# Test 4a: post-fix content contains canonical org
echo "--- 4a. post-fix contains dbc-oduffy/coordinator-claude"
fixed_content="$(cat "$FIXTURE_JSON")"
if assert_contains "canonical org" "dbc-oduffy/coordinator-claude" "$fixed_content"; then
  pass "4a. dbc-oduffy/coordinator-claude present after --fix"
else
  fail "4a. dbc-oduffy/coordinator-claude present after --fix"
fi

# Test 4b: post-fix content contains "the Coordinator Authors"
echo "--- 4b. post-fix contains 'the Coordinator Authors'"
if assert_contains "coordinator authors" "the Coordinator Authors" "$fixed_content"; then
  pass "4b. 'the Coordinator Authors' present after --fix"
else
  fail "4b. 'the Coordinator Authors' present after --fix"
fi

# Test 5a: post-fix does NOT contain "Dónal O'Duffy"
echo "--- 5a. post-fix does not contain Dónal O'Duffy"
if assert_not_contains "Dónal O'Duffy removed" "Dónal O'Duffy" "$fixed_content"; then
  pass "5a. 'Dónal O'Duffy' removed after --fix"
else
  fail "5a. 'Dónal O'Duffy' removed after --fix"
fi

# Test 5b: post-fix does NOT contain "oduffy-delphi"
echo "--- 5b. post-fix does not contain oduffy-delphi"
if assert_not_contains "oduffy-delphi removed" "oduffy-delphi" "$fixed_content"; then
  pass "5b. 'oduffy-delphi' removed after --fix"
else
  fail "5b. 'oduffy-delphi' removed after --fix"
fi

# Test 6: persona substitution unchanged — Patrik → Staff Engineer (any case)
# Note: sentence-initial "Patrik" becomes "The Staff Engineer" (capitalized by
# the post-pass cleanup). We check for the role string case-insensitively.
echo "--- 6. persona substitution: Patrik → the Staff Engineer"
"$SCRIPT" --fix "$FIXTURE_PERSONA_MD" > /dev/null 2>&1
persona_content="$(cat "$FIXTURE_PERSONA_MD")"
if echo "$persona_content" | grep -qiF "staff engineer" && \
   assert_not_contains "Patrik gone" "Patrik" "$persona_content"; then
  pass "6. Patrik → the Staff Engineer still works"
else
  fail "6. Patrik → the Staff Engineer still works"
fi

# Test 7: canonical-form JSON (dbc-oduffy/...) is NOT flagged by --check
echo "--- 7. canonical form dbc-oduffy/... is not flagged"
canon_out=$("$SCRIPT" --check "$FIXTURE_CANONICAL_JSON" 2>&1)
canon_exit=$?
if assert_exit "exit code" 0 "$canon_exit"; then
  pass "7. dbc-oduffy/... not flagged by --check (already canonical)"
else
  fail "7. dbc-oduffy/... not flagged by --check (got exit $canon_exit, output: $canon_out)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: $PASS passed, $FAIL failed."
if (( FAIL > 0 )); then
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do echo "  - $msg"; done
  exit 1
fi
exit 0
