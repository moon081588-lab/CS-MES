#!/usr/bin/env bash
# ============================================================
#  csmes-push  —  현재 레포를 GitHub 에 커밋·푸시
#  사용:  bash gh_sync.sh "커밋 메시지"
#  · 레포 위치는 스크립트 위치에서 자동 계산(폴더 이동에도 동작)
#  · 보안/용량 제외: wallet/, config.ini, .venv/, report/, 로그, 생성 xlsx, __pycache__, .DS_Store
# ============================================================
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../CS-MES/balance_outgoing_mailer
REPO="$(cd "$HERE/.." && pwd)"                          # .../CS-MES (git 루트)
MSG="${*:-update}"
[ -d "$REPO/.git" ] || { echo "git 레포가 아닙니다: $REPO"; exit 1; }
cd "$REPO"

# 루트 .gitignore 보강 (전체 경로 기준)
GI="$REPO/.gitignore"; touch "$GI"
for ig in \
  "report/" \
  "balance_outgoing_mailer/wallet/" \
  "balance_outgoing_mailer/config.ini" \
  "balance_outgoing_mailer/.venv/" \
  "balance_outgoing_mailer/*.log" \
  "balance_outgoing_mailer/BALANCE_OUTGOING_*.xlsx" \
  "**/__pycache__/" \
  ".DS_Store" "**/.DS_Store" ; do
  grep -qxF "$ig" "$GI" || echo "$ig" >> "$GI"
done

# 이미 추적 중일 수 있는 민감/대용량 항목을 추적 해제(파일은 보존)
git rm -r --cached report                          2>/dev/null || true
git rm -r --cached balance_outgoing_mailer/wallet  2>/dev/null || true
git rm    --cached balance_outgoing_mailer/config.ini 2>/dev/null || true
git rm -r --cached balance_outgoing_mailer/.venv   2>/dev/null || true

git add -A
echo "=== 커밋될 변경 (wallet/ , config.ini , .venv , report/ 가 보이면 안 됨) ==="
git status --short
git commit -m "$MSG" || { echo ">> 변경사항 없음"; exit 0; }
git push
echo "✅ GitHub 반영 완료: $MSG"
