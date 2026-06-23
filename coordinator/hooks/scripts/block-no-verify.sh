#!/usr/bin/env bash
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
#
# CRLF-robustness: this file MUST stay LF-only AND avoid backslash line-continuation
# in executable lines. A `\`+CRLF sequence makes `\` escape the CR (not the newline),
# splitting the statement and crashing the hook — which denies ALL bash. The pipeline
# below is therefore kept on a single physical line. (.gitattributes pins *.sh eol=lf.)

# Honor escape hatch before doing any work.
if [[ "${COORDINATOR_OVERRIDE_NO_VERIFY:-0}" == "1" ]]; then
  exit 0
fi

set -uo pipefail

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
#   1. Flatten every newline to a space so multi-line commands can't evade
#      detection. Three newline forms exist depending on the JSON parser path:
#      - Real LF (jq produces a real newline from JSON \n) — handled by `tr`.
#      - CRLF (\r\n from a Windows JSON path) — the `tr -d '\r'` strips the \r
#        first, then `tr '\n' ' '` turns the LF into a space.
#      - Literal \\n two-char (sed fallback leaves the JSON escape un-expanded)
#        — handled by the trailing `sed 's/\\n/ /g'`.
#      Any backslash left dangling from a former `\<LF>` line-continuation is
#      harmless: FLAT_COMMAND feeds the regex only, which tolerates arbitrary
#      chars between `git` and the bypass flag.
#   2. The result goes into FLAT_COMMAND for regex matching only;
#      COMMAND is preserved for the error message.
#   BSD-portability (DR-148): the previous GNU `sed ':a;N;$!ba'` slurp idiom
#   errors on macOS/BSD sed ("unused label") — labels/branches need newline,
#   not `;`, separators — leaking stderr on every commit. `tr '\n' ' '` is the
#   portable equivalent for a match-only flattened string.
FLAT_COMMAND=$(printf '%s' "$COMMAND" | tr -d '\r' | tr '\n' ' ' | sed 's/\\n/ /g')

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
  REASON="BLOCKED: git bypass flag detected. The coordinator doctrine prohibits --no-verify, --no-gpg-sign, and -c commit.gpgsign=false. If the PM has explicitly authorized bypassing hooks, set COORDINATOR_OVERRIDE_NO_VERIFY=1 before re-running."
  if command -v jq &>/dev/null; then
    jq -nc --arg r "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    esc="${REASON//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
fi

exit 0
