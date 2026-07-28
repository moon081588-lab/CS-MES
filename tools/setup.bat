@echo off
REM CKP Report - one time setup. ASCII + CRLF on purpose (cmd.exe parser).
REM All Korean guidance lives in tools\bootstrap.py
setlocal
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PY="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY where py.exe      >nul 2>&1 && set "PY=py -3"
if not defined PY where python.exe  >nul 2>&1 && set "PY=python"
if not defined PY where python3.exe >nul 2>&1 && set "PY=python3"
if not defined PY (
  echo [ERROR] Python not found.
  echo         Install Python 3 from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH".
  goto :end
)

%PY% "%~dp0tools\bootstrap.py"

:end
echo.
pause
endlocal
