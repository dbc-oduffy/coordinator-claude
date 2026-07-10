#!/usr/bin/env bash
# scaffold-canonical-structure.test.sh — Hermetic regression tests for scaffold-canonical-structure.sh
#
# Purpose: Validates FILE entry scaffolding (creation, content-match, idempotence),
#          missing-template exit behavior, directory scaffolding, and template:null skip.
#          All tests run against temp repos; nothing touches the real working tree.
#
# Usage: bash coordinator/bin/scaffold-canonical-structure.test.sh
# Exit:  0 = all tests pass; non-zero = at least one failure.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 2

# --- bash >= 4 guard (must be reachable on 3.2 — no bash-4 syntax before this) ---
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "scaffold-canonical-structure.test.sh: requires bash >= 4 (found ${BASH_VERSION})." >&2
  echo "  brew install bash  # macOS" >&2
  exit 1
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/scaffold-canonical-structure.sh"

PASS=0
FAIL=0
SCRATCHROOT=""

_setup() {
  SCRATCHROOT="$(mktemp -d)"
}

_teardown() {
  if [[ -n "$SCRATCHROOT" ]] && [[ -d "$SCRATCHROOT" ]]; then
    rm -rf "$SCRATCHROOT"
  fi
}

trap _teardown EXIT
_setup

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

_assert_exit_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" -eq "$expected" ]]; then
    _pass "$label — exit=${actual}"
  else
    _fail "$label — expected exit ${expected}, got ${actual}"
  fi
}

_assert_file_exists() {
  local label="$1" path="$2"
  if [[ -f "$path" ]]; then
    _pass "$label — file exists"
  else
    _fail "$label — file missing: ${path}"
  fi
}

_assert_file_missing() {
  local label="$1" path="$2"
  if [[ ! -f "$path" ]]; then
    _pass "$label — file absent as expected"
  else
    _fail "$label — file unexpectedly present: ${path}"
  fi
}

_assert_contents_match() {
  local label="$1" expected="$2" actual="$3"
  if diff -q "$expected" "$actual" >/dev/null 2>&1; then
    _pass "$label — content byte-matches"
  else
    _fail "$label — content mismatch (expected=${expected} actual=${actual})"
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

# ---------------------------------------------------------------------------
# Fixture helper: creates a copy of the script + a fixture manifest under a
# temp fixture dir so MANIFEST resolves to the fixture yaml, not the real one.
#
# Usage: _setup_fixture_dir <fixture_index> <yaml_body>
# Sets:  FIXTURE_SCRIPT (path to the copied script)
# ---------------------------------------------------------------------------
_setup_fixture_dir() {
  local idx="$1" yaml_body="$2"
  local fdir="${SCRATCHROOT}/fixture_${idx}"
  mkdir -p "${fdir}/bin"
  cp "$SUBJECT" "${fdir}/bin/scaffold-canonical-structure.sh"
  FIXTURE_SCRIPT="${fdir}/bin/scaffold-canonical-structure.sh"
  printf '%s\n' "$yaml_body" > "${fdir}/canonical-structure.yaml"
  # Note: templates/ dir under fdir is intentionally NOT created here for missing-template tests.
  # For tests that need a real template, callers create it explicitly.
}

# ---------------------------------------------------------------------------
# T1: valid FILE entry → target created, content byte-matches template
# Uses the REAL canonical-structure.yaml (bin/cross-repo-memo.md entry).
# ---------------------------------------------------------------------------
echo ""
echo "--- T1: valid FILE entry — created, content matches template ---"

REPO_T1="${SCRATCHROOT}/repo_t1"
mkdir -p "$REPO_T1"

set +e
bash "$SUBJECT" --root "$REPO_T1" >/dev/null 2>&1
EC_T1=$?
set -e

_assert_exit_eq "T1: scaffold exit code" 0 "$EC_T1"

MEMO_TARGET="${REPO_T1}/bin/cross-repo-memo.md"
MEMO_TEMPLATE="${SCRIPT_DIR}/../templates/cross-repo-memo-breadcrumb.md"
_assert_file_exists "T1: bin/cross-repo-memo.md created" "$MEMO_TARGET"
_assert_contents_match "T1: content byte-matches template" "$MEMO_TEMPLATE" "$MEMO_TARGET"

# ---------------------------------------------------------------------------
# T2: idempotent re-run — no clobber
# Tamper the created file, re-run, assert file is unchanged.
# ---------------------------------------------------------------------------
echo ""
echo "--- T2: idempotent re-run — no clobber ---"

echo "TAMPERED-$(date +%s)" >> "$MEMO_TARGET"
CONTENT_BEFORE="$(cat "$MEMO_TARGET")"

set +e
bash "$SUBJECT" --root "$REPO_T1" >/dev/null 2>&1
EC_T2=$?
set -e
_assert_exit_eq "T2: re-run exit code" 0 "$EC_T2"

CONTENT_AFTER="$(cat "$MEMO_TARGET")"
if [[ "$CONTENT_BEFORE" == "$CONTENT_AFTER" ]]; then
  _pass "T2: tampered file unchanged after re-run (no clobber)"
else
  _fail "T2: file was clobbered on re-run"
fi

# ---------------------------------------------------------------------------
# T3: missing template — live run → exit 2; --dry-run → warns and exits 0
# Uses a fixture manifest referencing a nonexistent template path.
# ---------------------------------------------------------------------------
echo ""
echo "--- T3: missing template — live run exit 2, dry-run warns+exit 0 ---"

_setup_fixture_dir 3 'entries:
  - path: bin/some-file.md
    creation: eager
    template: templates/nonexistent-template.md'

REPO_T3="${SCRATCHROOT}/repo_t3"
mkdir -p "$REPO_T3"

# Live run: expect exit 2
set +e
ERR_LIVE="$(bash "$FIXTURE_SCRIPT" --root "$REPO_T3" 2>&1 >/dev/null)"
EC_LIVE=$?
set -e
_assert_exit_eq "T3 (live): exit 2 on missing template" 2 "$EC_LIVE"
_assert_stderr_contains "T3 (live): stderr names the template" "declared template not found" "$ERR_LIVE"

# Dry-run: expect exit 0 + warning on stderr
set +e
ERR_DRY="$(bash "$FIXTURE_SCRIPT" --root "$REPO_T3" --dry-run 2>&1 >/dev/null)"
EC_DRY=$?
set -e
_assert_exit_eq "T3 (dry-run): exit 0 on missing template" 0 "$EC_DRY"
_assert_stderr_contains "T3 (dry-run): [dry-run] ERROR prefix" "[dry-run] ERROR: declared template not found" "$ERR_DRY"
_assert_stderr_contains "T3 (dry-run): 'would exit 2 on live run' annotation" "would exit 2 on live run" "$ERR_DRY"

# ---------------------------------------------------------------------------
# T4: directory entry scaffolded correctly (cross-repo/inbox/README.md)
# Uses the REAL canonical-structure.yaml.
# ---------------------------------------------------------------------------
echo ""
echo "--- T4: directory entry scaffolding (cross-repo/inbox/README.md) ---"

REPO_T4="${SCRATCHROOT}/repo_t4"
mkdir -p "$REPO_T4"

set +e
bash "$SUBJECT" --root "$REPO_T4" >/dev/null 2>&1
EC_T4=$?
set -e

_assert_exit_eq "T4: scaffold exit code" 0 "$EC_T4"
_assert_file_exists "T4: cross-repo/inbox/README.md created" "${REPO_T4}/cross-repo/inbox/README.md"

# ---------------------------------------------------------------------------
# T5: template: null on non-dir entry → not emitted, no file created
# Uses a fixture manifest with template: null on an eager non-dir path.
# ---------------------------------------------------------------------------
echo ""
echo "--- T5: template: null — no file entry emitted ---"

_setup_fixture_dir 5 'entries:
  - path: bin/should-not-exist.md
    creation: eager
    template: null'

REPO_T5="${SCRATCHROOT}/repo_t5"
mkdir -p "$REPO_T5"

set +e
bash "$FIXTURE_SCRIPT" --root "$REPO_T5" >/dev/null 2>&1
EC_T5=$?
set -e

_assert_exit_eq "T5: exit 0 for template:null entry" 0 "$EC_T5"
_assert_file_missing "T5: no file created for template:null entry" "${REPO_T5}/bin/should-not-exist.md"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "================================================="

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
