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
REM install-time-baked absolute path (__PYTHON_BIN__), else `where python.exe`
REM skipping WindowsApps aliases, else the `py -3` launcher. Parity with
REM templates/bin/python3.cmd and coordinator/bin/coordinator-lesson-add.cmd.
setlocal enableextensions
set "_impl=%~dp0_claude_home.py"

if not exist "%_impl%" (
  echo [claude-home] ERROR: implementation not found at %_impl% 1>&2
  exit /b 1
)

set "_py=__PYTHON_BIN__"
if "%_py%"=="__PYTHON_BIN__" set "_py="
if not "%_py%"=="" (
  "%_py%" "%_impl%" %*
  exit /b
)
for /f "delims=" %%p in ('where python.exe 2^>nul') do (
  echo %%p| findstr /I /C:"\WindowsApps\" >nul
  if errorlevel 1 (
    "%%p" "%_impl%" %*
    exit /b
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
