# claude-machine-local.ps1 — sourced helper exporting $env:REPO_* for portable paths.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.3
#
# Usage:
#   . ~/.claude/bin/claude-machine-local.ps1
#   "$($env:REPO_PROJECT_RAG)/subdir/file.py"

if ($env:CLAUDE_MACHINE_LOCAL_SOURCED) { return }

# OS-detect the reader invocation. On Windows use .cmd; elsewhere use the
# bash wrapper (pwsh runs on Linux and Mac too — must not hardcode .cmd).
$_reader = if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    "$HOME/.claude/bin/machine-local.cmd"
} else {
    "$HOME/.claude/bin/machine-local"
}

$keys = & $_reader keys 2>$null | Select-String -Pattern '^repos\.' -Raw
foreach ($key in $keys) {
    # Normalize: repos.foo-bar → REPO_FOO_BAR. Handle both . and - as separators.
    $var = "REPO_" + ($key.Substring("repos.".Length) -replace '[.\-]','_').ToUpper()
    # Validate identifier.
    if ($var -notmatch '^[A-Z_][A-Z0-9_]*$') {
        [Console]::Error.WriteLine("claude-machine-local: warning: skipping key '$key' — produces non-conformant identifier '$var'")
        continue
    }
    $value = & $_reader get $key 2>$null
    if ([string]::IsNullOrEmpty($value)) {
        [Console]::Error.WriteLine("claude-machine-local: warning: $key is unset (`$env:$var='')")
    }
    Set-Item -Path "env:$var" -Value $value
}

$env:CLAUDE_MACHINE_LOCAL_SOURCED = "1"
