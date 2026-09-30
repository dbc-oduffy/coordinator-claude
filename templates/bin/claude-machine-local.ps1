# Sourced helper exporting $env:REPO_* for portable, host-independent repo paths. This
# script is installed standalone on a consumer machine, so it resolves the settings home
# by pure path arithmetic rather than sourcing a shared lib that is not guaranteed present.
#
# Empty-string values are NOT exported: an empty $env:REPO_FOO would corrupt
# "$($env:REPO_FOO)/subdir" path joins to "/subdir".

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

# One process: `dump --prefix repos --include-unset` resolves every
# repos.<slug> key through the full 4-rung ladder (incl. autodiscovery) and
# returns one JSON object — replacing the enumerate-then-read loop this
# script used to run (one `keys` spawn, then one `get` spawn per key). `null`
# = clean absence (rc=1), `""` = declared-but-unconfigured (rc=0, AC14), any
# other string = a resolved value. An operationally-failed key (rc>=2) is
# omitted from the object; stderr is deliberately NOT redirected here so the
# reader's own failure message (which names the key) still reaches the
# caller, matching the JSON dump's failures block.
# psargv-nonempty-verified: $_reader is a Join-Path of three literal segments — non-empty by construction
$_dumpJson = & $_python $_reader dump --prefix repos --include-unset
$_dumpRc = $LASTEXITCODE
if ($_dumpRc -ne 0 -and [string]::IsNullOrWhiteSpace($_dumpJson)) {
    # Reader failed and produced nothing -- most often a settings-home whose
    # _machine_local.py predates the `dump` verb. Every $env:REPO_* would silently be
    # unset; say so instead of degrading to an empty hashtable.
    Write-Error "claude-machine-local: reader at $_reader failed (rc=$_dumpRc) and returned nothing — no `$env:REPO_* is set. If it predates the 'dump' verb, re-run the coordinator install to refresh it."
}
$_dumped = if ([string]::IsNullOrWhiteSpace($_dumpJson)) { @{} } else { $_dumpJson | ConvertFrom-Json -AsHashtable }

foreach ($key in $_dumped.Keys) {
    $value = $_dumped[$key]
    # Normalize: repos.foo-bar → REPO_FOO_BAR. Handle both . and - as separators.
    $var = "REPO_" + ($key.Substring("repos.".Length) -replace '[.\-]','_').ToUpper()
    # Validate identifier.
    if ($var -notmatch '^[A-Z_][A-Z0-9_]*$') {
        [Console]::Error.WriteLine("claude-machine-local: warning: skipping key '$key' — produces non-conformant identifier '$var'")
        continue
    }
    if ($null -eq $value) {
        # Clean absence (rc=1) -- ladder found no value for this key; skip export.
        [Console]::Error.WriteLine("claude-machine-local: warning: '$key' not resolved by ladder — `$env:${var} not exported")
    } elseif ([string]::IsNullOrEmpty($value)) {
        
        # Declared-but-unconfigured (rc=0, AC14) — exporting "" would corrupt
        # "$($env:REPO_FOO)/subdir" path joins (see negative-spec above).
        [Console]::Error.WriteLine("claude-machine-local: warning: '$key' declared but has no value — `$env:${var} not exported")
    } else {
        # A pre-set, non-empty override wins over the ladder.
        if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($var))) {
            continue
        }
        Set-Item -Path "env:$var" -Value $value
    }
}

Remove-Variable -Name _settingsHome, _homeRoot, _reader, _python, _candidate, _dumpJson, _dumped, key, var, value -ErrorAction SilentlyContinue

$env:CLAUDE_MACHINE_LOCAL_SOURCED = "1"
