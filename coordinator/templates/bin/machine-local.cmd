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
  REM Fallback: try PATH resolution (covers portable Git, Scoop, MSYS2, etc.)
  where bash.exe >nul 2>&1
  if not errorlevel 1 (
    bash.exe "%~dp0machine-local" %*
    exit /b %ERRORLEVEL%
  )
  echo [machine-local] ERROR: bash.exe not found. Install Git for Windows or add bash to PATH. 1>&2
  echo [machine-local] https://git-scm.com/download/win 1>&2
  exit /b 127
)
exit /b %ERRORLEVEL%
