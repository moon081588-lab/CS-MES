#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CKP 리포트 폴더 준비 — setup.bat 이 호출한다.

이 파일 하나로 '새 PC 에 처음 까는 일' 이 끝나야 한다. 그래서 순서가 이렇다.
  경로 점검 → 라이브러리(오프라인) → 지갑 찾기 → 계정·비밀번호 입력 → 실제 접속 시험

비밀번호는 zip 에 넣지 않는다. 여기서 한 번 입력받아 그 PC 의 config.ini 에만 적는다.
.bat 은 한글을 담을 수 없어(cmd.exe 가 OEM 코드페이지로 읽는다) 안내는 전부 여기서 낸다.
"""
import os, sys, glob, shutil, subprocess, getpass, configparser

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG    = os.path.join(ROOT, "ckp_reports")
VENDOR = os.path.join(ROOT, "vendor")
WALLET = os.path.join(ROOT, "wallet")
CFG    = os.path.join(PKG, "config.ini")
sys.path.insert(0, PKG)

def line(c="="): print(c * 62)
def head(t): print(); line(); print(f" {t}"); line()

def ask(prompt, default="", secret=False):
    """빈 입력이면 default 를 쓴다. 화면이 없는 실행(스케줄러)에서는 default 로 넘어간다."""
    try:
        v = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    except (EOFError, KeyboardInterrupt):
        print(); return default
    return v or default


def main():
    head("CKP 리포트 폴더 준비")
    print(f" 위치   : {ROOT}")
    print(f" 파이썬 : {sys.version.split()[0]}  ({sys.executable})")

    # ---------------------------------------------------------- 1) 경로
    head("[1/5] 폴더 위치")
    bad = []
    if " " in ROOT: bad.append("공백")
    if any(ord(c) > 127 for c in ROOT): bad.append("한글 등 비ASCII")
    if "OneDrive" in ROOT or "Google Drive" in ROOT: bad.append("클라우드 동기화 폴더")
    if bad:
        print(f"  ⚠ 경로에 {' / '.join(bad)} 가 있습니다 → {ROOT}")
        print("    지갑을 읽을 때 문제가 생깁니다. C:\\CKP-Report 로 옮기고 다시 실행하세요.")
    else:
        print("  OK")

    # ---------------------------------------------------------- 2) 라이브러리
    head("[2/5] 라이브러리 (인터넷 불필요)")
    whls = sorted(glob.glob(os.path.join(VENDOR, "*.whl")))
    need = []
    for mod, name in (("openpyxl", "openpyxl"), ("oracledb", "oracledb")):
        try:
            __import__(mod); print(f"  {name:10s} 이미 있음")
        except ImportError:
            need.append(name)
    if need:
        if not whls:
            print(f"  ❌ vendor 폴더에 설치 파일이 없습니다: {VENDOR}")
        else:
            print(f"  설치 중: {', '.join(need)}  (vendor/ 의 {len(whls)}개 파일 사용)")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                                "--no-index", f"--find-links={VENDOR}"] + need)
            if r.returncode == 0:
                print("  완료")
            else:
                print("  ⚠ 설치 실패 — 아래를 직접 실행해 보세요:")
                print(f'     "{sys.executable}" -m pip install --no-index '
                      f'--find-links="{VENDOR}" ' + " ".join(need))

    from core import db   # 위에서 설치한 뒤에 불러야 한다

    # ---------------------------------------------------------- 3) 지갑
    head("[3/5] Oracle 지갑")
    os.makedirs(WALLET, exist_ok=True)
    wdir = db.find_wallet(WALLET) or db.wallet_dir()
    if not wdir:
        print("  ❌ 지갑을 찾지 못했습니다.")
        print(f"     OCI 에서 받은 지갑 zip 을 이 폴더에 넣어 주세요 → {WALLET}")
        print("     (zip 째 넣어 두면 다음 실행 때 알아서 풀어 씁니다)")
    else:
        n = len([f for f in os.listdir(wdir) if os.path.isfile(os.path.join(wdir, f))])
        print(f"  찾음 : {wdir}  (파일 {n}개)")
        db.sync_sqlnet(wdir)          # 남의 PC 절대경로가 박힌 sqlnet.ora 를 이 PC 기준으로 고침
        print("  sqlnet.ora 를 이 PC 경로로 맞췄습니다.")
        if os.path.abspath(wdir) != os.path.abspath(WALLET):
            db.save_cfg({"wallet_dir": wdir})
            print("  config.ini 에 지갑 위치를 적어 두었습니다.")

    # ---------------------------------------------------------- 4) 계정
    head("[4/5] DB 계정")
    if not os.path.exists(CFG) and os.path.exists(CFG + ".example"):
        shutil.copy(CFG + ".example", CFG)
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    cp.read(CFG, encoding="utf-8")
    user = cp.get("db", "user", fallback="").strip()
    pw   = cp.get("db", "password", fallback="").strip()

    if user and pw:
        print(f"  이미 저장돼 있습니다 (계정 {user}).")
        if ask("  다시 입력하시겠습니까? 바꾸려면 y [n]: ", "n").lower() == "y":
            user = pw = ""
    if not (user and pw):
        print("  DB 접속 정보를 입력하세요. 이 PC 의 설정 파일에만 저장되고 화면에는 안 보입니다.")
        print("  (담당자에게 받은 값입니다. 모르면 Enter 로 건너뛰고 나중에 다시 실행하세요.)")
        user = ask("   계정 이름 [ADMIN]: ", "ADMIN")
        pw   = ask("   DB 비밀번호        : ", secret=True)
        wpw  = ask("   지갑 비밀번호      : ", secret=True)
        if pw:
            db.save_cfg({"user": user, "password": pw, "wallet_password": wpw, "backend": "auto"})
            print(f"  저장했습니다 → {CFG}")
        else:
            print("  건너뛰었습니다. 나중에 setup.bat 을 다시 실행하면 됩니다.")

    # ---------------------------------------------------------- 5) 접속 시험
    head("[5/5] 실제 접속 시험")
    cfg = db.load_cfg()
    backend, why = db.choose_backend(cfg)
    print(f"  접속 경로 : {backend} — {why}")
    dsn = cfg.get("db", "dsn", fallback="changshinincaipoc_medium").strip()
    host, port = db.dsn_endpoint(db.wallet_dir(cfg), dsn)
    if host:
        ok, msg = db.preflight(host, port)
        print(f"  네트워크  : {'OK' if ok else '❌'}  {msg}")
        if ok is False:
            print("     → 사내 방화벽/프록시에서 이 주소·포트로 나가는 것을 허용해야 합니다.")
            print(f"       (담당 IT 에 '{host} {port} 아웃바운드 허용' 을 요청하세요)")
    if backend == "oracledb" and not cfg.get("db", "password", fallback="").strip():
        print("  비밀번호가 비어 있어 접속 시험을 건너뜁니다.")
    else:
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "ckp_setup_check.csv")
        try:
            db.run_batch([(tmp, "SELECT USER FROM DUAL")],
                         cfg.get("db", "sqlcl_conn", fallback="changshinincaipoc"))
            print("  접속      : ✅ 성공")
        except Exception as e:
            print("  접속      : ❌ 실패")
            print(f"     {str(e)[:700]}")

    head("준비 끝")
    print("  · 리포트를 만들려면          run.bat")
    print("  · DB 만 빠르게 점검하려면    check.bat")
    print("  · Claude 스킬로 쓰려면       connect_claude.bat 을 한 번 실행하고 Claude 재시작")
    print()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n중단했습니다.")
