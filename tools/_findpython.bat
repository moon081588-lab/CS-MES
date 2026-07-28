@echo off
REM Locate a usable Python 3 and set PY. Called by run/setup/check/connect_claude.
REM ASCII + CRLF on purpose (cmd.exe reads .bat in the OEM codepage).
REM No setlocal here: PY must survive back into the caller.
REM Every candidate is actually executed once, because "where python.exe" on
REM Windows 10/11 also finds the Microsoft Store stub, which is not a Python.
set "PY="
if exist "%~dp0..\python\python.exe" call :try "%~dp0..\python\python.exe"
if not defined PY call :try "py" "-3"
if not defined PY call :try "python"
if not defined PY call :try "python3"
goto :eof

:try
if defined PY goto :eof
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set PY="%~1" %~2
goto :eof
