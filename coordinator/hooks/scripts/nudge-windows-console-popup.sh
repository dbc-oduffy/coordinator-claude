#!/usr/bin/env bash
# verify-no-console-flash: file-allow — this IS the C1 advisory hook; interpreter
# tokens in OFFER_TEXT strings below are user-facing advisory text, not spawns.
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
# Two env-agnostic suppression markers honored identically (parent-plan AC9, generalized
# to the two-marker set per docs/plans/2026-06-22-popup-suppression-marker-two-vocabulary-reconcile.md):
#   # popup-intentional-last-resort  — popup occurs and is accepted at this site
#   # popup-safe-env-suppressed      — popup suppressed at this site by env-var means (safe)
# When either marker appears in the command, the hook exits 0 silently.
# Review: code-reviewer (A-F5) — clarified AC reference to include reconcile plan citation.
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

# --- Canonical suppression markers (AC9) ---
if [[ "$CMD" == *'# popup-intentional-last-resort'* || "$CMD" == *'# popup-safe-env-suppressed'* ]]; then
  exit 0
fi

# --- Skip if already routed through a safe form ---
# python-quiet.sh wrapper, pythonw (GUI subsystem), or explicit creationflags suppressor.
if [[ "$CMD" == *'python-quiet.sh'* || "$CMD" == *'python3-quiet.sh'* ]]; then
  exit 0
fi
# spawn-hidden.sh is the coordinator's console-suppressing launcher (lib/spawn-hidden.sh):
# in --stdin-mode=safe it resolves to pythonw.exe (/SUBSYSTEM:WINDOWS, no AllocConsole),
# so a command routed through it is already popup-safe — same class as python-quiet.sh.
# (holodeck-em calibration, 2026-06-22-windows-fresh-install-fixes-reply memo item 4b.)
# Substring match (review F5): a command that merely mentions spawn-hidden.sh (in a comment
# or a path arg) is also skipped — same exposure as the python-quiet.sh precedent above; a
# false-negative on a genuine spawn is tolerable for this advisory-only hook.
if [[ "$CMD" == *'spawn-hidden.sh'* ]]; then
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
# Matches run against SCAN (lookup-neutralized below), not raw CMD.

# Neutralize pure PATH-lookup subexpressions before matching: a `command -v <tok>` /
# `which <tok>` / `type <tok>` / `hash <tok>` resolves a PATH entry and NEVER spawns the
# binary — matching it is a false-positive (holodeck-em calibration,
# 2026-06-22-windows-fresh-install-fixes-reply memo item 4a). Strip the lookup-keyword + its
# single token from a scan-only copy; the real CMD is untouched, so a compound that probes a
# tool and THEN runs it still fires on the genuine spawn half. The lookup keyword must sit at
# a command position (start or after a separator) so a quoted token inside an inline
# interpreter invocation is not stripped. Over-stripping can only yield a false-NEGATIVE on an
# advisory-only hook — strictly safer than the nag it removes.
SCAN="$CMD"
if command -v sed >/dev/null 2>&1; then
  SCAN=$(printf '%s' "$CMD" | sed -E 's/(^|[[:space:];|&`])(command[[:space:]]+-[vV]|which|type|hash)[[:space:]]+[^[:space:];|&`]+/\1 /g')
fi
# Maintainer notes (review F1/F2/F3):
#   - `type`/`hash` are also ordinary English words; ONLY the command-position anchor (the
#     leading separator class) keeps them from stripping non-builtin occurrences. Do not
#     extend the lookup alternation without re-checking separator coverage.
#   - A degenerate lookup with no following token (e.g. a bare `command -v`) does not match,
#     so SCAN is left unchanged; no downstream pattern fires on a bare `command` token, so
#     the result is correctly silent.
#   - The `SCAN="$CMD"` pre-seed + `command -v sed` guard is PROTECTIVE, not removable: with
#     `sed` absent the command substitution would yield an EMPTY SCAN and silently suppress
#     EVERY advisory (worse than a stray nag). The guard degrades to pre-4a behavior instead.
#     `sed` is present on every target (Git-Bash, macOS, Linux), so the fallback never fires
#     in practice.

MATCHED=0

# Pattern 1: python/-c/-m/- heredoc shapes
# Separator chars before python: start-of-line, space, tab, ;, &, |, backtick
# Review: code-reviewer — duplicate `-[[:space:]]` alternation; second should be `-$`
# to catch `python -` at end-of-string (heredoc form).
# Review: code-reviewer (F2) — include `py(\.exe)?` and versioned `python3?([0-9.]+)?`
# to cover `py -c` (common Windows launcher) and e.g. `python3.11 -c`.
if printf '%s' "$SCAN" | grep -qE '(^|[[:space:];|&`])(python3?([0-9.]+)?(\.exe)?|py(\.exe)?)[[:space:]]+(-c[[:space:]]|-c$|-m[[:space:]]|-m$|-[[:space:]]|-$|<<|<\()'; then
  MATCHED=1
fi

# Pattern 2: python3? / py followed by just " -" then end/space (python - <<EOF heredoc)
# Already covered by the <<|<\( branch above, but add a belt-and-braces for bare `-`
# (review F7): Pattern 2 is effectively subsumed by Pattern 1's `-$`/`-[[:space:]]` branches;
# retained only as belt-and-braces against future Pattern 1 edits.
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$SCAN" | grep -qE '(^|[[:space:];|&`])(python3?([0-9.]+)?(\.exe)?|py(\.exe)?)[[:space:]]+-[[:space:]]'; then
    MATCHED=1
  fi
fi

# Pattern 3: bare powershell.exe token
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$SCAN" | grep -qE '(^|[[:space:];|&`])powershell\.exe([[:space:]]|$)'; then
    MATCHED=1
  fi
fi

# Pattern 4: bare netstat.exe token
if [[ $MATCHED -eq 0 ]]; then
  if printf '%s' "$SCAN" | grep -qE '(^|[[:space:];|&`])netstat\.exe([[:space:]]|$)'; then
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
  # verify-no-console-flash: allow — OFFER_TEXT is a user-facing advisory message; python.exe /
  # powershell.exe tokens below are string literals describing the problem, not interpreter spawns.
  OFFER_TEXT="This command spawns a console-subsystem child (python.exe / powershell.exe / netstat.exe). Under the headless Claude Code Bash-tool parent on Windows, that child calls AllocConsole() and a focus-stealing console window pops up.

Popup-safe alternatives:
  • subprocess.run([...], creationflags=0x08000000)   # CREATE_NO_WINDOW
  • subprocess.Popen([...], creationflags=subprocess.CREATE_NO_WINDOW)
  • Use the project's bin/python-quiet.sh wrapper if present.

If the popup is intentional and expected (e.g. debugging on a local desktop), or suppressed by env-var means, add one of these marker comments to the calling shell line:
  python -c '...'  # popup-intentional-last-resort
  python -c '...'  # popup-safe-env-suppressed"
fi

# Review: code-reviewer (F13) — OFFER_TEXT is multi-line; embedding it raw in the JSON
# heredoc string produces literal newlines = invalid JSON. Encode \ " and \n before embed.
OFFER_TEXT_J="${OFFER_TEXT//\\/\\\\}"           # escape backslashes first
OFFER_TEXT_J="${OFFER_TEXT_J//\"/\\\"}"         # escape double-quotes
OFFER_TEXT_J="${OFFER_TEXT_J//$'\n'/\\n}"       # encode literal newlines as \n

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"WINDOWS CONSOLE POPUP ADVISORY: The command being executed contains a bare console-subprocess shape that will trigger AllocConsole() and flash a focus-stealing console window on Windows.\\n\\n%s\\n\\nThis advisory is suppress-able per invocation by adding '"'"'# popup-intentional-last-resort'"'"' (popup accepted) or '"'"'# popup-safe-env-suppressed'"'"' (popup suppressed by env-var means) as a comment on the calling shell line. Hook: nudge-windows-console-popup.sh (coordinator Layer 0)."}}\n' \
  "$OFFER_TEXT_J"
