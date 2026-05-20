@echo off
REM Windows shim for ~/.claude/bin/machine-local (extensionless bash script).
REM Prefer Git\bin\bash.exe (sets MSYSTEM + full PATH) over Git\usr\bin\bash.exe.
if exist "C:\Program Files\Git\bin\bash.exe" (
  "C:\Program Files\Git\bin\bash.exe" "%USERPROFILE%/.claude/bin/machine-local" %*
) else if exist "C:\Program Files\Git\usr\bin\bash.exe" (
  "C:\Program Files\Git\usr\bin\bash.exe" "%USERPROFILE%/.claude/bin/machine-local" %*
) else if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" (
  "%ProgramFiles(x86)%\Git\bin\bash.exe" "%USERPROFILE%/.claude/bin/machine-local" %*
) else (
  echo [machine-local] ERROR: Git for Windows not found in standard locations. 1>&2
  echo [machine-local] Install from https://git-scm.com/download/win 1>&2
  exit /b 127
)
exit /b %ERRORLEVEL%
