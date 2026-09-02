@echo off
REM Windows shim for coordinator-settings-home — python-direct (invokes the
REM extensionless `coordinator-settings-home` file, co-located with this .cmd,
REM under python.exe directly; no bash.exe re-exec).
REM
REM WHY THIS EXISTS: coordinator-settings-home is a `#!/usr/bin/env python3`
REM script kept extensionless (not a polyglot). Windows CreateProcess cannot
REM execute it (not a PE), so any Windows-layer launcher (Node child_process,
REM .NET Process.Start(UseShellExecute=true), PowerShell/cmd bare-name
REM resolution) falls through to ShellExecute, which walks PATHEXT, hits the
REM .py file association, and pops the Open-With picker asking which app
REM should open coordinator-settings-home. This .cmd is found by
REM CreateProcess/PATHEXT resolution BEFORE the ShellExecute fallback fires,
REM suppressing the picker.
REM
REM Unlike machine-local.cmd, the target here needs no settings-home seam: the
REM extensionless `coordinator-settings-home` file IS the implementation and
REM is always co-located with this shim (%~dp0), so "python" plus that file
REM runs it directly, no shell in the loop. See docs/wiki/windows-cmd-shims.md
REM — parity with machine-local.cmd / python3.cmd / claude-home.cmd.
REM
REM NOTE ON THIS COMMENT BLOCK: no bare angle-bracket, pipe, or ampersand
REM characters above — cmd.exe parses redirection/pipe/background
REM metacharacters INSIDE REM lines too (a REM line is not immune at the
REM tokenizer level), so an angle-bracket placeholder name or a version
REM comparison written with a literal greater-than-or-equal sign silently
REM corrupts the rest of the script's parse. See
REM docs/wiki/windows-cmd-shims.md section on REM metacharacters, and the
REM 2026-07-28 machine-local.cmd incident this note was added after.
setlocal enableextensions
set "_impl=%~dp0coordinator-settings-home"

if not exist "%_impl%" (
  echo [coordinator-settings-home] ERROR: implementation not found at %_impl% 1>&2
  echo [coordinator-settings-home]   Remediation: re-run coordinator:install to seed the settings-home bin/ family. 1>&2
  exit /b 2
)

set "_py=__PYTHON_BIN__"
REM Existence, not equality: install-substrate.py rewrites EVERY occurrence of the
REM placeholder, so an equality test against it has both sides substituted and clears
REM the baked path precisely when substitution worked. An exist test is immune to that
REM and additionally self-heals a baked path whose interpreter was moved or removed.
if not exist "%_py%" set "_py="
if not "%_py%"=="" goto :run_baked

REM Host-local resolution cache (DR-303 / windows-interpreter-bake-is-empty:
REM docs/decisions/DR-303-windows-spawn-economics-is-a-fix-not-a-desig.md).
REM An install-time bake that never happened (a macOS-run install, a
REM setup-only install, or a synced settings-home carrying the OTHER
REM platform's baked path) used to make every invocation re-walk where
REM python.exe plus the findstr filter from scratch -- roughly 10 processes
REM per op against 2. This cache lives under %LOCALAPPDATA%, which never
REM syncs between machines, so it cannot be poisoned the way a synced bake
REM can. Guarded by if-exist slash non-empty exactly like the bake rung
REM above -- self-heals when the cached path is stale or foreign. Same
REM shared cache file as machine-local.cmd, platform-localize.cmd, and the
REM engine-side launcher family, so a resolution any of them performs warms
REM this one too.
if not defined LOCALAPPDATA goto :skip_localappdata_read
set "_cachefile=%LOCALAPPDATA%\coordinator\python-bin-cache.txt"
if not exist "%_cachefile%" goto :skip_localappdata_read
set "_cached="
set /p _cached=<"%_cachefile%"
if "%_cached%"=="" goto :skip_localappdata_read
set "_cached=%_cached:"=%"
set "_cachedtest=%_cached:WindowsApps=%"
if not "%_cachedtest%"=="%_cached%" goto :skip_localappdata_read
if not exist "%_cached%" goto :skip_localappdata_read
set "_py=%_cached%"
goto :run_baked
:skip_localappdata_read

for /f "delims=" %%p in ('where python.exe 2^>nul') do (
    echo %%p| findstr /I /C:"\WindowsApps\" >nul
    if errorlevel 1 (
        set "_py=%%p"
        goto :cache_and_run_baked
    )
)

where py >nul 2>&1
if not errorlevel 1 goto :run_py3

echo [coordinator-settings-home] ERROR: no python3 (or python) found on PATH 1>&2
echo [coordinator-settings-home] https://www.python.org/downloads/windows/ 1>&2
exit /b 2

REM Persist the resolved interpreter for future invocations on THIS host.
REM Every writer resolves the same _py value (deterministic per machine), so
REM a write-write race can only ever race identical content into the
REM target. Written inside a per-writer temp DIRECTORY (mkdir is atomic,
REM unlike a bare %RANDOM% filename), then moved into place with move
REM (atomic same-volume rename, never an in-place write) -- a losing
REM writer's move silently no-ops, no retry needed.
:cache_and_run_baked
if not defined LOCALAPPDATA goto :run_baked
set "_cachedir=%LOCALAPPDATA%\coordinator"
if exist "%_cachedir%\" goto :cache_write
mkdir "%_cachedir%" 2>nul
:cache_write
set "_tmpdir=%_cachedir%\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if not errorlevel 1 goto :cache_write_got_dir
set "_tmpdir=%_cachedir%\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if not errorlevel 1 goto :cache_write_got_dir
set "_tmpdir=%_cachedir%\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if errorlevel 1 goto :run_baked
:cache_write_got_dir
set "_tmpfile=%_tmpdir%\python-bin-cache.tmp"
>"%_tmpfile%" echo %_py%
move /y "%_tmpfile%" "%_cachefile%" >nul 2>nul
2>nul rd /s /q "%_tmpdir%"
goto :run_baked

:run_baked
"%_py%" "%_impl%" %*
exit /b %ERRORLEVEL%

:run_py3
py -3 "%_impl%" %*
exit /b %ERRORLEVEL%
