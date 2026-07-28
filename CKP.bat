@echo off
REM CKP Manual Report - the only file you need to run.
REM ASCII + CRLF on purpose (cmd.exe reads .bat in the OEM codepage).
REM Korean text lives in program\tools\*.py, not here.
setlocal
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PY="
REM Two layouts are supported: the field bundle (code under program\)
REM and the git checkout (code at the repo root).
set "APP=%~dp0program"
if not exist "%APP%\tools\ckp.py" set "APP=%~dp0."
if exist "%APP%\python\python.exe" call :try "%APP%\python\python.exe"
if not defined PY call :try "py" "-3"
if not defined PY call :try "python"
if not defined PY call :try "python3"
if not defined PY (
  echo.
  echo  [ERROR] Python 3 was not found on this PC.
  echo          Install Python 3.12 ^(64-bit^) from https://www.python.org/downloads/
  echo          and tick "Add python.exe to PATH" during the install.
  echo.
  pause
  endlocal
  exit /b 1
)
%PY% "%APP%\tools\ckp.py" %*
echo.
pause
endlocal
exit /b 0

:try
if defined PY goto :eof
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set PY="%~1" %~2
goto :eof
