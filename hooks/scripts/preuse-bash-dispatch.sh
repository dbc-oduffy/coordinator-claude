#!/usr/bin/env bash
# PreToolUse(Bash) dispatcher — consolidates formerly-standalone hook scripts <!-- Review: code-reviewer — dropped hardcoded count (was 8, now 10); avoids future drift -->
# into a single shell process.
#
# Purpose: remedy (b) "reimplement the hook in the already-running shell" for the
# Windows console-flash class of overhead. On Windows each hook matcher spawns a
# new bash.exe process (visible console flash). By sourcing all check_* guards here and
# running their check_* functions in the already-running shell, 10 separate
# bash.exe spawns collapse into 1.
#
# Each folded check lives in its sibling script as a sourceable check_<name>()
# function. When sourced, those scripts only define functions (and any file-scope
# constants they need); they do NOT read stdin or execute logic at source time.
#
# Spec backlink: docs/plans/2026-06-30-pretooluse-bash-hook-dispatcher.md
#
# Contract:
#   stdin   — Claude Code PreToolUse JSON (tool_name, tool_input.command, session_id)
#   stdout  — nested hookSpecificOutput JSON on deny/advisory; NOTHING on allow
#   exit 0  — always (Claude Code reads exit code; non-zero is treated as infra error)
#
# CRLF-robustness: this file MUST stay LF-only. A \+CRLF line-continuation
# makes \ escape the CR rather than the newline, splitting statements and crashing
# the hook — which would deny ALL bash. (.gitattributes pins *.sh eol=lf.)

# ---------------------------------------------------------------------------
# BASH_VERSINFO guard — FIRST, before set flags and any bash-4-only syntax.
# Stock macOS ships /bin/bash 3.2; brew bash upgrades to 4+.
# On <4 we emit allow (NOT deny — a deny here blocks ALL bash before brew bash
# is installed) with an advisory to upgrade, then exit cleanly.
# This guard must PARSE on bash 3.2: no bash-4-only syntax above this point.
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"coordinator preuse-bash-dispatch.sh requires bash >= 4 (current: %s). All safety checks bypassed for this invocation. Upgrade via: brew install bash"}}\n' "${BASH_VERSINFO[0]:-unknown}"
  exit 0
fi

# set -uo pipefail — but explicitly NOT set -e.
# The deny-chain captures each check's exit code manually; set -e would abort
# the dispatcher on a check's nonzero return, preventing fail-closed handling.
set -uo pipefail

# ---------------------------------------------------------------------------
# Read stdin ONCE.
# timeout 2 cat is the portable idiom used by the folded scripts.
# If timeout is absent, the 2>/dev/null causes its "not found" stderr to
# disappear, the subshell exits nonzero, and || cat falls back to plain cat.
# ---------------------------------------------------------------------------
INPUT=$(timeout 2 cat 2>/dev/null || cat)
[ -z "$INPUT" ] && exit 0

# ---------------------------------------------------------------------------
# Parse tool_name, command, session_id ONCE from INPUT.
# Same jq → python3 → sed/grep fallback chain the folded scripts use.
# ---------------------------------------------------------------------------
_PARSE_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

if command -v jq &>/dev/null; then
  tool_name=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  cmd=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  sid=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
elif [ -n "$_PARSE_PY" ]; then
  tool_name=$(printf '%s' "$INPUT" | "$_PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
  cmd=$(printf '%s' "$INPUT" | "$_PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
  sid=$(printf '%s' "$INPUT" | "$_PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("session_id","")))' 2>/dev/null || true)
else
  tool_name=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  cmd=$(printf '%s' "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
  sid=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Parse cwd — used by check_offer_git_c for the tier-2 redundant-cd comparison.
# Same jq→python→empty fallback chain as sid; absent/unresolvable → empty string →
# check_offer_git_c fails open to tier 3 (deny+offer). Review: code-reviewer — F1:
# dispatcher did not forward .cwd, silently killing T2 in every production invocation.
if command -v jq &>/dev/null; then
  cwd=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
elif [ -n "$_PARSE_PY" ]; then
  cwd=$(printf '%s' "$INPUT" | "$_PARSE_PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("cwd","")))' 2>/dev/null || true)
else
  cwd=""
fi

# Non-Bash tool → nothing to check.
[ "${tool_name:-}" != "Bash" ] && exit 0

# Defense-in-depth CRLF normalization. On Windows/Git-Bash the native jq.exe emits
# its output in text mode, injecting a CR before every LF, so a multi-line command
# arrives here as `\<CR><LF>`. Each folded check_* function also strips CR at its
# own entry (that check-level strip is what preserves standalone == dispatcher
# golden-equivalence); stripping here too guarantees production coverage even if a
# future check is added without its own strip. A bare CR is never a meaningful
# shell token, so this is safe and idempotent with the per-check strips.
cmd="${cmd//$'\r'/}"

# ---------------------------------------------------------------------------
# Source all folded scripts — defines check_* functions, nothing else at
# source time. Resolved relative to this file's own directory so the dispatcher
# works regardless of the invoking cwd.
# ---------------------------------------------------------------------------
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=block-no-verify.sh
source "$_d/block-no-verify.sh"
# shellcheck source=block-destructive-git-orphan.sh
source "$_d/block-destructive-git-orphan.sh"
# shellcheck source=block-destructive-rm.sh
source "$_d/block-destructive-rm.sh"
# shellcheck source=block-destructive-git-clean.sh
source "$_d/block-destructive-git-clean.sh"
# shellcheck source=block-destructive-git-revert.sh
source "$_d/block-destructive-git-revert.sh"
# shellcheck source=block-blanket-git-add.sh
source "$_d/block-blanket-git-add.sh"
# shellcheck source=offer-git-c-over-cd.sh
source "$_d/offer-git-c-over-cd.sh"
# shellcheck source=nudge-probe-spray.sh
source "$_d/nudge-probe-spray.sh"
# shellcheck source=nudge-windows-console-popup.sh
source "$_d/nudge-windows-console-popup.sh"
# shellcheck source=validate-commit.sh
source "$_d/validate-commit.sh"

# ---------------------------------------------------------------------------
# Dispatcher crash-deny helper — used ONLY when a hard guard's subshell
# crashes (nonzero rc that is not a deny output). Fails closed so a buggy
# guard never silently permits what it was supposed to block.
# The message is dispatcher-authored; it is NOT a pass-through from the check fn.
# ---------------------------------------------------------------------------
_dispatch_crash_deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"coordinator hook dispatcher: %s guard crashed (exit %s); failing closed to avoid bypassing a safety guard. Re-run, or invoke the standalone hook to see the underlying error."}}\n' "$1" "$2"
}

# ---------------------------------------------------------------------------
# Hard deny chain — first deny wins, FAIL CLOSED on subshell crash.
#
# Invariant: check_* prints deny JSON to stdout and returns 0 on a deny;
# prints nothing and returns 0 on allow; returns nonzero ONLY on a crash
# (e.g. set -u unbound variable inside the check function). The rc != 0
# path is therefore the crash path, not the "allowed" path.
#
# Order follows the original hooks.json priority — most critical first:
#   1. no-verify          (git bypass flags)
#   2. destructive-git-orphan  (committed-work loss)
#   3. destructive-rm     (uncommitted-work loss)
#   4. destructive-git-clean  (uncommitted-clean loss)
#   5. destructive-git-revert (uncommitted-tracked-revert + unscoped stash-sweep loss)
#   6. blanket-git-add    (scoped-commit discipline)
# ---------------------------------------------------------------------------

out=$(check_no_verify "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "no-verify" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_destructive_git_orphan "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "destructive-git-orphan" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_destructive_rm "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "destructive-rm" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_destructive_git_clean "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "destructive-git-clean" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_destructive_git_revert "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "destructive-git-revert" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_blanket_git_add "$cmd" "$sid"); rc=$?
if [ "$rc" -ne 0 ]; then _dispatch_crash_deny "blanket-git-add" "$rc"; exit 0; fi
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

# ---------------------------------------------------------------------------
# Soft deny — offer-git-c (convenience guard; NOT fail-closed).
# A crash here is treated as empty/allow — it is an offer, not a safety gate.
# ---------------------------------------------------------------------------
out=$(check_offer_git_c "$cmd" "$sid" "$cwd") || out=""
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

# ---------------------------------------------------------------------------
# validate-commit — deny-capable commit-content gate, folded Phase 2.
# FAIL-OPEN (|| out=""), deliberately NOT routed through _dispatch_crash_deny:
# validate-commit.sh is fail-open on every error path standalone (a non-git-repo,
# an absent/erroring bin/ delegate, an unparseable subject → exit 0/allow) and its
# deny conditions are narrow/opt-in. Failing it CLOSED would block every commit on
# a transient delegate/infra error — a behavior change. It neutralizes the inherited
# set -uo pipefail itself (D6). Placed after offer-git-c (so the cd-prefix and
# no-verify guards win first-deny on overlapping shapes), before the advisory phase
# (it is deny-capable; its stderr warnings flow through regardless of position).
# ---------------------------------------------------------------------------
out=$(check_validate_commit "$cmd" "$sid") || out=""
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

# ---------------------------------------------------------------------------
# Advisory phase — at most ONE additionalContext emitted per invocation.
# First non-empty output wins. Crash is treated as empty (not fail-closed —
# a crash in an advisory must never block the user's intended command).
# ---------------------------------------------------------------------------
out=$(check_probe_spray "$cmd" "$sid") || out=""
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

out=$(check_windows_popup "$cmd" "$sid") || out=""
if [ -n "$out" ]; then printf '%s' "$out"; exit 0; fi

# ---------------------------------------------------------------------------
# All checks passed — allow.
# ---------------------------------------------------------------------------
exit 0
