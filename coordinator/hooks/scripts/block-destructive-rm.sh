#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks `rm` of a directory/tree that holds work git
# CANNOT recover — uncommitted modifications, untracked files, or the .git store
# itself — unless the loss is proven safe or explicitly overridden.
#
# Motivation: sibling to block-destructive-git-orphan.sh. That hook closes the
# COMMITTED-work loss class (reset --hard / force-push / branch -D). This hook
# closes the UNCOMMITTED-work loss class — the other half of the 2026-05-28
# flakiness near-miss surface. When the tool-output channel hands the model an
# empty/garbled result, the model can confabulate a plausible-but-false premise
# ("this directory is a stale duplicate, safe to delete") and drive an
# `rm -rf <path>` against real in-progress work. `git checkout` / reflog recover
# committed and staged content; they CANNOT recover untracked files or
# unstaged modifications, and nothing recovers a deleted .git store. That is the
# only file loss git cannot undo, so it is exactly what this hook guards.
#
# Like the orphan guard, the enforcement is at the tool boundary: the decision is
# re-derived from FRESH `git status` against the real target, independent of
# anything the model believes, and applied BEFORE the model narrates the result —
# so it holds even when the return channel that triggered the confabulation is
# itself flaky. Diagnosis: docs/architecture/audit-records/2026-05-29-tool-output-flakiness-diagnosis.md
#
# Trigger scope (deliberately narrow, to stay an offer not a nag):
#   - Only `rm` with recursive intent (-r/-R/--recursive) OR a target that is an
#     existing directory. A single-file `rm scratch.txt` is low-blast-radius and
#     left alone — guarding it would make the hook noisy and invite stripping.
#   - `git rm` is SKIPPED — it stages a tracked-file removal that git recovers.
#     The skip tolerates git's global options between `git` and the `rm`
#     subcommand (`git -C <path> rm`, `git -c k=v rm`, `git --no-pager rm`, …) —
#     a bare `\bgit[[:space:]]+rm\b` would miss `git -C <path> rm` and then
#     mis-evaluate the `-C` path as a raw-rm target against the wrong repo.
#
# Disposability is defined by GIT, not a hand-maintained allowlist: targets whose
# content is fully committed (clean) pass; gitignored trees (node_modules, build,
# .venv, __pycache__, dist) never appear in `git status --porcelain` so they pass
# automatically; targets OUTSIDE any git repo pass (scratch lives there, and the
# work this setup cares about lives in repos). DENY fires only when real,
# unrecoverable, in-repo work would be lost.
#
# KNOWN v1 limitations:
#   - Literal path targets only. `rm -rf $VAR` / glob `rm -rf *` are not resolved
#     (allowed); `rm -rf $(...)`/backtick targets under a recursive flag fail SAFE
#     (deny) — same unverifiable-target stance as the orphan guard.
#   - Bash only. PowerShell `Remove-Item` is a separate tool with no matcher here
#     (flagged residual — see the diagnosis doc).
#   - Evaluates against the literal target path; a `cd <dir> && rm -rf sub` is
#     resolved relative to the hook cwd, not the cd target (same class as
#     block-off-daily-branch.sh). Relative targets ARE resolved to absolute for
#     the git-status check, so a cwd-is-subdirectory `rm -rf sub` is handled.
#   - Comments / here-doc bodies are not stripped, so a segment like
#     `echo '# rm tmp'` whose word `rm` is followed by a real existing path in a
#     dirty repo can produce a benign false-positive deny (override-recoverable).
#   - Token extraction takes the text after the LAST `\brm\b` in a segment; with
#     separator-splitting done first this only bites a single separator-free
#     segment containing two bare `rm` words (rare; `git rm` is already skipped).
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
# Override: export COORDINATOR_ALLOW_RM=1 in the environment (NOT an inline
# prefix — that sets the var for the rm child, not this hook process).

set -uo pipefail

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Parse tool_name + command (jq -> python -> sed/grep fallback) ---
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
  CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  CMD=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
fi

[[ "$TOOL_NAME" != "Bash" ]] && exit 0
[[ -z "$CMD" ]] && exit 0

# Join backslash-newline continuations so a split op is one segment.
NL=$'\n'
CMD="${CMD//\\$NL/ }"

# Fast bail: nothing to do unless an `rm` appears.
echo "$CMD" | grep -qE '\brm\b' || exit 0

# Escape hatch (honored early).
[[ "${COORDINATOR_ALLOW_RM:-0}" == "1" ]] && exit 0

# --- Helpers ---
strip_q() {
  local t="$1"
  t="${t%\"}"; t="${t#\"}"
  t="${t%\'}"; t="${t#\'}"
  printf '%s' "$t"
}

deny() {
  local reason="$1"
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "$PY" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "$PY" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

OVERRIDE_HINT="If this deletion is genuinely intended, export COORDINATOR_ALLOW_RM=1 in your environment first (an inline prefix on the rm command does NOT reach this hook)."

# Resolve the current git repo root once. Used by the scratch allowlist to scope
# the exemption to THIS repo only — so tasks/*-scratch in a sibling repo does
# not accidentally inherit the exemption when referenced by absolute path.
CUR_REPO=$(git rev-parse --show-toplevel 2>/dev/null || true)

# --- Evaluate each command segment independently. Separators ; && || | & all
# collapse to newlines; erring toward MORE segments = more checks, never fewer. ---
SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

while IFS= read -r SEG; do
  [[ -z "${SEG//[[:space:]]/}" ]] && continue
  # Must contain a bare `rm`. Skip `git rm` (staged removal, git-recoverable),
  # tolerating git global options (-C <path>, -c <kv>, --git-dir, --work-tree,
  # --no-pager, …) between `git` and the `rm` subcommand.
  # Defense-in-depth: the separator split above (sed on [;&|]) is the PRIMARY
  # isolation — `git log && rm -rf x` is already two segments, so the `rm` segment
  # carries no `git` prefix. This `\bgit…rm\b` skip is the SECONDARY check within a
  # single separator-free segment. `-C` (path) and `-c` (config kv) are separate
  # arms — both take exactly one value token, but git's semantics differ.
  echo "$SEG" | grep -qE '\brm\b' || continue
  echo "$SEG" | grep -qE '\bgit([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|--(git-dir|work-tree|namespace)(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)|--exec-path(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)?|-p|--paginate|--no-pager|--bare|--no-replace-objects|--literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs|--no-optional-locks))*[[:space:]]+rm\b' && continue

  # Tokens after the `rm` verb.
  AFTER=$(echo "$SEG" | sed -E 's/.*\brm\b//')

  # Recursive intent? (-r / -R / --recursive, bundled like -rf / -fr)
  RECURSIVE=0
  if echo "$AFTER" | grep -qE '(^|[[:space:]])-[a-zA-Z]*[rR][a-zA-Z]*([[:space:]]|$)|--recursive'; then
    RECURSIVE=1
  fi

  # Unverifiable target under recursive intent -> fail safe (deny).
  if [[ "$RECURSIVE" == "1" ]] && echo "$AFTER" | grep -qE '\$\(|`'; then
    deny "BLOCKED: 'rm' with a recursive flag and a subshell-resolved target (\$(...) or backticks) cannot be verified safe — the hook will not run the subshell to learn what it would delete.

Resolve the target to a literal path first and re-check what lives there:
  git status --porcelain -- <resolved-path>   # uncommitted/untracked work that rm would destroy

${OVERRIDE_HINT}"
  fi

  # Collect literal (non-flag) path tokens, quote-stripped. Tokens carrying an
  # unresolved var ($VAR), glob (*?[), or NON-recursive subshell are skipped as a
  # documented v1 limitation (the recursive-subshell case already failed safe
  # above; a non-recursive `rm $(...)` can only delete files, since `rm` refuses
  # a directory without -r, so its blast radius is bounded to single files).
  TARGETS=()
  for tok in $AFTER; do
    case "$tok" in
      --) continue ;;
      -*) continue ;;
      *\$*|*\**|*\?*|*\[*) continue ;;
      *) TARGETS+=("$(strip_q "$tok")") ;;
    esac
  done

  [[ "${#TARGETS[@]}" -eq 0 ]] && continue
  for TGT in "${TARGETS[@]}"; do
    [[ -z "$TGT" ]] && continue
    # Nothing to lose if it does not exist.
    [[ -e "$TGT" ]] || continue

    # Resolve to an absolute path (relative tokens resolve against the hook cwd,
    # which is where the real `rm` would run). Required so the git-status pathspec
    # below is interpreted against the right location even when cwd is a repo
    # SUBDIRECTORY — a relative pathspec under `git -C <root>` would otherwise
    # resolve against the root and silently miss the work.
    # realpath/`readlink -f` are GNU; stock macOS (BSD) lacks `readlink -f` and older
    # macOS lacks `realpath` — fall back to python3 (already resolved into $PY) before the
    # bare-echo degradation, so a relative target still resolves to absolute on BSD hosts.
    TGT_ABS=$(realpath "$TGT" 2>/dev/null \
      || readlink -f "$TGT" 2>/dev/null \
      || { [[ -n "$PY" ]] && "$PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TGT" 2>/dev/null; } \
      || echo "$TGT")

    # Any part of a .git store is irreversible repo corruption — deny regardless
    # of which repo it belongs to and without needing to resolve a worktree root
    # (which `git rev-parse` cannot do from INSIDE .git). The `*/.git` glob matches
    # `.git` and `.git/objects` etc. but NOT bare-repo names like `foo.git`.
    if [[ "$TGT_ABS" == *"/.git" || "$TGT_ABS" == *"/.git/"* || "$(basename "$TGT_ABS")" == ".git" ]]; then
      deny "BLOCKED: 'rm' would delete part of the git store at '${TGT}'. This corrupts/destroys repository history irreversibly — no checkout, reflog, or stash recovers it.

${OVERRIDE_HINT}"
    fi

    # Allowlist: regenerable coordinator scratch directories.
    # These are created fresh each run by coordinator skills (e.g. /workday-complete
    # Step 4f creates tasks/daily-review-scratch). They may contain untracked files
    # by design — that is what makes them look dirty to git — but they hold no
    # irrecoverable work.
    #
    # Hardened allowlist — all conditions must hold:
    #   (a) Not a symlink — realpath-following a symlink could match against an
    #       unintended target; fall through to normal deny evaluation. The trailing
    #       slash is stripped before the `-L` test (`-L dir/` dereferences the link and
    #       mis-reports a symlink as a non-link, which would re-open the allowlist fast
    #       path for `rm -rf tasks/<sym>-scratch/` — F9).
    #   (b) Scoped to THIS repo — only allow when $TGT_ABS is exactly
    #       <repo-root>/tasks/<name>-scratch. "Any tasks/*-scratch anywhere on
    #       disk" is too broad; only THIS repo's regenerable scratch is exempt.
    #   (c) Basename matches ^[a-zA-Z0-9_-]+-scratch$ — rejects dotfile-ish
    #       names like .git-scratch that could sneak through.
    #
    #   Preferred v2: let coordinator skills write to a gitignored location
    #   (e.g. tasks/.scratch/) so git treats them as disposable automatically
    #   and no allowlist is needed.
    SCRATCH_BN=$(basename "$TGT_ABS")
    SCRATCH_PAR_ABS=$(dirname "$TGT_ABS")
    SCRATCH_REPO=$(git -C "$SCRATCH_PAR_ABS" rev-parse --show-toplevel 2>/dev/null || true)
    # Use -ef (inode/device equality) to compare paths — avoids Windows Git Bash
    # path-style mismatches between realpath (/c/Users/...) and git rev-parse
    # (C:/Users/...) representations of the same directory.
    # CUR_REPO -ef SCRATCH_REPO ensures the scratch dir belongs to THIS repo,
    # not a sibling repo that happens to have a tasks/*-scratch by the same name.
    if [[ -n "$SCRATCH_REPO" \
          && -n "$CUR_REPO" \
          && "$CUR_REPO" -ef "$SCRATCH_REPO" \
          && ! -L "${TGT%/}" \
          && -d "${SCRATCH_REPO}/tasks" \
          && "$SCRATCH_PAR_ABS" -ef "${SCRATCH_REPO}/tasks" \
          && "$SCRATCH_BN" =~ ^[a-zA-Z0-9_-]+-scratch$ ]]; then
      continue  # regenerable coordinator scratch in THIS repo — allow without git-status check
    fi

    # Only evaluate trees: a directory target, or a file under recursive intent.
    if [[ -d "$TGT" || "$RECURSIVE" == "1" ]]; then
      # Resolve the enclosing repo from the target's parent. Outside any git
      # repo -> allow (scratch lives there).
      ROOT=$(git -C "$(dirname "$TGT_ABS")" rev-parse --show-toplevel 2>/dev/null || true)
      [[ -z "$ROOT" ]] && continue

      # Uncommitted/untracked work under the target (gitignored paths excluded by
      # git, so node_modules/build/.venv pass automatically). Non-empty -> loss.
      # Single status call (bound traversal with head); the count is derived from
      # the same capture to avoid a second invocation and a TOCTOU display race.
      STATUS=$(git -C "$ROOT" status --porcelain -- "$TGT_ABS" 2>/dev/null | head -9)
      if [[ -n "$STATUS" ]]; then
        DISP=$(printf '%s\n' "$STATUS" | head -8)
        MORE=""
        [[ "$(printf '%s\n' "$STATUS" | grep -c .)" -gt 8 ]] && MORE="
  ... and more (first 8 shown)"
        deny "BLOCKED: 'rm' on '${TGT}' would destroy uncommitted/untracked work that git CANNOT recover (untracked files and unstaged edits live in no commit, no stash, no reflog):
${DISP}${MORE}

Before overriding, re-derive what would actually be lost (do not trust a remembered or narrated state):
  git -C \"${ROOT}\" status --porcelain -- \"${TGT_ABS}\"

To preserve the work first, commit or stash it:
  git -C \"${ROOT}\" add -- \"${TGT_ABS}\" && git -C \"${ROOT}\" stash push -- \"${TGT_ABS}\"

If these items are genuinely disposable, ${OVERRIDE_HINT}"
      fi
    fi
  done

done <<< "$SEGMENTS"

# No covered destructive rm (or all evaluated as safe) -> allow.
exit 0
