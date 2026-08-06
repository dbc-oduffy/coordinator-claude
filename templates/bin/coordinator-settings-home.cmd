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
if "%_py%"=="__PYTHON_BIN__" set "_py="
if not "%_py%"=="" goto :run_baked

for /f "delims=" %%p in ('where python.exe 2^>nul') do (
    echo %%p| findstr /I /C:"\WindowsApps\" >nul
    if errorlevel 1 (
        set "_py=%%p"
        goto :run_baked
    )
)

where py >nul 2>&1
if not errorlevel 1 goto :run_py3

echo [coordinator-settings-home] ERROR: no python3 (or python) found on PATH 1>&2
echo [coordinator-settings-home] https://www.python.org/downloads/windows/ 1>&2
exit /b 2

:run_baked
"%_py%" "%_impl%" %*
exit /b %ERRORLEVEL%

:run_py3
py -3 "%_impl%" %*
exit /b %ERRORLEVEL%
