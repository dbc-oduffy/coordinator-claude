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
#
# Sourceable interface: check_no_verify "$command_string" "$session_id"
#   Prints deny JSON to stdout when blocked; prints nothing and returns 0 when allowed.
#   Does NOT read stdin — caller is responsible for parsing input.

check_no_verify() {
  # Honor escape hatch before doing any work.
  if [[ "${COORDINATOR_OVERRIDE_NO_VERIFY:-0}" == "1" ]]; then
    return 0
  fi

  local COMMAND="$1"
  # $2 is session_id — accepted for dispatcher callers, unused in current detection logic.

  # Fast exit: no command to inspect.
  [[ -z "$COMMAND" ]] && return 0

  # Strip CR so the deny message shown to the agent is CR-clean — a bare CR
  # causes a misplaced cursor-return in some terminals and obscures the reason text.
  # On Windows/Git-Bash the native jq.exe injects CR before every LF (text-mode
  # decode); a bare CR is never a meaningful shell token, so stripping it is safe.
  # This also keeps the guard consistent with the other guards in the dispatcher set.
  # FLAT_COMMAND below strips \r independently for the regex match; this strip's
  # primary effect is clean deny-message output.
  COMMAND="${COMMAND//$'\r'/}"

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
  local FLAT_COMMAND
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
  local BYPASS_RE='(^|&&|\|\||;|\|)[[:space:]]*git[[:space:]]+(.*[[:space:]])?(-c[[:space:]]+commit\.gpgsign[[:space:]]*=[[:space:]]*false|--no-verify|--no-gpg-sign)'

  if echo "$FLAT_COMMAND" | grep -qE "$BYPASS_RE"; then
    local REASON="BLOCKED: git bypass flag detected. The coordinator doctrine prohibits --no-verify, --no-gpg-sign, and -c commit.gpgsign=false. If the PM has explicitly authorized bypassing hooks, set COORDINATOR_OVERRIDE_NO_VERIFY=1 before re-running."
    if command -v jq &>/dev/null; then
      jq -nc --arg r "$REASON" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
    else
      local esc="${REASON//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
    fi
    return 0
  fi

  return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -uo pipefail

  # Safe stdin read — timeout prevents hang on Windows/Git Bash.
  if command -v timeout &>/dev/null; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
  fi

  # Parse command — prefer jq, fall back to sed.
  if command -v jq &>/dev/null; then
    cmd=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  else
    cmd=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  # Parse session_id — prefer jq, fall back to sed.
  if command -v jq &>/dev/null; then
    sid=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  else
    sid=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  check_no_verify "$cmd" "$sid"; exit 0
fi
