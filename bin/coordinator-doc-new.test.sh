#!/usr/bin/env bash
# coordinator-doc-new.test.sh — regression tests for coordinator-doc-new path anchoring
#
# Spec backlink: docs/plans/2026-07-02-coordinator-doc-new-path-anchor-fix.md
#
# Coverage:
#   (a) subdir-cwd: invoking from a subdirectory does NOT produce a doubled path;
#       file lands at <repo>/state/review-trail/findings/<name>.md
#   (b) subdir-cwd: printed pointer is repo-root-relative, not absolute
#   (c) root-cwd: invoking from repo root is unchanged — same file location,
#       same printed pointer
#   (d) explicit --out: bypass anchoring; file written verbatim to temp path

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/coordinator-doc-new"

# ---------------------------------------------------------------------------
# Minimal test harness (mirrors coordinator-safe-name.test.sh convention)
# ---------------------------------------------------------------------------
_PASS=0
_FAIL=0

_pass() {
    printf 'PASS: %s\n' "$1"
    _PASS=$((_PASS + 1))
}

_fail() {
    printf 'FAIL: %s\n' "$1"
    _FAIL=$((_FAIL + 1))
}

# ---------------------------------------------------------------------------
# Scratch git repo shared across all test cases
# ---------------------------------------------------------------------------
_WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$_WORK_DIR"' EXIT

_REPO="$_WORK_DIR/testrepo"
mkdir -p "$_REPO"
git -C "$_REPO" init -q
git -C "$_REPO" -c user.email="test@test" -c user.name="Test" commit -q --allow-empty -m "init"

# Pre-create the state/review-trail/findings dir inside the repo so the subdir
# cwd test can cd into it without creating foreign files before the tool runs.
mkdir -p "$_REPO/state/review-trail/findings"

# ---------------------------------------------------------------------------
# (a)+(b) subdir-cwd: no path doubling, repo-root-relative printed pointer
# ---------------------------------------------------------------------------

_SUBDIR="$_REPO/state/review-trail/findings"
_output=$(cd "$_SUBDIR" && python3 "$CLI" --type review-findings --slice A1 --scope lib/foo.py 2>/dev/null)
# Review: code-reviewer — stderr suppressed here so warnings don't contaminate the path string parsed below
_exit_code=$?

if [ "$_exit_code" -eq 0 ]; then
    _pass "subdir-cwd: exit 0"
else
    _fail "subdir-cwd: non-zero exit (got: $_exit_code) output: $_output"
fi

# The printed pointer must be repo-root-relative (starts with state/review-trail)
if printf '%s' "$_output" | grep -qE '^state/review-trail/findings/'; then
    _pass "subdir-cwd: printed pointer is repo-root-relative (got: $_output)"
else
    _fail "subdir-cwd: printed pointer not repo-root-relative (got: '$_output')"
fi

# No doubling: the pointer must NOT contain the doubled segment
if printf '%s' "$_output" | grep -qF 'state/review-trail/findings/state/'; then
    _fail "subdir-cwd: doubled path detected in printed pointer (got: '$_output')"
else
    _pass "subdir-cwd: no doubled path in printed pointer"
fi

# The file must exist at the un-doubled location under the repo root
_rel_path="$(printf '%s' "$_output" | tr -d '\n')"
_abs_path="$_REPO/$_rel_path"
if [ -f "$_abs_path" ]; then
    _pass "subdir-cwd: file exists at correct un-doubled path ($_rel_path)"
else
    _fail "subdir-cwd: file NOT found at expected un-doubled path ('$_abs_path')"
fi

# The doubled path must NOT exist (the regression artifact)
_doubled_rel="state/review-trail/findings/state/review-trail/findings"
if [ -d "$_REPO/$_doubled_rel" ]; then
    _fail "subdir-cwd: doubled directory was created (regression present)"
else
    _pass "subdir-cwd: doubled directory was NOT created (regression absent)"
fi

# ---------------------------------------------------------------------------
# (c) root-cwd: invoking from repo root is unchanged
# ---------------------------------------------------------------------------

_output_root=$(cd "$_REPO" && python3 "$CLI" --type review-findings --slice B2 --scope lib/bar.py 2>/dev/null)
# Review: code-reviewer — stderr suppressed here so warnings don't contaminate the path string parsed below
_exit_root=$?

if [ "$_exit_root" -eq 0 ]; then
    _pass "root-cwd: exit 0"
else
    _fail "root-cwd: non-zero exit (got: $_exit_root) output: $_output_root"
fi

# Printed pointer must be repo-root-relative
if printf '%s' "$_output_root" | grep -qE '^state/review-trail/findings/'; then
    _pass "root-cwd: printed pointer is repo-root-relative (got: $_output_root)"
else
    _fail "root-cwd: printed pointer not repo-root-relative (got: '$_output_root')"
fi

# No doubling in root-cwd case either
if printf '%s' "$_output_root" | grep -qF 'state/review-trail/findings/state/'; then
    _fail "root-cwd: doubled path in printed pointer (got: '$_output_root')"
else
    _pass "root-cwd: no doubled path in printed pointer"
fi

# File must exist
_rel_root="$(printf '%s' "$_output_root" | tr -d '\n')"
_abs_root="$_REPO/$_rel_root"
if [ -f "$_abs_root" ]; then
    _pass "root-cwd: file exists at correct path ($_rel_root)"
else
    _fail "root-cwd: file NOT found at expected path ('$_abs_root')"
fi

# ---------------------------------------------------------------------------
# (d) explicit --out: file written verbatim, anchoring bypassed
# ---------------------------------------------------------------------------

_EXPLICIT_OUT="$_WORK_DIR/explicit-out.md"
_output_explicit=$(cd "$_SUBDIR" && python3 "$CLI" --type review-findings --slice C3 --scope lib/baz.py \
    --out "$_EXPLICIT_OUT" 2>&1)
_exit_explicit=$?

if [ "$_exit_explicit" -eq 0 ]; then
    _pass "explicit-out: exit 0"
else
    _fail "explicit-out: non-zero exit (got: $_exit_explicit) output: $_output_explicit"
fi

if [ -f "$_EXPLICIT_OUT" ]; then
    _pass "explicit-out: file exists at the supplied --out path"
else
    _fail "explicit-out: file NOT found at supplied --out path ('$_EXPLICIT_OUT')"
fi

# ---------------------------------------------------------------------------
# (e) hnd-/cmp- stable-ID minting (lvv-01/C1) — shape + uniqueness across two
# rapid calls. Reconciled onto the canonical shell/JS mint basis (see
# _mint_artifact_id docstring); this test only asserts the OBSERVABLE contract
# (prefix, slug, 6 lowercase hex chars) plus uniqueness, not the internal formula.
# ---------------------------------------------------------------------------

_HND_OUT_A="$_WORK_DIR/hnd-a.md"
_HND_OUT_B="$_WORK_DIR/hnd-b.md"
python3 "$CLI" --type handoff --title "Mint Shape Test" --out "$_HND_OUT_A" >/dev/null 2>&1
python3 "$CLI" --type handoff --title "Mint Shape Test" --out "$_HND_OUT_B" >/dev/null 2>&1

_hnd_id_a="$(grep -oE '^handoff_id: "hnd-[a-z0-9-]+-[0-9a-f]{6}"' "$_HND_OUT_A" | sed -E 's/^handoff_id: "(.*)"$/\1/')"
_hnd_id_b="$(grep -oE '^handoff_id: "hnd-[a-z0-9-]+-[0-9a-f]{6}"' "$_HND_OUT_B" | sed -E 's/^handoff_id: "(.*)"$/\1/')"

if [ -n "$_hnd_id_a" ]; then
    _pass "handoff mint: handoff_id present and matches hnd-<slug>-<6hex> shape (got: $_hnd_id_a)"
else
    _fail "handoff mint: no handoff_id matching hnd-<slug>-<6hex> found in $_HND_OUT_A"
fi

if [ -n "$_hnd_id_b" ]; then
    _pass "handoff mint: second call also mints a shape-valid handoff_id (got: $_hnd_id_b)"
else
    _fail "handoff mint: no handoff_id matching hnd-<slug>-<6hex> found in $_HND_OUT_B"
fi

if [ -n "$_hnd_id_a" ] && [ -n "$_hnd_id_b" ] && [ "$_hnd_id_a" != "$_hnd_id_b" ]; then
    _pass "handoff mint: two rapid calls from the same title mint DISTINCT handoff_ids ($_hnd_id_a != $_hnd_id_b)"
else
    _fail "handoff mint: rapid calls did not mint distinct handoff_ids (a: '$_hnd_id_a', b: '$_hnd_id_b')"
fi

_CMP_OUT_A="$_WORK_DIR/cmp-a.md"
_CMP_OUT_B="$_WORK_DIR/cmp-b.md"
python3 "$CLI" --type completion --title "Mint Shape Test" --out "$_CMP_OUT_A" >/dev/null 2>&1
python3 "$CLI" --type completion --title "Mint Shape Test" --out "$_CMP_OUT_B" >/dev/null 2>&1

_cmp_id_a="$(grep -oE '^completion_id: "cmp-[a-z0-9-]+-[0-9a-f]{6}"' "$_CMP_OUT_A" | sed -E 's/^completion_id: "(.*)"$/\1/')"
_cmp_id_b="$(grep -oE '^completion_id: "cmp-[a-z0-9-]+-[0-9a-f]{6}"' "$_CMP_OUT_B" | sed -E 's/^completion_id: "(.*)"$/\1/')"

if [ -n "$_cmp_id_a" ]; then
    _pass "completion mint: completion_id present and matches cmp-<slug>-<6hex> shape (got: $_cmp_id_a)"
else
    _fail "completion mint: no completion_id matching cmp-<slug>-<6hex> found in $_CMP_OUT_A"
fi

if [ -n "$_cmp_id_b" ]; then
    _pass "completion mint: second call also mints a shape-valid completion_id (got: $_cmp_id_b)"
else
    _fail "completion mint: no completion_id matching cmp-<slug>-<6hex> found in $_CMP_OUT_B"
fi

if [ -n "$_cmp_id_a" ] && [ -n "$_cmp_id_b" ] && [ "$_cmp_id_a" != "$_cmp_id_b" ]; then
    _pass "completion mint: two rapid calls from the same title mint DISTINCT completion_ids ($_cmp_id_a != $_cmp_id_b)"
else
    _fail "completion mint: rapid calls did not mint distinct completion_ids (a: '$_cmp_id_a', b: '$_cmp_id_b')"
fi

# ---------------------------------------------------------------------------
# (f) pln- shim regression (review finding F4, lvv-01/A): --type plan must
# still mint a plan_id via the _mint_plan_id shim over _mint_artifact_id.
# plan_id is REQUIRED/never-null per _scaffold_plan (D3), unlike the two
# optional hnd-/cmp- fields above — assert presence, not just shape.
# ---------------------------------------------------------------------------

_PLN_OUT="$_WORK_DIR/pln-a.md"
python3 "$CLI" --type plan --title "Mint Shim Test" --out "$_PLN_OUT" >/dev/null 2>&1

_pln_id="$(grep -oE '^plan_id: "pln-[a-z0-9-]+-[0-9a-f]{6}"' "$_PLN_OUT" | sed -E 's/^plan_id: "(.*)"$/\1/')"

if [ -n "$_pln_id" ]; then
    _pass "plan mint: plan_id present and matches pln-<slug>-<6hex> shape (got: $_pln_id)"
else
    _fail "plan mint: no plan_id matching pln-<slug>-<6hex> found in $_PLN_OUT"
fi

# ---------------------------------------------------------------------------
# (g) --type recovery scaffold: kind=recovery, predecessor default, recovers_session
# present, and the three distinct recovery body sections present (vs session-handoff's
# ## What Was Accomplished / ## Current State / ## Next Steps).
# ---------------------------------------------------------------------------

_RECOVERY_OUT="$_WORK_DIR/recovery-a.md"
python3 "$CLI" --type recovery --title "test recovery handoff" --out "$_RECOVERY_OUT" >/dev/null 2>&1
_recovery_exit=$?

if [ "$_recovery_exit" -eq 0 ]; then
    _pass "recovery scaffold: exit 0"
else
    _fail "recovery scaffold: non-zero exit (got: $_recovery_exit)"
fi

if [ -f "$_RECOVERY_OUT" ]; then
    _pass "recovery scaffold: file exists at supplied --out path"
else
    _fail "recovery scaffold: file NOT found at supplied --out path ('$_RECOVERY_OUT')"
fi

if grep -qE '^kind: recovery$' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: kind: recovery present"
else
    _fail "recovery scaffold: kind: recovery NOT found"
fi

if grep -qE '^predecessor: null\s+#.*crashed commit SHA or null' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: predecessor default is null with crashed-SHA hint"
else
    _fail "recovery scaffold: predecessor default/hint not found as expected"
fi

if grep -qE '^recovers_session: null' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: recovers_session field present with null default"
else
    _fail "recovery scaffold: recovers_session field NOT found"
fi

if grep -qF '## Recovery Context' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: ## Recovery Context section present"
else
    _fail "recovery scaffold: ## Recovery Context section NOT found"
fi

if grep -qF '## What Was Accomplished (by the crashed session, before it died)' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: ## What Was Accomplished (crashed session) section present"
else
    _fail "recovery scaffold: distinct crashed-session accomplishment section NOT found"
fi

if grep -qF '## In-Progress Work' "$_RECOVERY_OUT"; then
    _pass "recovery scaffold: ## In-Progress Work section present"
else
    _fail "recovery scaffold: ## In-Progress Work section NOT found"
fi

# ---------------------------------------------------------------------------
# (g2) --type recovery --recovers-session <id>: a supplied value is threaded
# through the CLI and emitted correctly quoted, including a session id that
# contains a colon (guards against naive unquoted YAML emission).
# Review: code-reviewer — regression coverage for the --recovers-session CLI
# arg (Finding 1/2): without this, a future change that forgets _yaml_quote or
# breaks colon-quoting goes uncaught.
# ---------------------------------------------------------------------------

_RECOVERY_SUPPLIED_OUT="$_WORK_DIR/recovery-b.md"
python3 "$CLI" --type recovery --title "test recovery with session" \
    --recovers-session "sess-abc123" --out "$_RECOVERY_SUPPLIED_OUT" >/dev/null 2>&1
_recovery_supplied_exit=$?

if [ "$_recovery_supplied_exit" -eq 0 ]; then
    _pass "recovery scaffold (--recovers-session): exit 0"
else
    _fail "recovery scaffold (--recovers-session): non-zero exit (got: $_recovery_supplied_exit)"
fi

if grep -qE '^recovers_session: "sess-abc123"' "$_RECOVERY_SUPPLIED_OUT"; then
    _pass "recovery scaffold (--recovers-session): supplied value threaded through and quoted"
else
    _fail "recovery scaffold (--recovers-session): supplied value NOT found or NOT quoted correctly"
fi

_RECOVERY_COLON_OUT="$_WORK_DIR/recovery-c.md"
python3 "$CLI" --type recovery --title "test recovery with colon session" \
    --recovers-session "sess-abc:123" --out "$_RECOVERY_COLON_OUT" >/dev/null 2>&1
_recovery_colon_exit=$?

if [ "$_recovery_colon_exit" -eq 0 ]; then
    _pass "recovery scaffold (--recovers-session, colon): exit 0"
else
    _fail "recovery scaffold (--recovers-session, colon): non-zero exit (got: $_recovery_colon_exit)"
fi

if grep -qE '^recovers_session: "sess-abc:123"' "$_RECOVERY_COLON_OUT"; then
    _pass "recovery scaffold (--recovers-session, colon): colon-containing value correctly double-quoted"
else
    _fail "recovery scaffold (--recovers-session, colon): colon-containing value NOT correctly quoted"
fi

# ---------------------------------------------------------------------------
# (g3) round-trip the freshly-scaffolded recovery file through the real
# handoff-schema validator (validateRecord against schemas/handoff.schema.json),
# proving it validates rather than only string-grepping for expected fields.
# Review: code-reviewer — Finding 4: a future CROSS_FIELD_RULES['handoff'] change
# that inadvertently starts rejecting kind: recovery records would not be caught
# by the grep-only assertions above.
# ---------------------------------------------------------------------------

_SCHEMA_VALIDATE_RESULT=$(node -e '
const path = require("path");
const fs = require("fs");
const schema = require(process.argv[1]);
schema.loadSchemas(process.argv[2]);
const content = fs.readFileSync(process.argv[3], "utf8");
const { frontmatter } = schema.parseFrontmatter(content);
const result = schema.validateRecord(frontmatter, "handoff");
process.stdout.write(result.ok ? "OK" : ("FAIL:" + JSON.stringify(result.errors)));
' "$SCRIPT_DIR/lib/schema.js" "$SCRIPT_DIR/../schemas" "$_RECOVERY_SUPPLIED_OUT" 2>&1)

if [ "$_SCHEMA_VALIDATE_RESULT" = "OK" ]; then
    _pass "recovery scaffold: round-trips through validateRecord against handoff.schema.json"
else
    _fail "recovery scaffold: validateRecord rejected the scaffolded record ($_SCHEMA_VALIDATE_RESULT)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf '\n--- Results: %d passed, %d failed ---\n' "$_PASS" "$_FAIL"
[ "$_FAIL" -eq 0 ]
