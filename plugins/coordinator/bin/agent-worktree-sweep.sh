#!/usr/bin/env bash
# agent-worktree-sweep.sh — find and (optionally) reap agent-isolation worktrees
#
# Background: Claude Code 2.1.x auto-creates per-dispatch git worktrees under
# <repo>/.claude/worktrees/agent-<hash>/ for backgrounded Agent dispatches.
# These are documented opt-out-only behavior (no per-dispatch flag yet, see
# anthropics/claude-code#58597). They persist locked until session deletion,
# accumulating across days.
#
# This script:
#   1. Enumerates `git worktree list` for paths matching .claude/worktrees/agent-*
#   2. Per worktree, classifies state vs. the calling repo's HEAD branch:
#        - empty-clean   : no commits ahead of HEAD, no dirty files
#        - commits-clean : commits ahead, no dirty files (salvageable)
#        - dirty         : uncommitted changes present (PM must handle)
#   3. With --reap: removes empty-clean; cherry-picks commits-clean onto HEAD
#      then removes; warns and leaves dirty alone.
#   4. Emits one JSON line per worktree: {path, branch, state, action, detail}
#
# Negative-spec: never touches non-agent worktrees. Never deletes branches that
# don't match worktree-agent-*. Never force-pushes. Never invokes destructive
# git commands without --reap.
#
# Exit codes:
#   0 — completed (with or without findings)
#   2 — not a git repo / no worktree command available
#   3 — --reap requested but cherry-pick conflict left a worktree in mid-state

set -euo pipefail

REAP=0
FORMAT="json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reap)         REAP=1;       shift ;;
    --format)       FORMAT="$2";  shift 2 ;;
    --help|-h)
      cat <<'EOF'
Usage: agent-worktree-sweep.sh [--reap] [--format json|text]

  --reap            Remove empty-clean worktrees; cherry-pick + remove
                    commits-clean worktrees. Without it, scan only.
  --format json     Default. One JSON line per worktree.
  --format text     Human-readable summary.
  --help            Show this help.

Operates on the repo containing $PWD. Touches only worktrees whose path
matches .claude/worktrees/agent-* relative to the repo root.
EOF
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "git not found" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "not in a git repo" >&2
  exit 2
fi

# Submodule-context surface: `git rev-parse --show-toplevel` resolves to the
# *submodule* root when $PWD is inside a submodule, so REPO_ROOT — and every
# worktree we enumerate below — would belong to the submodule, not its
# superproject. A submodule and its superproject keep independent worktree sets
# (agent worktrees live under <repo>/.claude/worktrees/). Surface which repo is
# actually being swept rather than silently operating on the inner one. This is
# offer-shape, not a block: it tells the operator how to target the superproject
# if that's what they meant, and never changes reap behavior.
SUPERPROJECT="$(git -C "$REPO_ROOT" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [[ -n "$SUPERPROJECT" ]]; then
  echo "note: $REPO_ROOT is a submodule of $SUPERPROJECT" >&2
  echo "      this sweep covers the submodule only; agent worktrees in $SUPERPROJECT will NOT be reached — re-run from there for those." >&2
fi

ACTIVE_BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || true)"
if [[ -z "$ACTIVE_BRANCH" ]]; then
  echo "calling repo is in detached HEAD; refuse to reap" >&2
  REAP=0
fi

# Comparison base for COMMITS_AHEAD: the active branch when on one, else the
# detached-HEAD SHA. Without this fallback, ACTIVE_BRANCH is empty under detached
# HEAD so COMMITS_AHEAD stays 0 for every worktree — a commits-ahead worktree is
# then misclassified as empty-clean in scan-only output. Worktrees share the repo's
# object store, so the SHA resolves from each worktree's context. Reap stays off
# under detached HEAD (above), so this affects classification only, never removal.
COMPARE_REF="$ACTIVE_BRANCH"
if [[ -z "$COMPARE_REF" ]]; then
  COMPARE_REF="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
fi

# git worktree list --porcelain emits stanzas like:
#   worktree /path
#   HEAD <sha>
#   branch refs/heads/<name>
#   locked
WORKTREES=()
CURRENT_PATH=""
CURRENT_BRANCH=""
CURRENT_LOCKED=0
while IFS= read -r line; do
  case "$line" in
    "worktree "*)
      if [[ -n "$CURRENT_PATH" ]]; then
        WORKTREES+=("${CURRENT_PATH}|${CURRENT_BRANCH}|${CURRENT_LOCKED}")
      fi
      CURRENT_PATH="${line#worktree }"
      CURRENT_BRANCH=""
      CURRENT_LOCKED=0
      ;;
    "branch refs/heads/"*)
      CURRENT_BRANCH="${line#branch refs/heads/}"
      ;;
    "locked"*)
      CURRENT_LOCKED=1
      ;;
    "")
      if [[ -n "$CURRENT_PATH" ]]; then
        WORKTREES+=("${CURRENT_PATH}|${CURRENT_BRANCH}|${CURRENT_LOCKED}")
        CURRENT_PATH=""
        CURRENT_BRANCH=""
        CURRENT_LOCKED=0
      fi
      ;;
  esac
done < <(git -C "$REPO_ROOT" worktree list --porcelain)
if [[ -n "$CURRENT_PATH" ]]; then
  WORKTREES+=("${CURRENT_PATH}|${CURRENT_BRANCH}|${CURRENT_LOCKED}")
fi

# Escape a value for safe embedding inside a JSON string literal. Worktree paths
# on Windows carry backslashes and either field can in principle contain a
# double-quote; raw interpolation produced malformed JSON for jq/script consumers.
# Backslash MUST be escaped before the double-quote so the quote's own backslash
# is not doubled. Control chars (tab/newline) cannot occur in git refs or worktree
# paths, so backslash + quote is the complete surface here.
_json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"   # backslash first, before any escape that introduces a backslash
  s="${s//\"/\\\"}"
  s="${s//$'\t'/\\t}" # the detail field is built from git-status output — a tab in a
  s="${s//$'\n'/\\n}" # dirty filename (legal on POSIX) would otherwise break the JSON
  printf '%s' "$s"
}

emit_json() {
  local path="$1" branch="$2" state="$3" action="$4" detail="$5"
  printf '{"path":"%s","branch":"%s","state":"%s","action":"%s","detail":"%s"}\n' \
    "$(_json_escape "$path")" "$(_json_escape "$branch")" "$(_json_escape "$state")" \
    "$(_json_escape "$action")" "$(_json_escape "$detail")"
}

emit_text() {
  local path="$1" branch="$2" state="$3" action="$4" detail="$5"
  printf '[%s] %-14s %-10s %s\n  branch=%s detail=%s\n' \
    "$(date -u +%H:%M:%S)" "$state" "$action" "$path" "$branch" "$detail"
}

emit() {
  case "$FORMAT" in
    json) emit_json "$@" ;;
    text) emit_text "$@" ;;
  esac
}

EXIT_CODE=0

for entry in "${WORKTREES[@]:-}"; do
  [[ -z "$entry" ]] && continue
  IFS='|' read -r WT_PATH WT_BRANCH _LOCKED <<<"$entry"

  # Match agent-isolation worktrees only — anything else is user-managed
  case "$WT_PATH" in
    *"/.claude/worktrees/agent-"*) ;;
    *) continue ;;
  esac

  if [[ ! -d "$WT_PATH" ]]; then
    emit "$WT_PATH" "$WT_BRANCH" "missing" "skip" "worktree path does not exist"
    continue
  fi

  # Count commits unique to the worktree relative to the calling branch
  COMMITS_AHEAD=0
  if [[ -n "$COMPARE_REF" ]]; then
    COMMITS_AHEAD="$(git -C "$WT_PATH" rev-list --count "${COMPARE_REF}..HEAD" 2>/dev/null || echo 0)"
  fi

  # Detect dirty state (staged + unstaged + untracked)
  DIRTY_OUT="$(git -C "$WT_PATH" status --porcelain 2>/dev/null || true)"
  DIRTY_LINES="$(printf '%s' "$DIRTY_OUT" | grep -c . || true)"

  # Benign-only classifier: every porcelain line touches a known auto-add path
  # (Claude Code permission auto-adds, last-cleanup timestamp, etc.). When the
  # entire dirt surface is benign, we --force the worktree away rather than
  # leaving it to accumulate. Pattern is intentionally narrow — anything outside
  # this allowlist falls through to "dirty" and surfaces for triage.
  BENIGN_ONLY=0
  if [[ "$DIRTY_LINES" -gt 0 ]]; then
    NON_BENIGN="$(printf '%s\n' "$DIRTY_OUT" | awk '{path=$0; sub(/^...[ ]?/, "", path); sub(/^"/, "", path); sub(/"$/, "", path); print path}' | grep -Ev '^(\.claude/settings\.local\.json|\.last-cleanup)$' || true)"
    if [[ -z "$NON_BENIGN" ]]; then
      BENIGN_ONLY=1
    fi
  fi

  STATE=""
  if [[ "$DIRTY_LINES" -gt 0 && "$BENIGN_ONLY" -eq 1 && "$COMMITS_AHEAD" -eq 0 ]]; then
    STATE="dirty-benign"
  elif [[ "$DIRTY_LINES" -gt 0 ]]; then
    STATE="dirty"
  elif [[ "$COMMITS_AHEAD" -gt 0 ]]; then
    STATE="commits-clean"
  else
    STATE="empty-clean"
  fi

  if [[ "$REAP" -eq 0 ]]; then
    emit "$WT_PATH" "$WT_BRANCH" "$STATE" "scan-only" "ahead=${COMMITS_AHEAD} dirty=${DIRTY_LINES}"
    continue
  fi

  case "$STATE" in
    empty-clean)
      if git -C "$REPO_ROOT" worktree remove --force "$WT_PATH" 2>/dev/null; then
        # Best-effort branch cleanup; ignore failure (branch may already be gone)
        if [[ -n "$WT_BRANCH" ]]; then
          git -C "$REPO_ROOT" branch -D "$WT_BRANCH" >/dev/null 2>&1 || true
        fi
        emit "$WT_PATH" "$WT_BRANCH" "$STATE" "removed" "ahead=0 dirty=0"
      else
        emit "$WT_PATH" "$WT_BRANCH" "$STATE" "remove-failed" "git worktree remove rejected"
        EXIT_CODE=3
      fi
      ;;

    dirty-benign)
      # Dirt is fully inside the known auto-add allowlist; --force removes it.
      if git -C "$REPO_ROOT" worktree remove --force "$WT_PATH" 2>/dev/null; then
        if [[ -n "$WT_BRANCH" ]]; then
          git -C "$REPO_ROOT" branch -D "$WT_BRANCH" >/dev/null 2>&1 || true
        fi
        emit "$WT_PATH" "$WT_BRANCH" "$STATE" "removed" "ahead=0 dirty=${DIRTY_LINES} (benign-allowlist only)"
      else
        emit "$WT_PATH" "$WT_BRANCH" "$STATE" "remove-failed" "git worktree remove --force rejected"
        EXIT_CODE=3
      fi
      ;;

    commits-clean)
      # Collect oldest-first commit list for cherry-pick.
      # ACTIVE_BRANCH is guaranteed non-empty here: REAP is forced to 0 under detached HEAD
      # (where ACTIVE_BRANCH is empty), so the commits-clean + REAP=1 path that reaches this
      # line is unreachable when ACTIVE_BRANCH is empty. Invariant depends on that guard
      # ordering above — do not reorder the REAP=0 detached-HEAD clamp below COMPARE_REF.
      mapfile -t COMMITS < <(git -C "$WT_PATH" rev-list --reverse "${ACTIVE_BRANCH}..HEAD")
      PICKED=0
      PICK_FAILED=""
      for sha in "${COMMITS[@]}"; do
        if COORDINATOR_OVERRIDE_BRANCH=1 \
           COORDINATOR_OVERRIDE_BRANCH_REASON="agent-worktree-sweep cherry-pick from $WT_PATH" \
           git -C "$REPO_ROOT" cherry-pick --allow-empty -x "$sha" >/dev/null 2>&1; then
          PICKED=$((PICKED + 1))
        else
          PICK_FAILED="$sha"
          # Abort the in-progress cherry-pick to leave the active branch clean
          git -C "$REPO_ROOT" cherry-pick --abort >/dev/null 2>&1 || true
          break
        fi
      done
      if [[ -n "$PICK_FAILED" ]]; then
        emit "$WT_PATH" "$WT_BRANCH" "$STATE" "salvage-conflict" \
          "picked=${PICKED}/${#COMMITS[@]} stopped_at=${PICK_FAILED} — worktree retained for PM"
        EXIT_CODE=3
      else
        if git -C "$REPO_ROOT" worktree remove --force "$WT_PATH" 2>/dev/null; then
          if [[ -n "$WT_BRANCH" ]]; then
            git -C "$REPO_ROOT" branch -D "$WT_BRANCH" >/dev/null 2>&1 || true
          fi
          emit "$WT_PATH" "$WT_BRANCH" "$STATE" "salvaged-removed" \
            "cherry-picked=${PICKED} onto=${ACTIVE_BRANCH}"
        else
          emit "$WT_PATH" "$WT_BRANCH" "$STATE" "salvaged-remove-failed" \
            "cherry-picked=${PICKED} onto=${ACTIVE_BRANCH} but worktree remove rejected"
          EXIT_CODE=3
        fi
      fi
      ;;

    dirty)
      emit "$WT_PATH" "$WT_BRANCH" "$STATE" "warned-skip" \
        "ahead=${COMMITS_AHEAD} dirty=${DIRTY_LINES} — uncommitted changes; PM must triage"
      ;;
  esac
done

# Best-effort prune; ignores failure on Windows when refs are still locked.
git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true

exit "$EXIT_CODE"
