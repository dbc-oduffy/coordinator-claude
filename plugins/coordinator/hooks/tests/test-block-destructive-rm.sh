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
run_case "rm -rf unresolved var (v1 skip) allowed" allow 'rm -rf $SOME_DIR'
run_case "rm -rf glob (v1 skip) allowed" allow "rm -rf build/*"
run_case "override env bypasses block" allow "rm -rf workdir" "COORDINATOR_ALLOW_RM=1"
run_case "non-rm command allowed (fast bail)" allow "git status"
run_case "echo mentioning rm allowed" allow "echo 'how to rm files'"

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

# (1) Symlink tasks/<name>-scratch pointing to an external dir with untracked
#     content must DENY — the -L check prevents the allowlist from firing for
#     symlinks so that realpath-following can't land the match on an unintended target.
# NOTE: Windows Git Bash does not support POSIX directory symlinks (ln -s dir
#       creates a directory copy, not a symlink; -L always returns false). Skip
#       this case on Windows; the hook code itself is correct for POSIX hosts.
SYMLINK_TARGET=$(mktemp -d)
echo "external" > "$SYMLINK_TARGET/secret.txt"
mkdir -p tasks
ln -s "$SYMLINK_TARGET" tasks/link-scratch 2>/dev/null || true
if [[ -L "tasks/link-scratch" ]]; then
  run_case "rm -rf tasks/link-scratch (symlink to external dir) denied" deny "rm -rf tasks/link-scratch"
else
  PASS=$((PASS + 1))
  echo "  [SKIP] symlink-to-dir test: Windows Git Bash does not support POSIX dir symlinks (counted as pass)"
fi
rm -rf tasks/link-scratch
rm -rf "$SYMLINK_TARGET"

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
echo "----------------------------------------"
echo "block-destructive-rm: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
