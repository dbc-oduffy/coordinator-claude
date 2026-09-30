

# directly. install-substrate.py substitutes __PYTHON_BIN__ with the


# is no longer on disk. That fallback also tries a host-local %LOCALAPPDATA%


$ErrorActionPreference = 'Stop'
$_here = Split-Path -Parent $MyInvocation.MyCommand.Path
$_entry = Join-Path $_here 'goal-kr-evidence.py'
$_pybin = '__PYTHON_BIN__'

# No placeholder-vs-placeholder test here: install-substrate.py replaces EVERY
# __PYTHON_BIN__ occurrence, so such a test compares the baked path against itself,
# is unconditionally true, and discards the bake precisely when it succeeded. The
# Test-Path line below is the property that matters and already covers the unbaked
# case -- the literal token is not a path.


if ($_pybin -ne '' -and -not (Test-Path -LiteralPath $_pybin)) { $_pybin = '' }
if ($_pybin -ne '') {
    & $_pybin $_entry @args
    exit $LASTEXITCODE
}

# Host-local resolution cache (DR-303 / windows-interpreter-bake-is-empty):
# %LOCALAPPDATA% never syncs between machines, unlike the settings-home a
# bake is written into, so it cannot be poisoned by a Mac/Windows-synced
# home the way a bake can. Mirrors the bake's own Test-Path self-heal: a
# cached path that is stale or foreign falls through to re-resolution.
# Every step here is in-process (no new spawn on the steady-state path).


$_cachefile = $null
if ($env:LOCALAPPDATA) {
    $_cachefile = Join-Path $env:LOCALAPPDATA 'coordinator\python-bin-cache-ps1.txt'
    if (Test-Path -LiteralPath $_cachefile) {
        $_cached = $null
        try { $_cached = Get-Content -LiteralPath $_cachefile -TotalCount 1 -ErrorAction SilentlyContinue } catch {}
        if ($_cached -and (Test-Path -LiteralPath $_cached)) {
            & $_cached $_entry @args
            exit $LASTEXITCODE
        }
    }
}
$_py = Get-Command python.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
if ($_py) {
    if ($_cachefile) {
        
        
        try {
            $_cachedir = Split-Path -Parent $_cachefile
            if (-not (Test-Path -LiteralPath $_cachedir)) {
                New-Item -ItemType Directory -Path $_cachedir -Force -ErrorAction SilentlyContinue | Out-Null
            }
            $_tmpfile = Join-Path $_cachedir ([System.Guid]::NewGuid().ToString('N') + '.tmp')
            [System.IO.File]::WriteAllText($_tmpfile, $_py.Source)
            Move-Item -LiteralPath $_tmpfile -Destination $_cachefile -Force -ErrorAction SilentlyContinue
        } catch {}
    }
    & $_py.Source $_entry @args
    exit $LASTEXITCODE
}
$_pyl = Get-Command py -ErrorAction SilentlyContinue
if ($_pyl) {
    & $_pyl.Source -3 $_entry @args
    exit $LASTEXITCODE
}
[Console]::Error.WriteLine('[goal-kr-evidence] ERROR: no Python interpreter found (python.exe / py -3).')
[Console]::Error.WriteLine('[goal-kr-evidence] Install Python: https://www.python.org/downloads/windows/')
exit 127
