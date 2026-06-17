#!/usr/bin/env bash
# PreToolUse hook: blocks Edit/Write/MultiEdit that flips a coordinator /bin/
# script's shebang from #!/usr/bin/env python to #!/usr/bin/env python3.
#
# Purpose: clean Windows python.org installs ship only `python`/`py` — no
# `python3` — so a python3 shebang exec-127s there. The `python` shebang is
# the deliberate cross-platform choice (commit 6fe5a986). The common
# misdiagnosis is seeing `env: python: No such file or directory` on macOS
# when running ./script directly and assuming the shebang is wrong; that is an
# INVOCATION error (the fix is `python3 <script>`), not a shebang bug.
#
# Spec backlink: docs/plans/2026-06-17-python3-shebang-flip-guard.md
# Tripwire entry: docs/wiki/coordinator-tripwires.md § BLOCK-PYTHON3-SHEBANG-FLIP
# DR-148: must run on bash 3.2 + BSD coreutils (no bash-4, no GNU-only tools)
#
# Detection gates (both must pass to deny):
#   1. PATH gate  — file_path contains a /bin/ path component.
#   2. STATE gate — on-disk line 1 of the file is exactly #!/usr/bin/env python.
#   3. FLIP gate  — the proposed change would result in #!/usr/bin/env python3 on
#                   line 1 (tool-type-specific checks; see below).
#
# Override: COORDINATOR_OVERRIDE_PYTHON3_SHEBANG_FLIP=1 (fail-open; logged to
# the overrides.log path per block-blanket-git-add.sh idiom).
#
# Deny mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.

set -uo pipefail
# -e deliberately omitted — all error paths are guarded via || true or explicit checks (deny hook must fail-open on unexpected error, never fail-closed mid-parse)

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# --- Override escape hatch (fail-open; checked before any gates) ---
if [[ "${COORDINATOR_OVERRIDE_PYTHON3_SHEBANG_FLIP:-0}" == "1" ]]; then
  GIT_ROOT=$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$GIT_ROOT" ]]; then
    OVERRIDE_LOG="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID:-no-session}/overrides.log"
    mkdir -p "$(dirname "$OVERRIDE_LOG")" 2>/dev/null || true
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${SESSION_ID:-no-session} | OVERRIDE-PYTHON3-SHEBANG-FLIP | python3-shebang-flip override" >> "$OVERRIDE_LOG" 2>/dev/null || true
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
# Match /bin/ anywhere in the path (e.g. ~/.claude/bin/foo or coordinator/bin/bar).
case "$FILE_PATH" in
  */bin/*) : ;;
  *) exit 0 ;;
esac

# --- STATE gate: on-disk line 1 must be exactly #!/usr/bin/env python ---
# If the file does not exist, it's new — no prior shebang to flip, allow.
# The || true is REQUIRED: prevents a file whose first line lacks a trailing
# newline from propagating non-zero exit into the set -e context.
[[ ! -f "$FILE_PATH" ]] && exit 0
DISK_LINE1=""
IFS= read -r DISK_LINE1 < "$FILE_PATH" || true
[[ "$DISK_LINE1" != "#!/usr/bin/env python" ]] && exit 0

# --- FLIP gate: tool-type-specific detection ---
# We must detect that the proposed operation would result in #!/usr/bin/env python3
# on line 1. The dominant misdiagnosis shape is a PARTIAL Edit:
#   old_string="env python" -> new_string="env python3"
# whose new_string does NOT contain the full shebang literal.

SHOULD_DENY=0

case "$TOOL_NAME" in

  Write)
    # Write: line 1 of tool_input.content == #!/usr/bin/env python3
    if command -v jq >/dev/null 2>&1; then
      CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      CONTENT=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("content","")))' 2>/dev/null || true)
    else
      # no-parser fallback: fail-safe over-fire — denies on any python3 in the payload
      # once path+state gates have passed; the override env var is the escape.
      # Over-blocks rather than under-blocks (correct direction for a deny guard).
      if printf '%s' "$INPUT" | grep -q 'python3'; then
        SHOULD_DENY=1
      fi
      # Set CONTENT empty so the CONTENT_LINE1 block below is a no-op in this branch.
      CONTENT=""
    fi
    # Get line 1 of content (content may have \n as literal escape or real newlines)
    # Handle both: split on \n literal (JSON-encoded) or real newline.
    CONTENT_LINE1=$(printf '%s' "$CONTENT" | head -1)
    # If content used JSON-encoded \n, head -1 gives us everything up to first real newline.
    # But if the content was decoded by jq, real newlines are present. head -1 handles both.
    # Also strip trailing carriage return for Windows line endings.
    CONTENT_LINE1="${CONTENT_LINE1%$'\r'}"
    if [[ "$CONTENT_LINE1" == "#!/usr/bin/env python3" ]]; then
      SHOULD_DENY=1
    fi
    ;;

  Edit)
    # Edit: new_string contains python3 AND old_string is a non-empty substring
    # of the on-disk line-1 shebang #!/usr/bin/env python.
    # This fires on the full-line form AND the dominant partial form.
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
      # no-parser fallback: fail-safe over-fire — denies on any python3 in the payload
      # once path+state gates have passed; the override env var is the escape.
      # Over-blocks rather than under-blocks (correct direction for a deny guard).
      if printf '%s' "$INPUT" | grep -q 'python3'; then
        SHOULD_DENY=1
      fi
      # Set OLD_STR/NEW_STR empty so the check below is a no-op in this branch.
      OLD_STR=""
      NEW_STR=""
    fi
    # new_string must contain python3 (the flip signal)
    # old_string must be non-empty and a substring of the on-disk shebang line
    if [[ -n "$OLD_STR" && "$NEW_STR" == *"python3"* ]]; then
      # Check old_string is a substring of the disk line 1
      case "$DISK_LINE1" in
        *"$OLD_STR"*) SHOULD_DENY=1 ;;
      esac
    fi
    ;;

  MultiEdit)
    # MultiEdit: iterate edits[]; fire if any edit has new_string containing python3
    # AND old_string a substring of the shebang line.
    # Per-edit check (not full sequential simulation): a two-step flip through an
    # intermediate interpreter name (python→python2→python3 across two edits) is not
    # caught — judged implausible; documented as accepted negative-space.
    if command -v jq >/dev/null 2>&1; then
      # Use jq to iterate edits and check each pair.
      # Bind each edit to $e so contains() receives $e.old_string as argument
      # (direct .old_string reference inside contains() fails: index-string error).
      DENY_FLAG=$(printf '%s' "$INPUT" | jq -r '
        .tool_input.edits[]? |
        . as $e |
        select(
          ($e.new_string | test("python3")) and
          ($e.old_string != null and $e.old_string != "") and
          ("#!/usr/bin/env python" | contains($e.old_string))
        ) | "deny"
      ' 2>/dev/null | head -1 || true)
      [[ "$DENY_FLAG" == "deny" ]] && SHOULD_DENY=1
    elif [[ -n "$PY" ]]; then
      DENY_FLAG=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
edits = d.get("tool_input", {}).get("edits", [])
shebang = "#!/usr/bin/env python"
for e in edits:
    old = e.get("old_string", "")
    new = e.get("new_string", "")
    if "python3" in new and old and old in shebang:
        sys.stdout.write("deny")
        break
' 2>/dev/null || true)
      [[ "$DENY_FLAG" == "deny" ]] && SHOULD_DENY=1
    else
      # no-parser fallback: fail-safe over-fire — denies on any python3 in the payload
      # once path+state gates have passed; the override env var is the escape.
      # Over-blocks rather than under-blocks (correct direction for a deny guard).
      if printf '%s' "$INPUT" | grep -q 'python3'; then
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

REASON="BLOCKED: python->python3 shebang flip on a coordinator /bin/ script.

DID YOU MEAN to fix an \`env: python: No such file or directory\` error? That's an INVOCATION error, not a shebang bug. Run \`python3 <script>\` — works for every script in this class. (\`bash <script>\` also works for trampoline-marked CLIs only; pure-Python .test.py files must use \`python3\`.) Direct \`./script\` failing on macOS is expected; the shebang is correct.

WHY: clean Windows python.org installs ship only \`python\`/\`py\` (no \`python3\`) -> a \`python3\` shebang exec-127s there. The \`python\` shebang is the deliberate cross-platform choice (commit 6fe5a986). See docs/wiki/bash-on-windows-gotchas.md § Windows exception.

Override (genuinely Linux/macOS-only script intentionally going python3): export COORDINATOR_OVERRIDE_PYTHON3_SHEBANG_FLIP=1 before the edit."

deny "$REASON"
