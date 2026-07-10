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
#   - Deeply-nested or mismatched quote-escaping (e.g. multiple layers of `\\"`)
#     is best-effort; pathologically crafted escape sequences may slip through.
#   - The `env(1)` command prefix (`env VAR=value git add -A`, or bare `env git add -A`)
#     bypasses the anchor — only inline `VAR=value` assignment prefixes are parsed, not
#     the external `env` command. (Same accepted class as command-substitution / $VAR.)
#   (Same documentation class as block-destructive-rm.sh:46-48.)
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.
#
# Sourceable: sourcing this file ONLY defines check_blanket_git_add().
# Main-guard at bottom handles standalone hook invocation (reads stdin once).

# ---------------------------------------------------------------------------
# check_blanket_git_add <command> <session_id>
#
# Evaluate one Bash tool command for blanket `git add` patterns in the
# ~/.claude meta-repo.  Prints Form-A deny JSON on deny; prints nothing on
# allow.  Returns 0 in both cases (deny is signalled by output, not exit code).
#
# $1 — the Bash tool command string (tool_input.command from the hook payload)
# $2 — the session_id from the hook payload (may be empty)
#
# Negative-spec: does NOT read stdin — caller is responsible for parsing the
# hook payload and passing command+session_id.  Fully self-contained: computes
# its own git root resolution and meta-repo cwd-guard.
# ---------------------------------------------------------------------------
check_blanket_git_add() {
  local cmd="$1"
  local sid="$2"

  # Detect python for JSON encoding fallback (used by _blanket_deny below).
  local _blanket_py
  _blanket_py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  # --- Inline helper: emit Form-A deny JSON, then return (NOT exit). ---
  # Negative-spec: does NOT call exit — sourced callers must not have their
  # shell terminated by a deny; the main-guard `exit 0` handles standalone exit.
  # _blanket_py is accessed via bash dynamic scoping from the enclosing function.
  _blanket_deny() {
    local reason="$1"
    if command -v jq >/dev/null 2>&1; then
      jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
    elif [[ -n "$_blanket_py" ]]; then
      local rj
      rj=$(printf '%s' "$reason" | "$_blanket_py" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
        || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
    else
      local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
    fi
  }

  [[ -z "$cmd" ]] && return 0

  # Normalize CRLF -> LF first. On Windows/Git-Bash the native jq.exe emits its
  # output in text mode, injecting a CR before every LF, so a command carrying a
  # real newline reaches this function as `\<CR><LF>` (backslash CR LF), not
  # `\<LF>`. A bare CR is never a meaningful shell token, so stripping every CR is
  # safe and makes the whole function CRLF-robust — without it the join below and
  # the awk segment-split silently miss any continuation on Windows.
  # (Matches the CR-strip in block-destructive-git-orphan.sh — kept consistent.)
  cmd="${cmd//$'\r'/}"

  # Join backslash-newline continuations so a split op is one segment.
  local nl=$'\n'
  cmd="${cmd//\\$nl/ }"

  # Fast bail: nothing to do unless `git add` appears somewhere.
  printf '%s\n' "$cmd" | grep -qE '\bgit[[:space:]]+add\b' || return 0

  # --- Cwd guard (fail-OPEN if not in ~/.claude meta-repo) ---
  # Resolve the git root of the current working directory. If it equals $HOME/.claude
  # (by inode, not string — avoids Windows Git-Bash path-style mismatches between
  # /c/Users/... and C:/Users/... representations), we are in the meta-repo and the
  # hook is active. Otherwise, return 0 immediately (no-op in consumer repos).
  local git_root
  git_root=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -z "$git_root" ]]; then
    return 0
  fi
  local meta_root
  meta_root=$(realpath "${HOME}/.claude" 2>/dev/null || readlink -f "${HOME}/.claude" 2>/dev/null || echo "${HOME}/.claude")
  # -ef compares inodes/device — avoids path-representation mismatches on Windows Git Bash
  if [[ ! "$git_root" -ef "$meta_root" ]]; then
    return 0
  fi

  # --- Escape hatches (fail-OPEN if either env is set) ---
  if [[ "${COORDINATOR_OVERRIDE_BLANKET_ADD:-0}" == "1" || "${_COORDINATOR_SAFE_COMMIT_INTERNAL_BLANKET:-0}" == "1" ]]; then
    local override_log="${git_root}/.git/coordinator-sessions/${sid:-no-session}/overrides.log"
    mkdir -p "$(dirname "$override_log")" 2>/dev/null || true
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${sid:-no-session} | OVERRIDE-BLANKET-GIT-ADD | $(printf '%s' "$cmd" | head -c 120)" >> "$override_log" 2>/dev/null || true
    return 0
  fi

  # --- Segment-split & evaluation ---
  # Quote-aware segment split: split on unquoted shell operators (; & |) only.
  # Operators INSIDE single/double quotes (e.g. inside a commit -m message) are
  # NOT split points, so prose mentioning a blanket-add form does not mis-split.
  # Quote characters are PRESERVED in each segment so a quoted flag survives to
  # the flag check below (which normalizes them). cmd stays intact for the
  # deny message and override-log; only segmentation/matching uses this.
  # ACCEPTED GAPS (same class as before): command-substitution $(...),
  # variable-expansion $VAR, and deeply-nested/mismatched quote-escaping are not
  # interpreted (see header limitations).
  local segments
  segments=$(printf '%s' "$cmd" | awk '
BEGIN { sq = 0; dq = 0; seg = "" }
{
  # Quote-state persists across input records (newlines). Default RS makes each
  # line a record; the v1 bug initialized sq/dq/seg per record, resetting quote
  # tracking at every newline so a newline INSIDE a quoted -m message desynced
  # the machine and let a trailing `&& git add -A` escape the command anchor.
  # State now lives in BEGIN/END. At each record boundary (a newline in $CMD):
  #   - inside a quote  -> the newline is literal message content; re-append it
  #     and keep the segment open (quote-state stays as-is).
  #   - outside a quote -> the newline is a real command separator (the shell
  #     treats a bare newline like `;`); flush the segment. This preserves the
  #     v1 record-boundary split, so `git add -A` on its own line is still caught.
  if (NR > 1) {
    if (sq == 0 && dq == 0) { print seg; seg = "" }
    else { seg = seg "\n" }
  }
  n = length($0)
  for (i = 1; i <= n; i++) {
    c = substr($0, i, 1)
    if (c == "\047" && dq == 0) { sq = 1 - sq; seg = seg c; continue }
    if (c == "\042" && sq == 0) { dq = 1 - dq; seg = seg c; continue }
    if (sq == 0 && dq == 0 && (c == ";" || c == "&" || c == "|")) { print seg; seg = ""; continue }
    seg = seg c
  }
}
END { print seg }')

  local matched_cmd=""

  while IFS= read -r seg; do
    [[ -z "${seg//[[:space:]]/}" ]] && continue

    # `git add` must be the COMMAND — anchored to segment-start after stripping leading
    # whitespace and any VAR=value env-assignment prefixes. An occurrence of `git add`
    # inside a quoted argument to another command (echo/printf) must NOT trigger.
    # Negative-spec: bare substring match `\bgit add\b` fires on `echo "git add -A"` — wrong.
    #
    # Anchor is checked against a quote-SPAN-stripped copy so an env-prefix value
    # containing spaces (VAR="John Doe" git add -A) collapses to an empty value and
    # the env-prefix pattern stays parseable. The raw $seg (with quotes) is still
    # used below to extract the flag args. (The awk splitter already guarantees
    # operators inside quotes did not split this segment.)
    local seg_cmd
    seg_cmd=$(printf '%s' "$seg" | sed -E 's/"[^"]*"/ /g' | sed -E "s/'[^']*'/ /g")
    printf '%s\n' "$seg_cmd" | grep -qE '^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*git[[:space:]]+add\b' || continue  # Review: code-reviewer — \s is GNU-only; ^[[:space:]]* is the portable POSIX form (DR-148)

    # Extract everything after `git add` (the args portion).
    # BSD sed's ERE lacks \b (GNU-only extension); use the [[:space:]]-boundary
    # idiom so this strips the phrase identically on BSD and GNU. `\bgit\b` was a
    # silent NO-OP on BSD sed (DR-148 audit, 2026-07-10).
    local after
    after=$(echo "$seg" | sed -E 's/.*(^|[[:space:]])git[[:space:]]+add[[:space:]]*/ /')
    # Normalize quoted flags: strip residual quote chars so git add "-A", '.',
    # "--all", "-u" are detected the same as their unquoted forms. The awk
    # splitter preserves quotes in segments; they must be removed here before
    # flag matching. Applies to both the dry-run loop and the main token loop.
    after="${after//\"/}"   # drop double-quote chars — git add "-A" → -A
    after="${after//\'/}"   # drop single-quote chars — git add '.' → .
    after="${after//\\/}"   # backslashes (handles \"-A\" escaped forms)

    # Dry-run exemption: if --dry-run or a standalone -n token is present (before any --),
    # skip this segment. A dry-run git add stages nothing — blocking it produces false positives
    # on preview commands.
    # Note: -n bundled inside a flag group (e.g. -An) is NOT exempt; only a standalone -n token
    # before `--` qualifies. After `--` all tokens are literal paths — a path literally named
    # `-n` must NOT trip the exemption (Review: code-reviewer D-F1 — mirror `--` tracking from
    # the main eval loop so `git add -A -- -n` is correctly DENIED, not exempted).
    local dryrun_exempt=0 _past_dd=0
    local _drtok
    for _drtok in $after; do
      [[ "$_drtok" == "--" ]] && _past_dd=1 && continue
      [[ "$_past_dd" == "1" ]] && continue
      if [[ "$_drtok" == "--dry-run" || "$_drtok" == "-n" ]]; then dryrun_exempt=1; break; fi
    done
    if [[ "$dryrun_exempt" == "1" ]]; then
      continue
    fi

    # Track whether we've passed a `--` end-of-options marker.
    # `-A`, `-u`, etc. before `--` still denote blanket adds even if paths follow.
    local past_double_dash=0
    local should_deny=0
    local deny_reason=""
    local tok

    # Tokenize args; evaluate each token.
    for tok in $after; do
      if [[ "$tok" == "--" ]]; then
        past_double_dash=1
        continue
      fi

      # Once past `--`, remaining tokens are literal paths — not flags.
      [[ "$past_double_dash" == "1" ]] && continue

      # Check for explicit long-form blanket flags.
      if [[ "$tok" == "--all" || "$tok" == "--update" ]]; then
        should_deny=1
        deny_reason="$tok"
        break
      fi

      # Check for the literal dot / dot-slash (stages everything in cwd tree).
      if [[ "$tok" == "." || "$tok" == "./" ]]; then
        should_deny=1
        deny_reason="$tok"
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
          local flag_chars="${tok#-}"
          if [[ "$flag_chars" == *A* || "$flag_chars" == *u* || "$flag_chars" == *U* ]]; then
            should_deny=1
            deny_reason="$tok"
            break
          fi
        fi
      fi
    done

    if [[ "$should_deny" == "1" ]]; then
      # Truncate the matched command for display.
      local full_seg_trimmed
      full_seg_trimmed=$(printf '%s' "$seg" | sed 's/^[[:space:]]*//' | head -c 120)
      # Review: code-reviewer — DENY_REASON was dead code (set but never used); now incorporated into matched_cmd for actionable deny output
      matched_cmd="${full_seg_trimmed} [matched flag: ${deny_reason}]"
      break
    fi

  done <<< "$segments"

  # If no blanket pattern matched, allow.
  [[ -z "$matched_cmd" ]] && return 0

  # --- Emit deny ---
  local reason="BLOCKED: blanket \`git add\` detected in the ~/.claude meta-repo (SC-DR-014).

Matched command: ${matched_cmd}

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

  _blanket_deny "$reason"
  return 0
}

# ---------------------------------------------------------------------------
# Main guard — standalone hook invocation.
# Reads stdin exactly once, parses command + session_id, delegates to
# check_blanket_git_add.  When sourced, this block does NOT execute.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -uo pipefail

  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

  # --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
  # Use `>/dev/null 2>&1` (not `&>/dev/null`) for redirect style consistency across the hook set.
  if command -v timeout >/dev/null 2>&1; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
    # NOTE: no timeout fallback on systems without GNU coreutils; matches block-destructive-rm.sh pattern. If hangs surface in practice, replace with 'read -t 2' loop.
  fi

  # --- Parse tool_name + command + session_id (jq -> python -> sed/grep fallback) ---
  # Review: code-reviewer (F20) — extract SESSION_ID from payload so override-log entries
  # are keyed per-session rather than all landing in the shared no-session/ bucket.
  if command -v jq >/dev/null 2>&1; then
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
    SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  elif [[ -n "$PY" ]]; then
    TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
    CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
    SESSION_ID=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("session_id","")))' 2>/dev/null || true)
  else
    TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    CMD=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
    SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  [[ "$TOOL_NAME" != "Bash" ]] && exit 0
  [[ -z "$CMD" ]] && exit 0

  check_blanket_git_add "$CMD" "$SESSION_ID"
  exit 0
fi
