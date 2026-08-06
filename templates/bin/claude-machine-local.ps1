# claude-machine-local.ps1 — sourced helper exporting $env:REPO_* for portable paths.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.3
#
# Settings-home contract (DR-072): the machine-local registry and its reader
# live under a settings home, not a fixed ~/.claude/bin path. Consumers MUST
# NOT invoke the bare-name `machine-local` wrapper to bootstrap — per
# docs/wiki/machine-local-registry.md:278, on Windows the bare-name `.cmd`
# wrapper hits a CreateProcess-no-PATHEXT / shebang trap when invoked from
# hidden-window install children. This script instead resolves the settings
# home by pure path arithmetic and invokes the reader impl directly:
#   <settings-home>/bin/_machine_local.py get|keys <key>
# Settings-home resolution ladder (most-specific first; mirrors, but does not
# source, coordinator/lib/settings-home.sh — this file is installed standalone
# on a consumer machine where that lib is not guaranteed present):
#   1. $env:COORDINATOR_SETTINGS_HOME (if non-empty) → use verbatim
#   2. else ${env:CLAUDE_HOME} (if non-empty), else $HOME → join
#      .coordinator-claude-settings
#
# Negative-spec: empty-string values are NOT exported. An empty $env:REPO_FOO
# would corrupt "$($env:REPO_FOO)/subdir" path joins to "/subdir" — matching
# the suppression in claude-machine-local.sh.
#
# Usage:
#   . <settings-home>/bin/claude-machine-local.ps1
#   "$($env:REPO_PROJECT_RAG)/subdir/file.py"

if ($env:CLAUDE_MACHINE_LOCAL_SOURCED) { return }

if ($env:COORDINATOR_SETTINGS_HOME) {
    $_settingsHome = $env:COORDINATOR_SETTINGS_HOME
} else {
    $_homeRoot = if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { $HOME }
    $_settingsHome = Join-Path $_homeRoot ".coordinator-claude-settings"
}
$_reader = Join-Path (Join-Path $_settingsHome "bin") "_machine_local.py"

$_python = $null
foreach ($_candidate in @("python3", "python")) {
    if (Get-Command $_candidate -ErrorAction SilentlyContinue) {
        $_python = $_candidate
        break
    }
}
if (-not $_python) {
    Write-Error "claude-machine-local: no python3 or python interpreter found on PATH — cannot invoke $_reader. Install Python 3 and re-source this file."
    Remove-Variable -Name _settingsHome, _homeRoot, _reader, _python, _candidate -ErrorAction SilentlyContinue
    return
}

# psargv-nonempty-verified: $_reader is a Join-Path of three literal segments — non-empty by construction
$keys = & $_python $_reader keys 2>$null | Select-String -Pattern '^repos\.' -Raw
foreach ($key in $keys) {
    # Normalize: repos.foo-bar → REPO_FOO_BAR. Handle both . and - as separators.
    $var = "REPO_" + ($key.Substring("repos.".Length) -replace '[.\-]','_').ToUpper()
    # Validate identifier.
    if ($var -notmatch '^[A-Z_][A-Z0-9_]*$') {
        [Console]::Error.WriteLine("claude-machine-local: warning: skipping key '$key' — produces non-conformant identifier '$var'")
        continue
    }
    # Review: code-reviewer — F2, capture $LASTEXITCODE immediately after the
    # reader invocation and branch three ways, matching the .sh sibling's
    # `case $_ml_rc in 0|1|*)` exactly — value-emptiness alone conflates a
    # clean rc=1 absence with an rc>=2 operational failure (malformed TOML,
    # version guard), reintroducing the ambiguity the reader's exit-code
    # contract exists to prevent (2026-06-24 daemon bug).
    # psargv-nonempty-verified: $_reader Join-Path-constructed; $key survived a '^repos\.' filter so it always carries that prefix
    $value = & $_python $_reader get $key 2>$null
    $rc = $LASTEXITCODE
    if ($rc -eq 0) {
        # Review: code-reviewer — F1/F2, guard against the AC14
        # declared-but-unconfigured case (rc=0 with empty stdout) — exporting
        # "" would corrupt "$($env:REPO_FOO)/subdir" path joins.
        if ([string]::IsNullOrEmpty($value)) {
            [Console]::Error.WriteLine("claude-machine-local: warning: '$key' declared but has no value — `$env:${var} not exported")
        } else {
            Set-Item -Path "env:$var" -Value $value
        }
    } elseif ($rc -eq 1) {
        [Console]::Error.WriteLine("claude-machine-local: warning: '$key' not resolved by ladder — `$env:${var} not exported")
    } else {
        [Console]::Error.WriteLine("claude-machine-local: error: machine-local reader failed for '$key' (rc=$rc)")
    }
}

Remove-Variable -Name _settingsHome, _homeRoot, _reader, _python, _candidate, keys, key, var, value -ErrorAction SilentlyContinue

$env:CLAUDE_MACHINE_LOCAL_SOURCED = "1"
