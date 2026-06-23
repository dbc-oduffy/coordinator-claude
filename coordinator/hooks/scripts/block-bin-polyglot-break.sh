#!/usr/bin/env bash
# PreToolUse hook: blocks Edit/Write/MultiEdit that breaks the /bin/ polyglot
# invariant — a coordinator bin script must keep BOTH of:
#   line 1  == #!/bin/sh
#   body    contains the verbatim trampoline line:
#             ''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
#
# The polyglot design survives on any OS: sh executes the trampoline which
# execs python3/python/py; Python's triple-quote syntax then treats the first
# two lines as a string literal and ignores them. Breaking either invariant
# makes the script exec-fail on at least one class of OS.
#
# Break shapes guarded here:
#   1. LINE-1 MUTATION — an edit that changes line 1 away from #!/bin/sh
#      (to #!/usr/bin/env python, #!/usr/bin/env python3, or anything else).
#   2. TRAMPOLINE STRIP — an edit whose result no longer contains the verbatim
#      trampoline literal (present on-disk / in old_string, absent in new_string).
#
# Supersedes: block-python3-shebang-flip.sh (guarded the old #!/usr/bin/env python
# shebang before the C1 polyglot migration).
#
# Spec backlink: docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md
# Tripwire entry: docs/wiki/coordinator-tripwires.md § BLOCK-BIN-POLYGLOT-BREAK
# DR-148: must run on bash 3.2 + BSD coreutils (no bash-4-only builtins,
#         no GNU-only sed/grep/date/realpath)
#
# NO-PARSER FALLBACK over-fire shape (documented accepted risk):
#   When jq and python are both absent the fallback checks whether the raw
#   JSON payload contains the trampoline substring or the #!/bin/sh literal.
#   This OVER-FIRES on legitimate edits that happen to discuss (or quote) those
#   strings without actually stripping them from the target file. The override
#   env var is the escape; correct tooling (jq or python) eliminates the false
#   positives. Under-fire (missed denial) is the wrong direction for a deny guard.
#
#   Edit-vs-Write asymmetry under no-parser: for Write, the fallback fires only
#   when the new content string lacks the shebang or trampoline — it catches
#   genuine strip operations. For Edit, the fallback fires on ANY edit payload
#   whose JSON body doesn't contain those strings (i.e. any edit that changes
#   body text unrelated to the shebang/trampoline), because old_string/new_string
#   are scanned raw without knowing which field is which. This means the no-parser
#   Edit fallback over-fires on ALL body edits — COORDINATOR_OVERRIDE_BIN_POLYGLOT_BREAK=1
#   is required for any Edit on a polyglot file on a jq/python-less system.
#   Review: code-reviewer — document Edit asymmetry in no-parser fallback (Finding F)
#
# Override: COORDINATOR_OVERRIDE_BIN_POLYGLOT_BREAK=1 (fail-open; logged to
#   overrides.log). Legacy COORDINATOR_OVERRIDE_PYTHON3_SHEBANG_FLIP=1 also
#   accepted for back-compat with any existing scripts/docs that set it.
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.

set -uo pipefail
# -e deliberately omitted — deny hooks must fail-open on unexpected error, never
# fail-closed mid-parse (a crash must not block the user).

TRAMPOLINE="''''exec \"\$(command -v python3 || command -v python || command -v py)\" \"\$0\" \"\$@\" #'''"
LINE1_EXPECTED='#!/bin/sh'

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# --- Override escape hatch (fail-open; checked before any gates) ---
# Accept both new and legacy env var names.
if [[ "${COORDINATOR_OVERRIDE_BIN_POLYGLOT_BREAK:-0}" == "1" ]] || \
   [[ "${COORDINATOR_OVERRIDE_PYTHON3_SHEBANG_FLIP:-0}" == "1" ]]; then
  GIT_ROOT=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$GIT_ROOT" ]]; then
    OVERRIDE_LOG="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID:-no-session}/overrides.log"
    mkdir -p "$(dirname "$OVERRIDE_LOG")" 2>/dev/null || true
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${SESSION_ID:-no-session} | OVERRIDE-BIN-POLYGLOT-BREAK | bin-polyglot-break override" >> "$OVERRIDE_LOG" 2>/dev/null || true
  fi
  exit 0
fi

# --- Parse tool_name (jq -> python -> sed cascade) ---
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
else
  TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Only act on file-mutation tools.
case "$TOOL_NAME" in
  Write|Edit|MultiEdit) : ;;
  *) exit 0 ;;
esac

# --- Parse file_path (jq -> python -> sed cascade) ---
if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  FILE_PATH=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("file_path","")))' 2>/dev/null || true)
else
  FILE_PATH=$(printf '%s' "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

[[ -z "$FILE_PATH" ]] && exit 0

# --- Backslash normalize (Windows path support) ---
FILE_PATH="${FILE_PATH//\\//}"

# --- PATH gate: must contain a /bin/ component ---
case "$FILE_PATH" in
  */bin/*) : ;;
  *) exit 0 ;;
esac

# --- STATE gate: on-disk line 1 must be #!/bin/sh AND file must contain trampoline ---
# If the file does not exist, it is new — no polyglot to break, allow.
[[ ! -f "$FILE_PATH" ]] && exit 0

DISK_LINE1=""
IFS= read -r DISK_LINE1 < "$FILE_PATH" || true
# Strip trailing carriage return (Windows line endings).
DISK_LINE1="${DISK_LINE1%$'\r'}"

# If on-disk line 1 is not #!/bin/sh, the file is not a polyglot — allow.
[[ "$DISK_LINE1" != "$LINE1_EXPECTED" ]] && exit 0

# If the on-disk file does not contain the trampoline, not a polyglot — allow.
if ! grep -qF "$TRAMPOLINE" "$FILE_PATH" 2>/dev/null; then
  exit 0
fi

# --- Break detection: tool-type-specific ---
# Two independent deny conditions:
#   DENY from LINE-1 MUTATION  — edit would change line 1 away from #!/bin/sh
#   DENY from TRAMPOLINE STRIP — edit would remove the trampoline line

SHOULD_DENY=0

case "$TOOL_NAME" in

  Write)
    # Write: the entire new file content replaces the existing polyglot.
    # old content for trampoline-strip detection = the on-disk file content.
    if command -v jq >/dev/null 2>&1; then
      CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      CONTENT=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("content","")))' 2>/dev/null || true)
    else
      # no-parser fallback (documented over-fire risk — see header comment):
      # deny if the payload appears to remove #!/bin/sh or the trampoline.
      if ! printf '%s' "$INPUT" | grep -qF '#!/bin/sh'; then
        SHOULD_DENY=1
      elif ! printf '%s' "$INPUT" | grep -qF "$TRAMPOLINE"; then
        SHOULD_DENY=1
      fi
      CONTENT=""
    fi
    if [[ -n "$CONTENT" ]]; then
      # LINE-1 MUTATION check.
      CONTENT_LINE1=$(printf '%s' "$CONTENT" | head -1)
      CONTENT_LINE1="${CONTENT_LINE1%$'\r'}"
      if [[ -n "$CONTENT_LINE1" && "$CONTENT_LINE1" != "$LINE1_EXPECTED" ]]; then
        SHOULD_DENY=1
      fi
      # TRAMPOLINE-STRIP check: on-disk file has trampoline (verified above);
      # if new content does not contain it, it is being stripped.
      case "$CONTENT" in
        *"$TRAMPOLINE"*) : ;;
        *) SHOULD_DENY=1 ;;
      esac
    fi
    ;;

  Edit)
    # Edit: old_string + new_string.
    # LINE-1 MUTATION: if old_string is a substring of DISK_LINE1, the edit
    # touches line 1; check new_string for a different shebang.
    # TRAMPOLINE STRIP: if old_string contains the trampoline and new_string
    # does not, the trampoline is being removed.
    if command -v jq >/dev/null 2>&1; then
      OLD_STR=$(printf '%s' "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null || true)
      NEW_STR=$(printf '%s' "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      OLD_STR=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("old_string","")))' 2>/dev/null || true)
      NEW_STR=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("new_string","")))' 2>/dev/null || true)
    else
      # no-parser fallback (documented over-fire risk — see header comment):
      if ! printf '%s' "$INPUT" | grep -qF '#!/bin/sh'; then
        SHOULD_DENY=1
      elif ! printf '%s' "$INPUT" | grep -qF "$TRAMPOLINE"; then
        SHOULD_DENY=1
      fi
      OLD_STR=""
      NEW_STR=""
    fi

    if [[ -n "$OLD_STR" || -n "$NEW_STR" ]]; then
      # LINE-1 MUTATION: edit touches line 1 if old_str is a substring of disk line 1.
      # Guard: empty OLD_STR matches *""* (which is everything) — skip the check
      # when old_str is empty to avoid spurious LINE1_TOUCHED=1 on empty-string edits.
      # Review: code-reviewer — empty old_string guard (Finding F)
      LINE1_TOUCHED=0
      if [[ -n "$OLD_STR" ]]; then
        case "$DISK_LINE1" in
          *"$OLD_STR"*) LINE1_TOUCHED=1 ;;
        esac
      fi
      if [[ "$LINE1_TOUCHED" -eq 1 ]]; then
        # Extract what line 1 would become after the replacement.
        NEW_LINE1_CANDIDATE=$(printf '%s' "$NEW_STR" | head -1)
        NEW_LINE1_CANDIDATE="${NEW_LINE1_CANDIDATE%$'\r'}"
        case "$NEW_LINE1_CANDIDATE" in
          '#!'*)
            if [[ "$NEW_LINE1_CANDIDATE" != "$LINE1_EXPECTED" ]]; then
              SHOULD_DENY=1
            fi
            ;;
        esac
      fi

      # TRAMPOLINE STRIP: old_string contains the trampoline, new_string does not.
      OLD_HAS_TRAMP=0
      NEW_HAS_TRAMP=0
      case "$OLD_STR" in
        *"$TRAMPOLINE"*) OLD_HAS_TRAMP=1 ;;
      esac
      case "$NEW_STR" in
        *"$TRAMPOLINE"*) NEW_HAS_TRAMP=1 ;;
      esac
      if [[ "$OLD_HAS_TRAMP" -eq 1 && "$NEW_HAS_TRAMP" -eq 0 ]]; then
        SHOULD_DENY=1
      fi
    fi
    ;;

  MultiEdit)
    # MultiEdit: iterate edits[]; fire if any edit breaks either invariant.
    # Per-edit check (not full sequential simulation — a two-step strip across
    # two edits is accepted negative-space, same as the predecessor hook).
    if command -v jq >/dev/null 2>&1; then
      DENY_FLAG=$(printf '%s' "$INPUT" | jq -r --arg line1 "$LINE1_EXPECTED" --arg tramp "$TRAMPOLINE" '
        .tool_input.edits[]? |
        . as $e |
        ($e.old_string // "") as $old |
        ($e.new_string // "") as $new |
        (
          # LINE-1 MUTATION: old touches disk line 1, new starts with a different shebang
          (($line1 | contains($old)) and $old != "" and
           (($new | split("\n")[0]) | startswith("#!")) and
           (($new | split("\n")[0]) != $line1))
          or
          # TRAMPOLINE STRIP: old contained trampoline, new does not
          (($old | contains($tramp)) and ($new | contains($tramp) | not))
        ) |
        select(.) | "deny"
      ' 2>/dev/null | head -1 || true)
      [[ "$DENY_FLAG" == "deny" ]] && SHOULD_DENY=1
    elif [[ -n "$PY" ]]; then
      DENY_FLAG=$(printf '%s' "$INPUT" | "$PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
edits = d.get('tool_input', {}).get('edits', [])
line1 = '$LINE1_EXPECTED'
tramp = '$TRAMPOLINE'
for e in edits:
    old = e.get('old_string', '')
    new = e.get('new_string', '')
    new_line1 = new.split('\n')[0].rstrip('\r')
    if old and old in line1 and new_line1.startswith('#!') and new_line1 != line1:
        sys.stdout.write('deny')
        break
    if tramp in old and tramp not in new:
        sys.stdout.write('deny')
        break
" 2>/dev/null || true)
      [[ "$DENY_FLAG" == "deny" ]] && SHOULD_DENY=1
    else
      # no-parser fallback (documented over-fire risk — see header comment):
      if ! printf '%s' "$INPUT" | grep -qF '#!/bin/sh'; then
        SHOULD_DENY=1
      elif ! printf '%s' "$INPUT" | grep -qF "$TRAMPOLINE"; then
        SHOULD_DENY=1
      fi
    fi
    ;;
esac

[[ "$SHOULD_DENY" -eq 0 ]] && exit 0

# --- Deny function (Form A) ---
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
    local esc
    esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

REASON="BLOCKED: edit would break the /bin/ sh-polyglot invariant on a coordinator bin script.

A coordinator bin script must keep BOTH:
  line 1 : #!/bin/sh
  body   : ''''exec \"\$(command -v python3 || command -v python || command -v py)\" \"\$0\" \"\$@\" #'''

DID YOU MEAN to invoke the script? Use \`python3 <script>\` or \`bash <script>\` directly — both work without touching the shebang. Calling \`./script\` from a shell that doesn't honour the #!/bin/sh shebang is an INVOCATION issue, not a script bug.

WHY the polyglot shape matters: line 1 #!/bin/sh makes the file a valid POSIX sh script; the trampoline re-execs with the best available Python interpreter (python3, python, or py). Removing either invariant breaks the script on at least one class of OS or Python environment. See docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md for the full rationale.

Override (you are intentionally restructuring this file and understand the cross-platform tradeoffs): export COORDINATOR_OVERRIDE_BIN_POLYGLOT_BREAK=1 before the edit."

deny "$REASON"
