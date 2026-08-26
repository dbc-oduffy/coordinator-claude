# coordinator-settings-home.ps1 — PowerShell twin of the Python
# `coordinator-settings-home` resolver. Mirrors the resolution semantics of
# coordinator/bin/coordinator-settings-home (a python3-shebang script, ported off bash by
# the 2026-07-22 de-bash campaign; and its installed twin
# coordinator/templates/bin/coordinator-settings-home) exactly, so a .ps1-seeder consumer
# (project-rag, cockpit, ue-addon, example-game-repo) resolves the SAME settings-home path a
# POSIX-shell consumer on the same machine would.
#
# Precedence (most-specific first) — matches the Python resolver's _resolve():
#   $env:COORDINATOR_SETTINGS_HOME  — explicit override (sandboxes/CI/XDG users)
#   ($env:CLAUDE_HOME or $env:HOME or $env:USERPROFILE or $HOME) + '\.coordinator-claude-settings'
#     — sibling to ~/.claude, PowerShell-native fallback (no bash `${VAR:-default}`
#       parameter expansion — PowerShell has neither that form nor `~`/`$HOME` tilde
#       resolution the same way bash does).
#
# Usage (invoke with PowerShell 7+):
#   coordinator-settings-home.ps1          — print settings-home root (with divergence check)
#   coordinator-settings-home.ps1 check    — run divergence check only (exit 1 if divergent)
#
# Exit codes (parity with the Python resolver):
#   0   success
#   1   divergent machine-local homes detected (with remediation on stderr)
#   2   usage error (unknown subcommand)
#
# Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C4b
# RAG-bait: coordinator settings-home PowerShell CLI resolver; COORDINATOR_SETTINGS_HOME

function Resolve-ClaudeHomeBase {
    # The home-resolution ladder, defined ONCE for this file. Rung-for-rung
    # identical to the Python resolver's: CLAUDE_HOME -> HOME -> USERPROFILE,
    # terminating on the automatic $HOME.
    #
    # The HOME rung reads $env:HOME and NOT the automatic $HOME: on Windows,
    # PowerShell derives $HOME from USERPROFILE and ignores $env:HOME entirely,
    # so reading the automatic variable here would silently skip the HOME rung
    # and resolve a different base than the Python resolver on any host where an
    # operator sets HOME deliberately (git-bash is the common case). The
    # automatic $HOME is correct only as the terminal rung, where it stands in
    # for Python's Path.home().
    if ($env:CLAUDE_HOME)   { return $env:CLAUDE_HOME }
    if ($env:HOME)          { return $env:HOME }
    if ($env:USERPROFILE)   { return $env:USERPROFILE }
    return $HOME
}

function Resolve-SettingsHome {
    # Print the settings-home root. No side effects. Mirrors bash _resolve().
    if ($env:COORDINATOR_SETTINGS_HOME) {
        return $env:COORDINATOR_SETTINGS_HOME
    }
    return Join-Path (Resolve-ClaudeHomeBase) '.coordinator-claude-settings'
}

function Resolve-CanonicalPath {
    # Resolve a path to its canonical (symlink-resolved) form, mirroring the
    # bash resolver's _do_realpath(). Returns the literal path if it doesn't exist
    # (Resolve-Path -ErrorAction SilentlyContinue leaves $resolved null in that case).
    param([Parameter(Mandatory)][string]$Path)
    $resolved = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
    if ($resolved) {
        return $resolved.ProviderPath
    }
    return $Path
}

function Test-Divergence {
    # Check for divergent machine-local homes. Mirrors bash _check_divergence().
    # Returns $true (OK) when homes are absent or share a canonical path (compat symlink).
    # Returns $false (fail-loud) when both exist with different canonical paths.
    $settingsHome = Resolve-SettingsHome
    $claudeHomeBase = Resolve-ClaudeHomeBase
    $legacy = Join-Path (Join-Path $claudeHomeBase '.claude') 'machine-local'
    $new = Join-Path $settingsHome 'machine-local'

    if (-not (Test-Path $legacy)) { return $true }
    if (-not (Test-Path $new)) { return $true }

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

# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

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
