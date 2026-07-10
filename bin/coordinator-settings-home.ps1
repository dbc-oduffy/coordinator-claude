# coordinator-settings-home.ps1 — bare-name forwarder (PowerShell twin of the bash
# coordinator/bin/coordinator-settings-home forwarder). The real resolver installs to
# <CLAUDE_HOME>\.claude\bin (CLAUDE_HOME-aware, retained compat forwarder that itself
# resolves the settings home); this forwarder lives in the harness-injected plugin bin
# so bare `coordinator-settings-home.ps1` resolves on Windows/pwsh tool shells where
# <CLAUDE_HOME>\.claude\bin is NOT on PATH — parity with the machine-local / claude-home
# PowerShell forwarders (see coordinator/templates/bin/claude-machine-local.ps1).
#
# WHY THIS EXISTS: shape-(iv) install-chain consumers bind to
# $(coordinator-settings-home)\<repo-id>\ per the agent-install-contract. Without this
# forwarder the seam CLI resolves only by absolute path (<CLAUDE_HOME>\.claude\bin or
# the settings-home bin, neither reliably on PATH), so consumers cannot bind bare —
# the exact gap example-game-repo-em flagged on 2026-07-06 for the bash resolver, mirrored here
# for the PowerShell/.ps1-seeder consumers (project-rag, cockpit, ue-addon, example-game-repo).
# Spec: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1/C9
#       docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C4b

# CLAUDE_HOME is a $HOME-substitute per machine-local-registry.md §4a (CLAUDE_HOME=/x →
# install at /x/.claude/), so the .claude suffix is correct here — same as the bash
# forwarder and the machine-local forwarder. PowerShell-native fallback chain:
# $env:CLAUDE_HOME, else $env:USERPROFILE (Windows analog of $HOME), else $HOME
# (pwsh sets $HOME cross-platform) — no bash `${VAR:-default}` parameter expansion.
$claudeHomeBase = if ($env:CLAUDE_HOME) {
    $env:CLAUDE_HOME
} elseif ($env:USERPROFILE) {
    $env:USERPROFILE
} else {
    $HOME
}

$real = Join-Path (Join-Path (Join-Path $claudeHomeBase '.claude') 'bin') 'coordinator-settings-home.ps1'

if (-not (Test-Path $real)) {
    [Console]::Error.WriteLine("coordinator-settings-home: resolver not installed at $real -- run /coordinator:setup (Phase 3).")
    exit 127
}

& $real @args
exit $LASTEXITCODE
