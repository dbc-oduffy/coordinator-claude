@echo off
REM Windows shim for python3. Prefers the native python.exe resolved and
REM baked in at coordinator install time (fast path: skips the `py -3`
REM launcher's double-indirection and its Microsoft Store App Execution
REM Alias risk). install-substrate.sh substitutes the token below with the
REM absolute path lib/resolve-python.sh resolved at install time. Falls
REM back to `py -3 %*` (today's behavior) when no interpreter could be
REM resolved at install time — e.g. a fresh machine with no Python yet —
REM AND when a baked path was resolved but has since disappeared from disk
REM (deleted/moved venv, wiped by a failed run). Without the `exist` check,
REM a baked path naming the coordinator venv's own interpreter deadlocks
REM ensure-coordinator-venv: this shim is used to CREATE that venv, so once
REM the venv is gone every invocation through it fails and the venv can
REM never be rebuilt -- and re-running the installer, the documented repair
REM for a half-configured machine, cannot fix it either.
set "_coordinator_python3_bin=__PYTHON_BIN__"
if not "%_coordinator_python3_bin%"=="" if exist "%_coordinator_python3_bin%" (
    "%_coordinator_python3_bin%" %*
    exit /b %ERRORLEVEL%
)
py -3 %*
exit /b %ERRORLEVEL%
