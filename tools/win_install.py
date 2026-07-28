#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS-MES Windows 설치 — install_windows.bat 이 호출한다. 단독 실행도 가능.

    python tools\\win_install.py

왜 파이썬인가:
  cmd.exe 는 배치 파일을 **OEM 코드페이지(한국 cp949)** 로 읽고 **CRLF 줄바꿈**을 요구한다.
  UTF-8 한글이 든 .bat 은 `chcp 65001` 을 해도 파서가 깨져 한글 조각이 명령으로 실행된다
  (2026-07-28 현장 확인). 그래서 .bat 은 ASCII 만 남기고, 사람이 읽는 안내는 전부 여기서 낸다.
  파이썬은 UTF-8 출력을 강제할 수 있어 이 문제가 없다.
"""
import os, sys, shutil, subprocess

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM  = os.path.join(ROOT, "balance_outgoing_mailer")
VENV = os.path.join(BOM, ".venv")
VPY  = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")
PKGS = ["oracledb", "openpyxl", "mcp", "tzdata"]

def line(c="="): print(c * 60)
def step(n, t): print(); line(); print(f" [{n}/6] {t}"); line()

def fail(msg, todo=None):
    print(f"\n[실패] {msg}")
    if todo:
        print("\n  조치:")
        for t in todo: print(f"    {t}")
    print("\n설치를 중단합니다.")
    sys.exit(1)

def main():
    line(); print(" CS-MES Windows 설치"); print(f" 위치: {ROOT}"); line()

    # 1) 경로 점검 --------------------------------------------------------
    step(1, "설치 경로 점검")
    bad = []
    if " " in ROOT: bad.append("공백")
    if any(ord(ch) > 127 for ch in ROOT): bad.append("한글 등 비ASCII 문자")
    if "OneDrive" in ROOT or "Google Drive" in ROOT: bad.append("클라우드 동기화 폴더")
    if bad:
        print(f"  ⚠ 경로에 {' / '.join(bad)} 가 있습니다.")
        print("    SQLcl 은 자바라서 이런 경로의 지갑을 읽지 못합니다(ORA-17956).")
        print("    권장: C:\\CS-MES 로 폴더를 옮긴 뒤 다시 실행하세요.")
        if input("\n    그래도 계속할까요? (y/N) ").strip().lower() != "y":
            sys.exit(1)
    else:
        print("  OK — 공백·한글 없는 경로입니다.")

    # 2) 가상환경 ---------------------------------------------------------
    step(2, "파이썬 가상환경(.venv)")
    if not os.path.exists(VPY):
        print("  생성 중...")
        r = subprocess.run([sys.executable, "-m", "venv", VENV])
        if r.returncode != 0 or not os.path.exists(VPY):
            fail("가상환경 생성 실패",
                 ["Microsoft Store 스텁 파이썬이면 python.org 정식 버전을 설치하세요.",
                  "설치 화면에서 'Add python.exe to PATH' 를 반드시 체크하세요."])
    print(f"  OK — {VPY}")

    # 3) 라이브러리 -------------------------------------------------------
    step(3, "라이브러리 설치")
    probe = "import oracledb, openpyxl, mcp; from zoneinfo import ZoneInfo; ZoneInfo('Asia/Seoul')"
    if subprocess.run([VPY, "-c", probe], capture_output=True).returncode != 0:
        print(f"  설치 중: {', '.join(PKGS)} ...")
        subprocess.run([VPY, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        if subprocess.run([VPY, "-m", "pip", "install", "--quiet"] + PKGS).returncode != 0:
            fail("라이브러리 설치 실패",
                 ["사내 프록시/방화벽을 확인하세요.",
                  f'수동 설치: "{VPY}" -m pip install ' + " ".join(PKGS)])
    print("  OK — " + ", ".join(PKGS))

    # 4) 설정 파일 --------------------------------------------------------
    step(4, "설정 파일(config.ini)")
    cfg, ex = os.path.join(BOM, "config.ini"), os.path.join(BOM, "config.ini.example")
    if not os.path.exists(cfg):
        if not os.path.exists(ex): fail(f"양식 파일이 없습니다: {ex}")
        shutil.copy(ex, cfg); print(f"  생성함 — {cfg}")
    else:
        print(f"  이미 있음 — {cfg}")

    # 5) 지갑 · SQLcl -----------------------------------------------------
    step(5, "Oracle 지갑 / SQLcl")
    tns = os.path.join(BOM, "wallet", "tnsnames.ora")
    if not os.path.exists(tns):
        fail(f"지갑이 없습니다: {tns}",
             ["OCI 콘솔에서 받은 지갑 zip 을 위 wallet 폴더에 풀어 넣으세요(8개 파일).",
              "그 뒤 이 설치 프로그램을 다시 실행하세요."])
    print(f"  지갑 OK — {os.path.dirname(tns)}")
    sqlcl = os.environ.get("SQLCL") or shutil.which("sql")
    if not sqlcl and os.name == "nt":
        for n in ("sql.exe", "sql.cmd", "sql.bat"):
            sqlcl = sqlcl or shutil.which(n)
    if sqlcl:
        print(f"  SQLcl OK — {sqlcl}")
    else:
        print("  ⚠ SQLcl 을 찾지 못했습니다. 리포트 11개 생성에 필요합니다.")
        print("    1) https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/download/")
        print("    2) C:\\sqlcl 에 압축을 풀고")
        print('    3) setx SQLCL "C:\\sqlcl\\bin\\sql.exe"')
        print("    4) 연결 저장:")
        print("         sql /nolog")
        print("         SQL> connmgr add -name changshinincaipoc"
              " -url jdbc:oracle:thin:@changshinincaipoc_medium -user ADMIN")

    # 6) Claude Desktop 등록 + 점검 ---------------------------------------
    step(6, "Claude Desktop MCP 등록")
    se = os.path.join(BOM, "setup_env.py")
    subprocess.run([VPY, se, "--init-claude"])
    print(); line("-"); print(" 최종 점검"); line("-")
    subprocess.run([VPY, se, "--check"])

    print(); line(); print(" 남은 순서"); line()
    print("  1) 설정 파일을 열어 값을 채우세요:")
    print(f"       {cfg}")
    print("       - [db] password        DB 비밀번호")
    print("       - [report] recipients  메일 받는 사람(메일을 쓸 때만)")
    print("  2) Claude Desktop 을 완전히 종료했다가(트레이 아이콘까지) 다시 켜세요.")
    print("  3) 채팅창에 이렇게 물어보세요:")
    print('       "CKP 레포트 11개 만들어줘"')
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단했습니다.")
