#!/usr/bin/env bash
# ============================================================
#  CS-MES  —  한 줄 실행 래퍼
#  의존성 설치 → 월렛 준비 → config 기본값 보강 → 전체 파이프라인 실행
#  사용:  bash csmes.sh            (전체: 조회→엑셀→메일)
#         bash csmes.sh --test-mail / --dry-run / --setup / --test-db
#  ※ 처음 1회만 비밀번호(메일·DB)를 숨김으로 물어보고 저장합니다. 이후엔 안 물어봅니다.
# ============================================================
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1) 라이브러리 (없을 때만 설치)
if ! python3 -c "import oracledb, openpyxl" 2>/dev/null; then
  echo "[setup] 라이브러리 설치 중 (oracledb, openpyxl)..."
  pip3 install --quiet --user oracledb openpyxl 2>/dev/null || pip3 install --quiet oracledb openpyxl
fi

# 2) 월렛(접속 지갑) 로컬 사본 — git 에는 올라가지 않음
if [ ! -f "$DIR/wallet/tnsnames.ora" ]; then
  for W in \
    "$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (공유)/Google Drive Files/AI 툴/Wallet_CHANGSHININCAIPOC" \
    "$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여/Google Drive Files/AI 툴/Wallet_CHANGSHININCAIPOC" ; do
    if [ -f "$W/tnsnames.ora" ]; then
      echo "[setup] 월렛 복사: $W"
      mkdir -p "$DIR/wallet"; cp -R "$W/." "$DIR/wallet/"; break
    fi
  done
  [ -f "$DIR/wallet/tnsnames.ora" ] || echo "[주의] 월렛을 못 찾았습니다. $DIR/wallet 에 월렛 파일을 직접 넣으세요."
fi

# 3) config.ini 기본값 보강 (기존 SMTP·비밀번호는 보존)
DIR="$DIR" python3 - <<'PY'
import configparser, os
DIR=os.environ["DIR"]; p=os.path.join(DIR,"config.ini")
c=configparser.ConfigParser(interpolation=None); c.read(p, encoding="utf-8")
for s in ("db","smtp","report"): c.setdefault(s,{})
c["db"].setdefault("user","ADMIN")
c["db"]["dsn"]="changshinincaipoc_medium"
c["db"]["wallet_dir"]=os.path.join(DIR,"wallet")
c["db"].setdefault("password",""); c["db"].setdefault("wallet_password","")
c["smtp"].setdefault("host","smtp.gmail.com"); c["smtp"].setdefault("port","587")
c["smtp"].setdefault("use_tls","true")
c["smtp"].setdefault("user","moon081588@gmail.com"); c["smtp"].setdefault("password","")
c["smtp"].setdefault("from","moon081588@gmail.com")
c["report"].setdefault("plants","3110,3120,3210")
c["report"].setdefault("window_before","3"); c["report"].setdefault("window_after","7")
c["report"].setdefault("recipients","moon081588@gmail.com, idea.seahsteel@gmail.com")
with open(p,"w",encoding="utf-8") as f: c.write(f)
try: os.chmod(p,0o600)
except Exception: pass
PY

# 4) .gitignore 보강 (월렛·실설정 커밋 방지)
touch .gitignore
grep -qxF "wallet/"    .gitignore || echo "wallet/"    >> .gitignore
grep -qxF "config.ini" .gitignore || echo "config.ini" >> .gitignore

# 5) 실행 (처음이면 비밀번호 1회 입력 → 저장, 이후 무인)
exec python3 balance_outgoing_mailer.py "$@"
