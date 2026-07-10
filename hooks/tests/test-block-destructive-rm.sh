#!/usr/bin/env bash
# Test suite for block-destructive-rm.sh
#
# Builds a REAL throwaway git repo (committed-clean, untracked, modified,
# gitignored, and out-of-repo scratch) and drives the hook with crafted Bash-tool
# JSON payloads, asserting allow vs deny. Real repo because the hook's whole value
# is re-deriving true `git status` — a mock would test nothing.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/block-destructive-rm.sh"
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

# Clean committed file + clean committed dir.
echo "tracked" > tracked.txt
mkdir cleandir && echo "kept" > cleandir/file.txt
# Gitignored tree (the node_modules analog) — must be treated as disposable.
echo "ignored/" > .gitignore
git add tracked.txt cleandir/file.txt .gitignore
git commit -q -m "c1"

# Uncommitted work: an untracked dir + an untracked file inside a tracked dir.
mkdir workdir && echo "wip" > workdir/new.txt          # whole dir untracked
echo "more wip" > cleandir/untracked.txt               # untracked file in clean dir
# Modified tracked file (unstaged edit).
echo "edited" >> tracked.txt

# Gitignored content present on disk.
mkdir ignored && echo "junk" > ignored/junk.txt

# Out-of-repo scratch content.
echo "scratch" > "$SCRATCH/throwaway.txt"

# ---------------------------------------------------------------------------
# DENY — irrecoverable in-repo work.
# ---------------------------------------------------------------------------
run_case "rm -rf untracked dir denied" deny "rm -rf workdir"
run_case "rm -fr (bundled order) untracked dir denied" deny "rm -fr workdir"
run_case "rm --recursive untracked dir denied" deny "rm --recursive workdir"
run_case "rm -rf clean dir with untracked file inside denied" deny "rm -rf cleandir"
run_case "rm -rf .git store denied" deny "rm -rf .git"
run_case "multiple targets, one dirty -> denied" deny "rm -rf cleandir workdir"
run_case "chained: status then rm -rf untracked denied" deny "git status && rm -rf workdir"
run_case "rm -rf subshell target (recursive, unverifiable) denied" deny 'rm -rf $(echo workdir)'
run_case "rm -r on untracked file denied" deny "rm -r workdir/new.txt"
run_case "rm -rf single-quoted untracked dir denied" deny "rm -rf 'workdir'"
run_case "rm -rf double-quoted untracked dir denied" deny 'rm -rf "workdir"'
run_case "rm -rf dot-relative untracked dir denied" deny "rm -rf ./workdir"
run_case "rm -rf trailing-slash untracked dir denied" deny "rm -rf workdir/"
run_case "rm -rf .git/objects subtree denied" deny "rm -rf .git/objects"

# ---------------------------------------------------------------------------
# ALLOW — recoverable, disposable, or out of scope.
# ---------------------------------------------------------------------------
run_case "rm -rf gitignored tree allowed (git calls it disposable)" allow "rm -rf ignored"
run_case "rm -rf out-of-repo scratch allowed" allow "rm -rf $SCRATCH"
run_case "rm -rf nonexistent path allowed" allow "rm -rf does-not-exist-xyz"
run_case "single-file rm (no -r, not a dir) left alone" allow "rm tracked.txt"
run_case "git rm (staged removal, recoverable) allowed" allow "git rm tracked.txt"
run_case "git -C <path> rm (global flag before subcommand) allowed" allow "git -C $TMP rm tracked.txt"
run_case "git -c k=v rm (config flag before subcommand) allowed" allow "git -c user.x=y rm tracked.txt"
run_case "git --no-pager rm (valueless global flag) allowed" allow "git --no-pager rm tracked.txt"
run_case "git --exec-path <path> rm (space-separated value) allowed" allow "git --exec-path /opt/git rm tracked.txt"
run_case "rm -rf unresolved var (v1 skip) allowed" allow 'rm -rf $SOME_DIR'
run_case "rm -rf glob (v1 skip) allowed" allow "rm -rf build/*"
run_case "override env bypasses block" allow "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"
run_case "non-rm command allowed (fast bail)" allow "git status"
run_case "echo mentioning rm allowed" allow "echo 'how to rm files'"
run_case "grep with rm in quoted arg allowed" allow "grep \"how to rm files\" tracked.txt"
run_case "token containing rm as substring allowed (ls)" allow "ls -la some-rm-named-file"
run_case "rm in quoted grep pattern and glob token allowed" allow 'grep -rl "DESTRUCTIVE-RM\|stuff" cleandir ; ls -la *rm*'

# sudo rm must still DENY (sudo prefix is explicitly handled by Part B).
run_case "sudo rm -rf untracked dir denied" deny "sudo rm -rf workdir"

# ---------------------------------------------------------------------------
# Part A — heredoc body stripping.
# ---------------------------------------------------------------------------
# The command contains rm lines ONLY inside a heredoc body — the literal text
# is being written to a file, not executed. Must ALLOW.
# workdir exists as an untracked dir; without heredoc stripping this would DENY.
HEREDOC_ALLOW=$'cat > out.txt <<\'EOF\'\n[[ -n "$f" ]] && rm -f "$f"\nrm -rf workdir\nEOF'
run_case "heredoc body containing rm — allowed (body stripped, not executed)" allow "$HEREDOC_ALLOW"

# A heredoc body is benign but a REAL rm follows after EOF. Must DENY.
HEREDOC_THEN_RM=$'cat > x <<\'EOF\'\nhello\nEOF\nrm -rf workdir'
run_case "heredoc body benign + real rm after EOF — denied" deny "$HEREDOC_THEN_RM"

# ---------------------------------------------------------------------------
# Part B hardening — wrapped / grouped / quoted-verb / shell-invoker forms.
# These bypass naive command-position detection but invoke a REAL rm on the
# untracked `workdir`, so they MUST still DENY (security-review findings F1-F7).
# ---------------------------------------------------------------------------
run_case "brace-group { rm -rf workdir; } denied" deny "{ rm -rf workdir; }"
run_case "subshell (rm -rf workdir) denied" deny "(rm -rf workdir)"
run_case "command-sub \$(rm -rf workdir) denied" deny "\$(rm -rf workdir)"
run_case "bash -c 'rm -rf workdir' denied" deny "bash -c 'rm -rf workdir'"
run_case "sh -c 'rm -rf workdir' denied" deny "sh -c 'rm -rf workdir'"
run_case "eval 'rm -rf workdir' denied" deny "eval 'rm -rf workdir'"
run_case "exec rm -rf workdir denied" deny "exec rm -rf workdir"
run_case "nice rm -rf workdir denied" deny "nice rm -rf workdir"
run_case "nohup rm -rf workdir denied" deny "nohup rm -rf workdir"
run_case "env rm -rf workdir (no VAR=val) denied" deny "env rm -rf workdir"
run_case "backslash-escaped verb \\rm -rf workdir denied" deny "\\rm -rf workdir"
run_case "single-quoted verb 'rm' -rf workdir denied" deny "'rm' -rf workdir"
run_case "double-quoted verb \"rm\" -rf workdir denied" deny "\"rm\" -rf workdir"
run_case "negated ! rm -rf workdir denied" deny "! rm -rf workdir"

# Part A — hyphenated heredoc terminator must not trap the awk stripper and swallow
# a REAL trailing rm (F8 fail-safe + broadened terminator word).
HEREDOC_HYPHEN=$'cat > out.txt <<END-OF-FILE\nhello\nEND-OF-FILE\nrm -rf workdir'
run_case "hyphenated heredoc terminator + real rm after — denied" deny "$HEREDOC_HYPHEN"

# ---------------------------------------------------------------------------
# Multi-line continuation coverage — CRLF/LF robustness (2026-06-30).
# On Windows the native jq.exe emits decode output in text mode, injecting a CR
# before every LF, so `rm -rf \<newline> <dir>` reaches the hook as `\<CR><LF>`.
# Before the check-level CR-strip, the backslash-continuation join (`\`+LF only)
# missed that form, the segment never re-joined, and the destructive rm EVADED
# the guard (false ALLOW). Both the `\`+LF and explicit `\`+CRLF forms of an
# already-destructive `rm -rf <tracked-tree>` MUST DENY — only the multi-line
# FORM changes; what counts as destructive does not.
# Inputs built from explicit backslash / LF / CR vars: ANSI-C `$'\\\n'` is
# reliable in a script file, but the explicit form is unambiguous across builds
# and documents the exact byte sequence under test.
CONT_BS='\'; CONT_NL=$'\n'; CONT_CR=$'\r'
run_case "multi-line rm -rf (backslash+LF continuation) untracked dir denied" \
  deny "rm -rf ${CONT_BS}${CONT_NL}  workdir"
run_case "multi-line rm -rf (backslash+CRLF continuation) untracked dir denied" \
  deny "rm -rf ${CONT_BS}${CONT_CR}${CONT_NL}  workdir"

# ---------------------------------------------------------------------------
# Part B 2nd-pass hardening — execution-wrapper FLAGS before rm + verb-resolver
# subshell. A wrapper runs another command, so an unquoted rm token after wrapper
# flags is a real invocation (second security-review findings F2/F3/F4). MUST DENY.
# ---------------------------------------------------------------------------
run_case "sudo -u root rm -rf workdir denied" deny "sudo -u root rm -rf workdir"
run_case "sudo -n rm -rf workdir denied" deny "sudo -n rm -rf workdir"
run_case "env -i rm -rf workdir denied" deny "env -i rm -rf workdir"
run_case "env -u FOO rm -rf workdir denied" deny "env -u FOO rm -rf workdir"
run_case "nice -n 10 rm -rf workdir denied" deny "nice -n 10 rm -rf workdir"
run_case "command rm -rf workdir denied" deny "command rm -rf workdir"
run_case "\$(which rm) -rf workdir denied" deny "\$(which rm) -rf workdir"
run_case "backtick which rm -rf workdir denied" deny "\`which rm\` -rf workdir"
# Wrapper false-positive guards — non-destructive forms (no rm target) MUST ALLOW.
run_case "bare which rm (no target) allowed" allow "which rm"
run_case "command -v rm (no target) allowed" allow "command -v rm"
run_case "type rm (no target) allowed" allow "type rm"
run_case "sudo grep quoted rm pattern allowed" allow 'sudo grep "how to rm files" tracked.txt'

# A genuinely clean committed dir (no untracked siblings) must pass.
mkdir purecommit && echo x > purecommit/a.txt && git add purecommit/a.txt && git commit -q -m c2
run_case "rm -rf a fully clean committed dir allowed" allow "rm -rf purecommit"

# ---------------------------------------------------------------------------
# Regenerable scratch allowlist — tasks/*-scratch dirs pass without env-var.
# ---------------------------------------------------------------------------
# Create a tasks/daily-review-scratch dir with untracked content (exactly the
# shape /workday-complete Step 4f produces). Without the allowlist this would
# DENY because git sees untracked files inside it.
mkdir -p tasks/daily-review-scratch
echo "ephemeral" > tasks/daily-review-scratch/notes.txt
run_case "rm -rf tasks/daily-review-scratch (regenerable scratch) allowed" allow "rm -rf tasks/daily-review-scratch"

# Other *-scratch siblings also match the pattern.
mkdir -p tasks/custom-scratch
echo "tmp" > tasks/custom-scratch/x.txt
run_case "rm -rf tasks/custom-scratch (any *-scratch) allowed" allow "rm -rf tasks/custom-scratch"

# A non-scratch tasks/ subdir with untracked content must still DENY — the
# allowlist must not broaden beyond the *-scratch convention.
mkdir -p tasks/important-work
echo "real wip" > tasks/important-work/plan.md
run_case "rm -rf tasks/important-work (non-scratch tasks dir) denied" deny "rm -rf tasks/important-work"

# A top-level dir named *-scratch (not under tasks/) is NOT on the allowlist
# and must still DENY when it contains untracked work.
mkdir -p top-scratch
echo "real wip" > top-scratch/plan.md
run_case "rm -rf top-scratch (not under tasks/) denied" deny "rm -rf top-scratch"

# A classic destructive rm of src/ or ~ is still blocked (sanity check).
mkdir -p fakesrc && echo "code" > fakesrc/main.c
run_case "rm -rf src-like dir with content denied" deny "rm -rf fakesrc"

# ---------------------------------------------------------------------------
# Hardened allowlist — new DENY cases added for security-audit-worker findings.
# ---------------------------------------------------------------------------

# (1) Symlink handling in the scratch allowlist (security-audit-worker findings + F9).
#     The hook guards IN-REPO git-unrecoverable work; targets outside any git repo are
#     out of scope by design, and `rm -rf <symlink>` removes the LINK, not the target.
#     So a tasks/*-scratch symlink to an EXTERNAL non-repo dir is ALLOWED (out of scope).
#     A tasks/*-scratch symlink to an IN-REPO dir with untracked content must DENY: the
#     -L check (trailing-slash-normalized, F9) excludes it from the allowlist fast path,
#     so it falls through to the git-status check which catches the in-repo work.
# NOTE: Windows Git Bash does not support POSIX directory symlinks (ln -s dir creates a
#       directory copy, not a symlink; -L always returns false). Skipped on Windows.

# (1a) Symlink -> external non-repo dir: ALLOWED (out of the hook's in-repo scope; the
#      rm unlinks the symlink, it does not recurse into the external target).
SYMLINK_TARGET=$(mktemp -d)
echo "external" > "$SYMLINK_TARGET/secret.txt"
mkdir -p tasks
ln -s "$SYMLINK_TARGET" tasks/link-scratch 2>/dev/null || true
if [[ -L "tasks/link-scratch" ]]; then
  run_case "rm -rf tasks/link-scratch (symlink to external non-repo dir) allowed — out of scope" allow "rm -rf tasks/link-scratch"
else
  PASS=$((PASS + 1))
  echo "  [SKIP] symlink-to-external test: Windows Git Bash no POSIX dir symlinks (counted as pass)"
fi
rm -rf tasks/link-scratch
rm -rf "$SYMLINK_TARGET"

# (1b) Symlink -> IN-REPO *-scratch dir with untracked content: DENY. The -L exclusion
#      forces fall-through to the git-status check; without it the allowlist would fire
#      via the resolved target's basename/parent and wrongly ALLOW. The trailing-slash
#      variant proves the F9 fix (`-L dir/` would otherwise dereference and skip the check).
mkdir -p tasks/inrepo-target-scratch
echo "in-repo wip" > tasks/inrepo-target-scratch/work.txt
ln -s "$TMP/tasks/inrepo-target-scratch" tasks/sym-scratch 2>/dev/null || true
if [[ -L "tasks/sym-scratch" ]]; then
  run_case "rm -rf tasks/sym-scratch (symlink to in-repo dirty scratch) denied" deny "rm -rf tasks/sym-scratch"
  run_case "rm -rf tasks/sym-scratch/ (trailing-slash symlink defeats -L? F9) denied" deny "rm -rf tasks/sym-scratch/"
else
  PASS=$((PASS + 2))
  echo "  [SKIP] in-repo symlink tests: Windows Git Bash no POSIX dir symlinks (counted as pass)"
fi
rm -rf tasks/sym-scratch
rm -rf tasks/inrepo-target-scratch

# (2) Path-traversal: rm -rf tasks/x-scratch/../../<dirty-dir> — the resolved
#     path is NOT under tasks/*-scratch basename, so it must DENY.
mkdir -p tasks/x-scratch
mkdir -p tasks/traversal-target
echo "wip" > tasks/traversal-target/secret.md
run_case "rm -rf path-traversal via tasks/x-scratch/../.. denied" deny "rm -rf tasks/x-scratch/../../tasks/traversal-target"
rm -rf tasks/x-scratch tasks/traversal-target

# (3) tasks/<name>-scratch that is NOT under the current repo root must DENY.
#     Create a SEPARATE git repo with a tasks/foo-scratch; feed its path to the
#     hook by absolute path from within OUR repo's cwd. The -ef check compares
#     inodes — the external repo's tasks/ dir will NOT be -ef our repo's tasks/,
#     so the allowlist will not fire and git-status will see untracked content.
EXT_REPO=$(mktemp -d)
cd "$EXT_REPO"
git init -q -b main
git config user.email t@t.t && git config user.name t && git config commit.gpgsign false
mkdir -p tasks/foo-scratch
echo "external wip" > tasks/foo-scratch/data.txt
cd "$TMP"  # back to our test repo
EXT_TASKS="$EXT_REPO/tasks/foo-scratch"
# Drive the hook with an absolute path to the external-repo scratch dir.
ext_out=$(emit "rm -rf $EXT_TASKS" | bash "$HOOK" 2>/dev/null || true)
if echo "$ext_out" | grep -q '"permissionDecision":"deny"'; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1)); echo "FAIL: external-repo tasks/foo-scratch (not in current repo) should DENY (expected deny, got allow)"
  [[ -n "$ext_out" ]] && echo "      out: $(echo "$ext_out" | head -c 300)"
fi
rm -rf "$EXT_REPO"

# (4) Mixed multi-target: one valid in-repo scratch + one dirty non-scratch dir.
#     The dirty non-scratch must still trigger DENY even though the scratch is OK.
mkdir -p tasks/ok-scratch
echo "ephemeral" > tasks/ok-scratch/notes.txt
mkdir -p dirty-non-scratch
echo "wip" > dirty-non-scratch/plan.md
run_case "rm -rf mixed: ok-scratch + dirty-non-scratch denied" deny "rm -rf tasks/ok-scratch dirty-non-scratch"
rm -rf tasks/ok-scratch dirty-non-scratch

# F3 regression: hook cwd is a repo SUBDIRECTORY, relative target. Before the
# absolute-path fix the git-status pathspec resolved against the repo ROOT and
# missed the work -> false allow. Must DENY.
mkdir -p sub/wipsub && echo "subwip" > sub/wipsub/f.txt
sub_out=$(emit "rm -rf wipsub" | (cd "$TMP/sub" && bash "$HOOK") 2>/dev/null || true)
if echo "$sub_out" | grep -q '"permissionDecision":"deny"'; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1)); echo "FAIL: subdir-cwd relative target denied (expected deny)"
fi

# ---------------------------------------------------------------------------
# Peer-contest hardening (2026-07-10) — COORDINATOR_ALLOW_RM=1 must not bypass
# a LIVE peer session's claim on untracked/uncommitted work in this shared
# worktree. Sets up .git/coordinator-sessions/ inside the temp repo per case.
# ---------------------------------------------------------------------------

SELF_SID="self-$(date +%s)-aaaa"
PEER_SID="peer-$(date +%s)-bbbb"

# (1) Override still bypasses an untracked delete when NO peer claims it.
mkdir -p .git/coordinator-sessions
echo "$SELF_SID" > .git/coordinator-sessions/.current-session-id
mkdir -p ".git/coordinator-sessions/${PEER_SID}"
: > ".git/coordinator-sessions/${PEER_SID}/touched.txt"   # empty — claims nothing
run_case "override bypasses untracked delete when no peer claims it" allow "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"

# (2) Override REFUSED when a live peer's touched.txt claims a path under target.
echo "workdir/new.txt" > ".git/coordinator-sessions/${PEER_SID}/touched.txt"
run_case "override refused: live peer claims path under target" deny "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"

# (3) Peer-claim deny fires even WITHOUT the override, and names the peer session.
peer_out=$(emit "rm -rf workdir" | bash "$HOOK" 2>/dev/null || true)
if echo "$peer_out" | grep -q '"permissionDecision":"deny"' && echo "$peer_out" | grep -q "LIVE peer session ${PEER_SID}"; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: peer-claim deny fires without override and names peer session"
  [[ -n "$peer_out" ]] && echo "      out: $(echo "$peer_out" | head -c 300)"
fi

# (4) A STALE peer (touched.txt mtime > 30 min old, not in cs_live_session_ids)
# does not contest -> override allow. This throwaway repo's synthetic peer sid
# will not appear in any real cs_live_session_ids output, so the degradation
# path (mtime) governs deterministically.
if [[ -n "$(command -v python3 2>/dev/null || command -v python 2>/dev/null)" ]]; then
  STALE_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  STALE_TS=$(( $("$STALE_PY" -c 'import time;print(int(time.time()))') - 3600 ))
  "$STALE_PY" -c 'import os,sys;os.utime(sys.argv[1],(int(sys.argv[2]),int(sys.argv[2])))' \
    ".git/coordinator-sessions/${PEER_SID}/touched.txt" "$STALE_TS"
  run_case "stale peer (mtime>30min) does not contest -> override allow" allow "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"
else
  PASS=$((PASS + 1))
  echo "  [SKIP] stale-peer mtime test: no python available (counted as pass)"
fi

# (5) Sentinel-collision regression (Finding 2, 2026-07-10 review): the
# .current-session-id sentinel names the PEER (simulating the peer's cs_init
# having last-written it after the caller's own session started — the exact
# last-writer-wins hazard the sentinel is documented to have). The peer's
# touched.txt claims a path under the target. Before the Finding 2 fix,
# _rm_peer_claim_of trusted the sentinel unconditionally as "self" and would
# have skipped this peer's dir, silently allowing the override through; with
# the fix, self-exclusion routes through cs_resolve_session_id and this
# throwaway repo's synthetic sids will not resolve as live/self via any real
# resolver tier, so the fail-safe "don't exclude on unresolvable identity"
# branch governs deterministically and the peer's claim must still be honored.
mkdir -p ".git/coordinator-sessions/${PEER_SID}"
echo "$PEER_SID" > .git/coordinator-sessions/.current-session-id
echo "workdir/new.txt" > ".git/coordinator-sessions/${PEER_SID}/touched.txt"
run_case "sentinel-collision: sentinel names peer, override still refused" deny "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"

# (6) No .git/coordinator-sessions/ dir at all -> override behaves exactly as before.
rm -rf .git/coordinator-sessions
run_case "no coordinator-sessions dir: override behaves as before" allow "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"

# ---------------------------------------------------------------------------
# bash 3.2 fail-open regression (2026-07-10): "${_live_sids[@]}" on an EMPTY
# array under `set -u` is a fatal "unbound variable" on bash < 4.4 (stock
# macOS /bin/bash 3.2) — including a DECLARED-empty array, not just unset.
# _live_sids is empty whenever cs_live_session_ids resolves zero live
# sessions, which is the case here: a dead-session dir with a meta.json is
# present (sess_dir glob non-empty, so the peer-claim probe runs and reaches
# the canonical-liveness branch) but has no valid heartbeat, so
# cs_live_session_ids returns nothing. Pre-fix this crashed the
# _rm_peer_claim_of subshell (contained — the outer hook survived — but the
# crash silently discarded whatever partial peer-claim result the subshell
# was computing). Runs the hook under /bin/bash directly (not the test
# suite's own $BASH) on the canonical destructive input to reproduce the
# exact 3.2 execution path and confirm both (a) DENY fires and (b) no
# "unbound variable" is emitted to stderr. Skips cleanly when /bin/bash is
# absent or is itself >=4.
# ---------------------------------------------------------------------------
if [[ -x /bin/bash ]]; then
  BASH32_MAJOR=$(/bin/bash -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 99)
  if [[ "$BASH32_MAJOR" -lt 4 ]]; then
    rm -rf .git/coordinator-sessions
    mkdir -p .git/coordinator-sessions/deadsession
    echo '{}' > .git/coordinator-sessions/deadsession/meta.json
    OUT32=$(emit "rm -rf workdir" | /bin/bash "$HOOK" 2>/tmp/rm32-stderr.$$ || true)
    ERR32=$(cat /tmp/rm32-stderr.$$ 2>/dev/null || true)
    rm -f /tmp/rm32-stderr.$$
    GOT32="allow"
    echo "$OUT32" | grep -q '"permissionDecision":"deny"' && GOT32="deny"
    if [[ "$GOT32" == "deny" ]] && ! echo "$ERR32" | grep -q 'unbound variable'; then
      PASS=$((PASS + 1))
    else
      FAIL=$((FAIL + 1))
      echo "FAIL: bash 3.2 (/bin/bash) rm -rf workdir with dead-session/no-live-peer must DENY with no unbound-variable crash (got $GOT32; stderr: $(printf '%s' "$ERR32" | head -c 120))"
    fi
    rm -rf .git/coordinator-sessions
  fi
fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "block-destructive-rm: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
