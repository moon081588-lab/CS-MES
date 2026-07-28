#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""리포트 11종 생성 — CKP.bat 의 1 번이 호출한다.

날짜를 인자로 주지 않으면 물어본다(그냥 Enter 치면 오늘).
실제 생성은 ckp_reports/run_all.py 가 한다. 이 파일은 안내와 오류 해설만 맡는다.
"""
import os, sys, datetime, subprocess

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # program\
TOP  = os.path.dirname(ROOT) if os.path.basename(ROOT).lower() == "program" else ROOT
PKG  = os.path.join(ROOT, "ckp_reports")
OUT  = os.path.join(TOP,  "report", "CKP_official")

def line(c="="): print(c * 62)

def ask_date(argv):
    for a in argv:
        if len(a) == 10 and a[4] == "-" and a[7] == "-":
            return a
    today = datetime.date.today().isoformat()
    try:
        s = input(f"\n기준 날짜를 입력하세요 (YYYY-MM-DD, 그냥 Enter = 오늘 {today}): ").strip()
    except EOFError:
        s = ""
    if not s:
        return today
    try:
        datetime.date.fromisoformat(s); return s
    except ValueError:
        print(f"  날짜 형식이 아닙니다 — 오늘({today})로 진행합니다.")
        return today

def main():
    line(); print(" CKP Manual Report — 공식 11종 생성"); line()
    date = ask_date(sys.argv[1:])
    print(f"\n기준일 {date} 로 생성합니다. 보통 1~2분 걸립니다.\n")

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
    wallet = os.path.join(TOP, "wallet")
    if os.path.isfile(os.path.join(wallet, "tnsnames.ora")):
        env.setdefault("TNS_ADMIN", wallet)

    rc = subprocess.run([sys.executable, os.path.join(PKG, "run_all.py"), date],
                        cwd=PKG, env=env).returncode

    print()
    line()
    if rc == 0:
        print(" 완료")
        line()
        newest = None
        if os.path.isdir(OUT):
            subs = [os.path.join(OUT, d) for d in os.listdir(OUT) if os.path.isdir(os.path.join(OUT, d))]
            if subs:
                newest = max(subs, key=os.path.getmtime)
        if newest:
            files = sorted(f for f in os.listdir(newest) if f.lower().endswith(".xlsx"))
            print(f" 저장 위치: {newest}")
            print(f" 파일 {len(files)}개:")
            for f in files:
                print(f"   - {f}")
        else:
            print(f" 저장 위치: {OUT}")
    else:
        print(" 실패 — 위 메시지를 확인하세요.")
        line()
        print(" 자주 나오는 원인")
        print("   · 접속 수단 없음      → CKP.bat 의 2 번을 실행해 어떤 경로로 붙는지 확인하세요.")
        print("   · ORA-12154 / 28759   → 지갑 파일이 wallet 폴더에 다 들어있는지 확인하세요.")
        print("   · ORA-01017           → DB 계정/비밀번호가 틀렸습니다 (config.ini).")
        print("   · 지갑 비밀번호 요구   → CKP.bat 의 2 번에서 지갑 비밀번호를 입력하세요.")
        print("   · 폴더 경로에 한글/공백 → C:\\CKP-Report 처럼 영문 경로로 옮기세요.")
    print()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n중단했습니다.")
