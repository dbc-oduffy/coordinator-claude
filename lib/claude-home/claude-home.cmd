@echo off
REM Windows shim for claude-home (invokes the co-located pure-Python
REM implementation _claude_home.py DIRECTLY under python.exe — no bash.exe
REM re-exec). Uses %~dp0 so the path tracks wherever ~/.claude/bin/ lives —
REM including non-default install roots set via CLAUDE_HOME.
REM
REM WHY THIS TARGETS _claude_home.py, NOT the co-located `claude-home` file:
REM `claude-home` (extensionless, this directory) is `#!/usr/bin/env bash` —
REM real bash, not an sh/python polyglot, so `python claude-home` cannot run
REM it. But its ENTIRE job is trivial glue: resolve a Python interpreter,
REM then `exec "$PYTHON" "$IMPL" "$@"` against _claude_home.py, which is
REM pure stdlib Python. That interpreter-resolution value is exactly what
REM this shim's own ladder already provides, so the shim invokes
REM _claude_home.py directly and the bash veneer is bypassed for the
REM Windows path entirely (POSIX callers still exec the bash file).
REM See docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 0, Pinned
REM pattern) and coordinator/lib/claude-home/README.md.
REM
REM PYTHON-DIRECT RESOLUTION: this shim carries its own interpreter ladder —
REM it CANNOT defer to lib/resolve-python.sh (that is bash). Order:
REM install-time-baked absolute path (__PYTHON_BIN__), else the host-local
REM %LOCALAPPDATA% resolution cache (DR-303 / windows-interpreter-bake-is-
REM empty -- docs/decisions/DR-303-windows-spawn-economics-is-a-fix-not-a-
REM desig.md), else `where python.exe` skipping WindowsApps aliases, else the
REM `py -3` launcher. Parity with templates/bin/python3.cmd and
REM coordinator/bin/coordinator-lesson-add.cmd.
setlocal enableextensions
set "_impl=%~dp0_claude_home.py"

if not exist "%_impl%" (
  echo [claude-home] ERROR: implementation not found at %_impl% 1>&2
  exit /b 1
)

set "_py=__PYTHON_BIN__"
if not "%_py%"=="" if exist "%_py%" goto :run_baked
set "_py="

REM Host-local resolution cache: lives under %LOCALAPPDATA%, which never
REM syncs between machines, so it cannot be poisoned by a Mac/Windows-synced
REM ~/.claude the way the bake above can. Guarded by `if exist`/non-empty
REM exactly like the bake rung -- self-heals when the cached path is stale
REM or foreign. A separate cache file from the machine-local family
REM (python-bin-cache.txt) so the two writers never race the same path.
if not defined LOCALAPPDATA goto :skip_cache_read
set "_cachefile=%LOCALAPPDATA%\coordinator\python-bin-cache-claude-home.txt"
if not exist "%_cachefile%" goto :skip_cache_read
set "_cached="
set /p _cached=<"%_cachefile%"
if "%_cached%"=="" goto :skip_cache_read
set "_cached=%_cached:"=%"
set "_cachedtest=%_cached:WindowsApps=%"
if not "%_cachedtest%"=="%_cached%" goto :skip_cache_read
if not exist "%_cached%" goto :skip_cache_read
set "_py=%_cached%"
goto :run_baked
:skip_cache_read

for /f "delims=" %%p in ('where python.exe 2^>nul') do (
  echo %%p| findstr /I /C:"\WindowsApps\" >nul
  if errorlevel 1 (
    set "_py=%%p"
    goto :cache_and_run_baked
  )
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%_impl%" %*
  exit /b
)
echo [claude-home] ERROR: no Python interpreter found. Install Python 3. 1>&2
echo [claude-home] https://www.python.org/downloads/windows/ 1>&2
exit /b 1

:cache_and_run_baked
REM Persist the resolved interpreter for future invocations on THIS host.
REM Same atomic-write shape as the machine-local family's rung: a per-writer
REM temp DIRECTORY (mkdir is atomic, unlike a bare %RANDOM% filename), moved
REM into place with `move` (atomic same-volume rename, never an in-place
REM write). A losing writer's `move` silently no-ops -- no retry needed,
REM every writer resolves the same deterministic value on this host.
if not defined LOCALAPPDATA goto :run_baked
set "_cachedir=%LOCALAPPDATA%\coordinator"
if exist "%_cachedir%\" goto :cache_write
mkdir "%_cachedir%" 2>nul
:cache_write
set "_tmpdir=%_cachedir%\python-bin-cache-claude-home.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if not errorlevel 1 goto :cache_write_got_dir
set "_tmpdir=%_cachedir%\python-bin-cache-claude-home.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if not errorlevel 1 goto :cache_write_got_dir
set "_tmpdir=%_cachedir%\python-bin-cache-claude-home.%RANDOM%%RANDOM%%RANDOM%.tmp"
2>nul mkdir "%_tmpdir%"
if errorlevel 1 goto :run_baked
:cache_write_got_dir
set "_tmpfile=%_tmpdir%\python-bin-cache-claude-home.tmp"
>"%_tmpfile%" echo %_py%
move /y "%_tmpfile%" "%_cachefile%" >nul 2>nul
2>nul rd /s /q "%_tmpdir%"
goto :run_baked

:run_baked
"%_py%" "%_impl%" %*
exit /b
