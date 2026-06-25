#!/usr/bin/env bash
# verify-no-console-flash: file-allow — test scaffolding; interpreter spawns run in the CI/local test harness, never the Windows interactive coordinator hot-path
# review-coverage-core.test.sh — test suite for lib/review-coverage-core.sh.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2
#
# Coverage:
#   TC1  SAFE_RANGE validation — injection-shaped sha_range is skipped with WARN
#   TC2  JSON single-object parse — diff record commits land in reviewed_set
#   TC3  JSONL dual-shape parse — both shapes parsed; diff record commits counted
#   TC4  scope_kind=plan record — skipped silently (no WARN, no error)
#   TC5  scope_kind=integration record — skipped silently
#   TC6  verdict=pending — commits NOT included in reviewed_set (excluded)
#   TC7  verdict=ok — commits included in reviewed_set
#   TC8  verdict=warn — commits included in reviewed_set
#   TC9  verdict=blocked — commits included in reviewed_set
#   TC10 verdict=waived — commits included (explicit PM waiver = coverage)
#   TC11 absent verdict — legacy record without verdict field is included
#   TC12 --segments-json mode — emits parseable JSON array with sha_range/shas/files
#   TC13 empty trail (no files) — exits 0, prints no SHAs, no crash
#   TC14 union across multiple records — reviewed_set = union of all valid segments
#
# Usage: bash <this-file>
# Exit:  0 if all tests pass, non-zero on any failure.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/review-coverage-core.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "ERROR: subject not found: $SUBJECT" >&2
  exit 1
fi
if [[ ! -x "$SUBJECT" ]]; then
  echo "ERROR: subject not executable: $SUBJECT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Pass/fail tally
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Temp-dir + cleanup
# ---------------------------------------------------------------------------
TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

STDERR_TMP="$TMPBASE/stderr"

# ---------------------------------------------------------------------------
# _make_fixture DIR  — build a git repo with a local-bare origin remote.
# Same harness style as bin/workweek-trail-scope.test.sh.
# ---------------------------------------------------------------------------
_make_fixture() {
  local base="$1"

  local origin_dir="$base/origin.git"
  mkdir -p "$origin_dir"
  git -C "$origin_dir" init -q --bare

  local seed_dir="$base/seed"
  git clone -q "$origin_dir" "$seed_dir" 2>/dev/null
  git -C "$seed_dir" config user.email "test@test.local"
  git -C "$seed_dir" config user.name  "Test"
  git -C "$seed_dir" checkout -q -b main 2>/dev/null || git -C "$seed_dir" checkout -q main 2>/dev/null || true
  touch "$seed_dir/.gitkeep"
  git -C "$seed_dir" add -- .gitkeep
  git -C "$seed_dir" commit -q -m "root"
  git -C "$seed_dir" push -q origin main
  rm -rf "$seed_dir"

  local repo_dir="$base/repo"
  git clone -q "$origin_dir" "$repo_dir" 2>/dev/null
  git -C "$repo_dir" config user.email "test@test.local"
  git -C "$repo_dir" config user.name  "Test"
  git -C "$repo_dir" checkout -q main 2>/dev/null || true

  mkdir -p "$repo_dir/state/review-trail"
}

# Helper: add a commit to a repo touching one or more files. Returns SHA via stdout.
_add_commit() {
  local repo="$1"; shift
  local sha
  for f in "$@"; do
    local dir
    dir="$(dirname "$repo/$f")"
    mkdir -p "$dir"
    printf 'content of %s\n' "$f" >> "$repo/$f"
    git -C "$repo" add -- "$f"
  done
  git -C "$repo" commit -q -m "touch $*"
  sha=$(git -C "$repo" rev-parse HEAD)
  printf '%s' "$sha"
}

# Helper: today's date (BSD-portable).
_today() { date -u +%Y-%m-%d; }

# Helper: run the subject in a given repo dir with a list of trail-file paths.
# Sets RC, STDOUT_OUT, STDERR_OUT.
RC=0
STDOUT_OUT=""
STDERR_OUT=""

# Usage: _run_core MODE REPO [--on-record-error skip|fail] [TRAIL_PATH...]
# Review: code-reviewer — the helper accepts --on-record-error flags intermixed with trail
# paths in its positional tail; this comment documents the accepted forms.
_run_core() {
  local mode="$1"; shift
  local repo="$1"; shift
  local trail_files=("$@")
  RC=0
  STDOUT_OUT=""
  STDERR_OUT=""
  STDOUT_OUT=$(cd "$repo" && bash "$SUBJECT" "$mode" "${trail_files[@]}" 2>"$STDERR_TMP") || RC=$?
  STDERR_OUT=$(cat "$STDERR_TMP" 2>/dev/null || true)
}

# ---------------------------------------------------------------------------
# TC1 — SAFE_RANGE validation: injection-shaped sha_range skipped with WARN.
# ---------------------------------------------------------------------------
TC1="$TMPBASE/tc1"
_make_fixture "$TC1"

_add_commit "$TC1/repo" "src/thing.py" >/dev/null

trail_tc1="$TC1/repo/state/review-trail/$(_today)-unsafe.json"
cat > "$trail_tc1" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "--output=/tmp/evil..HEAD",
  "artifact": "evil-record"
}
JSON

_run_core "--reviewed-set" "$TC1/repo" "$trail_tc1"

if [[ "$RC" -eq 0 ]] && echo "$STDERR_OUT" | grep -qi "unsafe sha_range\|failed rev-range validation"; then
  _pass "TC1: injection sha_range emits WARN, exits 0, produces no SHAs"
elif [[ "$RC" -ne 0 ]]; then
  _fail "TC1: SAFE_RANGE" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  _fail "TC1: SAFE_RANGE" "expected WARN in stderr; got: $STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# TC2 — JSON single-object parse: diff record commits in reviewed_set.
# ---------------------------------------------------------------------------
TC2="$TMPBASE/tc2"
_make_fixture "$TC2"

sha_c1=$(_add_commit "$TC2/repo" "src/alpha.py")
sha_c2=$(_add_commit "$TC2/repo" "src/beta.py")
origin_sha_tc2=$(git -C "$TC2/repo" rev-parse origin/main)
range_tc2="${origin_sha_tc2}..${sha_c2}"

trail_tc2="$TC2/repo/state/review-trail/$(_today)-single-obj.json"
cat > "$trail_tc2" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${range_tc2}",
  "verdict": "ok",
  "artifact": "tc2-ws"
}
JSON

_run_core "--reviewed-set" "$TC2/repo" "$trail_tc2"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC2: single-obj JSON" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  if echo "$STDOUT_OUT" | grep -qF "$sha_c1" && echo "$STDOUT_OUT" | grep -qF "$sha_c2"; then
    _pass "TC2: single-obj JSON — both commits in reviewed_set"
  else
    _fail "TC2: single-obj JSON" "expected $sha_c1 and $sha_c2 in reviewed_set; got: $STDOUT_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC3 — JSONL dual-shape: both JSON objects parsed; diff record commits counted.
# ---------------------------------------------------------------------------
TC3="$TMPBASE/tc3"
_make_fixture "$TC3"

sha_j1=$(_add_commit "$TC3/repo" "src/jsonl-a.py")
sha_j2=$(_add_commit "$TC3/repo" "src/jsonl-b.py")
origin_sha_tc3=$(git -C "$TC3/repo" rev-parse origin/main)
range_tc3="${origin_sha_tc3}..${sha_j2}"

trail_tc3="$TC3/repo/state/review-trail/$(_today)-jsonl.json"
printf '{"scope_kind":"diff","sha_range":"%s","verdict":"warn","artifact":"tc3-ws"}\n' "$range_tc3" > "$trail_tc3"
printf '{"scope_kind":"integration","artifact":"tc3-integrator","note":"envelope"}\n' >> "$trail_tc3"

_run_core "--reviewed-set" "$TC3/repo" "$trail_tc3"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC3: JSONL" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  if echo "$STDOUT_OUT" | grep -qF "$sha_j1" && echo "$STDOUT_OUT" | grep -qF "$sha_j2"; then
    _pass "TC3: JSONL dual-shape — diff line parsed, commits in reviewed_set"
  else
    _fail "TC3: JSONL" "expected $sha_j1 and $sha_j2 in reviewed_set; got: $STDOUT_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC4 — scope_kind=plan record: skipped silently (no WARN, no crash).
# ---------------------------------------------------------------------------
TC4="$TMPBASE/tc4"
_make_fixture "$TC4"

_add_commit "$TC4/repo" "docs/plan.md" >/dev/null

trail_tc4="$TC4/repo/state/review-trail/$(_today)-plan.json"
cat > "$trail_tc4" <<JSON
{
  "scope_kind": "plan",
  "artifact": "some-plan-review",
  "verdict": "ok"
}
JSON

_run_core "--reviewed-set" "$TC4/repo" "$trail_tc4"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC4: scope_kind=plan" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDERR_OUT" | grep -qi "skipping non-diff\|WARN.*plan"; then
  _fail "TC4: scope_kind=plan" "unexpected WARN for plan record; stderr: $STDERR_OUT"
else
  _pass "TC4: scope_kind=plan skipped silently, no WARN"
fi

# ---------------------------------------------------------------------------
# TC5 — scope_kind=integration record: skipped silently.
# ---------------------------------------------------------------------------
TC5="$TMPBASE/tc5"
_make_fixture "$TC5"

_add_commit "$TC5/repo" "docs/integration.md" >/dev/null

trail_tc5="$TC5/repo/state/review-trail/$(_today)-integration.json"
cat > "$trail_tc5" <<JSON
{
  "scope_kind": "integration",
  "artifact": "some-integration-review"
}
JSON

_run_core "--reviewed-set" "$TC5/repo" "$trail_tc5"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC5: scope_kind=integration" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDERR_OUT" | grep -qi "WARN.*integration"; then
  _fail "TC5: scope_kind=integration" "unexpected WARN; stderr: $STDERR_OUT"
else
  _pass "TC5: scope_kind=integration skipped silently, no WARN"
fi

# ---------------------------------------------------------------------------
# TC6 — verdict=pending: commits NOT in reviewed_set (excluded by verdict filter).
# ---------------------------------------------------------------------------
TC6="$TMPBASE/tc6"
_make_fixture "$TC6"

sha_pend1=$(_add_commit "$TC6/repo" "src/pend-a.py")
sha_pend2=$(_add_commit "$TC6/repo" "src/pend-b.py")
origin_sha_tc6=$(git -C "$TC6/repo" rev-parse origin/main)
range_tc6="${origin_sha_tc6}..${sha_pend2}"

trail_tc6="$TC6/repo/state/review-trail/$(_today)-pending.json"
cat > "$trail_tc6" <<JSON
{
  "scope_kind": "diff",
  "sha_range": "${range_tc6}",
  "verdict": "pending",
  "artifact": "tc6-pending-ws"
}
JSON

_run_core "--reviewed-set" "$TC6/repo" "$trail_tc6"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC6: verdict=pending excluded" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  # Pending commits must NOT appear in reviewed_set output.
  if echo "$STDOUT_OUT" | grep -qF "$sha_pend1" || echo "$STDOUT_OUT" | grep -qF "$sha_pend2"; then
    _fail "TC6: verdict=pending excluded" "pending commits appeared in reviewed_set (should be excluded); output: $STDOUT_OUT"
  else
    _pass "TC6: verdict=pending — commits excluded from reviewed_set (filter active)"
  fi
fi

# ---------------------------------------------------------------------------
# TC7 — verdict=ok: commits included in reviewed_set.
# ---------------------------------------------------------------------------
TC7="$TMPBASE/tc7"
_make_fixture "$TC7"

sha_ok1=$(_add_commit "$TC7/repo" "src/ok-a.py")
origin_sha_tc7=$(git -C "$TC7/repo" rev-parse origin/main)
range_tc7="${origin_sha_tc7}..${sha_ok1}"

trail_tc7="$TC7/repo/state/review-trail/$(_today)-ok.json"
cat > "$trail_tc7" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc7}","verdict":"ok","artifact":"tc7-ok"}
JSON

_run_core "--reviewed-set" "$TC7/repo" "$trail_tc7"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC7: verdict=ok" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDOUT_OUT" | grep -qF "$sha_ok1"; then
  _pass "TC7: verdict=ok — commits included in reviewed_set"
else
  _fail "TC7: verdict=ok" "expected $sha_ok1 in reviewed_set; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC8 — verdict=warn: commits included in reviewed_set.
# ---------------------------------------------------------------------------
TC8="$TMPBASE/tc8"
_make_fixture "$TC8"

sha_warn1=$(_add_commit "$TC8/repo" "src/warn-a.py")
origin_sha_tc8=$(git -C "$TC8/repo" rev-parse origin/main)
range_tc8="${origin_sha_tc8}..${sha_warn1}"

trail_tc8="$TC8/repo/state/review-trail/$(_today)-warn.json"
cat > "$trail_tc8" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc8}","verdict":"warn","artifact":"tc8-warn"}
JSON

_run_core "--reviewed-set" "$TC8/repo" "$trail_tc8"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC8: verdict=warn" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDOUT_OUT" | grep -qF "$sha_warn1"; then
  _pass "TC8: verdict=warn — commits included in reviewed_set"
else
  _fail "TC8: verdict=warn" "expected $sha_warn1 in reviewed_set; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC9 — verdict=blocked: commits included in reviewed_set.
# ---------------------------------------------------------------------------
TC9="$TMPBASE/tc9"
_make_fixture "$TC9"

sha_blk1=$(_add_commit "$TC9/repo" "src/blocked-a.py")
origin_sha_tc9=$(git -C "$TC9/repo" rev-parse origin/main)
range_tc9="${origin_sha_tc9}..${sha_blk1}"

trail_tc9="$TC9/repo/state/review-trail/$(_today)-blocked.json"
cat > "$trail_tc9" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc9}","verdict":"blocked","artifact":"tc9-blocked"}
JSON

_run_core "--reviewed-set" "$TC9/repo" "$trail_tc9"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC9: verdict=blocked" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDOUT_OUT" | grep -qF "$sha_blk1"; then
  _pass "TC9: verdict=blocked — commits included in reviewed_set"
else
  _fail "TC9: verdict=blocked" "expected $sha_blk1 in reviewed_set; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC10 — verdict=waived: commits included (explicit PM waiver = coverage decision).
# ---------------------------------------------------------------------------
TC10="$TMPBASE/tc10"
_make_fixture "$TC10"

sha_wv1=$(_add_commit "$TC10/repo" "src/waived-a.py")
origin_sha_tc10=$(git -C "$TC10/repo" rev-parse origin/main)
range_tc10="${origin_sha_tc10}..${sha_wv1}"

trail_tc10="$TC10/repo/state/review-trail/$(_today)-waived.json"
cat > "$trail_tc10" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc10}","verdict":"waived","artifact":"tc10-waived"}
JSON

_run_core "--reviewed-set" "$TC10/repo" "$trail_tc10"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC10: verdict=waived" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDOUT_OUT" | grep -qF "$sha_wv1"; then
  _pass "TC10: verdict=waived — commits included in reviewed_set (PM waiver counts)"
else
  _fail "TC10: verdict=waived" "expected $sha_wv1 in reviewed_set; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC11 — absent verdict: legacy record without verdict field is included.
# ---------------------------------------------------------------------------
TC11="$TMPBASE/tc11"
_make_fixture "$TC11"

sha_leg1=$(_add_commit "$TC11/repo" "src/legacy-a.py")
origin_sha_tc11=$(git -C "$TC11/repo" rev-parse origin/main)
range_tc11="${origin_sha_tc11}..${sha_leg1}"

trail_tc11="$TC11/repo/state/review-trail/$(_today)-legacy.json"
cat > "$trail_tc11" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc11}","artifact":"tc11-legacy-no-verdict"}
JSON

_run_core "--reviewed-set" "$TC11/repo" "$trail_tc11"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC11: absent verdict (legacy)" "expected exit 0, got $RC. stderr=$STDERR_OUT"
elif echo "$STDOUT_OUT" | grep -qF "$sha_leg1"; then
  _pass "TC11: absent verdict (legacy record) — commits included in reviewed_set"
else
  _fail "TC11: absent verdict (legacy)" "expected $sha_leg1 in reviewed_set; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC12 — --segments-json mode: emits parseable JSON array with shas and files.
# ---------------------------------------------------------------------------
TC12="$TMPBASE/tc12"
_make_fixture "$TC12"

sha_s1=$(_add_commit "$TC12/repo" "src/seg-a.py")
sha_s2=$(_add_commit "$TC12/repo" "src/seg-b.py")
origin_sha_tc12=$(git -C "$TC12/repo" rev-parse origin/main)
range_tc12="${origin_sha_tc12}..${sha_s2}"

trail_tc12="$TC12/repo/state/review-trail/$(_today)-seg.json"
cat > "$trail_tc12" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc12}","verdict":"ok","artifact":"tc12-seg"}
JSON

_run_core "--segments-json" "$TC12/repo" "$trail_tc12"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC12: --segments-json mode" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  # Output must be valid JSON containing both SHAs.
  # Write STDOUT_OUT to a temp file so Python reads it via open() instead of
  # shell-interpolation into a triple-quoted string (breaks on """ or backslashes).
  # Review: code-reviewer — TC12 previously interpolated ${STDOUT_OUT} into a Python
  # triple-quoted string heredoc, which breaks if output contains """ or backslashes.
  parsed_ok=0
  _tc12_json="$TMPBASE/tc12-stdout.json"
  printf '%s' "$STDOUT_OUT" > "$_tc12_json"
  if python3 - "$_tc12_json" "$sha_s1" "$sha_s2" <<'PYEOF' 2>/dev/null
import json, sys
with open(sys.argv[1]) as _f:
    data = json.load(_f)
sha1, sha2 = sys.argv[2], sys.argv[3]
all_shas = [s for seg in data for s in seg.get("shas", [])]
assert sha1 in all_shas and sha2 in all_shas
PYEOF
  then
    parsed_ok=1
  fi
  if [[ "$parsed_ok" -eq 1 ]]; then
    _pass "TC12: --segments-json mode — valid JSON with shas array containing both commits"
  else
    _fail "TC12: --segments-json mode" "JSON parse or SHA check failed; output: $STDOUT_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC13 — empty trail (no files): exits 0, no SHAs output, no crash.
# ---------------------------------------------------------------------------
TC13="$TMPBASE/tc13"
_make_fixture "$TC13"

_add_commit "$TC13/repo" "src/thing.py" >/dev/null
# No trail files written.

_run_core "--reviewed-set" "$TC13/repo"

if [[ "$RC" -eq 0 ]] && [[ -z "$STDOUT_OUT" ]]; then
  _pass "TC13: empty trail — exits 0, no output (no crash on empty union)"
elif [[ "$RC" -ne 0 ]]; then
  _fail "TC13: empty trail" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  _fail "TC13: empty trail" "expected empty stdout; got: $STDOUT_OUT"
fi

# ---------------------------------------------------------------------------
# TC14 — union across multiple records: reviewed_set = union of all segments.
# ---------------------------------------------------------------------------
TC14="$TMPBASE/tc14"
_make_fixture "$TC14"

sha_u1=$(_add_commit "$TC14/repo" "src/union-a.py")
sha_u2=$(_add_commit "$TC14/repo" "src/union-b.py")
sha_u3=$(_add_commit "$TC14/repo" "src/union-c.py")
origin_sha_tc14=$(git -C "$TC14/repo" rev-parse origin/main)
# Record A covers first two commits; Record B covers the third.
range_a_tc14="${origin_sha_tc14}..${sha_u2}"
range_b_tc14="${sha_u2}..${sha_u3}"

trail_a_tc14="$TC14/repo/state/review-trail/$(_today)-union-a.json"
cat > "$trail_a_tc14" <<JSON
{"scope_kind":"diff","sha_range":"${range_a_tc14}","verdict":"ok","artifact":"tc14-a"}
JSON

trail_b_tc14="$TC14/repo/state/review-trail/$(_today)-union-b.json"
cat > "$trail_b_tc14" <<JSON
{"scope_kind":"diff","sha_range":"${range_b_tc14}","verdict":"ok","artifact":"tc14-b"}
JSON

_run_core "--reviewed-set" "$TC14/repo" "$trail_a_tc14" "$trail_b_tc14"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC14: union across records" "expected exit 0, got $RC. stderr=$STDERR_OUT"
else
  if echo "$STDOUT_OUT" | grep -qF "$sha_u1" \
      && echo "$STDOUT_OUT" | grep -qF "$sha_u2" \
      && echo "$STDOUT_OUT" | grep -qF "$sha_u3"; then
    _pass "TC14: union across records — all three commits in reviewed_set"
  else
    _fail "TC14: union across records" "expected $sha_u1 $sha_u2 $sha_u3 in reviewed_set; got: $STDOUT_OUT"
  fi
fi

# ---------------------------------------------------------------------------
# TC15 — garbage file (neither JSON nor JSONL) with --on-record-error fail
#         (the DEFAULT) → core exits NON-ZERO.
# ---------------------------------------------------------------------------
TC15="$TMPBASE/tc15"
_make_fixture "$TC15"

_add_commit "$TC15/repo" "src/garbage-test.py" >/dev/null

trail_tc15="$TC15/repo/state/review-trail/$(_today)-garbage.json"
# Write a file that is neither a JSON object nor JSONL — concatenated JSON objects
# with no newline separator fail both json.load and per-line json.loads.
printf '{"a":1}{"b":2}\n' > "$trail_tc15"

# Default is --on-record-error fail; pass it explicitly to make the case self-documenting.
_run_core "--reviewed-set" "$TC15/repo" "--on-record-error" "fail" "$trail_tc15"

if [[ "$RC" -ne 0 ]]; then
  _pass "TC15: garbage file + --on-record-error fail → core exits non-zero"
else
  _fail "TC15: garbage file + --on-record-error fail" "expected non-zero exit; got 0. stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# TC16 — SAME garbage file with --on-record-error skip →
#         core exits 0, emits WARN on stderr, processes sibling valid record.
# ---------------------------------------------------------------------------
TC16="$TMPBASE/tc16"
_make_fixture "$TC16"

sha_tc16_valid=$(_add_commit "$TC16/repo" "src/valid-sibling.py")
origin_sha_tc16=$(git -C "$TC16/repo" rev-parse origin/main)
range_tc16="${origin_sha_tc16}..${sha_tc16_valid}"

# Garbage trail file — must be .json to be picked up.
trail_tc16_bad="$TC16/repo/state/review-trail/$(_today)-garbage.json"
printf '{"a":1}{"b":2}\n' > "$trail_tc16_bad"

# Valid sibling trail file.
trail_tc16_valid="$TC16/repo/state/review-trail/$(_today)-valid-sibling.json"
cat > "$trail_tc16_valid" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc16}","verdict":"ok","artifact":"tc16-valid"}
JSON

_run_core "--reviewed-set" "$TC16/repo" "--on-record-error" "skip" "$trail_tc16_bad" "$trail_tc16_valid"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC16: garbage + skip" "expected exit 0; got $RC. stderr=$STDERR_OUT"
elif ! printf '%s' "$STDERR_OUT" | grep -qi "WARN.*skip"; then
  _fail "TC16: garbage + skip" "expected WARN: skipping in stderr; got: $STDERR_OUT"
elif ! printf '%s' "$STDOUT_OUT" | grep -qF "$sha_tc16_valid"; then
  _fail "TC16: garbage + skip" "expected valid sibling commit $sha_tc16_valid in reviewed_set; got: $STDOUT_OUT"
else
  _pass "TC16: garbage + --on-record-error skip → exits 0, WARN on stderr, valid sibling processed"
fi

# ---------------------------------------------------------------------------
# TC17 — record with syntactically-valid-but-unresolvable sha_range
#         (real-sha..WORKING passes SAFE_RANGE; WORKING is not a real ref) with
#         --on-record-error skip → exits 0, WARN on stderr, sibling valid record counts.
# ---------------------------------------------------------------------------
TC17="$TMPBASE/tc17"
_make_fixture "$TC17"

sha_tc17_real=$(_add_commit "$TC17/repo" "src/tc17-real.py")
origin_sha_tc17=$(git -C "$TC17/repo" rev-parse origin/main)
range_tc17_valid="${origin_sha_tc17}..${sha_tc17_real}"
# sha_tc17_real..WORKING passes SAFE_RANGE (starts with hex digit + ..)
# but WORKING is not a git ref in this repo → git rev-list will fail.
range_tc17_bad="${sha_tc17_real}..WORKING"

# Unresolvable-range trail file.
trail_tc17_bad="$TC17/repo/state/review-trail/$(_today)-unresolvable.json"
cat > "$trail_tc17_bad" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc17_bad}","verdict":"ok","artifact":"tc17-bad-range"}
JSON

# Valid sibling.
trail_tc17_valid="$TC17/repo/state/review-trail/$(_today)-valid.json"
cat > "$trail_tc17_valid" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc17_valid}","verdict":"ok","artifact":"tc17-valid"}
JSON

_run_core "--reviewed-set" "$TC17/repo" "--on-record-error" "skip" "$trail_tc17_bad" "$trail_tc17_valid"

if [[ "$RC" -ne 0 ]]; then
  _fail "TC17: unresolvable range + skip" "expected exit 0; got $RC. stderr=$STDERR_OUT"
elif ! printf '%s' "$STDERR_OUT" | grep -qi "WARN.*skip\|WARN.*unresolvable\|WARN.*range"; then
  _fail "TC17: unresolvable range + skip" "expected WARN in stderr; got: $STDERR_OUT"
elif ! printf '%s' "$STDOUT_OUT" | grep -qF "$sha_tc17_real"; then
  _fail "TC17: unresolvable range + skip" "expected valid sibling commit $sha_tc17_real in reviewed_set; got: $STDOUT_OUT"
else
  _pass "TC17: unresolvable sha_range + --on-record-error skip → exits 0, WARN, sibling valid record counts"
fi

# ---------------------------------------------------------------------------
# TC18 — SAME unresolvable-range record with --on-record-error fail → exits NON-ZERO.
# ---------------------------------------------------------------------------
TC18="$TMPBASE/tc18"
_make_fixture "$TC18"

sha_tc18_real=$(_add_commit "$TC18/repo" "src/tc18-real.py")
range_tc18_bad="${sha_tc18_real}..WORKING"

trail_tc18="$TC18/repo/state/review-trail/$(_today)-unresolvable.json"
cat > "$trail_tc18" <<JSON
{"scope_kind":"diff","sha_range":"${range_tc18_bad}","verdict":"ok","artifact":"tc18-bad-range"}
JSON

_run_core "--reviewed-set" "$TC18/repo" "--on-record-error" "fail" "$trail_tc18"

if [[ "$RC" -ne 0 ]]; then
  _pass "TC18: unresolvable sha_range + --on-record-error fail → core exits non-zero"
else
  _fail "TC18: unresolvable range + fail" "expected non-zero exit; got 0. stderr=$STDERR_OUT"
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
TOTAL=$(( PASS + FAIL ))
echo ""
echo "Results: ${PASS} PASS / ${FAIL} FAIL (${TOTAL} total)"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
