#!/bin/bash
# verify-no-powershell-flash.sh — guard against blue-window flashes on Windows.
#
# Any powershell.exe/pwsh invocation from a hook, post-commit script, or hot-path
# helper must include `-WindowStyle Hidden` to suppress the brief console window
# Windows allocates for child processes. See:
# docs/wiki/claude-code-platform-gotchas.md § PowerShell hot-path invocations.
#
# Exits 0 if all sites are clean, 1 with a report otherwise.
# Scans coordinator/ and claude-unreal-holodeck/ plugin trees.

set -uo pipefail

ROOT="${1:-$HOME/.claude/plugins}"
fail=0

# Files where literal `powershell.exe` or ` pwsh ` appears as an invocation
# (not docs prose). We scan shell scripts, hook JSON, and helper binaries.
mapfile -t hits < <(
  grep -rEn --include='*.sh' --include='*.json' --include='coordinator-auto-push' \
    -e 'powershell\.exe[[:space:]]' -e '(^|[[:space:]/])pwsh[[:space:]]' \
    "$ROOT/coordinator-claude" "$ROOT/claude-unreal-holodeck" 2>/dev/null \
    | grep -v 'verify-no-powershell-flash' \
    || true
)

for line in "${hits[@]}"; do
  # Each line: file:lineno:content
  if ! grep -q -- '-WindowStyle[[:space:]]\+Hidden' <<<"$line"; then
    echo "MISSING -WindowStyle Hidden: $line"
    fail=1
  fi
done

if [[ "$fail" -eq 0 ]]; then
  echo "OK: all PowerShell hot-path invocations include -WindowStyle Hidden"
fi

exit "$fail"
