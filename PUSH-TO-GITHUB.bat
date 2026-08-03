@echo off
REM Push the folder-queue runner to GitHub. Uses the credentials already
REM saved on this PC - nothing is typed here.
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo  ==========================================================
echo   CKP - push to GitHub
echo  ==========================================================
echo.
where git >nul 2>&1
if errorlevel 1 (
  echo  [ERROR] git was not found on this PC.
  echo          Install Git for Windows: https://git-scm.com/download/win
  goto end
)
echo  repo : %CD%
git rev-parse --abbrev-ref HEAD
echo.
echo  --- files to publish ---
git add CKP-Watch.bat PUSH-TO-GITHUB.bat .gitignore README.md program/tools/watch.py
git status --short
echo.
git diff --cached --quiet
if not errorlevel 1 (
  echo  Nothing new to commit - already up to date.
  goto push
)
git commit -F "program\tools\_commit_msg.txt"
if errorlevel 1 (
  echo.
  echo  [ERROR] commit failed. Set your identity once, then run this again:
  echo      git config --global user.name  "your name"
  echo      git config --global user.email "your@email"
  goto end
)
:push
echo.
echo  --- pushing ---
git push
if errorlevel 1 (
  echo.
  echo  [ERROR] push failed.
  echo    - If it asked for a login, sign in to GitHub in the browser window,
  echo      or install GitHub CLI and run:  gh auth login
  echo    - If it says "rejected", run:     git pull --rebase   then try again.
  goto end
)
echo.
echo  Done. Pushed to GitHub.
:end
echo.
pause
endlocal
