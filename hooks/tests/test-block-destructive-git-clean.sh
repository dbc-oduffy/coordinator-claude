#!/usr/bin/env bash
# Test suite for block-destructive-git-clean.sh
#
# Builds a REAL throwaway git repo with untracked load-bearing deliverables
# (state/handoffs/, docs/plans/, cross-repo/inbox/) and scratch dirs
# (build/, tasks/), then drives the hook with crafted Bash-tool JSON payloads,
# asserting allow vs deny. Real repo because the hook's whole value is
# re-deriving true `git clean -nd` oracle output — a mock would test nothing.
#
# Spec backlink: coordinator/hooks/scripts/block-destructive-git-clean.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-destructive-git-clean.sh"
PASS=0
FAIL=0

emit() {
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}'
  else
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "${1//\"/\\\"}"
  fi
}

run_case() {
  # $1 = description, $2 = expected (allow|deny), $3 = command, $4 = env-prefix (optional)
  local desc="$1" expected="$2" cmd="$3" envp="${4:-}"
  local out got
  out=$(emit "$cmd" | env $envp bash "$HOOK" 2>/dev/null || true)
  got="allow"
  echo "$out" | grep -q '"permissionDecision":"deny"' && got="deny"
  if [[ "$got" == "$expected" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $desc (expected $expected, got $got)"
    [[ -n "$out" ]] && echo "      out: $(echo "$out" | head -c 200)"
  fi
}

# ---------------------------------------------------------------------------
# Build a real temp repo + out-of-repo scratch.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
SCRATCH=$(mktemp -d)          # deliberately NOT a git repo
trap 'rm -rf "$TMP" "$SCRATCH"' EXIT
cd "$TMP"

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
git init -q -b main
git config user.email t@t.t
git config user.name t
git config commit.gpgsign false

# Tracked committed file — makes the repo valid.
echo "tracked" > tracked.txt
# Gitignored tree — disposable, covered by -x sweeps.
echo "ignored_dir/" > .gitignore
git add tracked.txt .gitignore
git commit -q -m "c1"

# ---------------------------------------------------------------------------
# Fixtures: untracked load-bearing deliverables.
# These directories are entirely untracked so git clean -nd collapses them to
# "Would remove <dir>/" — the ancestor-direction classifier (Direction 2) must
# fire correctly for docs/ and cross-repo/ which are not named directly in the
# load-bearing regex but contain load-bearing subdirs.
# ---------------------------------------------------------------------------

# state/ — directly named in _gc_LOADBEARING_RE: (^|/)state(/|$)
mkdir -p state/handoffs
echo "session-spinoff-handoff content" > state/handoffs/session-handoff.md

# docs/ entirely untracked — "Would remove docs/" triggers Direction 2 ancestor
# check for docs/plans (a load-bearing prefix in _gc_LOADBEARING_PREFIXES).
mkdir -p docs/plans
echo "plan content" > docs/plans/my-plan.md

# docs/wiki/, docs/decisions/, docs/research/ — additional load-bearing sub-prefixes
# claimed in coordinator-tripwires.md. Fixtures here let pathspec-scoped deny cases
# independently confirm each prefix is in the hook's load-bearing list (F4).
# Review: code-reviewer — missing fixtures meant a mis-spelled prefix in the hook
# would pass the ancestor-collapse test silently.
mkdir -p docs/wiki
echo "tripwire content" > docs/wiki/coordinator-tripwires.md
mkdir -p docs/decisions
echo "decision content" > docs/decisions/DR-148.md
mkdir -p docs/research
echo "research content" > docs/research/sample-research.md

# cross-repo/ entirely untracked — "Would remove cross-repo/" triggers Direction 2
# ancestor check for cross-repo/inbox (in _gc_LOADBEARING_PREFIXES).
mkdir -p cross-repo/inbox
echo "memo content" > cross-repo/inbox/memo.md

# ---------------------------------------------------------------------------
# Fixtures: untracked scratch (non-load-bearing — safe to remove).
# ---------------------------------------------------------------------------
mkdir -p build
echo "build artifact" > build/artifact.o

mkdir -p tasks
echo "scratch note" > tasks/note.txt

# ---------------------------------------------------------------------------
# Fixtures: gitignored content (disposable — also cleaned by -x sweeps).
# ---------------------------------------------------------------------------
mkdir ignored_dir
echo "junk" > ignored_dir/junk.txt

# ---------------------------------------------------------------------------
# DENY — load-bearing untracked files would be destroyed.
# ---------------------------------------------------------------------------

# git clean -fd from the repo root removes state/handoffs/ → DENY.
run_case "git clean -fd (state/handoffs untracked) denied" deny "git clean -fd"

# -x flag also removes gitignored files; load-bearing paths still present → DENY.
run_case "git clean -fdx denied" deny "git clean -fdx"

# Pathspec -- docs: docs/ is entirely untracked; git collapses to "Would remove
# docs/" which is an ancestor of docs/plans (Direction 2 check) → DENY.
run_case "git clean -fd -- docs (ancestor-collapse to docs/plans) denied" deny "git clean -fd -- docs"

# Pathspec -- cross-repo: same ancestor-collapse for cross-repo/inbox → DENY.
run_case "git clean -fd -- cross-repo (ancestor-collapse) denied" deny "git clean -fd -- cross-repo"

# Pathspec -- docs/wiki: directly targets a load-bearing sub-prefix → DENY.
# Independently confirms docs/wiki is in the hook's load-bearing list (F4).
# Review: code-reviewer — ancestor-collapse case for docs/ did not cover sub-prefixes individually.
run_case "git clean -fd -- docs/wiki (load-bearing sub-prefix) denied" deny "git clean -fd -- docs/wiki"

# Pathspec -- docs/decisions: directly targets a load-bearing sub-prefix → DENY.
run_case "git clean -fd -- docs/decisions (load-bearing sub-prefix) denied" deny "git clean -fd -- docs/decisions"

# Pathspec -- docs/research: directly targets a load-bearing sub-prefix → DENY.
run_case "git clean -fd -- docs/research (load-bearing sub-prefix) denied" deny "git clean -fd -- docs/research"

# Shell-invoker broad fallback: bash -c 'git clean -fd' — the single-quoted
# payload's git clean is real; hook detects via shell-invoker regex → DENY.
# Single-quoted inner command: no JSON escaping needed; jq --arg handles it.
run_case "bash -c 'git clean -fd' denied" deny "bash -c 'git clean -fd'"

# Non-C locale: hook must force LC_ALL=C for the oracle internally; the oracle
# output stays English so "Would remove" is still parsed → DENY.
run_case "non-C locale git clean -fd denied (AC9 locale-pinning)" deny "git clean -fd" \
  "LANG=fr_FR.UTF-8 LC_ALL=fr_FR.UTF-8"

# Adversarial bypass probes (AC10 counterpart): these must all still DENY.

# Quoted verb: single-quoted 'git' is stripped by probe normalization → matches.
run_case "'git' clean -fd (quoted verb adversarial) denied" deny "'git' clean -fd"

# env-prefix with VAR=val: firstword is 'env', wrapper class fires → DENY.
run_case "env X=1 git clean -fd (env-prefix adversarial) denied" deny "env X=1 git clean -fd"

# Multi-segment: the second segment is a real git clean → DENY.
run_case "echo hi && git clean -fd (multi-segment adversarial) denied" deny "echo hi && git clean -fd"

# eval wrapping: eval is a shell-invoker; broad scan for 'git ... clean' fires → DENY.
run_case "eval 'git clean -fd' denied" deny "eval 'git clean -fd'"

# Execution wrapper class: sudo before git clean → wrapper detection → DENY.
run_case "sudo git clean -fd denied" deny "sudo git clean -fd"

# git -C <tmprepo> clean -fd run from OUTSIDE the repo (mirrors -C flag).
# Hook's oracle receives -C $TMP, scopes to the real repo, sees load-bearing → DENY.
gitc_out=$(emit "git -C $TMP clean -fd" | (cd "$SCRATCH" && bash "$HOOK") 2>/dev/null || true)
if echo "$gitc_out" | grep -q '"permissionDecision":"deny"'; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: git -C <tmprepo> clean -fd from outside repo (expected deny, got allow)"
  [[ -n "$gitc_out" ]] && echo "      out: $(echo "$gitc_out" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# ALLOW — safe operations: dry-run, scratch-only pathspecs, override, etc.
# ---------------------------------------------------------------------------

# Dry-run via -n: deletes nothing — hook short-circuits before oracle → ALLOW.
run_case "git clean -nd (dry-run -n flag) allowed" allow "git clean -nd"

# Dry-run via --dry-run flag — same short-circuit → ALLOW.
run_case "git clean --dry-run -fd allowed" allow "git clean --dry-run -fd"

# Dry-run bundled as -fdn — n anywhere in a bundled flag set → ALLOW.
run_case "git clean -fdn (bundled dry-run) allowed" allow "git clean -fdn"

# Scratch-only pathspec: build/ has no load-bearing content → ALLOW.
run_case "git clean -fd -- build (scratch only) allowed" allow "git clean -fd -- build"

# Multi-scratch pathspec: build/ and tasks/ are both scratch → ALLOW.
run_case "git clean -fd -- build tasks (scratch only) allowed" allow "git clean -fd -- build tasks"

# Override env var: COORDINATOR_OVERRIDE_GIT_CLEAN=1 bypasses guard before oracle.
run_case "git clean -fd with COORDINATOR_OVERRIDE_GIT_CLEAN=1 allowed" allow \
  "git clean -fd" "COORDINATOR_OVERRIDE_GIT_CLEAN=1"

# Paired DENY baseline (F2): proves git clean -fd -- state (without -e exclusion)
# fires the guard — makes the -e mirror test self-contained and exposes any
# pathspec-specific processing bug in the hook.
# Review: code-reviewer — without this, a bug where -- <pathspec> cleared the
# load-bearing match would pass silently.
run_case "git clean -fd -- state (scoped to load-bearing dir) denied" deny "git clean -fd -- state"

# -e exclude mirror (AC8): -e state/handoffs excludes the load-bearing path;
# oracle scoped to -- state sees nothing remaining → ALLOW.
# (state/ only contains state/handoffs/ which is excluded by -e state/handoffs.)
run_case "git clean -e state/handoffs -fd -- state (-e exclude mirror) allowed" \
  allow "git clean -e state/handoffs -fd -- state"

# Non-clean command: fast-bail on missing 'clean' keyword → ALLOW.
run_case "git status (non-clean command) allowed" allow "git status"

# Non-git command: fast-bail on missing 'git' keyword → ALLOW.
run_case "ls (non-git command) allowed" allow "ls"

# ---------------------------------------------------------------------------
# FALSE-POSITIVE regression guard (BUG 4 fix: anchor ^). These MUST ALLOW.
# Root cause: the unanchored \bgit matched mid-string after `echo`/`grep`/etc.
# Fixed by _gc_CLEAN_CMD_RE anchoring the precise check to command position.
# Re-adding these as a test regression guard prevents the anchor from being
# silently removed and re-opening the false-positive surface.
# ---------------------------------------------------------------------------

# git clean as a quoted arg to echo — echo is NOT a wrapper or shell-invoker;
# anchored regex requires git at command position; echo does not match → ALLOW.
run_case "echo 'git clean -fd' (git clean as echo arg) allowed" allow \
  "echo 'git clean -fd'"

# git clean as a grep pattern — grep is not in the wrapper/invoker class;
# anchored regex sees grep at command position, not git → ALLOW.
run_case "grep git clean file (git clean as grep args) allowed" allow \
  "grep 'git clean' file"

# printf with git clean in format string — printf is not a wrapper/invoker → ALLOW.
run_case "printf 'git clean command' (git clean as printf arg) allowed" allow \
  "printf 'git clean command'"

# echo with a longer mention: a human-readable note containing 'git clean' → ALLOW.
run_case "echo reminder about git clean (mid-string mention) allowed" allow \
  "echo 'remember to run git clean before merging'"

# Outside any git repo: oracle fails non-zero (not a git repo) → hook allows
# (nothing to lose — out-of-scope by definition).
outside_out=$(emit "git clean -fd" | (cd "$SCRATCH" && bash "$HOOK") 2>/dev/null || true)
if echo "$outside_out" | grep -q '"permissionDecision":"deny"'; then
  FAIL=$((FAIL + 1))
  echo "FAIL: git clean -fd outside any git repo (expected allow, got deny)"
  [[ -n "$outside_out" ]] && echo "      out: $(echo "$outside_out" | head -c 200)"
else
  PASS=$((PASS + 1))
fi

# Subdir-cwd (AC8): hook cwd is build/ (scratch only); oracle runs git clean -nd
# from that subdirectory and only sees build/artifact.o — no load-bearing paths
# visible from this scope. Does NOT flag root state/handoffs → ALLOW.
subdir_out=$(emit "git clean -fd" | (cd "$TMP/build" && bash "$HOOK") 2>/dev/null || true)
if echo "$subdir_out" | grep -q '"permissionDecision":"deny"'; then
  FAIL=$((FAIL + 1))
  echo "FAIL: subdir-cwd git clean -fd from build/ (expected allow, got deny)"
  [[ -n "$subdir_out" ]] && echo "      out: $(echo "$subdir_out" | head -c 200)"
else
  PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# bash 3.2 fail-open regression (2026-07-10): "${_gc_timeout_prefix[@]}" on an
# EMPTY array under `set -u` is a fatal "unbound variable" on bash < 4.4
# (stock macOS /bin/bash 3.2) — the array is empty whenever the `timeout`
# binary is absent (stock macOS BSD userland has none). This aborts the hook
# mid-run with no deny JSON emitted — silently ALLOWING a destructive
# `git clean`. Runs the hook under /bin/bash directly (not the test suite's
# own $BASH) from the repo root ($TMP, with state/handoffs/ untracked) to
# reproduce the exact 3.2 execution path. Skips cleanly when /bin/bash is
# absent or is itself >=4.
# ---------------------------------------------------------------------------
if [[ -x /bin/bash ]]; then
  BASH32_MAJOR=$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 99)
  if [[ "$BASH32_MAJOR" -lt 4 ]]; then
    OUT32=$(emit "git clean -fd" | (cd "$TMP" && /bin/bash "$HOOK") 2>/dev/null || true)
    GOT32="allow"
    echo "$OUT32" | grep -q '"permissionDecision":"deny"' && GOT32="deny"
    if [[ "$GOT32" == "deny" ]]; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      echo "FAIL: bash 3.2 (/bin/bash) git clean -fd must DENY, not fail-open (got $GOT32)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-destructive-git-clean: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
