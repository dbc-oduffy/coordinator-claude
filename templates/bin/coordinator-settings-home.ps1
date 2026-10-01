

# PowerShell twin of the Python coordinator-settings-home resolver -- must resolve the
# SAME settings-home path a POSIX-shell consumer on the same machine would.
# Hand-maintained, interpreter-free (never a generated trampoline): the contract with the
# .cmd twin is the OUTPUT -- same path, exit codes 0/1/2, divergence verdict.
# TRAP: the extensionless Python resolver is the source of truth; mirror every rung,
# subcommand and divergence-rule change here by hand. Keep the `$cmd = $args[0]` line
# intact -- test_settings_home_ps1_resolves_symlinks.py slices the script at it.
#   $env:COORDINATOR_SETTINGS_HOME  — explicit override (sandboxes/CI/XDG users)
#   ($env:CLAUDE_HOME or $env:HOME or $env:USERPROFILE or $HOME) + '\.coordinator-claude-settings'


# RAG-bait: coordinator settings-home PowerShell CLI resolver; COORDINATOR_SETTINGS_HOME

function Resolve-ClaudeHomeBase {
    # Rung-for-rung identical to the Python resolver: CLAUDE_HOME -> HOME -> USERPROFILE,
    # terminating on the automatic $HOME. Reads $env:HOME explicitly rather than the
    # automatic $HOME: PowerShell derives the automatic $HOME from USERPROFILE and ignores
    # $env:HOME on Windows, which would silently skip this rung and diverge from the Python resolver.
    if ($env:CLAUDE_HOME)   { return $env:CLAUDE_HOME }
    if ($env:HOME)          { return $env:HOME }
    if ($env:USERPROFILE)   { return $env:USERPROFILE }
    return $HOME
}

function Resolve-SettingsHome {
    # Mirrors bash _resolve(); no side effects.
    if ($env:COORDINATOR_SETTINGS_HOME) {
        return $env:COORDINATOR_SETTINGS_HOME
    }
    return Join-Path (Resolve-ClaudeHomeBase) '.coordinator-claude-settings'
}

function Resolve-CanonicalPath {
    # Mirrors the Python resolver's os.path.realpath: follows symlinks/junctions
    # to their target. Resolve-Path .ProviderPath does NOT do this -- it only
    # normalises the path, so a compat symlink reads as a false divergence.
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $Path }

    # [System.IO.Directory]::ResolveLinkTarget is .NET 6+ (pwsh 7+) and is not
    # present under Windows PowerShell 5.1. Probe before calling it.
    $resolveLinkTarget = [System.IO.Directory].GetMethod('ResolveLinkTarget')
    if ($resolveLinkTarget) {
        $target = [System.IO.Directory]::ResolveLinkTarget($Path, $true)
        if ($target) {
            return $target.FullName
        }
        return (Get-Item -Force -LiteralPath $Path).FullName
    }

    # PS 5.1 fallback: read the link's actual target rather than silently
    # returning the link's own FullName, which would reintroduce the bug.
    $item = Get-Item -Force -LiteralPath $Path
    if ($item.Target) {
        return (Get-Item -Force -LiteralPath $item.Target[0]).FullName
    }
    return $item.FullName
}

function Test-AbsentOrEmptyHusk {
    # Mirrors Python _is_absent_or_empty_husk(): a directory left empty by a completed
    # migration is not a second content home. Unreadable or non-directory counts as no-state.
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $true }
    try {
        return -not (Get-ChildItem -Force -LiteralPath $Path -ErrorAction Stop | Select-Object -First 1)
    } catch {
        return $true
    }
}

function Test-Divergence {
    # Mirrors Python _check_divergence(). True (OK) when either home holds no state (absent
    # or an empty post-migration husk) or both share a canonical path (compat symlink);
    # false (fail-loud) only when both hold content at different canonical paths.
    $settingsHome = Resolve-SettingsHome
    $claudeHomeBase = Resolve-ClaudeHomeBase
    $legacy = Join-Path (Join-Path $claudeHomeBase '.claude') 'machine-local'
    $new = Join-Path $settingsHome 'machine-local'

    if (Test-AbsentOrEmptyHusk -Path $legacy) { return $true }
    if (Test-AbsentOrEmptyHusk -Path $new) { return $true }

    $rpLegacy = Resolve-CanonicalPath -Path $legacy
    $rpNew = Resolve-CanonicalPath -Path $new

    if ($rpLegacy -ne $rpNew) {
        [Console]::Error.WriteLine("coordinator-settings-home: DIVERGENT MACHINE-LOCAL HOMES -- cannot safely resolve.")
        [Console]::Error.WriteLine("")
        [Console]::Error.WriteLine("Both <CLAUDE_HOME>\.claude\machine-local and <settings-home>\machine-local exist")
        [Console]::Error.WriteLine("and point at different content homes. Reading from either risks using stale or")
        [Console]::Error.WriteLine("incomplete registry data.")
        [Console]::Error.WriteLine("")
        [Console]::Error.WriteLine("Remediation -- re-run /coordinator:install (the substrate->settings-home")
        [Console]::Error.WriteLine("migration is now performed natively by the coordinator install step).")
        [Console]::Error.WriteLine("")
        [Console]::Error.WriteLine("Or set `$env:COORDINATOR_SETTINGS_HOME to the intended settings home and remove/")
        [Console]::Error.WriteLine("symlink the other directory to resolve the ambiguity.")
        [Console]::Error.WriteLine("  Legacy realpath : $rpLegacy")
        [Console]::Error.WriteLine("  New    realpath : $rpNew")
        return $false
    }
    return $true
}


$cmd = $args[0]

switch ($cmd) {
    $null {
        if (-not (Test-Divergence)) { exit 1 }
        Write-Output (Resolve-SettingsHome)
        exit 0
    }
    'check' {
        if (-not (Test-Divergence)) { exit 1 }
        exit 0
    }
    default {
        [Console]::Error.WriteLine("coordinator-settings-home: unknown subcommand: $cmd")
        [Console]::Error.WriteLine("Usage: coordinator-settings-home.ps1 [check]")
        exit 2
    }
}
