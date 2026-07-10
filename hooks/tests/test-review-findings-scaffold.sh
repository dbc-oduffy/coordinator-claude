#!/usr/bin/env bash
# test-review-findings-scaffold.sh — Tests for `coordinator-doc-new --type review-findings`.
#
# Spec backlink: docs/plans/2026-06-30-reviewer-findings-self-persist.md § AC11, AC12, AC13
#
# Coverage:
#   AC11 — scaffold emits skeleton and prints the output path to stdout; file is
#           created at state/review-trail/findings/YYYY-MM-DD-codereview-slice<ID>-<SLUG>.md
#           and contains the <!-- FINDINGS --> sentinel.
#   AC12 — the path formula is documented in BOTH schemas/review-findings.yaml AND
#           in the coordinator-doc-new --help output.
#   AC13 — replacing the single <!-- FINDINGS --> sentinel with body text via ONE
#           sed in-place edit removes the sentinel and installs the body.
#
# Cross-platform: runs on Git-Bash (Windows) and bash ≥ 4 on Linux/macOS.
# No bash 4+ features used (no declare -A, no mapfile, no ${v^^}).

set -uo pipefail
export COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate coordinator-doc-new — prefer the PATH-resolved binary, fall back to
# the sibling bin/ directory so this test is self-contained from the plugin root.
if command -v coordinator-doc-new &>/dev/null; then
  DOC_NEW="coordinator-doc-new"
else
  DOC_NEW="$SCRIPT_DIR/../../bin/coordinator-doc-new"
fi
if ! command -v "$DOC_NEW" &>/dev/null 2>&1 && [[ ! -f "$DOC_NEW" ]]; then
  echo "FAIL: coordinator-doc-new not found (tried PATH and $DOC_NEW)"
  exit 1
fi

# Schema file — relative to this test script's repo root.
SCHEMA_FILE="$SCRIPT_DIR/../../schemas/review-findings.yaml"
if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "FAIL: schema file not found at $SCHEMA_FILE"
  exit 1
fi

PASS=0
FAIL=0

pass_case() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail_case() { echo "FAIL: $1"; echo "      $2"; FAIL=$((FAIL + 1)); }

# ---------------------------------------------------------------------------
# Throwaway git repo — coordinator-doc-new resolves the git root from cwd,
# and the containment check (_assert_output_safe) allows paths inside it.
# ---------------------------------------------------------------------------
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

git init -q "$TMP_ROOT" 2>/dev/null
git -C "$TMP_ROOT" config user.email t@t.t
git -C "$TMP_ROOT" config user.name t
git -C "$TMP_ROOT" config commit.gpgsign false

# Verify git root is resolvable.
_GITCHECK=$(git -C "$TMP_ROOT" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$_GITCHECK" ]]; then
  echo "FAIL: git rev-parse failed inside $TMP_ROOT — cannot run tests"
  exit 1
fi

# ---------------------------------------------------------------------------
# AC11 — scaffold emits skeleton + prints path; file created at formula path;
#         file contains <!-- FINDINGS --> sentinel.
# ---------------------------------------------------------------------------
echo "=== AC11: scaffold emits skeleton and prints path ==="

_SLICE="Z"
_SCOPE="tests/x.py"

# Run the scaffolder from inside the tmp repo (cwd-anchored output).
_ac11_stdout=$(cd "$TMP_ROOT" && "$DOC_NEW" --type review-findings --slice "$_SLICE" --scope "$_SCOPE" 2>&1)
_ac11_exit=$?

if [[ "$_ac11_exit" -ne 0 ]]; then
  fail_case "AC11: coordinator-doc-new exits 0" \
    "exited $_ac11_exit; output: $_ac11_stdout"
else
  pass_case "AC11: coordinator-doc-new exits 0"
fi

# AC11a — file exists at the documented formula path.
# The CLI prints a relative path (OS-native separators); Git Bash handles both.
# We construct the expected pattern for date-stamping: the printed path must
# contain 'codereview-sliceZ-tests-x-py.md' (date prefix varies by run day).
_EXPECTED_SUFFIX="codereview-slice${_SLICE}-tests-x-py.md"
if echo "$_ac11_stdout" | grep -q "$_EXPECTED_SUFFIX"; then
  pass_case "AC11a: stdout contains expected path suffix ($_EXPECTED_SUFFIX)"
else
  fail_case "AC11a: stdout contains expected path suffix" \
    "expected '$_EXPECTED_SUFFIX' in output; got: '$_ac11_stdout'"
fi

# Verify the file actually exists by using the printed path directly.
# Git Bash handles both forward and backslash separators on Windows.
_PRINTED_PATH="$_ac11_stdout"
_ABS_PATH="$TMP_ROOT/${_PRINTED_PATH//\\/\/}"
# Fallback: if TMP_ROOT + forward-slash join doesn't work, try the raw printed path relative to TMP_ROOT.
if [[ ! -f "$_ABS_PATH" ]]; then
  _ABS_PATH=$(cd "$TMP_ROOT" && find . -name "$_EXPECTED_SUFFIX" 2>/dev/null | head -1)
  [[ -n "$_ABS_PATH" ]] && _ABS_PATH="$TMP_ROOT/${_ABS_PATH#./}"
fi

if [[ -f "$_ABS_PATH" ]]; then
  pass_case "AC11a: file exists at formula path"
else
  fail_case "AC11a: file exists at formula path" \
    "not found; printed='$_PRINTED_PATH' abs='$_ABS_PATH'"
fi

# AC11b — CLI prints the path to stdout (non-empty, contains expected suffix).
if [[ -n "$_ac11_stdout" ]]; then
  pass_case "AC11b: CLI printed path to stdout (non-empty)"
else
  fail_case "AC11b: CLI printed path to stdout" "stdout was empty"
fi

# AC11c — file contains the <!-- FINDINGS --> sentinel.
if [[ -f "$_ABS_PATH" ]] && grep -q '<!-- FINDINGS -->' "$_ABS_PATH"; then
  pass_case "AC11c: scaffolded file contains <!-- FINDINGS --> sentinel"
else
  fail_case "AC11c: scaffolded file contains <!-- FINDINGS --> sentinel" \
    "sentinel not found in $_ABS_PATH"
fi

# ---------------------------------------------------------------------------
# AC12 — path formula documented in schemas/review-findings.yaml AND --help.
#
# Both documents use 'codereview-slice' as the distinctive pattern
# (the formula is: YYYY-MM-DD-codereview-slice<ID>-<SLUG>.md).
# ---------------------------------------------------------------------------
echo "=== AC12: path formula documented in schema AND --help ==="

_FORMULA_PATTERN="codereview-slice"

if grep -q "$_FORMULA_PATTERN" "$SCHEMA_FILE"; then
  pass_case "AC12a: path formula pattern '$_FORMULA_PATTERN' in schemas/review-findings.yaml"
else
  fail_case "AC12a: path formula pattern in schemas/review-findings.yaml" \
    "'$_FORMULA_PATTERN' not found in $SCHEMA_FILE"
fi

_HELP_OUT=$("$DOC_NEW" --help 2>&1 || true)
if echo "$_HELP_OUT" | grep -q "$_FORMULA_PATTERN"; then
  pass_case "AC12b: path formula pattern '$_FORMULA_PATTERN' in --help output"
else
  fail_case "AC12b: path formula pattern in --help output" \
    "'$_FORMULA_PATTERN' not found in coordinator-doc-new --help"
fi

# ---------------------------------------------------------------------------
# AC13 — single sentinel-replace via ONE sed -i fills the skeleton.
#
# Takes the scaffolded file from AC11, replaces the single <!-- FINDINGS -->
# line with body text in ONE sed in-place edit, then asserts:
#   (a) sentinel is gone
#   (b) body text is present
# Simulates the reviewer's single Edit contract.
# ---------------------------------------------------------------------------
echo "=== AC13: single sentinel-replace fills skeleton ==="

if [[ ! -f "$_ABS_PATH" ]]; then
  fail_case "AC13: scaffold file available for sentinel-replace test" \
    "AC11 must pass for AC13 to run; file not found at $_ABS_PATH"
else
  _AC13_BODY="P0: example finding — refactor helper to avoid mutation."
  # One sentinel-replace via portable temp-file swap (simulates reviewer's
  # single Edit). GNU `sed -i "script" file` and BSD `sed -i '' "script" file`
  # are mutually incompatible in-place forms — the temp-file + mv pattern
  # works identically on both. See DR-148 / cross-platform-shell-portability.md.
  sed "s|<!-- FINDINGS -->|${_AC13_BODY}|" "$_ABS_PATH" > "$_ABS_PATH.tmp" && mv "$_ABS_PATH.tmp" "$_ABS_PATH"

  if ! grep -q '<!-- FINDINGS -->' "$_ABS_PATH"; then
    pass_case "AC13a: sentinel removed after single sed replacement"
  else
    fail_case "AC13a: sentinel removed after single sed replacement" \
      "<!-- FINDINGS --> still present in $_ABS_PATH"
  fi

  if grep -q "$_AC13_BODY" "$_ABS_PATH"; then
    pass_case "AC13b: body text present after single sed replacement"
  else
    fail_case "AC13b: body text present after single sed replacement" \
      "'$_AC13_BODY' not found in $_ABS_PATH"
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "test-review-findings-scaffold: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
