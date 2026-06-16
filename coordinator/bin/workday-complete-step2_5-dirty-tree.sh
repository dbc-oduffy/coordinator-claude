#!/usr/bin/env bash
# workday-complete-step2_5-dirty-tree.sh — mechanized Step 2.5 case-(c) auto-disposition.
#
# Spec backlink: commands/workday-complete.md § Step 2.5
# PM ruling:     cross-repo/inbox/2026-06-16-workday-complete-dirty-tree-autonomy.md
#
# Classifies every dirty path in the cwd's git repo and acts:
#   EOL-PHANTOM   — content-equal to index; silently skip
#   SUBMODULE     — mode 160000; silently skip (LEAVE-ALONE)
#   LEAVE-ALONE   — state/handoffs/ or .git/; silently skip (concurrent-session territory)
#   ORPHAN-TMP    — *.tmp.[0-9]*.[0-9]* basename; list on stderr, no action
#   AUTO-GITIGNORE — logs/, *.log, *.pid, .DS_Store, Thumbs.db; gitignore + rm --cached + commit
#   AUTO-COMMIT   — known-safe housekeeping roots (see allow-list below); explicit-path commit
#   SOURCE-TREE   — plugins/, bin/, hooks/, etc.; list on stderr, exit 2
#   AMBIGUOUS     — none of the above; list on stderr, exit 2
#
# Stdout: per-group summary lines + final OK / NEEDS-PM line
# Stderr: per-path detail for orphan-tmp / source-tree / ambiguous
# Exit codes:
#   0 — all clear-wins handled; no source-tree/ambiguous remain
#   1 — error during processing (git failed, .gitignore unwriteable, commit failed)
#   2 — clear-wins handled; source-tree or ambiguous paths remain
#
# --dry-run: print what would be done; no commits, no gitignore edits, no git rm

set -eu

# ---------------------------------------------------------------------------
# Bash ≥ 4 guard
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash ≥ 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
DRY_RUN=0
for _arg in "$@"; do
  case "$_arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "ERROR: unknown argument: $_arg" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Locate repo root; cd there so every relative path is consistent
# ---------------------------------------------------------------------------
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "[step2.5] ERROR: not inside a git repo" >&2
  exit 1
}
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Counters (parallel indexed arrays — no associative arrays; bash-4-guard is
# above, but prefer portable forms where they cost nothing)
# ---------------------------------------------------------------------------
cnt_eol=0
cnt_sub=0
cnt_leave=0
cnt_orphan=0
cnt_gitignore=0
cnt_commit=0
cnt_source=0
cnt_ambiguous=0

# Accumulators for staged operations
gitignore_paths=()
gitignore_patterns=()
commit_paths=()
commit_roots_seen=()   # tracks unique root prefixes for commit message

needs_pm=0

# ---------------------------------------------------------------------------
# Helper — check if a pattern already exists in .gitignore
# Avoids duplicating entries.  BSD grep + no -P.
# ---------------------------------------------------------------------------
_pattern_in_gitignore() {
  local pat="$1" gi="$2"
  [[ -f "$gi" ]] || return 1
  # Literal grep — no regex, just fixed-string match
  grep -qxF "$pat" "$gi" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Helper — append pattern to .gitignore (temp-file pattern; no sed -i)
# ---------------------------------------------------------------------------
_append_to_gitignore() {
  local pat="$1" gi="$2"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[step2.5] DRY-RUN: would append '$pat' to $gi" >&2
    return 0
  fi
  printf '\n%s\n' "$pat" >> "$gi" || {
    echo "[step2.5] ERROR: cannot write to $gi" >&2
    return 1
  }
}

# ---------------------------------------------------------------------------
# Helper — record a unique root for the commit message
# ---------------------------------------------------------------------------
_record_root() {
  local root="$1" r
  for r in "${commit_roots_seen[@]+"${commit_roots_seen[@]}"}"; do
    [[ "$r" == "$root" ]] && return 0
  done
  commit_roots_seen+=("$root")
}

# ---------------------------------------------------------------------------
# Main classification loop
# ---------------------------------------------------------------------------
while IFS= read -r status_line; do
  [[ -z "$status_line" ]] && continue

  # git status --porcelain format: XY PATH or XY PATH -> DEST
  # X = index status, Y = worktree status
  # Rename/copy: "XY old -> new"  (git porcelain v1 uses R/C)
  xy="${status_line:0:2}"
  rest="${status_line:3}"

  # Handle renames: "old -> new" — operate on the destination path
  case "$rest" in
    *" -> "*) path="${rest##* -> }" ;;
    *)        path="$rest" ;;
  esac

  # Strip leading/trailing whitespace (shouldn't be needed but defensive)
  # path is already clean from the porcelain format

  # -------------------------------------------------------------------------
  # 1. EOL-PHANTOM: content-equal to index (git diff --quiet exits 0)
  #    Only meaningful for tracked files; untracked always differ.
  # -------------------------------------------------------------------------
  case "$xy" in
    "??"*) : ;;  # untracked — skip EOL check
    *)
      if git diff --quiet -- "$path" 2>/dev/null; then
        cnt_eol=$(( cnt_eol + 1 ))
        continue
      fi
      ;;
  esac

  # -------------------------------------------------------------------------
  # 2. SUBMODULE: mode 160000
  # -------------------------------------------------------------------------
  if git ls-files --stage -- "$path" 2>/dev/null | grep -q '^160000'; then
    cnt_sub=$(( cnt_sub + 1 ))
    continue
  fi

  # -------------------------------------------------------------------------
  # 3. LEAVE-ALONE: state/handoffs/ or .git/
  # -------------------------------------------------------------------------
  case "$path" in
    state/handoffs/*|.git/*)
      cnt_leave=$(( cnt_leave + 1 ))
      continue
      ;;
  esac

  # -------------------------------------------------------------------------
  # 4. ORPHAN-TMP: basename matches *.tmp.[0-9]*.[0-9]*
  # -------------------------------------------------------------------------
  bname="${path##*/}"
  case "$bname" in
    *.tmp.[0-9]*.[0-9]*)
      echo "[step2.5] orphan-tmp: $path" >&2
      echo "[step2.5] WARN: inspect $path against its target before deleting — not auto-disposed (Edit-tool atomic-write crash artifact)" >&2
      cnt_orphan=$(( cnt_orphan + 1 ))
      continue
      ;;
  esac

  # -------------------------------------------------------------------------
  # 5. AUTO-GITIGNORE: transient noise that should never have been tracked
  # -------------------------------------------------------------------------
  gi_match=0
  gi_pattern=""
  case "$path" in
    logs/*) gi_match=1; gi_pattern="logs/" ;;
  esac
  if [[ "$gi_match" -eq 0 ]]; then
    case "$bname" in
      *.log)      gi_match=1; gi_pattern="*.log" ;;
      *.pid)      gi_match=1; gi_pattern="*.pid" ;;
      .DS_Store)  gi_match=1; gi_pattern=".DS_Store" ;;
      Thumbs.db)  gi_match=1; gi_pattern="Thumbs.db" ;;
    esac
  fi
  if [[ "$gi_match" -eq 1 ]]; then
    gitignore_paths+=("$path")
    gitignore_patterns+=("$gi_pattern")
    cnt_gitignore=$(( cnt_gitignore + 1 ))
    continue
  fi

  # -------------------------------------------------------------------------
  # 6. AUTO-COMMIT: known-safe housekeeping roots (allow-list, first-match)
  # -------------------------------------------------------------------------
  commit_match=0
  commit_root=""

  # Exact-file match first
  case "$path" in
    state/coordinator-improvement-queue.md)
      commit_match=1; commit_root="state/coordinator-improvement-queue.md"
      ;;
  esac

  # Prefix matches
  if [[ "$commit_match" -eq 0 ]]; then
    case "$path" in
      cross-repo/inbox/*)        commit_match=1; commit_root="cross-repo/inbox/" ;;
      cross-repo/archive/*)      commit_match=1; commit_root="cross-repo/archive/" ;;
      state/review-trail/*)      commit_match=1; commit_root="state/review-trail/" ;;
      state/memos/*)             commit_match=1; commit_root="state/memos/" ;;
      state/lessons-outbox/*)    commit_match=1; commit_root="state/lessons-outbox/" ;;
      state/improvement-queue/*) commit_match=1; commit_root="state/improvement-queue/" ;;
      state/debt-backlog/*)      commit_match=1; commit_root="state/debt-backlog/" ;;
      state/bug-backlog/*)       commit_match=1; commit_root="state/bug-backlog/" ;;
      state/lesson-triage-recheck-due-*)
        commit_match=1; commit_root="state/lesson-triage-recheck-due-" ;;
      tasks/learn-lessons-*)     commit_match=1; commit_root="tasks/learn-lessons-" ;;
      tasks/audits/*)            commit_match=1; commit_root="tasks/audits/" ;;
      tasks/daily-review-scratch/*)
        commit_match=1; commit_root="tasks/daily-review-scratch/" ;;
      archive/*)                 commit_match=1; commit_root="archive/" ;;
    esac
  fi

  # Glob-style matches for docs/plans/ pre-flight sidecars
  if [[ "$commit_match" -eq 0 ]]; then
    case "$path" in
      docs/plans/*.plan-coverage-check.md|\
      docs/plans/*.prior-art-check.md|\
      docs/plans/*.external-pattern-check.md)
        commit_match=1; commit_root="docs/plans/<sidecar>"
        ;;
    esac
  fi

  if [[ "$commit_match" -eq 1 ]]; then
    commit_paths+=("$path")
    _record_root "$commit_root"
    cnt_commit=$(( cnt_commit + 1 ))
    continue
  fi

  # -------------------------------------------------------------------------
  # 7. SOURCE-TREE: paths under source-tree roots
  # -------------------------------------------------------------------------
  source_match=0
  case "$path" in
    plugins/*|\
    bin/*|\
    hooks/*|\
    lib/*|\
    tests/*|\
    schemas/*|\
    docs/wiki/*|\
    docs/decisions/*|\
    setup/*|\
    skills/*|\
    agents/*|\
    snippets/*|\
    commands/*)
      source_match=1
      ;;
    docs/plans/*)
      # docs/plans/ sidecars already caught above; anything else is source-tree
      source_match=1
      ;;
  esac

  if [[ "$source_match" -eq 1 ]]; then
    echo "[step2.5] source-tree: $path" >&2
    cnt_source=$(( cnt_source + 1 ))
    needs_pm=1
    continue
  fi

  # -------------------------------------------------------------------------
  # 8. AMBIGUOUS
  # -------------------------------------------------------------------------
  echo "[step2.5] ambiguous: $path" >&2
  cnt_ambiguous=$(( cnt_ambiguous + 1 ))
  needs_pm=1

done < <(git status --porcelain --untracked-files=all 2>/dev/null)

# ---------------------------------------------------------------------------
# Act: AUTO-GITIGNORE
# ---------------------------------------------------------------------------
if [[ "${#gitignore_paths[@]}" -gt 0 ]]; then
  GI_FILE="$REPO_ROOT/.gitignore"
  patterns_committed=()
  gi_committed_paths=()

  for i in "${!gitignore_paths[@]}"; do
    p="${gitignore_paths[$i]}"
    pat="${gitignore_patterns[$i]}"

    # Add pattern to .gitignore if not already present
    if ! _pattern_in_gitignore "$pat" "$GI_FILE"; then
      _append_to_gitignore "$pat" "$GI_FILE"
    fi

    # Track which patterns we touched for the commit message
    already_seen=0
    for sp in "${patterns_committed[@]+"${patterns_committed[@]}"}"; do
      [[ "$sp" == "$pat" ]] && { already_seen=1; break; }
    done
    [[ "$already_seen" -eq 0 ]] && patterns_committed+=("$pat")

    # git rm --cached if the file is tracked (not untracked)
    if git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[step2.5] DRY-RUN: would git rm --cached -- $p" >&2
      else
        git rm --cached -- "$p" 2>/dev/null || true
      fi
    fi

    gi_committed_paths+=("$p")
  done

  # Build comma-sep pattern list for commit message
  pattern_list=""
  for pat in "${patterns_committed[@]+"${patterns_committed[@]}"}"; do
    [[ -z "$pattern_list" ]] && pattern_list="$pat" || pattern_list="${pattern_list}, ${pat}"
  done

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[step2.5] DRY-RUN: would commit .gitignore + ${#gi_committed_paths[@]} paths: chore(gitignore): exclude orphaned transients at workday-complete" >&2
  else
    # Stage .gitignore explicitly
    git add -- "$GI_FILE" 2>/dev/null || true
    git commit -m "chore(gitignore): exclude orphaned transients at workday-complete" -- "$GI_FILE" 2>/dev/null || {
      echo "[step2.5] ERROR: gitignore commit failed" >&2
      exit 1
    }
  fi
fi

# ---------------------------------------------------------------------------
# Act: AUTO-COMMIT
# ---------------------------------------------------------------------------
if [[ "${#commit_paths[@]}" -gt 0 ]]; then
  # Build root list for commit message
  roots_str=""
  for r in "${commit_roots_seen[@]+"${commit_roots_seen[@]}"}"; do
    [[ -z "$roots_str" ]] && roots_str="$r" || roots_str="${roots_str}, ${r}"
  done
  n_paths="${#commit_paths[@]}"
  commit_msg="chore: adopt orphaned WT housekeeping at workday-complete (${n_paths} paths under ${roots_str})"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[step2.5] DRY-RUN: would commit ${n_paths} paths under ${roots_str}" >&2
    for p in "${commit_paths[@]}"; do
      echo "[step2.5] DRY-RUN:   $p" >&2
    done
  else
    git add -- "${commit_paths[@]}" 2>/dev/null || {
      echo "[step2.5] ERROR: git add for auto-commit paths failed" >&2
      exit 1
    }
    # Check if there's actually something staged (untracked files that are new
    # vs tracked files that changed; git add handles both)
    if git diff --cached --quiet 2>/dev/null; then
      : # nothing staged — already committed or identical; no-op
    else
      git commit -m "$commit_msg" -- "${commit_paths[@]}" 2>/dev/null || {
        echo "[step2.5] ERROR: auto-commit failed" >&2
        exit 1
      }
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Summary output (stdout)
# ---------------------------------------------------------------------------
[[ "$cnt_eol"      -gt 0 ]] && echo "[step2.5] EOL-phantom skipped: ${cnt_eol}"
[[ "$cnt_sub"      -gt 0 ]] && echo "[step2.5] submodule skipped: ${cnt_sub}"
[[ "$cnt_leave"    -gt 0 ]] && echo "[step2.5] leave-alone skipped: ${cnt_leave}"
[[ "$cnt_orphan"   -gt 0 ]] && echo "[step2.5] orphan-tmp listed (no action): ${cnt_orphan}"

if [[ "$cnt_gitignore" -gt 0 ]]; then
  gi_pat_list=""
  for pat in "${gitignore_patterns[@]+"${gitignore_patterns[@]}"}"; do
    already=0
    for sp in ${gi_pat_list//,/ }; do
      [[ "$sp" == "$pat" ]] && { already=1; break; }
    done
    [[ "$already" -eq 0 ]] && { [[ -z "$gi_pat_list" ]] && gi_pat_list="$pat" || gi_pat_list="${gi_pat_list}, ${pat}"; }
  done
  echo "[step2.5] gitignore + commit: ${cnt_gitignore} paths, patterns: ${gi_pat_list}"
fi

if [[ "$cnt_commit" -gt 0 ]]; then
  roots_str2=""
  for r in "${commit_roots_seen[@]+"${commit_roots_seen[@]}"}"; do
    [[ -z "$roots_str2" ]] && roots_str2="$r" || roots_str2="${roots_str2}, ${r}"
  done
  echo "[step2.5] auto-commit: ${cnt_commit} paths under ${roots_str2}"
fi

[[ "$cnt_source"   -gt 0 ]] && echo "[step2.5] source-tree (needs PM): ${cnt_source}"
[[ "$cnt_ambiguous" -gt 0 ]] && echo "[step2.5] ambiguous (needs PM): ${cnt_ambiguous}"

# Final verdict
if [[ "$needs_pm" -eq 1 ]]; then
  echo "[step2.5] NEEDS-PM"
  exit 2
else
  echo "[step2.5] OK"
  exit 0
fi
