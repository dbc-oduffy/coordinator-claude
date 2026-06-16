#!/usr/bin/env bash
# PreToolUse(Bash) hook: blocks blanket `git add` forms inside the ~/.claude
# meta-repo, where sibling-session scope-corruption is the live failure mode.
#
# Purpose: `git add -A`, `git add .`, `git add --all`, `git add -u`, and
# bundled short-flag equivalents stage ALL modified/untracked files in the
# working tree, silently sweeping a sibling executor's in-progress edits into
# an unrelated commit. This hook prevents that class of scope-corruption at
# the tool boundary.
#
# Spec backlink: docs/plans/2026-06-15-harden-safe-commit-against-sibling-add-all.md
# Tripwire entry: docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD
# Doctrine: docs/wiki/scoped-safety-commits.md § SC-DR-008 / SC-DR-014
#
# Scope — cwd guard (IMPORTANT):
#   This hook is designed to fire only when the working directory is inside
#   the ~/.claude meta-repo. Consumer repos that receive this hook via plugin
#   percolation are NOT blocked — the cwd guard makes the hook a no-op outside
#   the meta-repo. The hook's presence in hooks.json is what enables it in
#   consumer repos; the cwd guard is what limits enforcement to meta-repo only.
#
# Escape hatches:
#   Two env vars unlock blanket-add when genuinely needed:
#     COORDINATOR_OVERRIDE_BLANKET_ADD=1   — operator-level override
#     _COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET=1  — used by coordinator-safe-commit
#                                                     --blanket internally
#
#   IMPORTANT — inline-prefix-is-useless property:
#     The env var is read from the hook-process environment, NOT an inline
#     `COORDINATOR_OVERRIDE_BLANKET_ADD=1 git add -A` prefix. An inline prefix
#     sets the variable in the child process (git add), not in this hook's
#     process, so it NEVER reaches this guard. Export the variable before
#     running the command, e.g.:
#       export COORDINATOR_OVERRIDE_BLANKET_ADD=1
#       git add -A
#       unset COORDINATOR_OVERRIDE_BLANKET_ADD
#
# KNOWN v1 limitations:
#   - Command-substitution (`git add $(echo -A)`) passes through undetected.
#   - Variable-expansion (`git add $FLAG`) passes through undetected.
#   - Here-doc bodies containing `git add -A` as text pass through undetected.
#   (Same documentation class as block-destructive-rm.sh:46-48.)
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.

set -uo pipefail

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
# Review: code-reviewer — &>/dev/null is bash 4+ syntax; must use >/dev/null 2>&1 so the script parses on bash 3.2 (CLAUDE.md § Cross-platform shell)
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
  # NOTE: no timeout fallback on systems without GNU coreutils; matches block-destructive-rm.sh pattern. If hangs surface in practice, replace with 'read -t 2' loop.
fi

# --- Parse tool_name + command (jq -> python -> sed/grep fallback) ---
if command -v jq >/dev/null 2>&1; then
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

# Fast bail: nothing to do unless `git add` appears somewhere.
printf '%s\n' "$CMD" | grep -qE '\bgit[[:space:]]+add\b' || exit 0

# --- Cwd guard (fail-OPEN if not in ~/.claude meta-repo) ---
# Resolve the git root of the current working directory. If it equals $HOME/.claude
# (by inode, not string — avoids Windows Git-Bash path-style mismatches between
# /c/Users/... and C:/Users/... representations), we are in the meta-repo and the
# hook is active. Otherwise, exit 0 immediately (no-op in consumer repos).
GIT_ROOT=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$GIT_ROOT" ]]; then
  exit 0
fi
META_ROOT=$(realpath "${HOME}/.claude" 2>/dev/null || readlink -f "${HOME}/.claude" 2>/dev/null || echo "${HOME}/.claude")
# -ef compares inodes/device — avoids path-representation mismatches on Windows Git Bash
if [[ ! "$GIT_ROOT" -ef "$META_ROOT" ]]; then
  exit 0
fi

# --- Escape hatches (fail-OPEN if either env is set) ---
if [[ "${COORDINATOR_OVERRIDE_BLANKET_ADD:-0}" == "1" || "${_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET:-0}" == "1" ]]; then
  OVERRIDE_LOG="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID:-no-session}/overrides.log"
  mkdir -p "$(dirname "$OVERRIDE_LOG")" 2>/dev/null || true
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${SESSION_ID:-no-session} | OVERRIDE-BLANKET-GIT-ADD | $(printf '%s' "$CMD" | head -c 120)" >> "$OVERRIDE_LOG" 2>/dev/null || true
  exit 0
fi

# --- Helpers ---
deny() {
  local reason="$1"
  if command -v jq >/dev/null 2>&1; then
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

# --- Segment-split & evaluation ---
# Collapse all shell separators (;  &&  ||  |  &) to newlines so each
# atomic command is evaluated independently. Erring toward MORE segments =
# more checks, never fewer (mirrors block-destructive-rm.sh:131-135 idiom).
SEGMENTS=$(printf '%s' "$CMD" | sed -E 's/[;&|]+/\n/g')

MATCHED_CMD=""

while IFS= read -r SEG; do
  [[ -z "${SEG//[[:space:]]/}" ]] && continue

  # Must contain `git add` to be relevant.
  printf '%s\n' "$SEG" | grep -qE '\bgit[[:space:]]+add\b' || continue

  # Extract everything after `git add` (the args portion).
  AFTER=$(echo "$SEG" | sed -E 's/.*\bgit[[:space:]]+add[[:space:]]*//')

  # Track whether we've passed a `--` end-of-options marker.
  # `-A`, `-u`, etc. before `--` still denote blanket adds even if paths follow.
  PAST_DOUBLE_DASH=0
  SHOULD_DENY=0
  DENY_REASON=""

  # Tokenize args; evaluate each token.
  for tok in $AFTER; do
    if [[ "$tok" == "--" ]]; then
      PAST_DOUBLE_DASH=1
      continue
    fi

    # Once past `--`, remaining tokens are literal paths — not flags.
    [[ "$PAST_DOUBLE_DASH" == "1" ]] && continue

    # Check for explicit long-form blanket flags.
    if [[ "$tok" == "--all" || "$tok" == "--update" ]]; then
      SHOULD_DENY=1
      DENY_REASON="$tok"
      break
    fi

    # Check for the literal dot / dot-slash (stages everything in cwd tree).
    if [[ "$tok" == "." || "$tok" == "./" ]]; then
      SHOULD_DENY=1
      DENY_REASON="$tok"
      break
    fi

    # Check for short-flag bundles (tokens starting with `-`, no `/` or `.`).
    # A path token starting with `-` would be unusual and contain `/` or `.`;
    # a flag token starts with `-` and contains only alpha chars + more dashes.
    # Deny if the bundle contains A (--all equivalent) or u/U (--update equivalent).
    # Pattern: token starts with `-`, has no `/` or second `.`, and contains A or u.
    if [[ "$tok" == -* && "$tok" != "--"* ]]; then
      # Exclude path-like tokens (contain / or start with ./)
      if [[ "$tok" != */* && "$tok" != "./"* ]]; then
        # Strip the leading `-` and check for A or u in the remainder.
        FLAG_CHARS="${tok#-}"
        if [[ "$FLAG_CHARS" == *A* || "$FLAG_CHARS" == *u* || "$FLAG_CHARS" == *U* ]]; then
          SHOULD_DENY=1
          DENY_REASON="$tok"
          break
        fi
      fi
    fi
  done

  if [[ "$SHOULD_DENY" == "1" ]]; then
    # Truncate the matched command for display.
    FULL_SEG_TRIMMED=$(printf '%s' "$SEG" | sed 's/^[[:space:]]*//' | head -c 120)
    # Review: code-reviewer — DENY_REASON was dead code (set but never used); now incorporated into MATCHED_CMD for actionable deny output
    MATCHED_CMD="${FULL_SEG_TRIMMED} [matched flag: ${DENY_REASON}]"
    break
  fi

done <<< "$SEGMENTS"

# If no blanket pattern matched, allow.
[[ -z "$MATCHED_CMD" ]] && exit 0

# --- Emit deny ---
REASON="BLOCKED: blanket \`git add\` detected in the ~/.claude meta-repo (SC-DR-014).

Matched command: ${MATCHED_CMD}

Blanket staging (\`git add -A\`, \`git add .\`, \`git add --all\`, \`git add -u\`, \`git add --update\`,
or bundled short-flag equivalents) sweeps ALL modified/untracked files from the working tree into the
commit — including files being edited by sibling executor sessions, silently corrupting their diffs.

Use scoped staging instead (SC-DR-008 default):
  git add -- path/to/file1 path/to/file2
  git commit -m \"<subject>\" -- path/to/file1 path/to/file2

Escape hatches (if blanket staging is genuinely required):
  1. Export COORDINATOR_OVERRIDE_BLANKET_ADD=1 in your environment BEFORE running
     (an inline prefix does NOT reach this hook — see inline-prefix-is-useless property in script header).
  2. Use coordinator-safe-commit --blanket (sets _COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET=1 internally).

Reference: docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD"

deny "$REASON"
