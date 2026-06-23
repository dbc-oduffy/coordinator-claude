#!/usr/bin/env bats
# nudge-windows-console-popup.bats — bats tests for hooks/scripts/nudge-windows-console-popup.sh
#
# Purpose: regression coverage for the Layer-0 PreToolUse Bash offer hook.
#   Verifies Windows-gated fire (allow+additionalContext), macOS/Linux/WSL2 silence,
#   positive console-subprocess shapes, negative (already-safe) shapes, and the
#   canonical suppression marker (AC9).
#
# Spec backlink: docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md
#   § C1 — AC1, AC2, AC2b, AC9
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/nudge-windows-console-popup.bats
#      from the ~/.claude repo root.
#      (Override subject: POPUP_HOOK=/abs/path npx bats <file>)
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / date -d / sed -i.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="${POPUP_HOOK:-${SCRIPT_DIR}/../hooks/scripts/nudge-windows-console-popup.sh}"

# ---------------------------------------------------------------------------
# Helper: build a minimal hook JSON payload for a given command string.
# Uses bash string substitution to escape inner double-quotes — no jq needed.
# ---------------------------------------------------------------------------
make_payload() {
  local cmd="$1"
  # Escape backslashes then double-quotes for JSON string embedding.
  local escaped="${cmd//\\/\\\\}"
  escaped="${escaped//\"/\\\"}"
  printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$escaped"
}

# ---------------------------------------------------------------------------
# AC1 — Windows-gated FIRE: set WINDIR to simulate Windows environment.
# Hook must emit permissionDecision:"allow" and additionalContext with the offer.
# ---------------------------------------------------------------------------

@test "AC1: fires allow+additionalContext for 'python -c' when WINDIR is set" {
  local payload
  payload=$(make_payload "python -c 'print(1)'")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
  [[ "$output" == *'"additionalContext"'* ]]
  [[ "$output" == *'WINDOWS CONSOLE POPUP ADVISORY'* ]]
}

# ---------------------------------------------------------------------------
# AC2 — macOS/Linux silence: WINDIR/OS unset, uname = Darwin (natural on this Mac).
# Hook must exit 0 with NO output.
# ---------------------------------------------------------------------------

@test "AC2: silent (no output, exit 0) on macOS — uname=Darwin, WINDIR and OS unset" {
  local payload
  payload=$(make_payload "python -c 'print(1)'")
  # Review: code-reviewer (F10) — stub uname to return Darwin so the test is hermetic
  # on any CI runner (not tied to BettaAir's natural uname output).
  local stub_dir
  stub_dir="$(mktemp -d)"
  printf '#!/bin/sh\necho Darwin\n' > "$stub_dir/uname"
  chmod +x "$stub_dir/uname"
  run env -i HOME="$HOME" PATH="${stub_dir}:$PATH" \
      bash "$SUBJECT" <<< "$payload"
  rm -rf "$stub_dir"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# AC2b — WSL2 silence: uname -s returns Linux, WINDIR/OS unset.
# This is CORRECT behavior — WSL python is a Linux ELF, no AllocConsole.
# A future maintainer must NOT "fix" this into WSL nagging.
# ---------------------------------------------------------------------------

@test "AC2b: silent (no output, exit 0) under WSL2 conditions — uname=Linux, WINDIR/OS unset" {
  local payload
  payload=$(make_payload "python -c 'print(1)'")
  # Stub uname to return Linux; unset WINDIR and OS to simulate WSL2 environment.
  local stub_dir
  stub_dir="$(mktemp -d)"
  printf '#!/bin/sh\necho Linux\n' > "$stub_dir/uname"
  chmod +x "$stub_dir/uname"
  run env -i HOME="$HOME" PATH="${stub_dir}:$PATH" \
      bash "$SUBJECT" <<< "$payload"
  rm -rf "$stub_dir"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Positive shapes (under WINDIR) — hook must fire for each.
# ---------------------------------------------------------------------------

@test "positive: 'python3 -c ...' fires advisory" {
  local payload
  payload=$(make_payload "python3 -c 'import sys; print(sys.version)'")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
}

@test "positive: 'python -m module' fires advisory" {
  local payload
  payload=$(make_payload "python -m pytest tests/")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
}

@test "positive: bare 'powershell.exe' fires advisory" {
  local payload
  payload=$(make_payload "powershell.exe -NoProfile -Command Get-Date")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
}

@test "positive: python heredoc shape 'python - <<EOF' fires advisory" {
  # The << heredoc trigger in the command string
  local payload
  payload=$(make_payload "python - <<EOF\nprint('hello')\nEOF")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
}

# ---------------------------------------------------------------------------
# Negative shapes — hook must stay SILENT (exit 0, no output) for each.
# ---------------------------------------------------------------------------

@test "negative: python-quiet.sh wrapper is already safe — silent" {
  local payload
  payload=$(make_payload "bin/python-quiet.sh -c 'print(1)'")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "negative: pythonw (GUI subsystem) — silent" {
  local payload
  payload=$(make_payload "pythonw myscript.py")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "negative: command already carries CREATE_NO_WINDOW — silent" {
  local payload
  payload=$(make_payload "python -c 'import subprocess; subprocess.run([\"cmd\"], creationflags=0x08000000)'")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "AC9: canonical suppression marker '# popup-intentional-last-resort' suppresses C1" {
  local payload
  payload=$(make_payload "python -c 'print(1)'  # popup-intentional-last-resort")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# F15 — netstat.exe positive test (was missing; Pattern 4 coverage)
# ---------------------------------------------------------------------------

@test "positive: 'netstat.exe -an' fires advisory" {
  # Review: code-reviewer (F15) — add explicit netstat.exe positive case for Pattern 4.
  local payload
  payload=$(make_payload "netstat.exe -an")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
  [[ "$output" == *'"additionalContext"'* ]]
}

# ---------------------------------------------------------------------------
# F8 — NUL-placeholder round-trip: command containing escaped quotes must
# extract correctly and still fire the advisory.
# ---------------------------------------------------------------------------

@test "F8 round-trip: command with escaped quotes (json.dumps) extracts and fires advisory" {
  # Review: code-reviewer (F8) — verify the SOH-sentinel round-trip correctly handles
  # commands containing escaped \" sequences (python -c with embedded dict literal).
  local payload
  payload=$(make_payload 'python -c "import json; print(json.dumps({\"k\":1}))"')
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision"'* ]]
  [[ "$output" == *'"allow"'* ]]
}

# ---------------------------------------------------------------------------
# F13 — JSON validity: the output of the hook must be valid JSON.
# ---------------------------------------------------------------------------

@test "F13 JSON validity: hook output parses as valid JSON" {
  # Review: code-reviewer (F13) — OFFER_TEXT is multi-line; embedding raw produces
  # invalid JSON. Verify the encoded output is parseable.
  local payload
  payload=$(make_payload "python -c 'print(1)'")
  run env -i HOME="$HOME" WINDIR="C:\\Windows" PATH="$PATH" \
      bash "$SUBJECT" <<< "$payload"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | python3 -c 'import json,sys; json.load(sys.stdin)'
}
