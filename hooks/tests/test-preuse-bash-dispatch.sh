#!/usr/bin/env bash
# Test suite: hooks/scripts/preuse-bash-dispatch.sh — unified PreToolUse(Bash) dispatcher.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md
# Exercises AC2, AC3–AC6, AC8–AC10, AC12–AC15 from that plan.
#
# Self-contained: builds throwaway git repos; never modifies any live repo or the
# meta-repo working tree. Run from the repo root or from this directory —
# paths resolve via BASH_SOURCE so neither matters.
#
# Pass/fail idiom follows test-block-destructive-rm.sh (same assertion style):
#   PASS/FAIL counters, "N passed, M failed" summary, exit 1 on any failure.
#
# Exit codes: 0 all passed, 1 one or more failed.

set -uo pipefail

# ---------------------------------------------------------------------------
# Path resolution — BASH_SOURCE-rooted so the test is cwd-independent.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCHER="$SCRIPT_DIR/../scripts/preuse-bash-dispatch.sh"
SCRIPTS_DIR="$SCRIPT_DIR/../scripts"
HOOKS_JSON="$SCRIPT_DIR/../hooks.json"
# REPO_ROOT = ~/.claude (the meta-repo root). block-blanket-git-add.sh's cwd
# guard (SC-DR-014) is hardcoded to compare against ${HOME}/.claude (not a
# path derived from this test file's location) — see its own source comment
# "Resolve the git root of the current working directory. If it equals
# $HOME/.claude...". Post-W4.2 relocation (coordinator source moved to the
# DoE-claude clone), a fixed "N levels up from tests/" no longer lands on
# ~/.claude, so this test must resolve REPO_ROOT the same way the guard
# itself does — directly against $HOME/.claude — rather than via BASH_SOURCE
# ancestry math that assumed the old ~/.claude/plugins/coordinator-claude/...
# layout. This does not execute any git write in ~/.claude: run_disp() only
# pipes a JSON tool_input to the dispatcher/guard simulation and captures its
# allow/deny decision — the underlying `git add -A` command is never actually
# run, so exercising this cwd is safe against the live meta-repo working tree.
REPO_ROOT="$(cd "${HOME}/.claude" && pwd)"

if [[ ! -f "$DISPATCHER" ]]; then
  echo "FATAL: dispatcher not found: $DISPATCHER" >&2; exit 1
fi
if [[ ! -f "$HOOKS_JSON" ]]; then
  echo "FATAL: hooks.json not found: $HOOKS_JSON" >&2; exit 1
fi

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# emit <command> [session_id]
# Produce a PreToolUse JSON payload for the given Bash command.
# ---------------------------------------------------------------------------
emit() {
  local cmd="$1" sid="${2:-test-$$-${RANDOM}}"
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$cmd" --arg s "$sid" '{tool_name:"Bash",tool_input:{command:$c},session_id:$s}'
  else
    local ce="${cmd//\\/\\\\}"; ce="${ce//\"/\\\"}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"session_id":"%s"}' "$ce" "$sid"
  fi
}

# ---------------------------------------------------------------------------
# decision_of <output>
# Extract permissionDecision from dispatcher stdout.
# Empty output means "allow" (silent pass-through).
# ---------------------------------------------------------------------------
decision_of() {
  local out="$1"
  [[ -z "$out" ]] && { echo "allow"; return 0; }
  if command -v python3 &>/dev/null; then
    printf '%s' "$out" | python3 -c '
import json,sys
try:
  d=json.load(sys.stdin)
  print(d.get("hookSpecificOutput",{}).get("permissionDecision","allow"))
except Exception:
  print("allow")
' 2>/dev/null || echo "allow"
  elif command -v jq &>/dev/null; then
    printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "allow"' 2>/dev/null || echo "allow"
  else
    local dec
    dec=$(printf '%s' "$out" | grep -o '"permissionDecision":"[^"]*"' | head -1 | sed 's/.*":"//; s/".*//')
    echo "${dec:-allow}"
  fi
}

# ---------------------------------------------------------------------------
# reason_of <output>
# Extract permissionDecisionReason (JSON-decoded) from dispatcher stdout.
# Falls back to raw grep so ASCII-only patterns remain matchable without jq.
# ---------------------------------------------------------------------------
reason_of() {
  local out="$1"
  [[ -z "$out" ]] && { echo ""; return 0; }
  if command -v jq &>/dev/null; then
    printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null || echo ""
  else
    # Raw search — sufficient for ASCII override-hint tokens (COORDINATOR_ALLOW_RM etc.)
    printf '%s' "$out" | grep -o '"permissionDecisionReason":"[^"]*"' | head -1 \
      | sed 's/.*":"//; s/".*//' || echo ""
  fi
}

# ---------------------------------------------------------------------------
# pass_fail <description> <ok:0|1> [detail]
# ---------------------------------------------------------------------------
pass_fail() {
  local desc="$1" ok="$2" detail="${3:-}"
  if [[ "$ok" == "1" ]]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc"
    [[ -n "$detail" ]] && echo "      $detail"
  fi
}

# ---------------------------------------------------------------------------
# run_disp <cwd> <command> <session_id> [env_prefix]
# Pipe command JSON to the dispatcher, run from given cwd.
# env_prefix is a single "VAR=val" string passed to env(1).
# ---------------------------------------------------------------------------
run_disp() {
  local fromdir="$1" cmd="$2" sid="$3" envp="${4:-}"
  local json
  json=$(emit "$cmd" "$sid")
  if [[ -n "$envp" ]]; then
    printf '%s' "$json" | (cd "$fromdir" && env $envp bash "$DISPATCHER" 2>/dev/null) || true
  else
    printf '%s' "$json" | (cd "$fromdir" && bash "$DISPATCHER" 2>/dev/null) || true
  fi
}

# ---------------------------------------------------------------------------
# Build a throwaway git repo used by rm, orphan, and branch tests.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Isolate from user git config (same pattern as test-block-destructive-rm.sh).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

# Init with explicit -b main (git >= 2.28); fall back to rename for older git.
git -C "$TMP" init -q -b main 2>/dev/null \
  || { git -C "$TMP" init -q; git -C "$TMP" symbolic-ref HEAD refs/heads/main 2>/dev/null || true; }
git -C "$TMP" config user.email t@t.t
git -C "$TMP" config user.name T
git -C "$TMP" config commit.gpgsign false

# c1–c4: four commits so HEAD~3 resolves for the orphan hatch test (AC15 hatch 3).
for n in 1 2 3 4; do
  echo "c$n" > "$TMP/c$n.txt"
  git -C "$TMP" add "c$n.txt" && git -C "$TMP" commit -q -m "c$n"
done

# A tracked directory (fully committed, safe to remove).
mkdir "$TMP/cleandir" && echo "tracked" > "$TMP/cleandir/file.txt"
git -C "$TMP" add cleandir/file.txt && git -C "$TMP" commit -q -m "cleandir"

# An untracked work directory — uncommitted work, rm must be denied.
mkdir "$TMP/workdir" && echo "wip" > "$TMP/workdir/new.txt"

# ---------------------------------------------------------------------------
# AC3: deny_destructive_rm
# rm -rf <untracked-dir> → permissionDecision:"deny"; reason contains "rm".
# ---------------------------------------------------------------------------
{
  out=$(run_disp "$TMP" "rm -rf workdir" "sid-ac3")
  dec=$(decision_of "$out")
  pass_fail "AC3: rm -rf untracked dir → deny" "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" \
    "got: $dec | out: $(printf '%s' "$out" | head -c 200)"

  reason=$(reason_of "$out")
  pass_fail "AC3: deny reason contains 'rm'" "$([[ "$reason" == *rm* || "$out" == *"rm"* ]] && echo 1 || echo 0)" \
    "reason: $(printf '%s' "$reason" | head -c 120)"
}

# ---------------------------------------------------------------------------
# AC-CRLF: multi-line continuation (CRLF/LF) robustness through the dispatcher.
#
# On Windows the native jq.exe emits its decode output in text mode, injecting a
# CR before every LF, so a `\<newline>` continuation reaches the hook as `\<CR><LF>`.
# The check-level CR-strip (folded into each check_* function) normalizes this so
# the backslash-continuation joins and the destructive command is SEEN — and the
# dispatcher-level strip is defense-in-depth. A multi-line destructive rm / reset
# MUST DENY through the dispatcher (the production path), in both `\`+LF and
# explicit `\`+CRLF forms. This is the regression that closes the evasion.
{
  CONT_BS='\'; CONT_NL=$'\n'; CONT_CR=$'\r'

  out=$(run_disp "$TMP" "rm -rf ${CONT_BS}${CONT_NL}  workdir" "sid-crlf-rm-lf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line rm -rf (\\+LF) untracked dir → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"

  out=$(run_disp "$TMP" "rm -rf ${CONT_BS}${CONT_CR}${CONT_NL}  workdir" "sid-crlf-rm-crlf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line rm -rf (\\+CRLF) untracked dir → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"

  out=$(run_disp "$TMP" "git reset --hard ${CONT_BS}${CONT_NL} HEAD~3" "sid-crlf-rst-lf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line git reset --hard (\\+LF) HEAD~3 → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"

  out=$(run_disp "$TMP" "git reset --hard ${CONT_BS}${CONT_CR}${CONT_NL} HEAD~3" "sid-crlf-rst-crlf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line git reset --hard (\\+CRLF) HEAD~3 → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"

  # Review: code-reviewer F1 — CRLF regression coverage for no-verify and blanket-add guards.
  # Note: off-daily-branch CRLF cases removed 2026-07-05; block-off-daily-branch.sh retired
  # (strang-04). Branch ensure is now handled by SessionStart session-ensure-branch.sh.
  out=$(run_disp "$TMP" "git commit --no-verify ${CONT_BS}${CONT_CR}${CONT_NL} -m x" "sid-crlf-noverify-crlf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line git commit --no-verify (\\+CRLF) → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"

  out=$(run_disp "$REPO_ROOT" "git add ${CONT_BS}${CONT_CR}${CONT_NL} -A" "sid-crlf-blanketadd-crlf")
  dec=$(decision_of "$out")
  pass_fail "AC-CRLF: multi-line git add -A (\\+CRLF) from meta-repo → deny" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" "got: $dec | out: $(printf '%s' "$out" | head -c 160)"
}

# ---------------------------------------------------------------------------
# AC4: deny_blanket_add
# git add -A from the meta-repo (cwd guard) → permissionDecision:"deny".
# ---------------------------------------------------------------------------
{
  out=$(run_disp "$REPO_ROOT" "git add -A" "sid-ac4")
  dec=$(decision_of "$out")
  pass_fail "AC4: git add -A from meta-repo → deny" "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" \
    "got: $dec | out: $(printf '%s' "$out" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC5: deny_no_verify
# git commit --no-verify → permissionDecision:"deny".
# ---------------------------------------------------------------------------
{
  out=$(run_disp "$TMP" "git commit --no-verify -m x" "sid-ac5")
  dec=$(decision_of "$out")
  pass_fail "AC5: git commit --no-verify → deny" "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" \
    "got: $dec | out: $(printf '%s' "$out" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC6: passthrough_readonly
# git log --oneline -5 → NO output (silent allow); dispatcher exits 0.
# ---------------------------------------------------------------------------
{
  out=$(run_disp "$TMP" "git log --oneline -5" "sid-ac6")
  pass_fail "AC6: git log → no output (allow)" "$([[ -z "$out" ]] && echo 1 || echo 0)" \
    "expected empty output, got: $(printf '%s' "$out" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC8: bash3_allow_with_advisory — source-level assertion.
#
# BASH_VERSINFO[0] cannot be overridden at runtime; testing the guard's
# live code path on a bash-4 machine would require launching a bash-3.2 binary.
# Instead, we verify the guard's CONTRACT at the SOURCE level:
#   (a) the dispatcher file contains the BASH_VERSINFO guard
#   (b) the guard emits permissionDecision:"allow" (not "deny") so a bash-<4
#       install is warned but never hard-blocked on every Bash tool call.
#   (c) the guard emits the brew upgrade advisory in the allow message.
#
# This is a documented source-grep assertion because runtime BASH_VERSINFO
# cannot be spoofed in a subshell — bash forbids assigning to BASH_VERSINFO.
# ---------------------------------------------------------------------------
{
  src="$DISPATCHER"

  # (a) Guard condition: BASH_VERSINFO[0] < 4 check is present
  grep -q 'BASH_VERSINFO\[0\]' "$src" \
    && guard_present=1 || guard_present=0
  pass_fail "AC8: BASH_VERSINFO[0] guard present in dispatcher source" "$guard_present"

  # (b) Guard's output path uses permissionDecision:"allow" (never "deny" for bash<4)
  # The guard block is the section from 'if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]' to the fi.
  # We check that "allow" appears in the relevant region and "deny" does not appear in it.
  # Method: extract the guard block by line range (first if block, before set -uo pipefail).
  guard_block=$(awk '/BASH_VERSINFO\[0\].*-lt 4/,/^fi$/' "$src" 2>/dev/null | head -10)
  guard_allows=0
  guard_no_deny=1
  if printf '%s' "$guard_block" | grep -q '"allow"'; then guard_allows=1; fi
  if printf '%s' "$guard_block" | grep -q '"deny"';  then guard_no_deny=0; fi
  pass_fail "AC8: bash<4 guard emits allow (never deny)" \
    "$([[ "$guard_allows" -eq 1 && "$guard_no_deny" -eq 1 ]] && echo 1 || echo 0)" \
    "guard_block: $(printf '%s' "$guard_block" | tr '\n' '|')"

  # (c) Guard includes brew advisory message
  grep -q 'brew install bash' "$src" \
    && brew_hint=1 || brew_hint=0
  pass_fail "AC8: bash<4 guard includes 'brew install bash' advisory" "$brew_hint"
}

# ---------------------------------------------------------------------------
# AC9: per_target_git_resolve
# Create a sibling git repo with uncommitted work. Pipe rm -rf <sibling-dir>
# to the dispatcher from a DIFFERENT cwd (TMP). The rm check must resolve
# the target's repo independently of cwd and still deny.
# ---------------------------------------------------------------------------
{
  SIBLING=$(mktemp -d)
  # Register SIBLING for cleanup (extend trap)
  trap 'rm -rf "$TMP" "$SIBLING"' EXIT

  git -C "$SIBLING" init -q -b main 2>/dev/null \
    || { git -C "$SIBLING" init -q; git -C "$SIBLING" symbolic-ref HEAD refs/heads/main 2>/dev/null || true; }
  git -C "$SIBLING" config user.email t@t.t
  git -C "$SIBLING" config user.name T
  git -C "$SIBLING" config commit.gpgsign false

  echo "init" > "$SIBLING/base.txt"
  git -C "$SIBLING" add base.txt && git -C "$SIBLING" commit -q -m "init"

  # Untracked work in the sibling repo — rm must be denied.
  mkdir "$SIBLING/sibwork" && echo "wip" > "$SIBLING/sibwork/data.txt"

  # Run dispatcher from TMP (different repo) but target is SIBLING/sibwork (absolute path).
  out=$(run_disp "$TMP" "rm -rf $SIBLING/sibwork" "sid-ac9")
  dec=$(decision_of "$out")
  pass_fail "AC9: rm -rf sibling-repo untracked dir → deny (per-target repo resolve)" \
    "$([[ "$dec" == "deny" ]] && echo 1 || echo 0)" \
    "got: $dec | out: $(printf '%s' "$out" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC10: advisory_preserved
#
# (a) Probe-spray advisory: a high-signal liveness probe (echo with the "heartbeat"
#     strong-probe lexeme, EFFECTIVE_THRESHOLD=1) should trigger an additionalContext
#     advisory (permissionDecision:"allow" + additionalContext) on the very first call.
#     Uses a unique session_id to avoid cooldown from other tests.
#     NOTE: must use a genuine strong-probe lexeme (alive/heartbeat/chan_ok/still-alive).
#     "se-flush-N" is deliberately NOT a first-call strong probe (it is a numbered marker
#     caught only at the 3-streak) — see nudge-probe-spray.sh lexeme_pat rationale.
#
# (b) Windows popup advisory: python -c '...' on Windows (MINGW/MSYS Git Bash)
#     produces a permissionDecision:"allow" + additionalContext advisory.
#     On non-Windows the check is a no-op (silent allow); both outcomes are valid
#     per the "tolerant of platform" spec note — the test records PASS in both cases.
# ---------------------------------------------------------------------------
{
  # (a) Probe spray — cross-platform
  # "echo heartbeat" matches the strong-probe lexeme classifier (heartbeat in CMD_LC),
  # so EFFECTIVE_THRESHOLD=1 and the nudge fires on the very first invocation with a
  # fresh session_id.
  SID_PROBE="sid-ac10-probe-$$-${RANDOM}"
  out=$(run_disp "$TMP" 'echo heartbeat' "$SID_PROBE")
  dec=$(decision_of "$out")
  has_ctx=0
  printf '%s' "$out" | grep -q '"additionalContext"' && has_ctx=1 || true
  pass_fail "AC10: probe-spray strong-probe → allow + additionalContext advisory" \
    "$([[ "$dec" == "allow" && "$has_ctx" -eq 1 ]] && echo 1 || echo 0)" \
    "decision=$dec has_additionalContext=$has_ctx | out: $(printf '%s' "$out" | head -c 200)"

  # (b) Windows popup advisory — platform-specific; tolerant
  SID_POPUP="sid-ac10-popup-$$-${RANDOM}"
  out=$(run_disp "$TMP" "python -c 'print(1)'" "$SID_POPUP")
  dec=$(decision_of "$out")
  has_popup_ctx=0
  printf '%s' "$out" | grep -q 'WINDOWS CONSOLE POPUP ADVISORY' && has_popup_ctx=1 || true

  uname_s=$(uname -s 2>/dev/null || echo "")
  is_windows=0
  case "$uname_s" in MINGW*|CYGWIN*|MSYS*) is_windows=1 ;; esac
  [[ "${OS:-}" == "Windows_NT" ]] && is_windows=1 || true

  if [[ "$is_windows" -eq 1 ]]; then
    pass_fail "AC10: python -c on Windows → allow + WINDOWS CONSOLE POPUP ADVISORY" \
      "$([[ "$dec" == "allow" && "$has_popup_ctx" -eq 1 ]] && echo 1 || echo 0)" \
      "decision=$dec has_popup_advisory=$has_popup_ctx | out: $(printf '%s' "$out" | head -c 200)"
  else
    # Non-Windows: popup check is silently skipped; no advisory expected.
    PASS=$((PASS+1))
    echo "  [SKIP] AC10b: non-Windows platform — popup advisory is a no-op (counted as pass)"
  fi
}

# ---------------------------------------------------------------------------
# AC12: fail_closed_on_crash
#
# Prove the dispatcher fails CLOSED when a hard-guard check function crashes.
# Mechanism:
#   1. Copy the dispatcher + all 8 hook scripts into a temp dir.
#   2. OVERWRITE the copy of block-destructive-rm.sh with a stub that defines
#      check_destructive_rm() { echo "$DEFINITELY_UNBOUND_VAR_XYZ"; }
#   3. With set -u (inherited from the dispatcher), the subshell referencing the
#      unbound var exits with non-zero rc, triggering _dispatch_crash_deny.
#   4. Pipe "rm -rf foo" to the temp-copy dispatcher and assert deny with a
#      reason mentioning the guard crashed / failing closed.
# ---------------------------------------------------------------------------
{
  FC_TMP=$(mktemp -d)
  trap 'rm -rf "$TMP" "$SIBLING" "$FC_TMP"' EXIT

  # Copy dispatcher and all 8 folded scripts into the temp dir.
  cp "$DISPATCHER" "$FC_TMP/preuse-bash-dispatch.sh"
  for s in block-no-verify.sh block-destructive-git-orphan.sh \
            block-destructive-rm.sh block-blanket-git-add.sh offer-git-c-over-cd.sh \
            nudge-probe-spray.sh nudge-windows-console-popup.sh; do
    cp "$SCRIPTS_DIR/$s" "$FC_TMP/$s"
  done

  # Overwrite block-destructive-rm.sh with the crashing stub.
  # The stub defines check_destructive_rm using an unbound variable.
  # With set -u active in the dispatcher's subshell (out=$(check_destructive_rm ...)),
  # referencing $DEFINITELY_UNBOUND_VAR_XYZ causes a non-zero exit → _dispatch_crash_deny fires.
  # Note: no main-guard needed in the stub — the dispatcher only SOURCES it (defines function).
  cat > "$FC_TMP/block-destructive-rm.sh" <<'STUB_EOF'
#!/usr/bin/env bash
# AC12 crashing stub: check_destructive_rm uses an unbound variable.
# Under set -u (inherited by the dispatcher subshell), this exits non-zero,
# triggering the dispatcher's _dispatch_crash_deny "destructive-rm" path.
check_destructive_rm() {
  echo "$DEFINITELY_UNBOUND_VAR_XYZ"
}
STUB_EOF

  FC_DISPATCHER="$FC_TMP/preuse-bash-dispatch.sh"
  fc_out=$(emit "rm -rf foo" "sid-ac12" | (cd "$TMP" && bash "$FC_DISPATCHER" 2>/dev/null) || true)
  fc_dec=$(decision_of "$fc_out")
  fc_reason=$(reason_of "$fc_out")

  pass_fail "AC12: crashing guard → fail-closed (deny)" \
    "$([[ "$fc_dec" == "deny" ]] && echo 1 || echo 0)" \
    "got decision=$fc_dec | out: $(printf '%s' "$fc_out" | head -c 200)"

  # Reason must reference the crash (the dispatcher's _dispatch_crash_deny message
  # says "crashed" and "failing closed" and names the guard "destructive-rm").
  crash_mentioned=0
  (printf '%s' "$fc_reason" | grep -qiE 'crash|failing closed|destructive-rm') && crash_mentioned=1 || true
  pass_fail "AC12: crash-deny reason mentions guard crash / failing closed" "$crash_mentioned" \
    "reason: $(printf '%s' "$fc_reason" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC13: rm_deny_offers_recovery_path + orphan_deny_has_allow_orphan
#
# rm: commit c80179a1 (2026-07-10 rm-safety hardening, design-as-offers) removed
# the COORDINATOR_ALLOW_RM=1 incantation from the deny message on purpose — the
# override still WORKS (still read at check_destructive_rm() via _RM_OVERRIDE,
# see block-destructive-rm.sh), it is just no longer advertised as the first
# reach-for. The deny now offers the recoverable `git stash push -u` path
# instead. Assert the NEW contract: the deny offers stash-push and does NOT
# advertise the literal COORDINATOR_ALLOW_RM incantation.
#
# orphan: unchanged this session — its deny reason must still name its own
# escape hatch env var, proving there is no namespace swap between
# COORDINATOR_ALLOW_RM and COORDINATOR_ALLOW_ORPHAN.
# ---------------------------------------------------------------------------
{
  # rm deny reason must offer the recoverable stash-push path...
  out=$(run_disp "$TMP" "rm -rf workdir" "sid-ac13-rm")
  reason=$(reason_of "$out")
  # Also search raw out (reason may be JSON-escaped in non-jq fallback)
  rm_hint=0
  (printf '%s' "$reason" | grep -q 'stash push') && rm_hint=1 || true
  (printf '%s' "$out"    | grep -q 'stash push') && rm_hint=1 || true
  pass_fail "AC13: rm deny reason offers 'git stash push' recovery path" "$rm_hint" \
    "reason: $(printf '%s' "$reason" | head -c 120)"

  # ...and must NOT advertise the COORDINATOR_ALLOW_RM incantation (design-as-offers,
  # c80179a1) — nor the wrong-guard's COORDINATOR_ALLOW_ORPHAN (no namespace swap).
  wrong_rm=0
  (printf '%s' "$reason" | grep -q 'COORDINATOR_ALLOW_RM') && wrong_rm=1 || true
  (printf '%s' "$out"    | grep -q 'COORDINATOR_ALLOW_RM') && wrong_rm=1 || true
  (printf '%s' "$reason" | grep -q 'COORDINATOR_ALLOW_ORPHAN') && wrong_rm=1 || true
  (printf '%s' "$out"    | grep -q 'COORDINATOR_ALLOW_ORPHAN') && wrong_rm=1 || true
  pass_fail "AC13: rm deny reason does NOT advertise COORDINATOR_ALLOW_RM or COORDINATOR_ALLOW_ORPHAN" \
    "$([[ "$wrong_rm" -eq 0 ]] && echo 1 || echo 0)" \
    "rm deny reason incorrectly references an ALLOW_* incantation"

  # orphan deny reason must contain COORDINATOR_ALLOW_ORPHAN (not COORDINATOR_ALLOW_RM)
  # git reset --hard HEAD~1 from TMP: HEAD is 5 commits (c1-c4 + cleandir),
  # HEAD~1 drops 1 commit → deny.
  out=$(run_disp "$TMP" "git reset --hard HEAD~1" "sid-ac13-orphan")
  reason=$(reason_of "$out")
  orphan_hint=0
  (printf '%s' "$reason" | grep -q 'COORDINATOR_ALLOW_ORPHAN') && orphan_hint=1 || true
  (printf '%s' "$out"    | grep -q 'COORDINATOR_ALLOW_ORPHAN') && orphan_hint=1 || true
  pass_fail "AC13: orphan deny reason contains COORDINATOR_ALLOW_ORPHAN" "$orphan_hint" \
    "reason: $(printf '%s' "$reason" | head -c 120)"

  wrong_orphan=0
  (printf '%s' "$reason" | grep -q 'COORDINATOR_ALLOW_RM') && wrong_orphan=1 || true
  (printf '%s' "$out"    | grep -q 'COORDINATOR_ALLOW_RM') && wrong_orphan=1 || true
  pass_fail "AC13: orphan deny reason does NOT contain COORDINATOR_ALLOW_RM (no namespace swap)" \
    "$([[ "$wrong_orphan" -eq 0 ]] && echo 1 || echo 0)" \
    "orphan deny reason incorrectly references COORDINATOR_ALLOW_RM"
}

# ---------------------------------------------------------------------------
# AC14: cd_prefix_tier1_rewrite
# cd /tmp && git status → TIER 1 allow + updatedInput.command rewrite (v3/v4
# offer-git-c-over-cd): a clean 2-segment `cd X && git Y` is auto-rewritten to
# `git -C X Y` and returned as permissionDecision:"allow" + updatedInput.command.
# (Prior v2 behaviour was deny+offer; v3 promoted 2-segment cases to TIER 1 allow.)
# ---------------------------------------------------------------------------
{
  out=$(run_disp "$TMP" "cd /tmp && git status" "sid-ac14")
  dec=$(decision_of "$out")
  pass_fail "AC14: cd /tmp && git status → allow (TIER 1 rewrite)" \
    "$([[ "$dec" == "allow" ]] && echo 1 || echo 0)" \
    "got: $dec | out: $(printf '%s' "$out" | head -c 200)"

  # Extract updatedInput.command — jq primary, grep fallback (mirrors reason_of pattern).
  rewritten_cmd=""
  if command -v jq &>/dev/null; then
    rewritten_cmd=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null || true)
  else
    rewritten_cmd=$(printf '%s' "$out" | grep -o '"command":"[^"]*"' | tail -1 | sed 's/.*"command":"//; s/".*//' || true)
  fi
  want_cmd="git -C /tmp status"
  pass_fail "AC14: updatedInput.command == 'git -C /tmp status'" \
    "$([[ "$rewritten_cmd" == "$want_cmd" ]] && echo 1 || echo 0)" \
    "want: $want_cmd | got: $rewritten_cmd"
}

# ---------------------------------------------------------------------------
# AC15: hatch_export_allows
#
# For each of the 7 escape hatches, export VAR=1 in the dispatcher's environment
# and pipe the command that would otherwise be denied — assert the result is ALLOW
# (empty output or permissionDecision:"allow" without the guard's deny message).
#
# Hatch commands match what the spec names; cwd is TMP for most, REPO_ROOT for
# the blanket-add hatch (which has a meta-repo cwd guard).
# ---------------------------------------------------------------------------

# Helper: assert hatch allows a command.
# $1=hatch_var, $2=var_value, $3=command, $4=cwd, $5=description
assert_hatch_allows() {
  local var="$1" val="$2" cmd="$3" fromdir="$4" desc="$5"
  local envp="${var}=${val}"
  local out
  out=$(run_disp "$fromdir" "$cmd" "sid-ac15-${var}" "$envp")
  local dec
  dec=$(decision_of "$out")
  pass_fail "AC15: $desc → allow" "$([[ "$dec" == "allow" ]] && echo 1 || echo 0)" \
    "envp=$envp got=$dec | out: $(printf '%s' "$out" | head -c 200)"
}

# Hatch 1: COORDINATOR_OVERRIDE_NO_VERIFY + git commit --no-verify
assert_hatch_allows "COORDINATOR_OVERRIDE_NO_VERIFY" "1" \
  "git commit --no-verify -m x" "$TMP" \
  "COORDINATOR_OVERRIDE_NO_VERIFY=1 + git commit --no-verify"

# Hatch 2: COORDINATOR_OVERRIDE_BRANCH + git checkout -b junk
assert_hatch_allows "COORDINATOR_OVERRIDE_BRANCH" "1" \
  "git checkout -b junk" "$TMP" \
  "COORDINATOR_OVERRIDE_BRANCH=1 + git checkout -b junk"

# Hatch 3: COORDINATOR_ALLOW_ORPHAN + git reset --hard HEAD~3
# TMP has 5 commits (c1-c4 + cleandir); HEAD~3 is valid and would be denied without hatch.
assert_hatch_allows "COORDINATOR_ALLOW_ORPHAN" "1" \
  "git reset --hard HEAD~3" "$TMP" \
  "COORDINATOR_ALLOW_ORPHAN=1 + git reset --hard HEAD~3"

# Hatch 4: COORDINATOR_ALLOW_RM + rm -rf workdir (untracked dir in TMP)
assert_hatch_allows "COORDINATOR_ALLOW_RM" "1" \
  "rm -rf workdir" "$TMP" \
  "COORDINATOR_ALLOW_RM=1 + rm -rf workdir"

# Hatch 5: COORDINATOR_OVERRIDE_BLANKET_ADD + git add -A (from meta-repo root)
assert_hatch_allows "COORDINATOR_OVERRIDE_BLANKET_ADD" "1" \
  "git add -A" "$REPO_ROOT" \
  "COORDINATOR_OVERRIDE_BLANKET_ADD=1 + git add -A (from meta-repo)"

# Hatch 6: COORDINATOR_ALLOW_CD_PREFIX + cd /tmp && git status
assert_hatch_allows "COORDINATOR_ALLOW_CD_PREFIX" "1" \
  "cd /tmp && git status" "$TMP" \
  "COORDINATOR_ALLOW_CD_PREFIX=1 + cd /tmp && git status"

# Hatch 7: COORDINATOR_PROBE_NUDGE_OFF + a genuine first-call strong-probe (echo heartbeat).
# WITHOUT the hatch this command fires the PROBE-SPRAY advisory (proven in AC10); WITH the
# hatch set, check_probe_spray returns 0 immediately (no output) — so this assertion is
# non-vacuous: it proves the hatch SUPPRESSES an advisory that would otherwise fire.
# check_windows_popup sees "echo heartbeat" which has no console-subprocess → no output.
# Result: empty output → allow, no PROBE-SPRAY DETECTED advisory.
{
  SID_HATCH7="sid-ac15-probe-off-$$-${RANDOM}"
  out=$(run_disp "$TMP" 'echo heartbeat' "$SID_HATCH7" "COORDINATOR_PROBE_NUDGE_OFF=1")
  dec=$(decision_of "$out")
  probe_nudge_absent=0
  printf '%s' "$out" | grep -q 'PROBE-SPRAY DETECTED' && probe_nudge_absent=0 || probe_nudge_absent=1
  pass_fail "AC15: COORDINATOR_PROBE_NUDGE_OFF=1 + echo heartbeat → allow (no probe advisory)" \
    "$([[ "$dec" == "allow" && "$probe_nudge_absent" -eq 1 ]] && echo 1 || echo 0)" \
    "decision=$dec probe_nudge_in_output=$(( 1 - probe_nudge_absent )) | out: $(printf '%s' "$out" | head -c 200)"
}

# ---------------------------------------------------------------------------
# AC2: registration_count
#
# Assert hooks.json has exactly 4 PreToolUse "matcher":"Bash" command entries:
#   session-heartbeat.sh, preuse-bash-dispatch.sh,
#   block-subagent-plan-body-bash-write.sh, block-reviewer-bash-outside-allowlist.sh.
# (validate-commit was folded into the dispatcher Phase 2, 2026-06-30;
#  block-subagent-plan-body-bash-write.sh (added f6343d3b, plan-body-immutability
#  enforcement, dispatch-sidecar C7) and block-reviewer-bash-outside-allowlist.sh
#  (reviewer confinement, D2) are separate load-bearing guards — neither folded
#  into the dispatcher — bringing the canonical count to 4.)
# Assert NONE of the 7 folded script basenames appear as individual Bash command entries.
# (block-off-daily-branch.sh retired 2026-07-05; strang-04.)
#
# NOTE: this assertion depends on the hooks.json dispatcher-rewire having landed.
# If it has not landed yet (the scripts are still registered individually),
# the entry count will be > 4 (well above — 8+) and this test fails — that is
# expected until the rewire lands and the suite is re-run in the verification sweep.
# All OTHER tests in this file must pass regardless of AC2 status.
# ---------------------------------------------------------------------------
{
  FOLDED_SCRIPTS=(
    "block-no-verify.sh"
    "block-destructive-git-orphan.sh"
    "block-destructive-rm.sh"
    "block-blanket-git-add.sh"
    "offer-git-c-over-cd.sh"
    "nudge-probe-spray.sh"
    "nudge-windows-console-popup.sh"
  )

  if command -v python3 &>/dev/null; then
    count=$(python3 - "$HOOKS_JSON" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
  d = json.load(f)
entries = [
  h
  for entry in d["hooks"]["PreToolUse"]
  if entry.get("matcher") == "Bash"
  for h in entry.get("hooks", [])
  if h.get("type") == "command"
]
print(len(entries))
PY
) 2>/dev/null || count="err"
  elif command -v jq &>/dev/null; then
    count=$(jq '[.hooks.PreToolUse[] | select(.matcher=="Bash") | .hooks[] | select(.type=="command")] | length' \
      "$HOOKS_JSON" 2>/dev/null) || count="err"
  else
    count="skip"
  fi

  if [[ "$count" == "skip" ]]; then
    PASS=$((PASS+1))
    echo "  [SKIP] AC2: no python3/jq available to parse hooks.json (counted as pass)"
  elif [[ "$count" == "err" ]]; then
    FAIL=$((FAIL+1))
    echo "FAIL: AC2: failed to parse hooks.json entry count"
  else
    pass_fail "AC2: PreToolUse Bash entry count == 4 (session-heartbeat + dispatcher + block-subagent-plan-body-bash-write + block-reviewer-bash-outside-allowlist)" \
      "$([[ "$count" == "4" ]] && echo 1 || echo 0)" \
      "expected 4, got $count — validate-commit folded Phase 2; block-subagent-plan-body-bash-write.sh and block-reviewer-bash-outside-allowlist.sh are separate load-bearing guards (not folded); if 8+ the Phase-1 dispatcher rewire has not landed"
  fi

  # Check that none of the 8 folded basenames appear as PreToolUse Bash command entries.
  folded_found=""
  for script in "${FOLDED_SCRIPTS[@]}"; do
    found=""
    if command -v python3 &>/dev/null; then
      found=$(python3 - "$HOOKS_JSON" "$script" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
  d = json.load(f)
needle = sys.argv[2]
for entry in d["hooks"]["PreToolUse"]:
  if entry.get("matcher") != "Bash":
    continue
  for h in entry.get("hooks", []):
    if h.get("type") == "command" and needle in h.get("command", ""):
      print("found")
      break
PY
) 2>/dev/null || true
    elif command -v jq &>/dev/null; then
      found=$(jq -r --arg s "$script" \
        '[.hooks.PreToolUse[] | select(.matcher=="Bash") | .hooks[] | select(.type=="command") | .command | select(contains($s))] | if length>0 then "found" else "" end' \
        "$HOOKS_JSON" 2>/dev/null) || true
    fi
    if [[ "$found" == "found" ]]; then
      folded_found="$folded_found $script"
    fi
  done
  pass_fail "AC2: 7 folded script basenames absent from PreToolUse Bash entries" \
    "$([[ -z "$folded_found" ]] && echo 1 || echo 0)" \
    "scripts still individually registered:$folded_found"
}

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "preuse-bash-dispatch: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
