#!/usr/bin/env bash
# PreToolUse hook: blocks illegal filename components (NTFS-illegal chars) at the
# tool boundary, preventing colon-named or otherwise unresolvable paths from
# entering the git tree.
#
# Purpose: A file committed from a non-Windows machine with an NTFS-illegal
# character in its name (e.g. ':' — the Windows ADS separator) blocks
# `git checkout` on every Windows machine. This hook intercepts the Write/Edit/
# NotebookEdit/Bash tool boundary and denies path targets whose basename contains
# any NTFS-illegal character BEFORE they land on disk or in the index.
#
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § D1
# Tripwire entry: docs/wiki/coordinator-tripwires.md § BLOCK-ILLEGAL-FILENAME
# Doctrine: docs/wiki/cross-platform-shell-portability.md § Cross-platform safe filename components
#
# Class-3 universal-safety — FAIL-CLOSED. NO directory exemption:
#   tasks/, state/scratch/, and all other git-tracked paths are in-scope.
#   An NTFS-illegal char breaks the git tree regardless of directory.
#   (Platform-conditional guard taxonomy class-3 carve-out — B1.)
#
# TWO ARMS:
#
#   RELIABLE arm — Write | Edit | NotebookEdit:
#     Extracts tool_input.file_path (structured JSON field, always reliable).
#     Takes the basename and runs csn_check. If illegal → BLOCK.
#     Covers: new file creation + rename targets (any Write/Edit with a colon
#     in the file_path basename).
#
#   BEST-EFFORT arm — Bash:
#     Scans the command string for mv / git mv / --out <path> / shell
#     redirection targets and checks their basenames. This arm is EXPLICITLY
#     BEST-EFFORT — `mv $VAR "$dest"`, heredocs, multi-command lines, and
#     variable-expansion patterns defeat static extraction. Do NOT rely on this
#     arm for exhaustive coverage; the commit/merge backstop (D2, `check-no-
#     illegal-paths.sh`) is the real enforcement net for Bash-constructed paths.
#     POSTURE: NON-BLOCKING ADVISORY only — emits permissionDecision:"allow" +
#     additionalContext warning. Rationale: static command-string scanning provides
#     no guarantee the D2 backstop doesn't already cover, and was the sole source
#     of false positives (four incidents, most recently `2>&1` flagged as illegal
#     filename via greedy --out extraction). The reliable arm (above) is the only
#     blocking surface.
#
# Design-as-offers: the advisory message LEADS WITH the safe alternative,
# consistent with coordinator design-as-offers doctrine
# (docs/wiki/eager-agent-calibration.md). Both arms use make_deny_msg; only
# the reliable arm blocks — the Bash arm emits it as a non-blocking advisory.
#
# Escape hatch:
#   COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 — set in the hook-process environment
#   BEFORE the tool call. An inline prefix (e.g. `COORDINATOR_OVERRIDE_ILLEGAL_
#   FILENAME=1 mv a b:c`) sets the child's env, which this hook never sees —
#   export it first. Use only when the target platform is confirmed non-Windows
#   AND the path will never be checked out on Windows.
#
# Reliable arm (deny — Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Bash arm (advisory): emit permissionDecision:"allow" + additionalContext, exit 0.
# Allow (silent): exit 0, no stdout.
#
# KNOWN v1 LIMITATIONS (best-effort arm):
#   - `mv $DEST_VAR` (variable expansion): passes through undetected.
#   - Heredoc bodies containing path targets: passes through undetected.
#   - `mv a "b${SUFFIX}"` (concatenation): passes through undetected.
#   - Multi-hop redirections with dynamic components: passes through undetected.
#   - Quoted string stripping (best-effort): double- and single-quoted spans are
#     removed before redirect/mv scanning; does not handle escaped quotes or
#     multi-line spans (e.g. --body "foo \"bar\"" or a string split across lines).
#   - `&>file` (bash combined stdout+stderr redirect): `&` is not in the
#     token-boundary anchor set (^|[[:space:]]|[0-9]), so `&>file:illegal.md`
#     passes undetected. The commit/merge backstop is the net.
#   These limitations are identical in class to block-blanket-git-add.sh:39-43.
#   The commit/merge backstop (check-no-illegal-paths.sh, AC6) is the net.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve the coordinator-safe-name lib (same path-resolution as sibling hooks)
# ---------------------------------------------------------------------------
# CLAUDE_PLUGIN_ROOT is set by the Claude Code hook runner. Prefer it; fall back
# to a BASH_SOURCE-relative resolve so the hook is self-contained for testing.
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  _LIB="${CLAUDE_PLUGIN_ROOT}/bin/lib/coordinator-safe-name.sh"
else
  _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _LIB="${_SCRIPT_DIR}/../../bin/lib/coordinator-safe-name.sh"
fi

if [[ ! -f "$_LIB" ]]; then
  # Lib not found — fail-open (no false positives on misconfigured installs).
  exit 0
fi
# shellcheck source=../../bin/lib/coordinator-safe-name.sh
. "$_LIB"

# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------
if [[ "${COORDINATOR_OVERRIDE_ILLEGAL_FILENAME:-0}" == "1" ]]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Read stdin (timeout guard prevents hangs on Windows / Git Bash)
# ---------------------------------------------------------------------------
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

[[ -z "$INPUT" ]] && exit 0

# ---------------------------------------------------------------------------
# Parse tool_name (jq → python → sed fallback)
# ---------------------------------------------------------------------------
_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
elif [[ -n "$_PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$_PY" -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: d = {}
sys.stdout.write(str(d.get("tool_name", "")))
' 2>/dev/null || true)
else
  TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

[[ -z "$TOOL_NAME" ]] && exit 0

# ---------------------------------------------------------------------------
# deny helper — emit permissionDecision:deny to stdout, then exit 0
# ---------------------------------------------------------------------------
deny() {
  local reason="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg r "$reason" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "$_PY" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "$_PY" -c \
      'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

# ---------------------------------------------------------------------------
# advise helper — Bash arm only. Non-blocking advisory: emit
# permissionDecision:"allow" + additionalContext, then exit 0 (tool proceeds).
# Mirrors deny()'s jq -> python -> printf portability ladder. The Bash arm is
# best-effort and NOT the enforcement net (check-no-illegal-paths.sh is); it warns
# rather than blocks so shell redirects/pipes it misparses do not block legit work.
# ---------------------------------------------------------------------------
advise() {
  local reason="$1"
  local ctx="ILLEGAL-FILENAME ADVISORY (non-blocking): ${reason} This is a best-effort static scan of the command string and may misfire on shell redirects/pipes; the commit/merge backstop check-no-illegal-paths.sh is the real enforcement net. Hook: block-illegal-filename.sh (Bash arm, advisory-only)."
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg c "$ctx" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",additionalContext:$c}}'
  elif [[ -n "$_PY" ]]; then
    local cj
    cj=$(printf '%s' "$ctx" | "$_PY" -c \
      'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || cj="\"$(printf '%s' "$ctx" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":%s}}\n' "$cj"
  else
    local esc="${ctx//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"%s"}}\n' "$esc"
  fi
  exit 0
}

# ---------------------------------------------------------------------------
# Construct a human-readable deny message for an illegal basename.
# Leads with the safe alternative (design-as-offers).
# ---------------------------------------------------------------------------
make_deny_msg() {
  local raw_name="$1" illegal_char_hint="$2"
  # Strip the illegal char for the suggested safe form: replace : ? * < > | " \ / with -
  local safe_suggestion
  safe_suggestion=$(printf '%s' "$raw_name" \
    | tr ':?*<>|"\\/' '-' \
    | tr -s '-' \
    | sed 's/^-//; s/-$//' \
    | sed 's/[. ]*$//')  # Review: code-reviewer F2 — strip trailing dot/space so suggestion is genuinely NTFS-safe
  # Review: code-reviewer F6 — ADS-separator claim fires only for ':'; generic for all other chars
  local _char_desc
  if [[ "$illegal_char_hint" == ":" ]]; then
    _char_desc="${illegal_char_hint} is the NTFS ADS separator / reserved character; commits containing this name block \`git checkout\` on Windows"
  else
    _char_desc="${illegal_char_hint} is NTFS-reserved / illegal on Windows; commits containing this name block \`git checkout\` on Windows"
  fi
  printf '%s' \
    "'${raw_name}' contains '${illegal_char_hint}' (illegal on Windows — ${_char_desc}). "\
    "Use a hyphen instead: '${safe_suggestion}' — or call \`coordinator-safe-name timestamp\` for a safe timestamp component. "\
    "Reference: docs/wiki/cross-platform-shell-portability.md § Cross-platform safe filename components. "\
    "Override (rarely needed, Windows-free environments only): export COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 before the tool call."
}

# ---------------------------------------------------------------------------
# RELIABLE ARM — Write | Edit | NotebookEdit
# Extract tool_input.file_path (structured, always reliable).
# ---------------------------------------------------------------------------
case "$TOOL_NAME" in
  Write|Edit|NotebookEdit)
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
    elif [[ -n "$_PY" ]]; then
      FILE_PATH=$(printf '%s' "$INPUT" | "$_PY" -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: d = {}
sys.stdout.write(str(d.get("tool_input", {}).get("file_path", "")))
' 2>/dev/null || true)
    else
      FILE_PATH=$(printf '%s' "$INPUT" \
        | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi

    [[ -z "$FILE_PATH" ]] && exit 0

    # Use the basename only — directory components may legitimately contain
    # chars that look suspicious in isolation (forward slash is a path separator,
    # not illegal in that role). We guard the LEAF component.
    #
    # Use bash parameter expansion (not basename) to strip up to the last '/' OR '\'.
    # On Windows the Claude Code harness delivers file_path with backslash separators
    # (e.g. X:\repo\state\memo-outbox\topic.md). ${FILE_PATH##*/} finds no '/' and
    # returns the entire path as the "leaf", causing csn_check to flag the drive-letter
    # colon (X:) and FALSE-DENY a path whose actual leaf (topic.md) is legal.
    # [/\\] is a glob bracket expression matching '/' OR a literal '\', so ##*[/\\]
    # yields the true leaf on both POSIX and Windows paths.
    # Note: `basename` treats '\' as a path separator on Git Bash, which is why we
    # hand-strip rather than calling it — but we must strip BOTH separators, not just '/'.
    # A literal '\' inside a POSIX leaf is itself NTFS-illegal and vanishingly rare;
    # the commit/merge backstop (check-no-illegal-paths.sh) remains the net for that edge.
    # Review: Windows-backslash fix — strip both '/' and '\' for the true leaf on Windows
    BNAME="${FILE_PATH##*[/\\]}"
    [[ -z "$BNAME" ]] && exit 0

    # Run csn_check; capture the stderr message for the deny reason.
    CHECK_MSG=$(csn_check "$BNAME" 2>&1) && exit 0

    # Illegal basename detected. Extract the offending character hint from the
    # csn_check message. Handles all csn_check forms:
    #   illegal char "X" in "..." / trailing dot / trailing space / control character
    # Review: code-reviewer F6 — extend CHAR_HINT sed to capture all csn_check message forms
    CHAR_HINT=$(printf '%s' "$CHECK_MSG" | sed -n \
      -e 's/.*illegal char "\([^"]*\)".*/\1/p' \
      -e 's/.*\(trailing dot\).*/\1/p' \
      -e 's/.*\(trailing space\).*/\1/p' \
      -e 's/.*\(control character\).*/\1/p')
    [[ -z "$CHAR_HINT" ]] && CHAR_HINT="illegal character"

    deny "$(make_deny_msg "$BNAME" "$CHAR_HINT")"
    ;;
esac

# ---------------------------------------------------------------------------
# BEST-EFFORT ARM — Bash
# Scan the command string for mv / git mv / --out <path> / shell redirections.
# Explicitly best-effort: variable-expansion / heredoc / multi-command patterns
# defeat static extraction. The commit/merge backstop (D2) is the real net.
# ---------------------------------------------------------------------------
case "$TOOL_NAME" in
  Bash)
    if command -v jq >/dev/null 2>&1; then
      CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
    elif [[ -n "$_PY" ]]; then
      CMD=$(printf '%s' "$INPUT" | "$_PY" -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: d = {}
sys.stdout.write(str(d.get("tool_input", {}).get("command", "")))
' 2>/dev/null || true)
    else
      CMD=$(printf '%s' "$INPUT" \
        | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi

    [[ -z "$CMD" ]] && exit 0

    # Join backslash-newline continuations so a split op is one segment.
    NL=$'\n'
    CMD="${CMD//\\$NL/ }"

    # Strip heredoc bodies from CMD before scanning for mv/redirect targets.
    # Prevents false positives when code inside a heredoc contains '>' operators
    # or trailing-dot tokens (e.g. python3 - <<'PY'\n...\nPY) that would
    # otherwise be extracted as redirect targets and incorrectly flagged.
    # Handles: <<DELIM, <<'DELIM', <<"DELIM", <<-DELIM (tab-stripped) forms.
    # Best-effort: does not handle nested heredocs (acceptable — this arm is
    # explicitly best-effort; the commit/merge backstop D2 is the real net).
    CMD=$(printf '%s\n' "$CMD" | awk '
BEGIN { in_hd = 0; delim = ""; strip_tabs = 0 }
{
  if (in_hd) {
    check = $0
    if (strip_tabs) { gsub(/^\t+/, "", check) }
    if (check == delim) { in_hd = 0; strip_tabs = 0 }
    next
  }
  if ($0 ~ /<</) {
    rest = $0
    sub(/.*<</, "", rest)
    strip_tabs = (rest ~ /^-/) ? 1 : 0
    if (strip_tabs) sub(/^-/, "", rest)
    sub(/^[[:space:]]+/, "", rest)
    if (rest ~ /^'"'"'/) sub(/^'"'"'/, "", rest)
    else if (rest ~ /^"/) sub(/^"/, "", rest)
    sub(/['"'"'" \t].*/, "", rest)
    if (rest != "") { delim = rest; in_hd = 1 }
  }
  print
}')

    # Strip double- and single-quoted string spans before scanning for redirect/mv
    # targets — prevents --body/--message/-m values (including multi-line `-m "..."` bodies)
    # from being misread as redirect contexts. perl -0777 slurp mode strips multi-line
    # quoted spans (the root cause of the commit-message false-positive); sed fallback is
    # line-oriented (v1 limitation — Change A's token-boundary anchoring is the backstop
    # that neutralizes -> / => arrows surviving in a non-perl environment).
    # Double-quoted spans stripped first, then single — order matters so an apostrophe
    # inside a double-quoted body is removed before the single-quote pass.
    if command -v perl >/dev/null 2>&1; then
      # Slurp mode (-0777): strip multi-line quoted spans so a multi-line `-m`/`--message`
      # body is removed before redirect scanning. Double-quoted spans first, then single —
      # order matters so an apostrophe inside a double-quoted body is gone before the
      # single-quote pass (prevents it pairing with a later apostrophe and eating redirects).
      # If perl exits non-zero (present-but-broken binary), fall through to the sed fallback
      # rather than leaving CMD_FOR_SCAN empty and silently failing-open the entire arm.
      # Review: F3 — broken-perl fall-through to sed fallback (prevents silent fail-open)
      CMD_FOR_SCAN=$(printf '%s' "$CMD" | perl -0777 -pe 's/"[^"]*"//g; s/'"'"'[^'"'"']*'"'"'//g' 2>/dev/null) || \
        CMD_FOR_SCAN=$(printf '%s' "$CMD" | sed 's/"[^"]*"//g' | sed "s/'[^']*'//g")
    else
      # Portable fallback: line-oriented strip (v1 limitation — a quoted span split across
      # lines is not fully removed; Change A's token-boundary anchoring is the backstop that
      # still neutralizes -> / => arrows in a surviving multi-line body).
      CMD_FOR_SCAN=$(printf '%s' "$CMD" | sed 's/"[^"]*"//g' | sed "s/'[^']*'//g")
    fi

    # Fast bail: no move or redirect-like operator in the command at all.
    # Review: code-reviewer F4 — broaden '>>' to '>' to catch single-redirect (echo x > file:name);
    # Review: code-reviewer F7 — remove dead inner git-mv grep (\bmv\b already word-boundary-matches
    #   git mv, so the inner grep was unreachable).
    printf '%s\n' "$CMD_FOR_SCAN" | grep -qE '\bmv\b|>' || exit 0

    # Extract candidate destination paths from:
    #   mv <src> <dest>           — second non-flag argument after mv
    #   git mv <src> <dest>       — second non-flag argument after git mv
    #   >> <path>                 — target of append-redirect
    #   > <path>                  — target of overwrite-redirect (excluding >>)
    #   --out <path>              — named output flag (best-effort)
    #
    # Strategy: scan the raw command text for literal path-like tokens that
    # appear after the above patterns. We only look for LITERAL tokens (no $VAR,
    # no $(...), no quotes containing whitespace) — variable-expansion is an
    # accepted v1 limitation documented in the header.
    #
    # Use a simple sed approach: for each pattern, pull the token that immediately
    # follows it. The token must look like a filename (no spaces, non-empty).

    check_candidate() {
      local candidate="$1"
      # Strip surrounding quotes (single or double) — literal quoted paths only.
      candidate="${candidate//\"/}"
      candidate="${candidate//\'/}"
      # F6 fix: strip a trailing heredoc (<<, <<-, <<<) or process-substitution
      # opener that glued onto this candidate due to missing whitespace (e.g.
      # `cat >file<<EOF` tokenizes under the redirect-capture regex as
      # destination "file<<EOF"). These are shell OPERATORS, not filename
      # characters, and would otherwise cause csn_check to flag the harmless
      # '<' from the heredoc/process-sub marker as an NTFS-illegal char.
      # Done via `sed` (not a bare `${candidate%%<<*}` parameter expansion):
      # bash's lexer recognizes literal `<<` and `<(` as heredoc/process-sub
      # START tokens wherever they appear unquoted in source, INCLUDING inside
      # a `${...%%pattern}` glob pattern — writing them bare breaks script
      # parsing itself (verified: caused "unexpected EOF" on this very file).
      # Routing the strip through a single-quoted sed regex keeps `<<`/`<(`
      # as inert DATA (a pattern string), never as shell syntax.
      # Strips from the FIRST "<<" onward (covers <<, <<-, and <<<, since all
      # three contain a leading "<<"), then from a "<(" onward. A GENUINE
      # illegal single '<' in a literal filename (e.g. foo<bar) is UNAFFECTED:
      # it matches neither the doubled ("<<") nor paren ("<(") form, so
      # csn_check still flags it below.
      candidate=$(printf '%s' "$candidate" | sed -E 's/<<.*$//; s/<\(.*$//')
      # Ignore variable expansions, empty strings, flags, and pure-directory tokens.
      [[ -z "$candidate" ]] && return 0
      [[ "$candidate" == '$'* ]] && return 0
      [[ "$candidate" == -* ]] && return 0
      # Take the basename — use bash substring (not `basename`) to strip up to the last
      # '/' OR '\'. On Windows the harness delivers backslash-separated paths; ##*[/\\]
      # yields the true leaf on both platforms (same rationale as reliable arm above).
      # Review: Windows-backslash fix — strip both '/' and '\' for the true leaf on Windows
      local b
      b="${candidate##*[/\\]}"
      [[ -z "$b" || "$b" == "." || "$b" == ".." ]] && return 0
      # Run csn_check on the basename.
      local check_out
      check_out=$(csn_check "$b" 2>&1) && return 0
      # Illegal: build deny message.
      local char_hint
      # Review: code-reviewer F6 — extend char_hint to capture all csn_check message forms
      char_hint=$(printf '%s' "$check_out" | sed -n \
        -e 's/.*illegal char "\([^"]*\)".*/\1/p' \
        -e 's/.*\(trailing dot\).*/\1/p' \
        -e 's/.*\(trailing space\).*/\1/p' \
        -e 's/.*\(control character\).*/\1/p')
      [[ -z "$char_hint" ]] && char_hint="illegal character"
      advise "$(make_deny_msg "$b" "$char_hint")"
    }

    # Extract: `mv <token> <dest>` and `git mv <token> <dest>`
    # Pull the two non-flag tokens after the mv; the second is the destination.
    # Use printf+awk: split on whitespace, find the mv keyword, skip flags.
    DEST_CANDIDATES=$(printf '%s\n' "$CMD_FOR_SCAN" | awk '
    BEGIN { in_mv = 0; arg_count = 0 }
    {
      n = split($0, tok, /[[:space:]]+/)
      for (i = 1; i <= n; i++) {
        t = tok[i]
        if (t == "" || t == "\\") continue
        if (in_mv) {
          if (t ~ /^-/) continue   # skip flags
          arg_count++
          if (arg_count == 2) { print t; in_mv = 0; arg_count = 0 }
          continue
        }
        if (t == "mv" || (t == "mv" && tok[i-1] == "git")) { in_mv = 1; arg_count = 0 }
      }
    }')

    # Also extract redirection targets: >> target and > target (not >>).
    # Anchored to shell-token boundaries: '>' must be preceded by whitespace or a
    # file-descriptor digit — or appear at start of line. This prevents '->' and '=>'
    # (arrow operators in commit-message prose, C++, TypeScript, range notation, etc.)
    # from being misread as redirect operators.
    # Negative-spec: '->' / '=>' have no whitespace/digit before '>' and are NOT shell
    # redirects — they must never trigger this scan.
    # Note: 'echo x>file' (no space around '>') passes through — accepted v1
    # limitation; the commit/merge backstop (D2, check-no-illegal-paths.sh) is the
    # real enforcement net.
    # Fix: cross-repo/inbox/2026-07-01-block-illegal-filename-commit-message-false-positive.md
    # When `^` matches (redirect at line-start), grep emits `>...` with no leading
    # character. The sed strip's `[[:space:]0-9]*` matches zero chars in that shape,
    # covering both the zero-width anchor case and the single-char-prefix (space or
    # digit) case with a single expression. (Review: F5 — document ^ zero-width prefix shape)
    # `>*` (zero-or-more) in the sed expression is safe: the upstream grep guarantees
    # >{1,2} in each match, and the `[^[:space:]>|;&]+` filename class excludes `>`,
    # so `>*` strips the redirect chars without risk of consuming filename characters.
    # (Review: F4 — document >* strip invariant)
    REDIR_CANDIDATES=$(printf '%s\n' "$CMD_FOR_SCAN" | \
      grep -oE '(^|[[:space:]]|[0-9])>{1,2}[[:space:]]*[^[:space:]>|;&]+' | \
      sed -E 's/^[[:space:]0-9]*>*//' | tr -d ' \t')

    # Also extract --out <token>
    OUT_CANDIDATES=$(printf '%s\n' "$CMD" | \
      grep -oE '(--out|-o)[[:space:]]+("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]+)' | \
      sed -E 's/^(--out|-o)[[:space:]]*//')

    # Check all candidates (dest from mv/git mv)
    while IFS= read -r cand; do
      [[ -z "$cand" ]] && continue
      check_candidate "$cand"
    done <<< "$DEST_CANDIDATES"

    # Check redirection targets
    while IFS= read -r cand; do
      [[ -z "$cand" ]] && continue
      check_candidate "$cand"
    done <<< "$REDIR_CANDIDATES"

    # Check --out targets
    while IFS= read -r cand; do
      [[ -z "$cand" ]] && continue
      check_candidate "$cand"
    done <<< "$OUT_CANDIDATES"
    ;;
esac

# All arms passed — allow.
exit 0
