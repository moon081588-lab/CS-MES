@echo off
REM CKP Report - link this folder to Claude Desktop (MCP).
setlocal
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
call "%~dp0tools\_findpython.bat"
if not defined PY (
  echo.
  echo [ERROR] Python 3 was not found on this PC.
  echo         Install Python 3.12 ^(64-bit^) from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH" during the install.
  echo.
  pause
  endlocal
  exit /b 1
)
%PY% "%~dp0tools\register_mcp.py" %*
echo.
pause
endlocal
