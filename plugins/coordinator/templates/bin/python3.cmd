@echo off
REM Windows shim for python3. Routes to py.exe (Python Launcher) which is
REM bundled with all modern Python 3 Windows installs. Avoids bare `python`
REM which can hit the Microsoft Store App Execution Alias on some installs.
py -3 %*
exit /b %ERRORLEVEL%
