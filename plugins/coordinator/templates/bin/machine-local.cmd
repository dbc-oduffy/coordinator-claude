@echo off
REM Windows shim for machine-local (calls the extensionless bash shim co-located
REM with this .cmd file). Uses %~dp0 so the path tracks wherever ~/.claude/bin/
REM lives — including non-default install roots set via CLAUDE_HOME.
REM Prefer Git\bin\bash.exe (sets MSYSTEM + full PATH) over Git\usr\bin\bash.exe.
if exist "C:\Program Files\Git\bin\bash.exe" (
  "C:\Program Files\Git\bin\bash.exe" "%~dp0machine-local" %*
) else if exist "C:\Program Files\Git\usr\bin\bash.exe" (
  "C:\Program Files\Git\usr\bin\bash.exe" "%~dp0machine-local" %*
) else if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" (
  "%ProgramFiles(x86)%\Git\bin\bash.exe" "%~dp0machine-local" %*
) else (
  echo [machine-local] ERROR: Git for Windows not found in standard locations. 1>&2
  echo [machine-local] Install from https://git-scm.com/download/win 1>&2
  exit /b 127
)
exit /b %ERRORLEVEL%
