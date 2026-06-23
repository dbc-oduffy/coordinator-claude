#!/usr/bin/env bash
# bin/check-plugin-drift.test.sh — regression net for the Leg 3 working-tree guard.
#
# Pins the fix in d82ba601 + follow-up 9acb8ab9: check-plugin-drift.sh Leg 3 ran
# `git -C "$live_path" status` assuming a standalone checkout. For a data-only live
# path nested inside a parent git repo (no nested .git — project-rag's
# ~/.claude/plugins/project-rag), `git -C` escapes UPWARD to the enclosing repo and
# reports the parent's transient dirty tree as the plugin's, a perpetual false
# "[drift] working-tree ... refresh blocked" on every active session.
#
# _git_worktree_root_if_self encapsulates the guard (empty → skip Leg 3). These tests
# exercise it directly (loaded via the CHECK_PLUGIN_DRIFT_LIB_ONLY sourcing hatch) plus
# the emergent _check_plugin behavior on the exact reported scenario.
#
# Spec backlink: state/lessons.md "git -C <dir> status silently escapes to the enclosing repo".
#
# `set -uo pipefail` WITHOUT `-e`: each case captures results manually and the harness
# continues-on-failure to run all assertions. Hermetic — only temp git repos, never the
# real registry or live installs.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIFT="${SCRIPT_DIR}/check-plugin-drift.sh"

PASS=0
FAIL=0
TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

_ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_bad() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL + 1)); }

# Hermetic git identity so `git commit` works regardless of the operator's global config.
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=t@t

_mkrepo() {  # $1 = path; creates an initialized git repo with one committed file
    local r="$1"
    mkdir -p "$r"
    git -C "$r" init -q
    echo seed > "$r/seed.txt"
    git -C "$r" add seed.txt
    git -C "$r" commit -qm seed
}

# Load the helper functions without running the registry scan.
CHECK_PLUGIN_DRIFT_LIB_ONLY=1 source "$DRIFT"

if ! type _git_worktree_root_if_self >/dev/null 2>&1; then
    echo "FATAL: _git_worktree_root_if_self not loaded via lib-only source hatch"
    exit 1
fi

echo "=== Test A: standalone git repo root → returns its own canonical path ==="
REPO_A="$TMPROOT/standalone"
_mkrepo "$REPO_A"
GOT="$(_git_worktree_root_if_self "$REPO_A")"
# pwd -P canonicalizes (macOS /tmp is a symlink to /private/tmp), so compare against canon.
WANT="$( (cd "$REPO_A" && pwd -P) )"
[[ "$GOT" == "$WANT" ]] && _ok "A: own-root returns canon path" || _bad "A: own-root" "got='$GOT' want='$WANT'"

echo "=== Test B (REGRESSION): data-only dir nested in a parent repo → returns EMPTY ==="
PARENT="$TMPROOT/parent"
_mkrepo "$PARENT"
NESTED="$PARENT/plugins/data-only-live"   # no nested .git — escapes to $PARENT pre-fix
mkdir -p "$NESTED"; echo payload > "$NESTED/data.bin"
GOT="$(_git_worktree_root_if_self "$NESTED")"
[[ -z "$GOT" ]] && _ok "B: nested data-only dir returns empty (no parent-repo escape)" \
                 || _bad "B: nested escape not guarded" "got='$GOT' (should be empty)"

echo "=== Test C: nonexistent path → returns EMPTY ==="
GOT="$(_git_worktree_root_if_self "$TMPROOT/does-not-exist")"
[[ -z "$GOT" ]] && _ok "C: nonexistent path returns empty" || _bad "C: nonexistent" "got='$GOT'"

echo "=== Test D: plain non-git dir (outside any repo) → returns EMPTY ==="
PLAIN="$TMPROOT/plain"; mkdir -p "$PLAIN"
GOT="$(_git_worktree_root_if_self "$PLAIN")"
[[ -z "$GOT" ]] && _ok "D: non-git dir returns empty" || _bad "D: non-git dir" "got='$GOT'"

echo "=== Test E (REGRESSION, emergent): dirty parent + nested data-only live_path ==="
# The exact bug shape: parent repo has uncommitted edits; if Leg 3 escaped, `git status`
# would be non-empty and emit the false "refresh blocked". prop_mode="" reaches Leg 3.
echo dirty >> "$PARENT/seed.txt"   # make the PARENT working tree dirty
OUT="$(_check_plugin "testplug" "$PARENT" "$NESTED" "origin/main" "" "" "" 2>&1)"
if echo "$OUT" | grep -q "working-tree:.*refresh blocked"; then
    _bad "E: emergent false-positive" "Leg 3 emitted 'refresh blocked' for a nested data-only live_path"
else
    _ok "E: no false 'refresh blocked' for nested data-only live_path"
fi
# And the informative [info] skip fires (live_path IS a git path via the parent).
if echo "$OUT" | grep -q "Leg 3 skipped — live_path is not its own work-tree root"; then
    _ok "E2: emits [info] skip diagnostic for nested/submodule path"
else
    _bad "E2: missing [info] skip diagnostic" "out='$OUT'"
fi

echo "=== Test F: standalone DIRTY repo as live_path → DOES emit working-tree drift ==="
# Guard must not over-suppress: a genuine own-root checkout with uncommitted edits is drift.
REPO_F="$TMPROOT/dirty-live"
_mkrepo "$REPO_F"; echo change >> "$REPO_F/seed.txt"
OUT="$(_check_plugin "dirtyplug" "$REPO_F" "$REPO_F" "origin/main" "" "" "" 2>&1)"
if echo "$OUT" | grep -q "working-tree:.*refresh blocked"; then
    _ok "F: own-root dirty checkout still flagged (guard not over-suppressing)"
else
    _bad "F: real drift missed" "out='$OUT'"
fi

echo
echo "================ check-plugin-drift.test.sh: ${PASS} passed, ${FAIL} failed ================"
[[ "$FAIL" -eq 0 ]]
