#!/usr/bin/env bats
# nudge-windows-subprocess-popup.bats — bats tests for
#   hooks/scripts/nudge-windows-subprocess-popup.sh
#
# Purpose: regression coverage for the Layer-0' PreToolUse Write/Edit deny-with-offer
#   hook that blocks authoring of bare console-subprocess calls in .sh/.py/.ps1/.psm1
#   files and offers the PORTABLE creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
#   form as the fix. Throwaway paths (*/tasks/*, */state/scratch/*) are exempt (Option A,
#   2026-06-20) — session-scratch never ships to Windows.
#
# Design contract:
#   POSITIVE cases — hook emits permissionDecision:"deny" containing offer text.
#   NEGATIVE cases — hook exits 0 with NO output (silent allow).
#
# AC-coverage:
#   AC3 — deny-with-offer on bare subprocess.run(["powershell.exe",...]) and & python
#   AC9 — BOTH canonical markers suppress the hook:
#          `# popup-intentional-last-resort`  (popup occurs and is accepted)
#          `# popup-safe-env-suppressed`       (popup suppressed by env-var means; safe)
#   AC7 — bare env-var prefix (e.g. FOR_DISABLE_CONSOLE_CTRL_HANDLER=1) WITHOUT a marker
#          is NOT a suppression escape — hook still fires deny on BOTH detection branches
#          (the .ps1 branch and the .sh/.py subprocess.run/bare-python-c branch)
# Review: code-reviewer (A-F2) — added second marker and AC7 to coverage header.
#
# Run: npx bats plugins/coordinator-claude/coordinator/tests/nudge-windows-subprocess-popup.bats
#      from the ~/.claude repo root.
#      Override subject: HOOK=/abs/path npx bats <file>
#
# Portability (DR-148): bash >= 4 + BSD coreutils; no grep -P / sed -i.

SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
SUBJECT="${HOOK:-${SCRIPT_DIR}/../hooks/scripts/nudge-windows-subprocess-popup.sh}"

# ---------------------------------------------------------------------------
# Helper: build stdin JSON for Write tool
# ---------------------------------------------------------------------------
write_json() {
  local file_path="$1"
  local content="$2"
  # Use python3/python for reliable JSON encoding, fall back to printf with
  # manual escaping (BSD-portable, no jq dependency in test harness).
  local PY
  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if [[ -n "$PY" ]]; then
    printf '%s' "$content" | "$PY" -c "
import json, sys
content = sys.stdin.read()
print(json.dumps({
    'tool_name': 'Write',
    'tool_input': {
        'file_path': '$file_path',
        'content': content
    }
}))
"
  else
    # Minimal fallback — escapes double-quotes and newlines only.
    local esc_path="${file_path//\"/\\\"}"
    local esc_content
    esc_content=$(printf '%s' "$content" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
    printf '{"tool_name":"Write","tool_input":{"file_path":"%s","content":"%s"}}' \
      "$esc_path" "$esc_content"
  fi
}

# Helper: build stdin JSON for Edit tool (new_string only).
edit_json() {
  local file_path="$1"
  local new_string="$2"
  local PY
  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if [[ -n "$PY" ]]; then
    printf '%s' "$new_string" | "$PY" -c "
import json, sys
new_string = sys.stdin.read()
print(json.dumps({
    'tool_name': 'Edit',
    'tool_input': {
        'file_path': '$file_path',
        'old_string': '',
        'new_string': new_string
    }
}))
"
  else
    local esc_path="${file_path//\"/\\\"}"
    local esc_str
    esc_str=$(printf '%s' "$new_string" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
    printf '{"tool_name":"Edit","tool_input":{"file_path":"%s","old_string":"","new_string":"%s"}}' \
      "$esc_path" "$esc_str"
  fi
}

# ---------------------------------------------------------------------------
# Positive: Python file with bare subprocess.run(["powershell.exe",...])
# Expects: deny + offer text mentioning CREATE_NO_WINDOW
# AC3
# ---------------------------------------------------------------------------

@test "AC3: Python Write with bare subprocess.run powershell.exe → deny with offer" {
  local content
  content='import subprocess
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], capture_output=True)
print(result.stdout)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/check.py" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]] || \
    [[ "$output" == *'permissionDecision" : "deny"'* ]]
  [[ "$output" == *'CREATE_NO_WINDOW'* ]] || [[ "$output" == *'0x08000000'* ]]
}

# ---------------------------------------------------------------------------
# Positive: Python file with subprocess.Popen(["python.exe",...])
# Expects: deny
# ---------------------------------------------------------------------------

@test "AC3: Python Write with bare subprocess.Popen python.exe → deny" {
  local content
  content='import subprocess
proc = subprocess.Popen(["python.exe", "-c", "print(1)"])
proc.wait()'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/runner.py" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Positive: PowerShell file with bare `& python`
# Expects: deny
# AC3
# ---------------------------------------------------------------------------

@test "AC3: PowerShell Write with bare & python → deny with offer" {
  local content
  content='$result = & python -c "print(42)"
Write-Host $result'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/run.ps1" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Positive: PowerShell file with bare powershell.exe (no -WindowStyle Hidden)
# Expects: deny
# ---------------------------------------------------------------------------

@test "AC3: PowerShell Write with bare powershell.exe → deny" {
  local content
  content='powershell.exe -Command "Get-Process"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/helper.ps1" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Positive: .sh file with bare python -c invocation
# Expects: deny
# ---------------------------------------------------------------------------

@test "AC3: shell Write with bare python -c → deny" {
  local content
  content='#!/usr/bin/env bash
python -c "import sys; print(sys.version)"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/probe.sh" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Positive: Edit tool with bare subprocess.run in new_string
# Expects: deny
# ---------------------------------------------------------------------------

@test "AC3: Python Edit (new_string) with bare subprocess.run powershell.exe → deny" {
  local new_string
  new_string='result = subprocess.run(["powershell.exe", "-Command", "ls"], capture_output=True)'

  run bash "$SUBJECT" <<< "$(edit_json "/tmp/tool.py" "$new_string")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Negative: creationflags=subprocess.CREATE_NO_WINDOW present → silent
# AC3 negative
# ---------------------------------------------------------------------------

@test "AC3 neg: creationflags=subprocess.CREATE_NO_WINDOW present → silent" {
  local content
  content='import subprocess
result = subprocess.run(
    ["powershell.exe", "-Command", "Get-Date"],
    creationflags=subprocess.CREATE_NO_WINDOW,
    capture_output=True
)
print(result.stdout)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/safe.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: creationflags=0x08000000 literal present → silent
# ---------------------------------------------------------------------------

@test "AC3 neg: creationflags=0x08000000 present → silent" {
  local content
  content='import subprocess
proc = subprocess.run(["python.exe", "-c", "print(1)"], creationflags=0x08000000)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/safe2.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: no_console_creationflags() spread present → silent
# ---------------------------------------------------------------------------

@test "AC3 neg: no_console_creationflags() kwargs spread present → silent" {
  local content
  content='import subprocess
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], **no_console_creationflags())'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/safe3.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: canonical marker `# popup-intentional-last-resort` present → silent
# AC9 — cross-layer marker consistency
# ---------------------------------------------------------------------------

@test "AC9: # popup-intentional-last-resort marker suppresses hook → silent" {
  local content
  content='import subprocess
# popup-intentional-last-resort
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], capture_output=True)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/intentional.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: AC9 marker in PowerShell file → silent
# ---------------------------------------------------------------------------

@test "AC9: # popup-intentional-last-resort in .ps1 suppresses hook → silent" {
  local content
  content='# popup-intentional-last-resort
& python -c "print(42)"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/intentional.ps1" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: canonical marker `# popup-safe-env-suppressed` present → silent
# AC9 — second canonical cross-layer marker (env-var suppression confirmed safe)
# ---------------------------------------------------------------------------

@test "AC9: # popup-safe-env-suppressed in .py suppresses hook → silent" {
  local content
  content='import subprocess
# popup-safe-env-suppressed
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], capture_output=True)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/env_suppressed.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: AC9 second marker in PowerShell file → silent
# ---------------------------------------------------------------------------

@test "AC9: # popup-safe-env-suppressed in .ps1 suppresses hook → silent" {
  local content
  content='# popup-safe-env-suppressed
& python -c "print(42)"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/env_suppressed.ps1" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Positive: bare env-var prefix WITHOUT a marker does NOT suppress the hook.
# Pins the decision that structural env-var prefix alone is NOT a suppression
# escape — only the explicit canonical markers are. (generic-substrate rule)
# AC9 negative — env-prefix-only still fires deny
# ---------------------------------------------------------------------------

@test "AC9 neg: bare env-var prefix FOR_DISABLE_CONSOLE_CTRL_HANDLER=1 alone → still deny" {
  local content
  content='FOR_DISABLE_CONSOLE_CTRL_HANDLER=1 & python -c "print(42)"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/env_prefix_only.ps1" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# AC7 negative — env-var prefix on the .py / bare-python-c detection branch.
# The AC9 neg above only exercises the .ps1 branch (& python pattern).
# AC7 asserts the structural env-prefix escape is not adopted AT ALL — so the
# .sh/.py detection branch (subprocess.run/bare python -c grep, lines ~195-210)
# must also still fire deny when only the env-var prefix is present.
# Review: code-reviewer (A-F1) — pin AC7 on BOTH detection branches.
# ---------------------------------------------------------------------------

@test "AC9 neg: bare env-var prefix FOR_DISABLE_CONSOLE_CTRL_HANDLER=1 on .py branch → still deny" {
  local content
  content='FOR_DISABLE_CONSOLE_CTRL_HANDLER=1 python -c "print(42)"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/env_prefix_only.py" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Negative: PowerShell with -WindowStyle Hidden → silent
# AC3 negative
# ---------------------------------------------------------------------------

@test "AC3 neg: PowerShell .ps1 with -WindowStyle Hidden → silent" {
  local content
  content='powershell.exe -WindowStyle Hidden -Command "Get-Process"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/hidden.ps1" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: SHELL (.sh) with powershell.exe -WindowStyle Hidden → silent
# Regression: the .sh/.py allow-guard once recognized only Python suppressors
# and omitted -WindowStyle Hidden, denying legitimately-suppressed powershell.exe
# calls authored in shell scripts (e.g. install-substrate.sh Windows PATH steps).
# A direct shell powershell.exe invocation IS suppressed by -WindowStyle Hidden,
# matching the .ps1 branch and bin/verify-no-console-flash.sh.
# ---------------------------------------------------------------------------

@test "AC3 neg: shell .sh with powershell.exe -WindowStyle Hidden → silent" {
  local content
  content='#!/usr/bin/env bash
powershell.exe -NoProfile -WindowStyle Hidden -Command "Get-Process"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/path-add.sh" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Positive guard: SHELL (.sh) with bare powershell.exe (no -WindowStyle Hidden)
# still denies — the fix must not weaken protection for unsuppressed calls.
# ---------------------------------------------------------------------------

@test "AC3: shell .sh with bare powershell.exe (no suppression) → deny" {
  local content
  content='#!/usr/bin/env bash
powershell.exe -NoProfile -Command "Get-Process"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/bare-ps.sh" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# Negative: non-matching extension (.md) → silent skip
# ---------------------------------------------------------------------------

@test "Non-.py/.sh/.ps1/.psm1 extension (.md) → silent skip" {
  local content
  content='subprocess.run(["powershell.exe", "-Command", "Get-Date"])'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/notes.md" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: non-matching extension (.txt) → silent skip
# ---------------------------------------------------------------------------

@test "Non-matching extension (.txt) → silent skip" {
  local content
  content='powershell.exe -Command "Get-Process"'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/readme.txt" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Negative: non-file-mutation tool name (Bash) → silent skip
# ---------------------------------------------------------------------------

@test "Tool name Bash → silent skip (not a file-mutation tool)" {
  local json
  json='{"tool_name":"Bash","tool_input":{"command":"subprocess.run([\"powershell.exe\"])", "file_path":"/tmp/x.py"}}'

  run bash "$SUBJECT" <<< "$json"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Positive: .psm1 extension with bare python.exe -c → deny
# ---------------------------------------------------------------------------

@test "AC3: .psm1 file with python.exe -c → deny" {
  local content
  content='function Invoke-PythonCheck {
    python.exe -c "import sys; print(sys.version)"
}'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/module.psm1" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

# ---------------------------------------------------------------------------
# F12 — MultiEdit tool coverage (was missing)
# Review: code-reviewer (F12) — add positive MultiEdit case (edits[].new_string
# with a bare subprocess) → deny, and one negative with creationflags → silent.
# Note on F11: test-helper path injection (HOOK env var override) is a known
# limitation of the current harness — tests use the HOOK env var for override
# but do not validate PATH injection of stub tools. Acceptable for now.
# ---------------------------------------------------------------------------

# Helper: build stdin JSON for MultiEdit tool.
multiedit_json() {
  local file_path="$1"
  local new_string="$2"
  local PY
  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
  if [[ -n "$PY" ]]; then
    printf '%s' "$new_string" | "$PY" -c "
import json, sys
new_string = sys.stdin.read()
print(json.dumps({
    'tool_name': 'MultiEdit',
    'tool_input': {
        'file_path': '$file_path',
        'edits': [
            {'old_string': '', 'new_string': new_string}
        ]
    }
}))
"
  else
    local esc_path="${file_path//\"/\\\"}"
    local esc_str
    esc_str=$(printf '%s' "$new_string" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
    printf '{"tool_name":"MultiEdit","tool_input":{"file_path":"%s","edits":[{"old_string":"","new_string":"%s"}]}}' \
      "$esc_path" "$esc_str"
  fi
}

@test "F12: MultiEdit with bare subprocess in edits[].new_string → deny" {
  # Review: code-reviewer (F12) — MultiEdit path must also trigger deny on bare subprocess.
  local new_string
  new_string='import subprocess
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], capture_output=True)'

  run bash "$SUBJECT" <<< "$(multiedit_json "/tmp/runner.py" "$new_string")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}

@test "F12 neg: MultiEdit with creationflags in edits[].new_string → silent" {
  # Review: code-reviewer (F12) — MultiEdit negative: creationflags suppression → silent.
  local new_string
  new_string='import subprocess
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], creationflags=0x08000000)'

  run bash "$SUBJECT" <<< "$(multiedit_json "/tmp/safe_runner.py" "$new_string")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# ---------------------------------------------------------------------------
# Option A (2026-06-20): the offered fix must be the PORTABLE getattr form,
# not a bare 0x08000000 that crashes on macOS/Linux. Assert the deny reason
# carries the getattr form. (Memo Issue 2.)
# ---------------------------------------------------------------------------

@test "Option A: deny reason offers the portable getattr(CREATE_NO_WINDOW) form" {
  local content
  content='import subprocess
result = subprocess.run(["powershell.exe", "-Command", "Get-Date"], capture_output=True)'

  run bash "$SUBJECT" <<< "$(write_json "/tmp/check.py" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
  # The portable one-liner must be present in the offer text.
  [[ "$output" == *'getattr'* ]]
  [[ "$output" == *'CREATE_NO_WINDOW'* ]]
}

# ---------------------------------------------------------------------------
# Option A (2026-06-20): throwaway-path exemption. A bare console-subprocess
# in a */tasks/* or */state/scratch/* file is session-scratch that never ships
# to Windows → the authoring deny does NOT fire (silent allow). This closes the
# memo's dominant false-positive (a sys.executable re-invoke harness in tasks/).
# Production paths (no tasks/ or state/scratch/ segment) STILL deny — asserted
# by every other positive case above (all use /tmp/<name>.py).
# ---------------------------------------------------------------------------

@test "Option A: bare subprocess in a */tasks/* .py → silent (throwaway exemption)" {
  local content
  content='import subprocess, sys
proc = subprocess.Popen([sys.executable, "-m", "pkg.lsp.entry"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)'

  run bash "$SUBJECT" <<< "$(write_json "/Users/dev/project-rag-ue-addon/tasks/lsp_driver.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "Option A: bare subprocess in a */state/scratch/* .py → silent (throwaway exemption)" {
  local content
  content='import subprocess
subprocess.run(["python.exe", "-c", "print(1)"])'

  run bash "$SUBJECT" <<< "$(write_json "/Users/dev/.claude/state/scratch/probe.py" "$content")"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "Option A: bare subprocess in a PRODUCTION path (not tasks/scratch) → still deny" {
  # Guard against the exemption being too broad: a real source path must still deny.
  local content
  content='import subprocess
subprocess.run(["powershell.exe", "-Command", "Get-Date"])'

  run bash "$SUBJECT" <<< "$(write_json "/Users/dev/project-rag/src/probe.py" "$content")"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"permissionDecision":"deny"'* ]] || \
    [[ "$output" == *'permissionDecision": "deny"'* ]]
}
