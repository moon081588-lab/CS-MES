@echo off
REM ===========================================================
REM  CS-MES runner (Windows)
REM  ASCII-only + CRLF on purpose - see install_windows.bat.
REM
REM  csmes.bat                  full run (query -> excel -> mail)
REM  csmes.bat --doctor         diagnose db / mail
REM  csmes.bat --dry-run        excel only, no mail
REM  csmes.bat --install-schedule   register daily task
REM  csmes.bat --check-env      check environment and exit
REM ===========================================================
setlocal
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "VPY=%DIR%\.venv\Scripts\python.exe"

if not exist "%VPY%" (
  echo [ERROR] Not installed yet. Run install_windows.bat in the parent folder first.
  goto :end
)

if /I "%~1"=="--check-env" (
  "%VPY%" "%DIR%\setup_env.py" --check
  goto :end
)

"%VPY%" "%DIR%\setup_env.py"
if exist "%DIR%\wallet\tnsnames.ora" (
  set "TNS_ADMIN=%DIR%\wallet"
) else (
  echo [ERROR] Oracle wallet not found: %DIR%\wallet\tnsnames.ora
  echo         Unzip the OCI wallet into that folder, then retry.
  goto :end
)

"%VPY%" "%DIR%\balance_outgoing_mailer.py" %*

:end
endlocal
