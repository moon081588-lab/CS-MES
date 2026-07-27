@echo off
REM ============================================================
REM  CS-MES  -  Windows 한 줄 실행 래퍼 (csmes.sh 의 Windows 판)
REM  venv 준비 -> 라이브러리 -> 월렛/config 정리(setup_env.py) -> 실행
REM
REM  사용:  csmes.bat                      전체 (조회 -> 엑셀 -> 메일)
REM         csmes.bat --doctor             연결/메일 진단
REM         csmes.bat --dry-run            메일 발송 없이 엑셀만
REM         csmes.bat --install-schedule   매일 자동 실행 등록 (작업 스케줄러)
REM         csmes.bat --check-env          환경만 점검하고 종료
REM
REM  * 접속 모드는 config.ini [db] mode=auto
REM    -> thick(Instant Client) 먼저 시도, 실패하면 thin 으로 자동 폴백
REM ============================================================
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

REM ---- 1) 파이썬 찾기 ----------------------------------------
set "PY="
where py.exe     >nul 2>&1 && set "PY=py -3"
if not defined PY  where python.exe  >nul 2>&1 && set "PY=python"
if not defined PY  where python3.exe >nul 2>&1 && set "PY=python3"
if not defined PY (
  echo [오류] Python 을 찾을 수 없습니다.
  echo        https://www.python.org/downloads/ 에서 설치하고,
  echo        설치 화면에서 "Add python.exe to PATH" 를 반드시 체크하세요.
  exit /b 1
)

REM ---- 2) 가상환경(.venv) ------------------------------------
if not exist "%DIR%\.venv\Scripts\python.exe" (
  echo [setup] 가상환경^(.venv^) 생성...
  %PY% -m venv "%DIR%\.venv"
)
if exist "%DIR%\.venv\Scripts\python.exe" set "PY=%DIR%\.venv\Scripts\python.exe"

REM ---- 3) 라이브러리 -----------------------------------------
"%PY%" -c "import oracledb, openpyxl, mcp" >nul 2>&1
if errorlevel 1 (
  echo [setup] 라이브러리 설치 ^(oracledb, openpyxl, mcp^)...
  "%PY%" -m pip install --quiet --upgrade pip
  "%PY%" -m pip install --quiet oracledb openpyxl mcp
  if errorlevel 1 (
    echo [주의] 라이브러리 설치에 실패했습니다. 사내 프록시/방화벽을 확인하세요.
    echo        수동 설치:  "%PY%" -m pip install oracledb openpyxl mcp
  )
)

REM ---- 4) 월렛 경로 교정 + config 기본값 ----------------------
if /I "%~1"=="--check-env" (
  "%PY%" "%DIR%\setup_env.py" --check
  exit /b 0
)
"%PY%" "%DIR%\setup_env.py"
if exist "%DIR%\wallet\tnsnames.ora" set "TNS_ADMIN=%DIR%\wallet"

REM ---- 5) 실행 ------------------------------------------------
"%PY%" "%DIR%\balance_outgoing_mailer.py" %*
