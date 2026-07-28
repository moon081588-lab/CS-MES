@echo off
REM CKP Report - DB connection check only (no reports).
REM ASCII + CRLF on purpose. Korean guidance lives in tools\db_check.py
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
  goto :end
)

%PY% "%~dp0tools\db_check.py"

:end
echo.
pause
endlocal
