

# directly. install-substrate.py substitutes __PYTHON_BIN__ with the


# is no longer on disk. That fallback also tries a host-local %LOCALAPPDATA%


$ErrorActionPreference = 'Stop'
$_here = Split-Path -Parent $MyInvocation.MyCommand.Path
$_entry = Join-Path $_here 'compose-review-wave.py'
$_pybin = '__PYTHON_BIN__'

# __PYTHON_BIN__ occurrence, so such a test compares the baked path against itself,


if ($_pybin -ne '' -and -not (Test-Path -LiteralPath $_pybin)) { $_pybin = '' }
if ($_pybin -ne '') {
    & $_pybin $_entry @args
    exit $LASTEXITCODE
}

# %LOCALAPPDATA% never syncs between machines, unlike the settings-home a


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
[Console]::Error.WriteLine('[compose-review-wave] ERROR: no Python interpreter found (python.exe / py -3).')
[Console]::Error.WriteLine('[compose-review-wave] Install Python: https://www.python.org/downloads/windows/')
exit 127
