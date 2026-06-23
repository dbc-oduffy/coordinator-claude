#!/usr/bin/env bash
# Review: code-reviewer — use env bash; /bin/bash on macOS is 3.2 (DR-148)
# PreToolUse(Bash) hook: offer the popup-safe alternative when a bare
# console-subprocess shape (python -c, powershell.exe, netstat.exe, etc.)
# is executed via the Bash tool on Windows.
#
# Output shape: permissionDecision:"allow" + additionalContext — advisory only,
# NEVER blocks. Model: suggest-sonnet-research.sh (not offer-git-c-over-cd.sh
# which denies; see plan C1 rationale for why these differ).
#
# Windows self-gate (load-bearing, AC2/AC2b): the hook silently exits 0 on
# macOS/Linux and under WSL2 (uname -s = Linux, WINDIR/OS unset). The WSL
# case is CORRECT — WSL-resolved python is a Linux ELF that does NOT call
# AllocConsole; the gate must NOT use /proc/version Microsoft-detection or it
# would nag WSL operators on a popup that cannot occur (fight-the-hook).
# Detection pattern: bash-on-windows-gotchas.md § Windows detection idiom.
#
# Canonical suppression marker: # popup-intentional-last-resort
# When this marker appears in the command, the hook exits 0 silently (AC9).
#
# Spec backlink: docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md § C1

# --- Windows self-gate (load-bearing — must be first) ---
_uname_s=""
_uname_s=$(uname -s 2>/dev/null || true)
case "$_uname_s" in
  MINGW*|CYGWIN*|MSYS*) : ;;  # native Windows Git-Bash / Cygwin / MSYS2
  *)
    # Also Windows if WINDIR or OS=Windows_NT are set (covers conhost + cmd.exe parents).
    if [[ -z "${WINDIR:-}" && "${OS:-}" != "Windows_NT" ]]; then
      exit 0  # macOS, Linux, WSL2 — all silent (correct)
    fi
    ;;
esac

# --- Read stdin JSON and extract tool_input.command ---
INPUT=$(cat 2>/dev/null || true)

CMD=""
# Bash parameter-expansion extraction idiom (no jq dependency — same pattern as
# suggest-sonnet-research.sh's AGENT_ID extraction).
if [[ "$INPUT" == *'"command"'* ]]; then
  _tmp="${INPUT#*\"command\":\"}"
  # The value may span multiple lines in a heredoc command; grab the raw JSON string.
  # We need to handle escaped quotes inside the value — extract up to the first
  # unescaped closing quote by removing known escape sequences first.
  # Review: code-reviewer — NUL placeholder was broken: literal "\x00" 4-char string
  # on write side vs ANSI-C $'\x00' on restore (bash vars cannot hold NUL anyway).
  # Fix: use SOH ($'\x01') as a printable sentinel — evaluated identically on both sides.
  _ph=$'\x01'
  _unesc="${_tmp//\\\"/$_ph}"          # replace \" with SOH sentinel
  CMD="${_unesc%%\"*}"                  # cut at the first real closing quote
  CMD="${CMD//$_ph/\"}"                 # restore literal quotes
  # Unescape common JSON escape sequences for matching purposes.
  CMD="${CMD//\\n/$'\n'}"
  CMD="${CMD//\\t/$'\t'}"
  CMD="${CMD//\\\\/\\}"
fi

[[ -z "$CMD" ]] && exit 0

# --- Canonical suppression marker (AC9) ---
if [[ "$CMD" == *'# popup-intentional-last-resort'* ]]; then
  exit 0
fi

# --- Skip if already routed through a safe form ---
# python-quiet.sh wrapper, pythonw (GUI subsystem), or explicit creationflags suppressor.
if [[ "$CMD" == *'python-quiet.sh'* || "$CMD" == *'python3-quiet.sh'* ]]; then
  exit 0
fi
if [[ "$CMD" == *'pythonw'* ]]; then
  exit 0
fi
if [[ "$CMD" == *'CREATE_NO_WINDOW'* || "$CMD" == *'creationflags'* ]]; then
  exit 0
fi

# --- Match bare console-subprocess shapes ---
# Regex targets (BRE, BSD grep compatible — no grep -P):
#   (^|whitespace/;&|`) python[3][.exe]  (-c | -m | - | << | <()
#   bare powershell.exe or netstat.exe token
#
# We use case matching and grep -E (ERE) with -q since grep -P is forbidden (DR-148).
# The backtick character is included in the separator class via a literal in the ERE.

MATCHED=0

# Pattern 1: python/-c/-m/- heredoc shapes
# Separator chars before python: start-of-line, space, tab, ;, &, |, backtick
# Review: code-reviewer — duplicate `-[[:space:]]` alternation; second should be `-$`
# to catch `python -` at end-of-string (heredoc form).
# Review: code-reviewer (F2) — include `py(\.exe)?` and versioned `python3?([0-9.]+)?`
# to cover `py -c` (common Windows launcher) and e.g. `python3.11 -c`.
if printf '%s' "$CMD" | grep -qE '(^|[[:space:];|&`])(python3?([0-9.]+)?(\.exe)?|py(\.exe)?)[[:space:]]+(-c[[:space:]]|-c$|-m[[:space:]]|-m$|-[[:space:]]|-$|<<|<\()'; then
  MATCHED=1
fi

# Pattern 2: python3? / py followed by just " -" then end/space (python - <<EOF heredoc)
# Already covered by the <<|<\( branch above, but add a belt-and-braces for bare `-`
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$CMD" | grep -qE '(^|[[:space:];|&`])(python3?([0-9.]+)?(\.exe)?|py(\.exe)?)[[:space:]]+-[[:space:]]'; then
    MATCHED=1
  fi
fi

# Pattern 3: bare powershell.exe token
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$CMD" | grep -qE '(^|[[:space:];|&`])powershell\.exe([[:space:]]|$)'; then
    MATCHED=1
  fi
fi

# Pattern 4: bare netstat.exe token
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$CMD" | grep -qE '(^|[[:space:];|&`])netstat\.exe([[:space:]]|$)'; then
    MATCHED=1
  fi
fi

[[ $MATCHED -eq 0 ]] && exit 0

# --- Determine the best offer to make ---
# If the consuming project ships python-quiet.sh, name it; otherwise offer creationflags.
OFFER_TEXT=""
if [[ -f "$(pwd)/bin/python-quiet.sh" || -f "$(pwd)/python-quiet.sh" ]]; then
  OFFER_TEXT="Use the project's popup-safe wrapper instead of the bare interpreter:

  bin/python-quiet.sh -c '...'   # or  bin/python-quiet.sh -m module

This wrapper sets CREATE_NO_WINDOW so the python process does NOT call AllocConsole() or steal focus under the headless Claude Code Bash-tool parent on Windows.

If a wrapper is not available, add creationflags=0x08000000 (subprocess.CREATE_NO_WINDOW) to your subprocess.run() / Popen() call."
else
  OFFER_TEXT="This command spawns a console-subsystem child (python.exe / powershell.exe / netstat.exe). Under the headless Claude Code Bash-tool parent on Windows, that child calls AllocConsole() and a focus-stealing console window pops up.

Popup-safe alternatives:
  • subprocess.run([...], creationflags=0x08000000)   # CREATE_NO_WINDOW
  • subprocess.Popen([...], creationflags=subprocess.CREATE_NO_WINDOW)
  • Use the project's bin/python-quiet.sh wrapper if present.

If the popup is intentional and expected (e.g. debugging on a local desktop), add the marker comment to the calling shell line:
  python -c '...'  # popup-intentional-last-resort"
fi

# Review: code-reviewer (F13) — OFFER_TEXT is multi-line; embedding it raw in the JSON
# heredoc string produces literal newlines = invalid JSON. Encode \ " and \n before embed.
OFFER_TEXT_J="${OFFER_TEXT//\\/\\\\}"           # escape backslashes first
OFFER_TEXT_J="${OFFER_TEXT_J//\"/\\\"}"         # escape double-quotes
OFFER_TEXT_J="${OFFER_TEXT_J//$'\n'/\\n}"       # encode literal newlines as \n

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"WINDOWS CONSOLE POPUP ADVISORY: The command being executed contains a bare console-subprocess shape that will trigger AllocConsole() and flash a focus-stealing console window on Windows.\\n\\n%s\\n\\nThis advisory is suppress-able per invocation by adding '"'"'# popup-intentional-last-resort'"'"' as a comment on the calling shell line. Hook: nudge-windows-console-popup.sh (coordinator Layer 0)."}}\n' \
  "$OFFER_TEXT_J"
