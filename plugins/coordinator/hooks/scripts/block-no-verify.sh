#!/bin/bash
# PreToolUse hook: Blocks git invocations that skip commit hooks or signing.
# Fires on ALL Bash tool invocations (matcher: "Bash").
# Exits immediately (<5ms) on non-matching commands.
#
# Doctrine: coordinator/CLAUDE.md § Git Commit Policy — "Never skip hooks
# (--no-verify) or bypass signing (--no-gpg-sign, -c commit.gpgsign=false)
# unless the user has explicitly asked for it."
#
# Escape hatch: COORDINATOR_OVERRIDE_NO_VERIFY=1 (mirrors COORDINATOR_OVERRIDE_SCOPE=1).
# Use only when the PM explicitly instructs it; the override is logged.
#
# Input schema (PreToolUse for Bash):
#   { "tool_name": "Bash", "tool_input": { "command": "..." }, "session_id": "..." }

# Honor escape hatch before doing any work.
if [[ "${COORDINATOR_OVERRIDE_NO_VERIFY:-0}" == "1" ]]; then
  exit 0
fi

# Safe stdin read — timeout prevents hang on Windows/Git Bash.
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Parse command — prefer jq, fall back to sed.
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fast exit: no command to inspect.
[[ -z "$COMMAND" ]] && exit 0

# Normalise before matching:
#   1. Collapse backslash-newline continuations (\ at line-end) into a single space.
#      Two forms exist depending on the JSON parser path:
#      - Real backslash + LF   (jq produces a real newline from JSON \n)
#      - Literal \\n two-char  (sed fallback leaves JSON escape un-expanded)
#      Both are normalised so multi-line commands don't evade detection.
#   2. The result goes into FLAT_COMMAND for regex matching only;
#      COMMAND is preserved for the error message.
FLAT_COMMAND=$(printf '%s' "$COMMAND" \
  | tr -d '\r' \
  | sed ':a;N;$!ba;s/\\\n/ /g' \
  | sed 's/\\n/ /g')

# ERE that catches the three bypass forms our doctrine prohibits.
# Branch explanations:
#   (^|&&|\|\||;|\|)    — command start or chaining operators: &&, ||, ;, |
#                          (|| listed before | so the two-char form matches first)
#   [[:space:]]*git[[:space:]]+ — the git invocation with optional surrounding whitespace
#   (.*[[:space:]])?    — any intervening git subcommand / args before the bypass flag
#   (-c[[:space:]]+commit\.gpgsign[[:space:]]*=[[:space:]]*false|--no-verify|--no-gpg-sign)
#                       — the three bypass forms: config-level signing disable,
#                          hook-bypass flag, and gpg-sign bypass flag
BYPASS_RE='(^|&&|\|\||;|\|)[[:space:]]*git[[:space:]]+(.*[[:space:]])?(-c[[:space:]]+commit\.gpgsign[[:space:]]*=[[:space:]]*false|--no-verify|--no-gpg-sign)'

if echo "$FLAT_COMMAND" | grep -qE "$BYPASS_RE"; then
  echo "BLOCKED: git bypass flag detected in command." >&2
  echo "" >&2
  echo "  Command: $COMMAND" >&2
  echo "" >&2
  echo "  The coordinator doctrine prohibits --no-verify, --no-gpg-sign, and" >&2
  echo "  -c commit.gpgsign=false. These flags skip commit hooks or signing that" >&2
  echo "  guard the audit trail and quality gates." >&2
  echo "" >&2
  echo "  If the PM has explicitly authorized bypassing hooks for this commit," >&2
  echo "  set COORDINATOR_OVERRIDE_NO_VERIFY=1 before re-running." >&2
  exit 2
fi

exit 0
