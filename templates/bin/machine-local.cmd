@echo off
REM Windows shim for machine-local, python-direct: invokes _machine_local.py
REM under python.exe directly; no bash.exe re-exec.
REM
REM WHY THIS EXISTS. The extensionless machine-local bash forwarder, at
REM templates/bin/machine-local and coordinator/bin/machine-local, is a real
REM bin-bash-env-bash script, not a python/sh polyglot, so Windows
REM CreateProcess cannot execute it directly since it is not a PE. Any
REM Windows-layer launcher therefore falls through to ShellExecute, which
REM pops the Open-With picker asking which app should open the file. The bash
REM forwarder's only job, though, is to locate _machine_local.py via the
REM settings-home seam and exec a Python interpreter on it: pure
REM path-resolution plus interpreter-dispatch value, which this shim promotes
REM directly into the .cmd ladder below rather than re-wrapping the bash
REM forwarder. _machine_local.py itself is a plain dot-py file, not a
REM polyglot, so running python against that file runs it directly, no shell
REM in the loop. See docs/wiki/windows-cmd-shims.md and
REM docs/plans/2026-07-19-debash-coordinator-windows.md, Wave 0.
REM
REM SETTINGS-HOME SEAM, ported verbatim from the bash forwarder's resolution
REM order, NOT percent-tilde-dp0-relative. _machine_local.py is not always
REM co-located with this shim: the primary copy installs at settings-home's
REM bin directory, but this shim is ALSO installed as a compat forwarder at
REM the dotfile claude bin directory during the settings-home migration
REM window, where no local _machine_local.py exists. Precedence:
REM COORDINATOR_SETTINGS_HOME env var, else CLAUDE_HOME-or-USERPROFILE-or-HOME
REM joined with dot-coordinator-claude-settings, mirroring the bash original's
REM nested-default expansion, with CLAUDE_HOME slash USERPROFILE slash HOME
REM ordering per the HOME-substitute convention in
REM coordinator-settings-home.ps1: there is no HOME env var on a bare cmd.exe
REM session, so USERPROFILE is the Windows analog, checked ahead of a literal
REM HOME in case a POSIX-style shell set one.
REM Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md, section C4
REM
REM NOTE. The bash forwarder ALSO probes multiple python3.NN candidates for a
REM 3.11-or-newer match before falling back to first-python-found as a last
REM resort, so that _machine_local.py's own version guard, a plain
REM sys.version_info check that exits 2 with an actionable message rather than
REM a shell construct, emits the clearer error. That probe loop is a UX
REM optimization, not load-bearing correctness, per the bash script's own
REM fallback comment, so this shim does not replicate it: it resolves any
REM interpreter and lets _machine_local.py's own guard fire on a stale one,
REM exactly like the bash forwarder's documented last-resort path already
REM does. Exit code 2 for both implementation-missing and
REM no-interpreter-found below matches the bash original's
REM operational-failure contract, _machine_local.py's own EXIT_OPERATIONAL
REM equals 2, not the generic-shim 127 convention.
REM
REM NOTE ON THIS COMMENT BLOCK. No angle brackets, pipes, ampersands, or
REM parentheses anywhere above, and no double quote left unclosed on its own
REM line. cmd.exe parses redirection, pipe, and background metacharacters,
REM plus paren grouping and quote balance, INSIDE REM lines too, since a REM
REM line is not immune at the tokenizer level: an angle-bracket placeholder
REM name, a version comparison written with a literal greater-than-or-equal
REM sign, a parenthesized aside split across lines, or a quoted phrase that
REM spans two REM lines can all silently corrupt the rest of the script's
REM parse. This exact file broke that way in production on 2026-07-28. See
REM docs/wiki/windows-cmd-shims.md, section on REM metacharacters.
setlocal enableextensions
set "_settings_home="
if not "%COORDINATOR_SETTINGS_HOME%"=="" set "_settings_home=%COORDINATOR_SETTINGS_HOME%"
if "%_settings_home%"=="" if not "%CLAUDE_HOME%"=="" set "_settings_home=%CLAUDE_HOME%\.coordinator-claude-settings"
if "%_settings_home%"=="" if not "%USERPROFILE%"=="" set "_settings_home=%USERPROFILE%\.coordinator-claude-settings"
if "%_settings_home%"=="" set "_settings_home=%HOME%\.coordinator-claude-settings"
set "_impl=%_settings_home%\bin\_machine_local.py"

if not exist "%_impl%" (
  echo [machine-local] ERROR: implementation not found at %_impl% 1>&2
  echo [machine-local]   Settings home: %_settings_home% 1>&2
  echo [machine-local]   Remediation: re-run coordinator:install to seed the settings-home bin/ family. 1>&2
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

echo [machine-local] ERROR: no python3 (or python) found on PATH 1>&2
echo [machine-local] https://www.python.org/downloads/windows/ 1>&2
exit /b 2

:run_baked
"%_py%" "%_impl%" %*
exit /b %ERRORLEVEL%

:run_py3
py -3 "%_impl%" %*
exit /b %ERRORLEVEL%
