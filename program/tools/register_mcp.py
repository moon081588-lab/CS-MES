#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude 데스크톱에 이 폴더를 연결한다 — CKP.bat 의 4 번이 호출한다.

왜 필요한가.
  스킬(SKILL.md)만 올려서는 Claude 가 리포트를 못 만든다. 스킬은 '어떻게 시킬지'만
  적혀 있고, 실제로 도는 것은 이 폴더의 ckp_mcp.py 다. 둘을 이어 주는 것이
  claude_desktop_config.json 이고, 그 파일에는 **절대경로**가 들어간다.

  지금까지 겪은 경로 문제의 대부분이 여기서 나왔다. 폴더를 옮기거나 다른 PC 에
  깔면 그 절대경로가 옛 위치를 가리킨 채 남아 조용히 실패한다. 그래서 사람이 손으로
  적지 않고, 이 스크립트가 **지금 이 폴더 위치**를 읽어 그때그때 써 넣는다.

  폴더를 옮겼다면 옮긴 자리에서 이 파일을 한 번 더 실행하면 된다.
"""
import os, sys, io, json, shutil, datetime

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # program 폴더
PKG  = os.path.join(ROOT, "ckp_reports")
MCP  = os.path.join(PKG, "ckp_mcp.py")

# 이 프로젝트가 Claude 에 등록하는 서버들. 폴더를 옮기면 여기 경로가 전부 깨지므로
# 하나만 고치면 나머지가 조용히 죽는다(2026-07-28 balance-outgoing 이 그렇게 끊겼다).
SERVERS = [
    ("ckp-reports", os.path.join(PKG, "ckp_mcp.py")),
]
# 더 이상 쓰지 않는 서버. 설정에 남아 있으면 Claude 가 '연결 끊김' 경고를 띄우므로 지운다.
RETIRED = ["balance-outgoing"]

def line(c="="): print(c * 62)


def config_path():
    """Claude 데스크톱 설정 파일 위치 (OS 별)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


_MCP_CACHE = {}


def can_import_mcp(exe):
    """그 파이썬으로 실제로 서버가 뜰 수 있는지 확인한다.
    이 서버는 mcp 패키지가 있어야 한다. 이걸 안 보고 경로만 적으면
    Claude 는 '서버 연결 실패' 만 조용히 내고 원인을 안 알려 준다."""
    if not exe:
        return False
    if exe in _MCP_CACHE:                 # 같은 파이썬을 여러 번 묻지 않는다(자동 점검이 느려진다)
        return _MCP_CACHE[exe]
    try:
        import subprocess
        r = subprocess.run([exe, "-c", "import mcp"], capture_output=True, timeout=8)
        ok = (r.returncode == 0)
    except Exception:
        ok = False
    _MCP_CACHE[exe] = ok
    return ok


def project_venvs():
    """이 프로젝트 안에 이미 있는 가상환경들. 새로 만들지 않고 있는 것을 쓴다.
    (실제로 이 서버는 program\\mailer\\.venv 의 파이썬으로 돌고 있었다.)"""
    import glob as _g
    exe = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    out = []
    for d in (ROOT, os.path.dirname(ROOT)):
        out += sorted(_g.glob(os.path.join(d, "*", ".venv", *exe.split("/"))))
        out += sorted(_g.glob(os.path.join(d, ".venv", *exe.split("/"))))
    return out


def pick_python(previous=None):
    """mcp 를 불러올 수 있는 파이썬을 고른다. 없으면 만들지 말고 그대로 알린다.
    원래 설정값 > 프로젝트 안의 기존 가상환경 > 지금 이 스크립트를 돌린 파이썬 > PATH."""
    import shutil, glob as _g
    cands = [previous] + project_venvs() + [sys.executable]
    for n in ("python3", "python", "python3.14", "python3.13", "python3.12", "python3.11"):
        cands.append(shutil.which(n))
    cands += sorted(_g.glob("/opt/homebrew/opt/python@3.*/bin/python3*"))
    cands += sorted(_g.glob("/usr/local/opt/python@3.*/bin/python3*"))
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        if can_import_mcp(c):
            if c != sys.executable:
                print(f" 파이썬   : {c}")
                print("            (지금 실행한 파이썬에는 mcp 가 없어 이쪽을 씁니다)")
            return c
    return install_mcp()


def install_mcp():
    """mcp 가 깔린 파이썬이 하나도 없으면 직접 깔아 준다.

    현장에선 사람이 명령창을 열어 pip 를 치는 것 자체가 큰 장벽이고,
    원격으로 화면을 주고받을 수 없는 상황도 있다. 그래서 여기서 끝낸다.
    vendor 폴더에 휠을 동봉해 두었으므로 인터넷도 필요 없다."""
    import subprocess, glob as _g
    vendor = os.path.join(ROOT, "vendor")
    tgt = sys.executable
    off = bool(_g.glob(os.path.join(vendor, "mcp-*.whl")))
    print(" mcp 라이브러리가 없어 지금 설치합니다"
          + (" (동봉된 파일 사용, 인터넷 불필요)" if off else " (인터넷에서 받습니다)"))
    tries = []
    if off:
        tries.append([tgt, "-m", "pip", "install", "--quiet", "--no-index",
                      f"--find-links={vendor}", "mcp"])
        tries.append([tgt, "-m", "pip", "install", "--quiet", "--no-index",
                      f"--find-links={vendor}", "--user", "mcp"])
    tries.append([tgt, "-m", "pip", "install", "--quiet", "mcp"])
    tries.append([tgt, "-m", "pip", "install", "--quiet", "--user", "mcp"])
    for cmd in tries:
        try:
            subprocess.run(cmd, capture_output=True, timeout=300)
        except Exception:
            continue
        _MCP_CACHE.pop(tgt, None)
        if can_import_mcp(tgt):
            print("   설치 완료")
            return tgt
    print(" ❌ 설치하지 못했습니다. 아래를 명령 프롬프트에 붙여넣어 주세요.")
    print(f'    "{tgt}" -m pip install --no-index --find-links="{vendor}" mcp')
    return ""


def our_wallet():
    """이 프로그램이 쓰는 지갑 폴더. 없으면 ""."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "ckp_reports"))
        from core import db
        return db.wallet_dir() or ""
    except Exception:
        return ""


def fix_sqlcl_tns(servers):
    """sqlcl 서버의 TNS_ADMIN 이 없는 폴더를 가리키면 우리 지갑 폴더로 고친다.

    이 값은 우리가 만든 게 아니라 사람이 설정 파일에 손으로 적어 넣은 것이라,
    폴더를 옮기거나 지우면 그대로 남아 조용히 깨진다(2026-07-29 실제로 그랬다).
    저장된 연결로 붙을 때는 멀쩡해 보여서 한참 뒤에야 드러난다."""
    ent = servers.get("sqlcl")
    if not isinstance(ent, dict):
        return None
    env = ent.get("env")
    if not isinstance(env, dict):
        return None
    cur = (env.get("TNS_ADMIN") or "").strip()
    if not cur or os.path.isfile(os.path.join(cur, "tnsnames.ora")):
        return None                                   # 비었거나 멀쩡하면 그대로 둔다
    w = our_wallet()
    if not w:
        print(f" ⚠ sqlcl 의 TNS_ADMIN 이 없는 폴더를 가리킵니다 → {cur}")
        print("    (우리 지갑 폴더도 못 찾아 고치지 못했습니다)")
        return None
    env["TNS_ADMIN"] = w
    print(f" 정리     : sqlcl 의 TNS_ADMIN 을 고쳤습니다")
    print(f"            {cur}  →  {w}")
    return w


def read_config():
    """(경로, 내용) — 못 읽으면 (경로, None)."""
    cfgp = config_path()
    if not os.path.isfile(cfgp):
        return cfgp, None
    try:
        return cfgp, json.load(open(cfgp, encoding="utf-8"))
    except Exception:
        return cfgp, None


def diagnose():
    """지금 Claude 설정이 이 폴더를 제대로 가리키는지 본다(등록 대상 전부). 고치지는 않는다.
    반환: (문제없음?, 사람이 읽는 사유)"""
    cfgp, data = read_config()
    if not os.path.isdir(os.path.dirname(cfgp)):
        return True, "Claude 데스크톱 없음(점검 안 함)"      # Claude 를 안 쓰는 PC 는 정상
    if data is None:
        return False, "설정 파일을 읽지 못함"
    servers = data.get("mcpServers") or {}
    bad = [f"{n}: 안 쓰는 서버가 남아 있음" for n in RETIRED if n in servers]
    _sq = servers.get("sqlcl")
    if isinstance(_sq, dict) and isinstance(_sq.get("env"), dict):
        _t = (_sq["env"].get("TNS_ADMIN") or "").strip()
        if _t and not os.path.isfile(os.path.join(_t, "tnsnames.ora")):
            bad.append(f"sqlcl: TNS_ADMIN 이 없는 폴더 → {_t}")
    for name, script in SERVERS:
        if not os.path.isfile(script):
            continue                                    # 이 폴더에 없는 기능은 등록 대상이 아니다
        ent = servers.get(name)
        if not ent:
            bad.append(f"{name}: 등록 안 됨"); continue
        args = ent.get("args") or []
        if not args or os.path.abspath(args[0]) != os.path.abspath(script):
            bad.append(f"{name}: 옛 경로 → {args[0] if args else '(없음)'}"); continue
        if not can_import_mcp(ent.get("command")):
            bad.append(f"{name}: 그 파이썬에 mcp 없음 → {ent.get('command')}")
    return (not bad), ("정상" if not bad else " / ".join(bad))


def check_and_repair(verbose=False):
    """어긋나 있으면 조용히 고친다. CKP.bat 을 쓸 때마다 자동으로 불린다.
    오늘 하루를 통째로 날린 원인(폴더 이동 → 옛 경로 잔존, 파이썬 교체 → mcp 없음)이
    바로 이 두 가지라, 사람이 눈치채기 전에 프로그램이 먼저 맞춰 놓는다.
    반환: (고쳤는가, 사유)"""
    ok, why = diagnose()
    if ok:
        if verbose: print(f" [연결] {why}")
        return False, why
    print(f" [연결] Claude 설정이 어긋나 있어 고칩니다 — {why}")
    buf = io.StringIO()
    try:
        import contextlib
        with contextlib.redirect_stdout(buf):
            rc = main(quiet=True)
    except Exception as e:
        print(f" [연결] 자동 복구 실패: {e}")
        print("        CKP.bat 의 4 번을 직접 실행해 보세요.")
        return False, why
    if rc == 0:
        print(" [연결] 고쳤습니다. Claude 를 완전히 종료했다 다시 켜면 붙습니다.")
    else:
        print(" [연결] 자동으로 고치지 못했습니다. 아래를 보세요.")
        for ln in buf.getvalue().splitlines():
            if ln.strip().startswith(("❌", "⚠")) or "pip install" in ln:
                print("        " + ln.strip())
    return (rc == 0), why


def main(quiet=False):
    if quiet:
        print(" [연결] Claude 설정이 옛 경로를 가리키고 있어 지금 위치로 고칩니다...")
    else:
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
        print("    (Claude 없이 CKP.bat 의 1 번만 써도 리포트는 똑같이 나옵니다.)")
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
    before = json.dumps([servers.get(n) for n, _ in SERVERS] + [servers.get(n) for n in RETIRED]
                        + [servers.get("sqlcl")], ensure_ascii=False)
    for name in RETIRED:
        if servers.pop(name, None) is not None:
            print(f" 정리     : {name} 등록을 지웠습니다(더 이상 쓰지 않는 기능)")
    fixed_tns = fix_sqlcl_tns(servers)

    py = pick_python((servers.get("ckp-reports") or {}).get("command"))
    if not py:
        print()
        print(" ❌ mcp 가 깔린 파이썬을 못 찾았습니다. 설정은 건드리지 않았습니다.")
        print("    이 프로젝트 안의 가상환경을 먼저 확인해 보세요:")
        for v in project_venvs():
            print(f"      {v}")
        print("    아무것도 없으면 쓰던 가상환경에 한 번만 넣으면 됩니다:")
        print('      <그 가상환경>/bin/python -m pip install mcp')
        return 1

    wrote = []
    for name, script in SERVERS:
        if not os.path.isfile(script):
            continue
        servers[name] = {
            "command": py,
            "args": [script],
            "cwd": os.path.dirname(script),
            "env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        }
        wrote.append((name, script))
    after = json.dumps([servers.get(n) for n, _ in SERVERS] + [servers.get(n) for n in RETIRED]
                       + [servers.get("sqlcl")], ensure_ascii=False)

    os.makedirs(os.path.dirname(cfgp), exist_ok=True)
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    line("-")
    if before == after:
        print(" 이미 이 폴더로 연결돼 있었습니다. 바뀐 것 없음.")
    else:
        print(" 연결했습니다.")
        print(f"   python : {py}")
        for name, script in wrote:
            print(f"   {name:17s}: {script}")
    line("-")
    # 여기서 한 번 실제로 띄워 본다. Claude 는 서버가 죽어도 이유를 안 알려 준다.
    try:
        import subprocess
        r = subprocess.run([py, MCP], cwd=PKG, capture_output=True, timeout=5,
                           input=b"", env={**os.environ, "PYTHONUTF8": "1"})
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        err = ""            # 5초를 버텼다 = 정상적으로 대기 중
    except Exception as e:
        err = str(e)
    if err and "Traceback" in err:
        print(" ⚠ 서버를 띄워 봤더니 오류가 납니다 — 아래를 먼저 해결해야 합니다.")
        print("   " + err.strip().splitlines()[-1])
        print(f'   보통은:  "{py}" -m pip install mcp')
        line("-")
    else:
        print(" 서버 시험 기동: 정상")
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
