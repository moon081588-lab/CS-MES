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
REM 콘솔뿐 아니라 파일/파이프로 리다이렉트될 때도 UTF-8 로 출력하게 한다.
REM (chcp 는 콘솔에만 적용된다 — 작업 스케줄러 실행은 로그 파일로 가므로 이게 필요)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
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
if not exist "%DIR%\.venv\Scripts\python.exe" (
  echo [오류] 가상환경 생성 실패. Microsoft Store 스텁 파이썬이면 python.org 정식 버전을 설치하세요.
  echo        ERROR: venv creation failed. Install the full Python from python.org.
  exit /b 1
)
set "PY=%DIR%\.venv\Scripts\python.exe"

REM ---- 3) 라이브러리 -----------------------------------------
"%PY%" -c "import oracledb, openpyxl, mcp; from zoneinfo import ZoneInfo; ZoneInfo('Asia/Jakarta')" >nul 2>&1
if errorlevel 1 (
  echo [setup] 라이브러리 설치 ^(oracledb, openpyxl, mcp, tzdata^)...
  "%PY%" -m pip install --quiet --upgrade pip
  "%PY%" -m pip install --quiet oracledb openpyxl mcp tzdata
  if errorlevel 1 (
    echo [오류] 라이브러리 설치 실패. 사내 프록시/방화벽을 확인하세요.
    echo        ERROR: package install failed. Check proxy/firewall.
    echo        수동 설치:  "%PY%" -m pip install oracledb openpyxl mcp tzdata
    exit /b 1
  )
)

REM ---- 3.5) config.ini 준비 ----------------------------------
if not exist "%DIR%\config.ini" (
  if exist "%DIR%\config.ini.example" (
    copy /Y "%DIR%\config.ini.example" "%DIR%\config.ini" >nul
    echo [setup] config.ini 를 생성했습니다 ^(config.ini.example 복사^).
    echo         Created config.ini. Fill in DB / SMTP / recipients before use:
    echo         %DIR%\config.ini
  )
)

REM ---- 4) 월렛 경로 교정 + config 기본값 ----------------------
if /I "%~1"=="--check-env" (
  "%PY%" "%DIR%\setup_env.py" --check
  exit /b 0
)
"%PY%" "%DIR%\setup_env.py"
if exist "%DIR%\wallet\tnsnames.ora" (
  set "TNS_ADMIN=%DIR%\wallet"
) else (
  echo [오류] 월렛을 찾을 수 없습니다: %DIR%\wallet\tnsnames.ora
  echo        ERROR: Oracle wallet not found. Unzip the wallet into the folder above.
  echo        ^(경로에 공백/한글이 없어야 합니다 - SQLcl 이 ORA-17956 을 냅니다^)
  exit /b 1
)

REM ---- 5) 실행 ------------------------------------------------
"%PY%" "%DIR%\balance_outgoing_mailer.py" %*
