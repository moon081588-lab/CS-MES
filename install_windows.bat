@echo off
REM ============================================================
REM  CS-MES  Windows 설치 (한 번만 실행)
REM  CS-MES Windows setup - run once
REM
REM  이 파일을 더블클릭하거나 명령프롬프트에서 실행하세요.
REM  Double-click this file, or run it from Command Prompt.
REM
REM  끝나면 Claude Desktop 을 완전히 종료했다가 다시 켜세요.
REM  When done, quit Claude Desktop completely and restart it.
REM ============================================================
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BOM=%ROOT%\balance_outgoing_mailer"
set "VENVPY=%BOM%\.venv\Scripts\python.exe"

echo.
echo ============================================================
echo  CS-MES  Windows 설치 / setup
echo  위치 / location : %ROOT%
echo ============================================================

echo %ROOT%| findstr /R /C:" " >nul && (
  echo.
  echo [경고] 설치 경로에 공백이 있습니다: %ROOT%
  echo        WARNING: install path has spaces. SQLcl ^(Java^) may fail with ORA-17956.
  echo        권장 / recommended:  C:\CS-MES
  echo.
)

echo.
echo [1/4] Python, 라이브러리, config.ini 준비...
call "%BOM%\csmes.bat" --check-env
if errorlevel 1 (
  echo [실패] 1단계에서 중단되었습니다 / FAILED at step 1. See message above.
  goto :end
)

echo.
echo [2/4] Oracle 월렛 확인...
if not exist "%BOM%\wallet\tnsnames.ora" (
  echo [실패] 월렛이 없습니다 / wallet not found:
  echo        %BOM%\wallet\tnsnames.ora
  echo.
  echo   조치 / what to do:
  echo     OCI 지갑 zip 을 위 wallet 폴더에 풀어 넣으세요 ^(8개 파일^).
  echo     Unzip the OCI wallet into that folder ^(cwallet.sso, tnsnames.ora, ...^).
  goto :end
)
echo   OK - %BOM%\wallet

echo.
echo [3/4] SQLcl 확인...
where sql.exe >nul 2>&1 || where sql.cmd >nul 2>&1 || where sql.bat >nul 2>&1
if errorlevel 1 (
  echo [경고] SQLcl 을 PATH 에서 찾지 못했습니다 / SQLcl not found in PATH.
  echo        리포트 11개 생성에 필요합니다 / required to build the 11 reports.
  echo.
  echo   설치 / install:
  echo     1^) https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/
  echo     2^) C:\sqlcl 에 압축 해제 / unzip to C:\sqlcl
  echo     3^) setx SQLCL "C:\sqlcl\bin\sql.exe"
  echo     4^) 연결 저장 / save a connection:
  echo          sql /nolog
  echo          SQL^> connmgr add -name changshinincaipoc -url jdbc:oracle:thin:@changshinincaipoc_medium -user ADMIN
  echo.
) else (
  echo   OK
)

echo.
echo [4/4] Claude Desktop MCP 등록...
"%VENVPY%" "%BOM%\setup_env.py" --init-claude

echo.
echo ============================================================
echo  최종 점검 / final check
echo ============================================================
"%VENVPY%" "%BOM%\setup_env.py" --check

echo.
echo ============================================================
echo  다음 순서 / next steps
echo ============================================================
echo   1^) config.ini 에 값을 채우세요 / fill in config.ini:
echo        %BOM%\config.ini
echo        - [db] password        DB 비밀번호 / database password
echo        - [report] recipients  메일 받는 사람 / mail recipients
echo   2^) Claude Desktop 을 완전히 종료했다가 다시 켜세요.
echo      Quit Claude Desktop COMPLETELY ^(tray icon too^) and restart.
echo   3^) 채팅창에 물어보세요 / then ask in a chat:
echo        "CKP 레포트 11개 만들어줘"
echo.

:end
echo.
pause
