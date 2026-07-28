#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CKP 리포트 — 하나뿐인 실행 창구. CKP.bat 이 이 파일만 부른다.

.bat 을 넷으로 나눠 두었더니 폴더가 복잡해져서, 메뉴 하나로 합쳤다.
번호를 인자로 주면 메뉴를 건너뛴다(예: 스케줄러에서 `ckp.py 1 2026-07-13`).

  1 리포트 만들기   2 처음 설정 / 설정 바꾸기   3 DB 연결 점검   4 Claude 에 연결
"""
import os, sys

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MENU = [
    ("1", "리포트 만들기 (엑셀 11개)", "run_reports"),
    ("2", "처음 설정 / 설정 바꾸기",   "bootstrap"),
    ("3", "DB 연결만 점검",            "db_check"),
    ("4", "Claude 에 이 폴더 연결",    "register_mcp"),
]


def choose(argv):
    for a in argv:
        if a in ("1", "2", "3", "4"):
            return a
    print()
    print("=" * 62)
    print(" CKP Manual Report")
    print("=" * 62)
    for k, label, _ in MENU:
        print(f"   {k}. {label}")
    print("   0. 닫기")
    print("-" * 62)
    print(" 처음이라면 2 번을 먼저 하세요. 평소에는 1 번만 쓰면 됩니다.")
    while True:
        try:
            v = input("\n번호를 고르세요 [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print(); return "0"
        if v in ("0", "1", "2", "3", "4"):
            return v
        print("  1 ~ 4 또는 0 중에서 골라 주세요.")


def autoheal():
    """CKP.bat 을 쓸 때마다 Claude 연결이 어긋났는지 보고 조용히 맞춰 놓는다.
    폴더를 옮기거나 파이썬이 바뀌면 등록이 깨지는데, 그걸 사람이 알아채는 시점은
    늘 '왜 안 되지' 하고 한참 헤맨 뒤였다. 그래서 여기서 먼저 본다.
    실패해도 메뉴는 정상 진행한다 — 리포트 생성은 Claude 와 무관하게 되어야 하므로."""
    try:
        import register_mcp
        register_mcp.check_and_repair()
    except Exception:
        pass


def main():
    autoheal()
    pick = choose(sys.argv[1:])
    if pick == "0":
        return 0
    mod = dict((k, m) for k, _, m in MENU)[pick]
    # 각 기능은 원래 파일 그대로 두고 여기서 부르기만 한다(파일은 줄이되 코드는 안 섞는다).
    rest = [a for a in sys.argv[1:] if a != pick]
    sys.argv = [mod + ".py"] + rest
    return __import__(mod).main() or 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n중단했습니다.")
