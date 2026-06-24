#!/usr/bin/env bash
# ============================================================
#  csmes-push  —  최신 산출물을 레포에 반영하고 GitHub 에 커밋·푸시
#  사용:  bash gh_sync.sh "커밋 메시지"
#  · 동기화 폴더(_CS_MES_deploy)의 최신 파일을 레포로 복사
#  · 월렛(wallet/)·실설정(config.ini)·가상환경(.venv)은 커밋에서 자동 제외(보안)
# ============================================================
set -e
SRC="$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (개인)/_CS_MES_deploy"
REPO="$HOME/Desktop/CS-MES"
MSG="${*:-update}"
[ -d "$REPO/.git" ] || { echo "레포가 없습니다: $REPO"; exit 1; }
[ -f "$SRC/balance_outgoing_mailer.py" ] || { echo "동기화 폴더에 파일이 아직 없습니다(OneDrive 동기화 대기?): $SRC"; exit 1; }
cd "$REPO"
mkdir -p balance_outgoing_mailer
cp "$SRC/balance_outgoing_mailer.py" "$SRC/csmes.sh" "$SRC/gh_sync.sh" \
   "$SRC/report_template.xlsx" "$SRC/legend.png" "$SRC/README.md" balance_outgoing_mailer/ 2>/dev/null || true
cp "$SRC/README.md" README.md 2>/dev/null || true
chmod +x balance_outgoing_mailer/csmes.sh balance_outgoing_mailer/gh_sync.sh 2>/dev/null || true
# 보안: 비밀·월렛 커밋 방지
GI=balance_outgoing_mailer/.gitignore; touch "$GI"
for ig in "wallet/" "config.ini" ".venv/" "*.log" "BALANCE_OUTGOING_*.xlsx" "__pycache__/"; do
  grep -qxF "$ig" "$GI" || echo "$ig" >> "$GI"
done
git rm -r --cached balance_outgoing_mailer/wallet  2>/dev/null || true
git rm    --cached balance_outgoing_mailer/config.ini 2>/dev/null || true
git rm -r --cached balance_outgoing_mailer/.venv    2>/dev/null || true
git add -A
echo "=== 커밋될 변경 (wallet/ , config.ini 가 없어야 정상) ==="
git status --short
git commit -m "$MSG" || { echo ">> 변경사항 없음"; exit 0; }
git push
echo "✅ GitHub 반영 완료: $MSG"
