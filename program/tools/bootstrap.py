#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CKP 리포트 폴더 준비 — CKP.bat 의 2 번이 호출한다.

이 파일 하나로 '새 PC 에 처음 까는 일' 이 끝나야 한다. 그래서 순서가 이렇다.
  경로 점검 → 라이브러리(오프라인) → 지갑 찾기 → 계정·비밀번호 입력 → 실제 접속 시험

비밀번호는 zip 에 넣지 않는다. 여기서 한 번 입력받아 그 PC 의 config.ini 에만 적는다.
.bat 은 한글을 담을 수 없어(cmd.exe 가 OEM 코드페이지로 읽는다) 안내는 전부 여기서 낸다.
"""
import os, sys, glob, shutil, subprocess, getpass, configparser

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # program\
TOP    = os.path.dirname(ROOT) if os.path.basename(ROOT).lower() == "program" else ROOT
PKG    = os.path.join(ROOT, "ckp_reports")
VENDOR = os.path.join(ROOT, "vendor")
WALLET = os.path.join(TOP,  "wallet")      # 지갑은 사람이 여는 최상위 폴더에 둔다
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


# 윈도우를 처음 쓰는 사람에게 '폴더를 C 드라이브로 옮기기' 가 가장 어려운 단계다.
# 경로가 나쁘면 프로그램이 대신 옮겨 준다. (실행 중인 폴더는 잠겨 있어 이동이 안 되므로
#  복사해 두고 새 자리에서 다시 실행하게 안내한다.)
DEST_DEFAULT = r"C:\CKP-Report"


def _ignore(_dir, names):
    return [n for n in names if n in ("__pycache__", ".venv", ".git") or n.endswith(".pyc")]


def relocate(top):
    """반환: 옮긴 새 경로(옮겼을 때) / "" (안 옮겼을 때)."""
    import shutil
    if os.name != "nt" and not os.environ.get("CKP_TEST_MOVE"):
        return ""                                   # 윈도우에서만 제안한다
    try:
        if not sys.stdin.isatty():
            return ""                               # 스케줄러 등 사람이 없는 실행에서는 건드리지 않는다
    except Exception:
        return ""
    dest = os.environ.get("CKP_DEST") or DEST_DEFAULT
    if os.path.abspath(top).rstrip("\\/").lower() == os.path.abspath(dest).rstrip("\\/").lower():
        return ""
    print()
    print(f"  이 폴더를 {dest} 로 옮기면 해결됩니다.")
    if ask("  지금 옮겨 드릴까요? 옮기려면 y, 그냥 두려면 n [y]: ", "y").lower() != "y":
        print("  옮기지 않았습니다. 나중에 직접 옮기고 CKP.bat 을 다시 실행하세요.")
        return ""
    if os.path.exists(os.path.join(dest, "CKP.bat")):
        print(f"  ⚠ {dest} 에 이미 프로그램이 있습니다.")
        if ask("     덮어쓸까요? [n]: ", "n").lower() != "y":
            print("  옮기지 않았습니다.")
            return ""
    try:
        os.makedirs(dest, exist_ok=True)
        shutil.copytree(top, dest, dirs_exist_ok=True, ignore=_ignore)
    except Exception as e:
        print(f"  ❌ 옮기지 못했습니다: {e}")
        print(f"     탐색기에서 이 폴더를 {dest} 로 직접 옮겨 주세요.")
        return ""
    print(f"  ✅ 옮겼습니다 → {dest}")
    print()
    print("  ────────────────────────────────────────────────")
    print("   이제 새 자리에서 다시 실행하세요.")
    print(f"     {os.path.join(dest, 'CKP.bat')}  더블클릭")
    print("   (지금 창은 닫으셔도 됩니다. 옛 폴더는 지우셔도 됩니다.)")
    print("  ────────────────────────────────────────────────")
    try:
        os.startfile(dest)                          # 새 폴더를 탐색기로 열어 준다
    except Exception:
        pass
    return dest


def main():
    head("CKP 리포트 폴더 준비")
    print(f" 위치   : {TOP}")
    print(f" 파이썬 : {sys.version.split()[0]}  ({sys.executable})")

    # ---------------------------------------------------------- 1) 경로
    head("[1/5] 폴더 위치")
    bad = []
    if " " in TOP: bad.append("공백")
    if any(ord(c) > 127 for c in TOP): bad.append("한글 등 비ASCII")
    if "OneDrive" in TOP or "Google Drive" in TOP: bad.append("클라우드 동기화 폴더")
    if bad:
        print(f"  ⚠ 경로에 {' / '.join(bad)} 가 있습니다 → {TOP}")
        print("    이대로 두면 Oracle 지갑을 읽을 때 실패합니다(ORA-17956).")
        if relocate(TOP):
            return 0                                # 새 자리에서 다시 실행하면 된다
    else:
        print("  OK")

    # ---------------------------------------------------------- 2) 라이브러리
    head("[2/5] 라이브러리")
    # vendor 에 담아 둔 것은 64비트 윈도우 · 파이썬 3.11~3.14 용이다.
    # 여기서 먼저 걸러 주지 않으면 pip 이 뱉는 긴 영어 오류만 보게 된다.
    import struct
    vmaj, vmin = sys.version_info[:2]
    bits = struct.calcsize("P") * 8
    if os.name == "nt" and bits != 64:
        print(f"  ❌ 32비트 파이썬입니다. 64비트 파이썬 3.12 를 설치해 주세요.")
        print("     https://www.python.org/downloads/  ('Windows installer (64-bit)')")
    elif (vmaj, vmin) < (3, 11) or (vmaj, vmin) > (3, 14):
        print(f"  ❌ 파이썬 {vmaj}.{vmin} 은 이 폴더가 담고 있는 설치 파일과 맞지 않습니다.")
        print("     3.11 ~ 3.14 중 하나가 필요합니다. 3.12 를 권합니다.")
        print("     https://www.python.org/downloads/  (설치할 때 'Add python.exe to PATH' 체크)")
    whls = sorted(glob.glob(os.path.join(VENDOR, "*.whl")))
    need = []
    for mod, name in (("openpyxl", "openpyxl"), ("oracledb", "oracledb")):
        try:
            __import__(mod); print(f"  {name:10s} 이미 있음")
        except ImportError:
            need.append(name)
    if need:
        # vendor/ 가 있으면 인터넷 없이(현장 배포본), 없으면 인터넷으로(GitHub 에서 받은 경우).
        if whls:
            print(f"  설치 중: {', '.join(need)}  (vendor/ 의 {len(whls)}개 파일 사용, 인터넷 불필요)")
            cmd = [sys.executable, "-m", "pip", "install", "--quiet",
                   "--no-index", f"--find-links={VENDOR}"] + need
        else:
            print(f"  설치 중: {', '.join(need)}  (vendor 폴더가 없어 인터넷에서 받습니다)")
            cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + need
        r = subprocess.run(cmd)
        if r.returncode != 0 and "--no-index" not in cmd:
            # 회사 PC 는 pip 이 시스템 파이썬을 건드리지 못하게 막혀 있는 경우가 있다.
            print("  전역 설치가 막혀 있어 사용자 영역으로 다시 시도합니다...")
            r = subprocess.run(cmd + ["--user"])
        if r.returncode == 0:
            print("  완료")
        else:
            print("  ⚠ 설치 실패 — 아래를 직접 실행해 보세요:")
            print("     " + " ".join(f'"{c}"' if " " in c else c for c in cmd))

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
            print("  건너뛰었습니다. 나중에 CKP.bat 의 2 번을 다시 실행하면 됩니다.")

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
    print("  CKP.bat 을 다시 실행해서")
    print("    1 번 → 리포트 11개 만들기")
    print("    3 번 → DB 연결만 점검")
    print("    4 번 → Claude 에 연결 (그 뒤 Claude 완전 종료 후 재시작)")
    print()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n중단했습니다.")
