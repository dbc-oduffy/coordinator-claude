#!/usr/bin/env bash
# Golden differential equivalence test: preuse-bash-dispatch.sh vs legacy hooks.
#
# Purpose: prove the consolidated dispatcher produces byte-identical
# {permissionDecision, permissionDecisionReason/additionalContext} to the legacy
# separate-hooks behavior for a representative corpus of command shapes.
#
# Model of "legacy" behavior: the guards fired as separate PreToolUse hooks
# in hooks.json REGISTRATION ORDER, and the first one to emit a deny won.
# Registration order (deny-relevant):
#   1. block-no-verify.sh
#   2. block-destructive-git-orphan.sh
#   3. block-destructive-rm.sh
#   4. block-blanket-git-add.sh
#   5. offer-git-c-over-cd.sh
#   6. nudge-probe-spray.sh        (advisory)
#   7. nudge-windows-console-popup.sh (advisory)
#
# Note: block-off-daily-branch.sh retired 2026-07-05 (strang-04). Branch ensure
# is now handled actively by the SessionStart session-ensure-branch.sh hook.
#
# This test asserts EQUIVALENCE, not absolute correctness. Because every guard's
# decision logic lives in a shared check_<name>() function sourced by BOTH the
# standalone (legacy) main-guard AND the dispatcher, any fix landed at the check
# level appears identically on both paths — so equivalence holds regardless of the
# verdict. The 2026-06-30 CRLF-continuation hardening (a CR-strip at the top of each
# check function) is exactly this shape: the `rm -rf` / `git reset --hard` split
# across a CRLF backslash-continuation that formerly ALLOWed in BOTH now DENIES in
# BOTH. The CRLF cases below lock in that the dispatcher did NOT diverge from legacy
# on these shapes — they remain EQUAL after the fix.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/../scripts"
DISPATCHER="$HOOKS_DIR/preuse-bash-dispatch.sh"
META_REPO="${HOME}/.claude"

PASS=0
FAIL=0

# Unique prefix for every session_id used in this run, so prior aborted test
# runs do not leave stale probe-spray state files in TMPDIR that contaminate
# this run's counts. The PID + epoch makes collisions essentially impossible.
RUN_ID="golden-$$-$(date +%s 2>/dev/null || echo 0)"

# Clean up any stale probe-spray state files from prior runs that used the
# same session_id pattern (defensive belt-and-suspenders alongside the unique prefix).
rm -f "${TMPDIR:-/tmp}"/coordinator-probe-spray-golden-*.times \
       "${TMPDIR:-/tmp}"/coordinator-probe-spray-golden-*.ring \
       "${TMPDIR:-/tmp}"/coordinator-probe-spray-golden-*.cool 2>/dev/null || true

# ---------------------------------------------------------------------------
# emit <cmd> [<session_id>]
# Build a PreToolUse JSON payload for a Bash tool call.
# ---------------------------------------------------------------------------
emit() {
  local cmd="$1"
  local sid="${2:-golden-test-default}"
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$cmd" --arg s "$sid" \
      '{tool_name:"Bash",tool_input:{command:$c},session_id:$s}'
  else
    local ec="${cmd//\\/\\\\}"; ec="${ec//\"/\\\"}"; ec="${ec//$'\n'/\\n}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"session_id":"%s"}\n' \
      "$ec" "$sid"
  fi
}

# ---------------------------------------------------------------------------
# legacy_decision <json> [<cwd>]
# Emulates the legacy 8-separate-hooks behavior in registration order.
# The legacy model: each script ran as a separate process, and the first to
# emit a non-empty deny/advisory stdout won.
#
# Performance note: spawning 8 bash processes per test case is prohibitively
# slow on Windows (~5s per process × 8 = 40s/case). Instead, we SOURCE the
# scripts in the same shell (they expose sourceable check_* functions) and
# call the check functions in registration order. The sourced check_* functions
# produce identical output to the standalone scripts because:
#   (a) the standalone scripts parse the same fields and call the same check_*
#       function with (cmd, sid) positional args
#   (b) the function body is identical in both execution contexts
# This is the exact same equivalence the test is proving: the dispatcher does
# the same sourcing as this helper, so any difference in output IS the proof.
#
# CWD is honoured by cd-ing before sourcing and calling so cwd-guarded checks
# (block-blanket-git-add's meta-repo inode check) fire correctly.
# ---------------------------------------------------------------------------
legacy_decision() {
  local json="$1"
  local cwd="${2:-$PWD}"

  # Parse cmd + sid from JSON using the same fallback chain the standalone scripts use.
  local _cmd _sid
  if command -v jq &>/dev/null; then
    _cmd=$(printf '%s' "$json" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
    _sid=$(printf '%s' "$json" | jq -r '.session_id // empty' 2>/dev/null || true)
  else
    _cmd=$(printf '%s' "$json" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    _sid=$(printf '%s' "$json" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  # Source all 8 scripts in a subshell so their file-scope side effects
  # (set -uo pipefail, PY=...) don't contaminate the test's shell state.
  # The subshell cd's to the target cwd so cwd-guarded checks fire correctly.
  (
    cd "$cwd"
    # shellcheck source=/dev/null
    source "$HOOKS_DIR/block-no-verify.sh"
    source "$HOOKS_DIR/block-destructive-git-orphan.sh"
    source "$HOOKS_DIR/block-destructive-rm.sh"
    source "$HOOKS_DIR/block-blanket-git-add.sh"
    source "$HOOKS_DIR/offer-git-c-over-cd.sh"
    source "$HOOKS_DIR/validate-commit.sh"
    source "$HOOKS_DIR/nudge-probe-spray.sh"
    source "$HOOKS_DIR/nudge-windows-console-popup.sh"

    # Registration order: call each check function; first non-empty output wins.
    local _out
    _out=$(check_no_verify "$_cmd" "$_sid")
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_destructive_git_orphan "$_cmd" "$_sid")
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_destructive_rm "$_cmd" "$_sid")
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_blanket_git_add "$_cmd" "$_sid")
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_offer_git_c "$_cmd" "$_sid") || _out=""
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_validate_commit "$_cmd" "$_sid") || _out=""
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_probe_spray "$_cmd" "$_sid") || _out=""
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    _out=$(check_windows_popup "$_cmd" "$_sid") || _out=""
    [[ -n "$_out" ]] && { printf '%s' "$_out"; exit 0; }
    # All checks passed — allow; return empty.
  ) 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# dispatcher_decision <json> [<cwd>]
# Pipes JSON to the consolidated dispatcher, captures output.
# ---------------------------------------------------------------------------
dispatcher_decision() {
  local json="$1"
  local cwd="${2:-$PWD}"
  cd "$cwd" && printf '%s' "$json" | bash "$DISPATCHER" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# get_decision <output> → "allow" | "deny"
# Extracts permissionDecision; defaults to "allow" on empty/missing output.
# ---------------------------------------------------------------------------
get_decision() {
  local out="$1"
  [[ -z "$out" ]] && { printf 'allow'; return; }
  if command -v jq &>/dev/null; then
    local d
    d=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null || true)
    printf '%s' "${d:-allow}"
  else
    if printf '%s' "$out" | grep -q '"permissionDecision":"deny"'; then printf 'deny'
    elif printf '%s' "$out" | grep -q '"permissionDecision":"allow"'; then printf 'allow'
    else printf 'allow'
    fi
  fi
}

# ---------------------------------------------------------------------------
# get_reason <output>
# Extracts permissionDecisionReason OR additionalContext (advisory channel).
# Returns empty string on empty/missing output.
# ---------------------------------------------------------------------------
get_reason() {
  local out="$1"
  [[ -z "$out" ]] && { printf ''; return; }
  if command -v jq &>/dev/null; then
    printf '%s' "$out" | jq -r '
      .hookSpecificOutput.permissionDecisionReason //
      .hookSpecificOutput.additionalContext //
      ""' 2>/dev/null || true
  else
    # Best-effort without jq: extract reason field only (not additionalContext)
    printf '%s' "$out" | grep -o '"permissionDecisionReason":"[^"]*"' | head -1 \
      | sed 's/"permissionDecisionReason":"//; s/"$//' || true
  fi
}

# ---------------------------------------------------------------------------
# assert_equiv <desc> <json> [<cwd>]
# Runs both legacy and dispatcher; asserts decision AND reason are byte-identical.
# ---------------------------------------------------------------------------
assert_equiv() {
  local desc="$1"
  local json="$2"
  local cwd="${3:-$PWD}"

  local leg_out disp_out
  leg_out=$(legacy_decision "$json" "$cwd")
  disp_out=$(dispatcher_decision "$json" "$cwd")

  local leg_dec disp_dec leg_reason disp_reason
  leg_dec=$(get_decision "$leg_out")
  disp_dec=$(get_decision "$disp_out")
  leg_reason=$(get_reason "$leg_out")
  disp_reason=$(get_reason "$disp_out")

  if [[ "$leg_dec" == "$disp_dec" && "$leg_reason" == "$disp_reason" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL: %s\n' "$desc"
    if [[ "$leg_dec" != "$disp_dec" ]]; then
      printf '  decision: legacy=%s  dispatcher=%s\n' "$leg_dec" "$disp_dec"
    fi
    if [[ "$leg_reason" != "$disp_reason" ]]; then
      printf '  reason differs:\n'
      printf '    legacy[0:150]:     %s\n' "$(printf '%s' "$leg_reason" | head -c 150)"
      printf '    dispatcher[0:150]: %s\n' "$(printf '%s' "$disp_reason" | head -c 150)"
    fi
  fi
}

# ---------------------------------------------------------------------------
# assert_equiv_true_process <desc> <json> [<cwd>]
# TRUE standalone-process differential — the Staff Engineer Finding 1.
#
# The sourced emulation in assert_equiv runs check_validate_commit under the
# test's own `set -uo pipefail` (line ~32 of this file), so it CANNOT detect
# an env divergence between the dispatcher and the REAL standalone hook
# process. This helper compares:
#   "legacy"     → bash "$HOOKS_DIR/validate-commit.sh"  (own process, own set-flags)
#   "dispatcher" → bash "$DISPATCHER"
# Both run as separate processes, inheriting any exported env vars from the
# caller (e.g., COORDINATOR_SCOPE_STRICT=1). The main-guard in
# validate-commit.sh reads stdin just like the dispatcher does, so both see
# the same JSON input. A divergence here would indicate that the
# `set +u +o pipefail` neutralization inside check_validate_commit is
# load-bearing — exactly what this test is designed to catch.
# ---------------------------------------------------------------------------
assert_equiv_true_process() {
  local desc="$1"
  local json="$2"
  local cwd="${3:-$PWD}"

  local proc_out disp_out
  proc_out=$(cd "$cwd" && printf '%s' "$json" | bash "$HOOKS_DIR/validate-commit.sh" 2>/dev/null || true)
  disp_out=$(dispatcher_decision "$json" "$cwd")

  local proc_dec disp_dec proc_reason disp_reason
  proc_dec=$(get_decision "$proc_out")
  disp_dec=$(get_decision "$disp_out")
  proc_reason=$(get_reason "$proc_out")
  disp_reason=$(get_reason "$disp_out")

  if [[ "$proc_dec" == "$disp_dec" && "$proc_reason" == "$disp_reason" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    printf 'FAIL: %s\n' "$desc"
    if [[ "$proc_dec" != "$disp_dec" ]]; then
      printf '  decision: standalone=%s  dispatcher=%s\n' "$proc_dec" "$disp_dec"
    fi
    if [[ "$proc_reason" != "$disp_reason" ]]; then
      printf '  reason differs:\n'
      printf '    standalone[0:150]:   %s\n' "$(printf '%s' "$proc_reason" | head -c 150)"
      printf '    dispatcher[0:150]:   %s\n' "$(printf '%s' "$disp_reason" | head -c 150)"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Build a real temp repo and sibling repo for rm / orphan / branch tests.
# The meta-repo (META_REPO) is the real ~/.claude repo, used for blanket-add
# tests that require the cwd-guard to fire.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
SIBLING=$(mktemp -d)
VC_CLAUDE_REPO=$(mktemp -d)
VC_SCOPE_REPO=$(mktemp -d)
VC_FM_REPO=$(mktemp -d)
VC_LEAK_REPO=$(mktemp -d)
VC_CLEAN_REPO=$(mktemp -d)
VC_SCOPE_SID="golden-vc-scope-$$"
trap 'rm -rf "$TMP" "$SIBLING" "$VC_CLAUDE_REPO" "$VC_SCOPE_REPO" "$VC_FM_REPO" "$VC_LEAK_REPO" "$VC_CLEAN_REPO"' EXIT

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

# --- TMP repo setup: 5 commits (gives HEAD~3 room), untracked content, clean dir ---
cd "$TMP"
git init -q -b main
git config user.email t@t.t
git config user.name T
git config commit.gpgsign false
printf 'r1\n' > file1.txt && git add file1.txt && git commit -q -m "r1"
printf 'r2\n' > file2.txt && git add file2.txt && git commit -q -m "r2"
printf 'r3\n' > file3.txt && git add file3.txt && git commit -q -m "r3"
printf 'r4\n' > file4.txt && git add file4.txt && git commit -q -m "r4"
printf 'r5\n' > file5.txt && git add file5.txt && git commit -q -m "r5"
# Untracked content for destructive-rm deny tests
mkdir workdir && printf 'wip\n' > workdir/wip.txt
# Clean committed dir (for allow baseline)
mkdir cleandir && printf 'clean\n' > cleandir/clean.txt
git add cleandir && git commit -q -m "cleandir"

# --- SIBLING repo: 2 commits ahead of initial state, plus untracked content ---
cd "$SIBLING"
git init -q -b main
git config user.email t@t.t
git config user.name T
git config commit.gpgsign false
mkdir sibdir && printf 'content\n' > sibdir/a.txt
git add sibdir && git commit -q -m "sibling-init"
printf 'sibling-r2\n' > sibdir/b.txt && git add sibdir/b.txt && git commit -q -m "sibling-r2"
# Untracked dir in sibling for cross-repo rm test
mkdir sibwip && printf 'wip\n' > sibwip/x.txt

# Return to TMP as default cwd for most tests
cd "$TMP"

# ============================================================================
# validate-commit fixture repos (one per deny point; isolated staged state)
# ============================================================================

# ---- Fixture 1: oversized CLAUDE.md staged (> 40000 chars) ----
(
  cd "$VC_CLAUDE_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  # awk is popup-safe (not a console-subsystem process on Windows)
  awk 'BEGIN{for(i=0;i<41001;i++) printf "A"; print ""}' > CLAUDE.md
  git add CLAUDE.md
)

# ---- Fixture 2: SCOPE_STRICT foreign file staged ----
# Session dir: started_at = 2050 (far future) so foreign.txt mtime (~now, 2026)
# is below started_at_epoch; cs_compute_scope mtime-fallback does NOT pull
# foreign.txt into MY_SCOPE. touched.txt lists only "other.txt".
(
  cd "$VC_SCOPE_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  printf 'foreign content\n' > foreign.txt && git add foreign.txt
  mkdir -p ".git/coordinator-sessions/${VC_SCOPE_SID}"
  printf '2050-01-01T00:00:00Z\n' > ".git/coordinator-sessions/${VC_SCOPE_SID}/started_at"
  printf 'other.txt\n' > ".git/coordinator-sessions/${VC_SCOPE_SID}/touched.txt"
)

# ---- Fixture 3: FRONTMATTER_STRICT staged docs/plans file ----
# docs/plans/x.md has `status: active` in its staged diff; commit subject
# "initial" contains no frontmatter key or lifecycle verb → deny fires.
(
  cd "$VC_FM_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  mkdir -p docs/plans
  printf -- '---\nstatus: active\n---\n# Plan\n' > docs/plans/x.md
  git add docs/plans/x.md
)

# ---- Fixture 4: machine-path-leak staged settings.json ----
(
  cd "$VC_LEAK_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  # jq: C:\\Users\\foo in jq string literal = string C:\Users\foo
  # jq JSON output: "C:\\Users\\foo" (valid — \\ in JSON = one backslash)
  if command -v jq &>/dev/null; then
    jq -n '{"path": "C:\\Users\\foo\\something"}' > settings.json
  else
    printf '%s\n' '{"path": "C:\\Users\\foo\\something"}' > settings.json
  fi
  git add settings.json
)

# ---- Fixture 5: clean — one small normal file staged (allow baseline) ----
(
  cd "$VC_CLEAN_REPO"
  git init -q -b main
  git config user.email t@t.t && git config user.name T && git config commit.gpgsign false
  printf 'x\n' > init.txt && git add init.txt && git commit -q -m "init"
  printf 'normal content\n' > normal.txt && git add normal.txt
)

# ============================================================================
# CORPUS — hard guard DENY shapes
# For each, assert legacy_decision == dispatcher_decision on BOTH decision
# AND reason string.
# ============================================================================

# --- block-no-verify.sh (guard #1): git bypass flags ---

assert_equiv \
  "DENY: git commit --no-verify -m x [block-no-verify, guard #1]" \
  "$(emit "git commit --no-verify -m x")" \
  "$TMP"

assert_equiv \
  "DENY: git commit --no-gpg-sign -m x [block-no-verify, guard #1]" \
  "$(emit "git commit --no-gpg-sign -m x")" \
  "$TMP"

# --- block-destructive-git-orphan.sh (guard #2): commits would be orphaned ---
# TMP has 6 commits; HEAD~3 drops 3 — orphan guard fires.

assert_equiv \
  "DENY: git reset --hard HEAD~3 [block-destructive-git-orphan, guard #2, drops 3 commits]" \
  "$(emit "git reset --hard HEAD~3")" \
  "$TMP"

# --- block-destructive-rm.sh (guard #3): untracked content would be lost ---
# workdir/ has untracked content; rm -rf would lose it irreversibly.

assert_equiv \
  "DENY: rm -rf workdir [block-destructive-rm, guard #3, untracked content]" \
  "$(emit "rm -rf workdir")" \
  "$TMP"

# --- block-blanket-git-add.sh (guard #4): blanket add in the meta-repo ---
# CWD must be ~/.claude (the meta-repo) for the cwd-guard to activate.

assert_equiv \
  "DENY: git add -A [block-blanket-git-add, guard #4, meta-repo cwd]" \
  "$(emit "git add -A" "golden-blanket-A-sid")" \
  "$META_REPO"

assert_equiv \
  "DENY: git add --all [block-blanket-git-add, guard #4, meta-repo cwd]" \
  "$(emit "git add --all" "golden-blanket-all-sid")" \
  "$META_REPO"

assert_equiv \
  "DENY: git add -u [block-blanket-git-add -u, guard #4, meta-repo cwd]" \
  "$(emit "git add -u" "golden-blanket-u-sid")" \
  "$META_REPO"

# --- offer-git-c-over-cd.sh (guard #5): cd-prefix redirect offer ---
# "cd /tmp && git status" triggers the offer-git-c redirect (deny with suggestion).

assert_equiv \
  "DENY(offer): cd /tmp && git status [offer-git-c, guard #5]" \
  "$(emit "cd /tmp && git status")" \
  "$TMP"

# ============================================================================
# Near-miss ALLOW shapes: commands that look like deny candidates but pass.
# ============================================================================

# git commit WITHOUT bypass flags → no deny
assert_equiv \
  "ALLOW: git commit -m x (no bypass flags)" \
  "$(emit "git commit -m x")" \
  "$TMP"

# Scoped git add with explicit paths → not a blanket add; allow even in meta-repo
assert_equiv \
  "ALLOW: git add -- README.md (scoped, not blanket; meta-repo cwd)" \
  "$(emit "git add -- README.md" "golden-scoped-add-sid")" \
  "$META_REPO"

# rm -rf of a path outside any git repo → destructive-rm guard does not fire
assert_equiv \
  "ALLOW: rm -rf /tmp/coordinator-golden-test-nonexistent (outside git scope)" \
  "$(emit "rm -rf /tmp/coordinator-golden-test-nonexistent-zzz")" \
  "$TMP"

# git log is read-only — no guard fires
assert_equiv \
  "ALLOW: git log --oneline (read-only)" \
  "$(emit "git log --oneline")" \
  "$TMP"

# git push --force-with-lease is explicitly allowed (only plain --force / -f denied)
assert_equiv \
  "ALLOW: git push --force-with-lease (orphan guard excludes this form)" \
  "$(emit "git push origin main --force-with-lease")" \
  "$TMP"

# ============================================================================
# Read-only commands
# ============================================================================

assert_equiv \
  "ALLOW: git rev-parse HEAD (read-only)" \
  "$(emit "git rev-parse HEAD")" \
  "$TMP"

assert_equiv \
  "ALLOW: git merge-base --is-ancestor a b (read-only)" \
  "$(emit "git merge-base --is-ancestor a b")" \
  "$TMP"

assert_equiv \
  "ALLOW: git status (read-only)" \
  "$(emit "git status")" \
  "$TMP"

# ============================================================================
# Cross-repo target: throwaway sibling git repo in a tempdir.
# Proves per-target resolution is consistent across both paths.
# ============================================================================

# rm -rf of the sibling's untracked dir → orphan-by-rm; destructive-rm fires
assert_equiv \
  "DENY: rm -rf SIBLING/sibwip (cross-repo target, untracked content; guard #4)" \
  "$(emit "rm -rf ${SIBLING}/sibwip")" \
  "$TMP"

# git -C SIBLING reset --hard HEAD~1 → drops 1 commit from sibling; orphan guard fires
assert_equiv \
  "DENY: git -C SIBLING reset --hard HEAD~1 (cross-repo target; guard #3)" \
  "$(emit "git -C ${SIBLING} reset --hard HEAD~1")" \
  "$TMP"

# ============================================================================
# Hatch cases: escape-hatch env vars make both legacy and dispatcher allow.
# ============================================================================

# COORDINATOR_ALLOW_RM=1: bypass the destructive-rm guard
export COORDINATOR_ALLOW_RM=1
assert_equiv \
  "ALLOW: COORDINATOR_ALLOW_RM=1 rm -rf workdir (hatch; both allow)" \
  "$(emit "rm -rf workdir" "golden-hatch-rm-sid")" \
  "$TMP"
unset COORDINATOR_ALLOW_RM

# ============================================================================
# OVERLAPPING shape: a command that two guards would BOTH deny.
# Registration order determines the winner — the SAME winner in both paths.
#
# git push --force --no-verify matches:
#   guard #1 (block-no-verify)    — fires on --no-verify
#   guard #3 (block-destructive-git-orphan) — fires on push --force
# guard #1 fires first → no-verify reason wins in both legacy AND dispatcher.
# ============================================================================

assert_equiv \
  "DENY(overlap): git push --force --no-verify — no-verify wins (guard #1 before #3)" \
  "$(emit "git push --force --no-verify origin main" "golden-overlap-sid")" \
  "$TMP"

# ============================================================================
# Advisory equivalence: nudge-probe-spray.sh (guard #7, advisory)
# Uses unique session IDs per case so probe-spray state files don't contaminate
# across test cases. A single probe-shaped command is below the nudge threshold
# (THRESHOLD=3), so both paths produce no output → equivalence confirmed.
# ============================================================================

assert_equiv \
  "ALLOW(advisory): echo probe (single below-threshold probe; no nudge yet)" \
  "$(emit "echo probe" "golden-probe-spray-sid-1")" \
  "$TMP"

# A "real work" command resets the probe streak in both paths
assert_equiv \
  "ALLOW(advisory): git log -1 (real work; probe streak reset)" \
  "$(emit "git log -1" "golden-probe-spray-sid-2")" \
  "$TMP"

# ============================================================================
# Advisory equivalence: nudge-windows-console-popup.sh (guard #8, advisory)
# On Windows (MINGW/CYGWIN/OS=Windows_NT) the advisory fires for bare console
# subprocess shapes. Both legacy and dispatcher call the same check_windows_popup()
# function, so the advisory JSON is byte-identical.
# ============================================================================

assert_equiv \
  "ALLOW(advisory): python3 -c \"print(1)\" (windows popup advisory on Windows)" \
  "$(emit "python3 -c \"print(1)\"" "golden-popup-sid-1")" \
  "$TMP"

# A command with the suppression marker should be silent in both paths (AC9)
assert_equiv \
  "ALLOW: python3 -c 'x'  # popup-intentional-last-resort (suppressed in both)" \
  "$(emit "python3 -c 'x'  # popup-intentional-last-resort" "golden-popup-sid-2")" \
  "$TMP"

assert_equiv \
  "ALLOW: git log --oneline (no popup advisory; not a console-subprocess shape)" \
  "$(emit "git log --oneline" "golden-popup-sid-3")" \
  "$TMP"

# ============================================================================
# CRLF / multi-line equivalence cases.
#
# A `rm -rf` or `git reset --hard` split across a CRLF backslash-continuation is
# the 2026-06-30 Windows evasion: jq.exe injects a CR before every LF, so the
# continuation arrives as `\<CR><LF>` and the legacy `\`+LF join missed it. The
# check-level CR-strip closes this; because the logic is shared, BOTH legacy and
# dispatcher now resolve the continuation and DENY. These cases lock in that the
# dispatcher did NOT diverge from legacy on CRLF/multi-line edge shapes — they
# remain EQUAL after the fix (now both DENY where the target holds real work).
# ============================================================================

# Case 1: rm -rf with a CRLF backslash-continuation before the target.
# After the CR-strip the `\<CR><LF>` join resolves the target (TMP/workdir, an
# untracked dir holding uncommitted work) — both scripts now DENY, equally.
CRLF_RM_CMD="$(printf 'rm -rf\\\r\n%s/workdir' "$TMP")"
assert_equiv \
  "EQUIV(CRLF fix): CRLF-continuation rm -rf — both deny (continuation now joined)" \
  "$(emit "$CRLF_RM_CMD" "golden-crlf-rm-sid")" \
  "$TMP"

# Case 2: git reset --hard with a plain LF backslash-continuation, targeting HEAD
# (0 commits dropped). The orphan guard joins \<LF> continuations, evaluates
# `git reset --hard HEAD` → safe (no commits lost) → both allow.
# This locks in that the join behavior is consistent between legacy and dispatcher.
MULTILINE_RESET="$(printf 'git reset \\\n--hard HEAD')"
assert_equiv \
  "EQUIV(multi-line): git reset \\<LF>--hard HEAD (safe target; join consistent)" \
  "$(emit "$MULTILINE_RESET" "golden-multiline-reset-sid")" \
  "$TMP"

# Case 3: git reset --hard with a CRLF backslash-continuation, targeting HEAD~3
# (3 commits dropped). After the CR-strip the \<CR><LF> join resolves the target
# (HEAD~3 — drops commits from TMP which has 6 commits) → orphan guard fires →
# both legacy AND dispatcher DENY, equally.
# Review: code-reviewer F2 — lock in orphan-guard CRLF divergence detection.
CRLF_RESET_CMD="$(printf 'git reset --hard\\\r\nHEAD~3')"
assert_equiv \
  "EQUIV(CRLF fix): CRLF-continuation git reset --hard HEAD~3 — both deny (orphan guard)" \
  "$(emit "$CRLF_RESET_CMD" "golden-crlf-reset-sid")" \
  "$TMP"

# ============================================================================
# A.1 — validate-commit SOURCED EMULATION CORPUS (assert_equiv)
# Each case runs both legacy_decision (extended to source validate-commit) and
# dispatcher_decision and asserts byte-identical {decision, reason}.
# ============================================================================

# A.1.1 — CLAUDEMD deny: oversized CLAUDE.md staged, plain git commit.
assert_equiv \
  "A.1.1 DENY(vc): CLAUDEMD > 40K chars staged [validate-commit deny]" \
  "$(emit "git commit -m x" "golden-vc-claude-sid")" \
  "$VC_CLAUDE_REPO"

# A.1.2 — SCOPE_STRICT deny: foreign file staged, session dir lists only "other.txt".
# Use export+unset (not a subshell) so PASS/FAIL propagate to the parent shell.
export COORDINATOR_SCOPE_STRICT=1
assert_equiv \
  "A.1.2 DENY(vc): SCOPE_STRICT — foreign file not in touched.txt [validate-commit deny]" \
  "$(emit "git commit -m x" "$VC_SCOPE_SID")" \
  "$VC_SCOPE_REPO"
unset COORDINATOR_SCOPE_STRICT

# A.1.3 — FRONTMATTER_STRICT deny: docs/plans/x.md with status: line staged;
# commit subject "initial" lacks the required frontmatter key or lifecycle verb.
export COORDINATOR_FRONTMATTER_STRICT=1
assert_equiv \
  "A.1.3 DENY(vc): FRONTMATTER_STRICT — docs/plans mutation, subject lacks lifecycle verb [validate-commit deny]" \
  "$(emit "git commit -m initial")" \
  "$VC_FM_REPO"
unset COORDINATOR_FRONTMATTER_STRICT

# A.1.4 — MACHINE-PATH-LEAK deny: settings.json with C:\Users\ path staged.
assert_equiv \
  "A.1.4 DENY(vc): MACHINE-PATH-LEAK — settings.json with machine path [validate-commit deny]" \
  "$(emit "git commit -m x")" \
  "$VC_LEAK_REPO"

# A.1.5 — CLEAN allow: one small staged file, no violations.
assert_equiv \
  "A.1.5 ALLOW(vc): clean staged file, no validate-commit violations [both allow]" \
  "$(emit "git commit -m normal")" \
  "$VC_CLEAN_REPO"

# A.1.6 — OVERLAP: no-verify wins over CLAUDEMD deny.
# git commit --no-verify -m x with oversized CLAUDE.md staged: guard #1
# (block-no-verify) fires BEFORE validate-commit (#7). Both paths agree on
# the no-verify deny reason; validate-commit is never reached.
assert_equiv \
  "A.1.6 DENY(overlap): --no-verify wins over CLAUDEMD (guard #1 before validate-commit)" \
  "$(emit "git commit --no-verify -m x" "golden-vc-overlap-nv-sid")" \
  "$VC_CLAUDE_REPO"

# A.1.7 — OVERLAP: offer-git-c wins over CLAUDEMD deny.
# "cd /x && git commit -m x" triggers the cd-prefix offer (guard #6, offer-git-c)
# before validate-commit (#7). Both paths agree on the offer-git-c reason.
assert_equiv \
  "A.1.7 DENY(overlap): cd-prefix offer-git-c wins over CLAUDEMD (guard #6 before validate-commit)" \
  "$(emit "cd /x && git commit -m x" "golden-vc-overlap-cd-sid")" \
  "$VC_CLAUDE_REPO"

# ============================================================================
# A.2 — TRUE STANDALONE-PROCESS DIFFERENTIAL (assert_equiv_true_process)
# Compares bash "$HOOKS_DIR/validate-commit.sh" (standalone process, its own
# set-flags, no inherited set -uo pipefail) vs bash "$DISPATCHER".
# Catches any env-isolation divergence the sourced emulation in A.1 would hide.
# ============================================================================

# A.2.1 — CLAUDEMD deny (true process)
assert_equiv_true_process \
  "A.2.1 DENY(vc true-process): CLAUDEMD > 40K — standalone==dispatcher" \
  "$(emit "git commit -m x" "golden-vc-tp-claude-sid")" \
  "$VC_CLAUDE_REPO"

# A.2.2 — SCOPE_STRICT deny (true process): export+unset for PASS/FAIL propagation.
export COORDINATOR_SCOPE_STRICT=1
assert_equiv_true_process \
  "A.2.2 DENY(vc true-process): SCOPE_STRICT — standalone==dispatcher" \
  "$(emit "git commit -m x" "$VC_SCOPE_SID")" \
  "$VC_SCOPE_REPO"
unset COORDINATOR_SCOPE_STRICT

# A.2.3 — FRONTMATTER_STRICT deny (true process)
export COORDINATOR_FRONTMATTER_STRICT=1
assert_equiv_true_process \
  "A.2.3 DENY(vc true-process): FRONTMATTER_STRICT — standalone==dispatcher" \
  "$(emit "git commit -m initial")" \
  "$VC_FM_REPO"
unset COORDINATOR_FRONTMATTER_STRICT

# A.2.4 — MACHINE-PATH-LEAK deny (true process)
assert_equiv_true_process \
  "A.2.4 DENY(vc true-process): MACHINE-PATH-LEAK — standalone==dispatcher" \
  "$(emit "git commit -m x")" \
  "$VC_LEAK_REPO"

# A.2.5 — CLEAN allow (true process)
assert_equiv_true_process \
  "A.2.5 ALLOW(vc true-process): clean staged file — standalone==dispatcher (both allow)" \
  "$(emit "git commit -m normal")" \
  "$VC_CLEAN_REPO"

# ============================================================================
echo "----------------------------------------"
printf 'preuse-bash-dispatch-golden: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
