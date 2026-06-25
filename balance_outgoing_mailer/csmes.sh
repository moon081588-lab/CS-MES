#!/usr/bin/env bash
# ============================================================
#  CS-MES  —  한 줄 실행 래퍼 (자동로그인/thick 모드)
#  venv 준비 → 라이브러리 → Instant Client(자동로그인) → 월렛 → config → 실행
#  사용:  bash csmes.sh                 (전체: 조회→엑셀→메일)
#         bash csmes.sh --setup / --doctor / --dry-run / --test-mail
#         bash csmes.sh --install-schedule
#  ※ 자동로그인(cwallet.sso) 방식이라 월렛 비밀번호는 필요 없습니다. DB 계정 비번만 1회 입력.
# ============================================================
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1) 가상환경(.venv)
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then echo "[setup] 가상환경(.venv) 생성..."; python3 -m venv "$DIR/.venv" 2>/dev/null || true; fi
if [ -x "$PY" ]; then PIPFLAGS=""; else PY="python3"; PIPFLAGS="--break-system-packages --user"; fi

# 2) 라이브러리 (oracledb=SMTP경로 / openpyxl=엑셀 / mcp=Claude Desktop MCP서버)
if ! "$PY" -c "import oracledb, openpyxl, mcp" 2>/dev/null; then
  echo "[setup] 라이브러리 설치 (oracledb, openpyxl, mcp)..."
  "$PY" -m pip install --quiet --upgrade pip $PIPFLAGS 2>/dev/null || true
  "$PY" -m pip install --quiet $PIPFLAGS oracledb openpyxl mcp
fi

# 3) Oracle Instant Client (thick 자동로그인) — 없으면 brew 로 설치, lib 경로 탐지
find_ic() {
  for d in "$(brew --prefix 2>/dev/null)/lib" "$(brew --prefix instantclient-basic 2>/dev/null)/lib"; do
    [ -n "$d" ] && ls "$d"/libclntsh.dylib* >/dev/null 2>&1 && { echo "$d"; return; }
  done
  /usr/bin/find /opt/homebrew/Cellar /opt/homebrew/Caskroom /usr/local 2>/dev/null -name 'libclntsh.dylib*' 2>/dev/null | head -1 | xargs -I{} dirname {} 2>/dev/null
}
ICDIR="$(find_ic)"
if [ -z "$ICDIR" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "[setup] Oracle Instant Client 설치 중 (brew, 수 분 소요)..."
    brew tap InstantClientTap/instantclient 2>/dev/null || true
    brew install instantclient-basic 2>/dev/null || true
    ICDIR="$(find_ic)"
  fi
fi
[ -n "$ICDIR" ] && echo "[setup] Instant Client: $ICDIR" || echo "[주의] Instant Client 미발견 — 'brew tap InstantClientTap/instantclient && brew install instantclient-basic' 후 다시 실행"

# 4) 월렛(접속 지갑) 로컬 사본 — git 제외
if [ ! -f "$DIR/wallet/tnsnames.ora" ]; then
  for W in \
    "$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (공유)/Google Drive Files/AI 툴/Wallet_CHANGSHININCAIPOC" \
    "$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여/Google Drive Files/AI 툴/Wallet_CHANGSHININCAIPOC" ; do
    [ -f "$W/tnsnames.ora" ] && { echo "[setup] 월렛 복사: $W"; mkdir -p "$DIR/wallet"; cp -R "$W/." "$DIR/wallet/"; break; }
  done
  [ -f "$DIR/wallet/tnsnames.ora" ] || echo "[주의] 월렛 미발견 — $DIR/wallet 에 월렛 파일을 넣으세요."
fi
# sqlnet.ora 의 WALLET_LOCATION 을 실제 월렛 경로로 교정 (thick 자동로그인 필수)
if [ -f "$DIR/wallet/sqlnet.ora" ]; then
  DIR="$DIR" "$PY" - <<'PY'
import os,re
wd=os.path.join(os.environ["DIR"],"wallet"); p=os.path.join(wd,"sqlnet.ora")
s=open(p,encoding="utf-8").read()
s=re.sub(r'DIRECTORY\s*=\s*"[^"]*"', f'DIRECTORY="{wd}"', s)
open(p,"w",encoding="utf-8").write(s)
PY
fi

# 5) config.ini 기본값 보강 (기존 SMTP·비밀번호 보존, mode=thick 자동로그인)
DIR="$DIR" ICDIR="$ICDIR" "$PY" - <<'PY'
import configparser, os
DIR=os.environ["DIR"]; IC=os.environ.get("ICDIR",""); p=os.path.join(DIR,"config.ini")
c=configparser.ConfigParser(interpolation=None); c.read(p, encoding="utf-8")
for s in ("db","smtp","report"): c.setdefault(s,{})
c["db"].setdefault("user","ADMIN")
c["db"]["dsn"]="changshinincaipoc_medium"
c["db"]["wallet_dir"]=os.path.join(DIR,"wallet")
c["db"]["mode"]="thick"                       # 자동로그인(월렛 비번 불필요)
if IC: c["db"]["oracle_client_lib"]=IC
c["db"].setdefault("oracle_client_lib","")
c["db"].setdefault("password",""); c["db"].setdefault("wallet_password","")
c["smtp"].setdefault("host","smtp.gmail.com"); c["smtp"].setdefault("port","587"); c["smtp"].setdefault("use_tls","true")
c["smtp"].setdefault("user","moon081588@gmail.com"); c["smtp"].setdefault("password",""); c["smtp"].setdefault("from","moon081588@gmail.com")
c["report"].setdefault("plants","3110,3120,3210")
c["report"].setdefault("window_before","3"); c["report"].setdefault("window_after","7")
c["report"].setdefault("recipients","moon081588@gmail.com, idea.seahsteel@gmail.com")
c["report"].setdefault("output_dir","")   # 비우면 코드 기본값 ../report (=CS-MES/report) 사용
c["report"].setdefault("share_link","https://postechackr-my.sharepoint.com/:f:/g/personal/nicklee100_postech_ac_kr/IgCe7BW9lHo3TIFhzzd6zFlcASay4Xr5YJBD-pv0uvV3VrY?e=dDpxts")
with open(p,"w",encoding="utf-8") as f: c.write(f)
try: os.chmod(p,0o600)
except Exception: pass
PY

# 6) .gitignore 보강
touch .gitignore
for ig in "wallet/" "config.ini" ".venv/"; do grep -qxF "$ig" .gitignore || echo "$ig" >> .gitignore; done

# 7) 실행 (처음이면 DB 계정 비밀번호 1회 입력 → 저장)
exec "$PY" balance_outgoing_mailer.py "$@"
