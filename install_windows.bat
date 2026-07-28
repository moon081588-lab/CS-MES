@echo off
REM ===========================================================
REM  CS-MES Windows setup  (run once)
REM  Keep this file ASCII-only with CRLF line endings:
REM  cmd.exe reads .bat in the OEM codepage and needs CRLF.
REM  All Korean messages live in tools\win_install.py instead.
REM ===========================================================
setlocal
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

set "PY="
where py.exe      >nul 2>&1 && set "PY=py -3"
if not defined PY where python.exe  >nul 2>&1 && set "PY=python"
if not defined PY where python3.exe >nul 2>&1 && set "PY=python3"
if not defined PY (
  echo [ERROR] Python not found.
  echo         Install from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH" during setup.
  goto :end
)

%PY% "%~dp0tools\win_install.py"

:end
echo.
pause
endlocal
