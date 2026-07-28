#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude 데스크톱에 이 폴더를 연결한다 — connect_claude.bat 이 호출한다.

왜 필요한가.
  스킬(SKILL.md)만 올려서는 Claude 가 리포트를 못 만든다. 스킬은 '어떻게 시킬지'만
  적혀 있고, 실제로 도는 것은 이 폴더의 ckp_mcp.py 다. 둘을 이어 주는 것이
  claude_desktop_config.json 이고, 그 파일에는 **절대경로**가 들어간다.

  지금까지 겪은 경로 문제의 대부분이 여기서 나왔다. 폴더를 옮기거나 다른 PC 에
  깔면 그 절대경로가 옛 위치를 가리킨 채 남아 조용히 실패한다. 그래서 사람이 손으로
  적지 않고, 이 스크립트가 **지금 이 폴더 위치**를 읽어 그때그때 써 넣는다.

  폴더를 옮겼다면 옮긴 자리에서 이 파일을 한 번 더 실행하면 된다.
"""
import os, sys, json, shutil, datetime

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG  = os.path.join(ROOT, "ckp_reports")
MCP  = os.path.join(PKG, "ckp_mcp.py")

def line(c="="): print(c * 62)


def config_path():
    """Claude 데스크톱 설정 파일 위치 (OS 별)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def main():
    line(); print(" Claude 데스크톱 연결"); line()
    print(f" 이 폴더 : {ROOT}")

    if not os.path.isfile(MCP):
        print(f" ❌ ckp_mcp.py 가 없습니다: {MCP}")
        print("    압축이 제대로 안 풀렸을 수 있습니다."); return 1

    cfgp = config_path()
    print(f" 설정 파일: {cfgp}")
    if not os.path.isdir(os.path.dirname(cfgp)):
        print(" ❌ Claude 데스크톱이 설치돼 있지 않은 것 같습니다.")
        print("    Claude 를 먼저 설치·실행한 뒤 다시 돌려 주세요.")
        print("    (Claude 없이 run.bat 만 써도 리포트는 똑같이 나옵니다.)")
        return 1

    data = {}
    if os.path.isfile(cfgp):
        try:
            data = json.load(open(cfgp, encoding="utf-8"))
        except Exception as e:
            print(f" ⚠ 기존 설정을 읽지 못했습니다({e}). 새로 만듭니다.")
            data = {}
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{cfgp}.bak_{stamp}"
        try:
            shutil.copy(cfgp, bak); print(f" 백업     : {bak}")
        except Exception:
            pass

    servers = data.setdefault("mcpServers", {})
    before = json.dumps(servers.get("ckp-reports"), ensure_ascii=False)
    servers["ckp-reports"] = {
        "command": sys.executable,
        "args": [MCP],
        "cwd": PKG,
        "env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    }
    after = json.dumps(servers["ckp-reports"], ensure_ascii=False)

    os.makedirs(os.path.dirname(cfgp), exist_ok=True)
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    line("-")
    if before == after:
        print(" 이미 이 폴더로 연결돼 있었습니다. 바뀐 것 없음.")
    else:
        print(" 연결했습니다.")
        print(f"   python : {sys.executable}")
        print(f"   서버   : {MCP}")
    line("-")
    print(" 다음 순서")
    print("   1) Claude 를 완전히 종료했다가 다시 켜세요 (창만 닫으면 안 됩니다).")
    print("   2) 스킬 파일(CKP-skills-v12.7.skill)을 Claude 에 올리세요.")
    print('   3) 채팅창에 "레포트 11개 작성해줘" 라고 치면 됩니다.')
    print()
    print(" ※ 이 폴더를 다른 곳으로 옮기면 이 파일을 옮긴 자리에서 한 번 더 실행하세요.")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n중단했습니다.")
