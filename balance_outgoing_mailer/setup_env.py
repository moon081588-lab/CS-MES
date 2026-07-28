#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환경 준비 헬퍼 — csmes.bat / csmes.sh 가 호출한다. 단독 실행도 가능.

    python setup_env.py                # 월렛 경로 교정 + config.ini 기본값 보강
    python setup_env.py --check        # 진단만 (파일을 고치지 않음)
    python setup_env.py --fix-claude   # Claude Desktop 설정의 경로를 '이 폴더' 기준으로 다시 씀

하는 일 (전부 '이 폴더 기준'으로만 동작 — 절대경로를 코드에 박지 않는다):
  1) wallet/sqlnet.ora 의 WALLET_LOCATION DIRECTORY 를 이 PC 의 실제 wallet 폴더로 교정
     → 다른 PC 에서 복사해 온 월렛의 ORA-12154 / ORA-28759 / ORA-29024 를 예방
  2) config.ini 에 없는 키만 기본값으로 채움 (기존 값·비밀번호는 절대 건드리지 않음)
  3) 진단 출력 — 월렛 파일, TNS 별칭, Instant Client, 파이썬 패키지
  4) --fix-claude: claude_desktop_config.json 의 command/args/TNS_ADMIN 을 현재 설치 위치로 재작성
     (MCP 규격상 절대경로만 쓸 수 있어 폴더를 옮기면 반드시 깨진다. 옮긴 뒤 이 한 줄로 복구.)
"""
import os, re, sys, json, shutil, configparser

# Windows 에서 stdout 이 파일/파이프면 ANSI 코드페이지로 인코딩되어 한글·기호 출력이
# UnicodeEncodeError 로 죽는다. 진입점에서 한 번 UTF-8 로 고정한다.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

HERE   = os.path.dirname(os.path.abspath(__file__))          # .../balance_outgoing_mailer
REPO   = os.path.abspath(os.path.join(HERE, ".."))           # 저장소 루트
WALLET = os.path.join(HERE, "wallet")
CONFIG = os.path.join(HERE, "config.ini")
WALLET_FILES = ["cwallet.sso", "ewallet.p12", "ewallet.pem", "keystore.jks",
                "truststore.jks", "ojdbc.properties", "sqlnet.ora", "tnsnames.ora"]

DEFAULTS = {
    "db":     {"user": "ADMIN", "password": "", "dsn": "changshinincaipoc_medium",
               "wallet_dir": "", "wallet_password": "", "mode": "auto",
               "oracle_client_lib": "", "sqlcl_conn": ""},
    "smtp":   {"host": "", "port": "587", "use_tls": "true", "user": "", "password": "", "from": ""},
    "report": {"plant": "3120", "plants": "3110,3120,3210", "window_before": "3", "window_after": "7",
               "recipients": "", "output_dir": "", "share_link": "", "site_timezone": "Asia/Seoul",
               "strict_outgoing": "false", "src_workbook": ""},
}


def fix_sqlnet(check=False):
    """sqlnet.ora 의 WALLET_LOCATION 을 실제 wallet 폴더로 맞춘다."""
    p = os.path.join(WALLET, "sqlnet.ora")
    if not os.path.isfile(p):
        return "없음"
    s = open(p, encoding="utf-8").read()
    m = re.search(r'DIRECTORY\s*=\s*"([^"]*)"', s)
    cur = m.group(1) if m else "(DIRECTORY 항목 없음)"
    if os.path.normpath(cur) == os.path.normpath(WALLET):
        return "정상"
    if check:
        return f"불일치 — 현재값: {cur}"
    new = re.sub(r'DIRECTORY\s*=\s*"[^"]*"', 'DIRECTORY="%s"' % WALLET.replace("\\", "\\\\"), s)
    open(p, "w", encoding="utf-8").write(new)
    return f"교정함 ({cur} → {WALLET})"


def fix_config(check=False):
    """없는 키만 채운다. 기존 값은 절대 덮어쓰지 않는다."""
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(CONFIG, encoding="utf-8")
    added = []
    for sec, kv in DEFAULTS.items():
        if not cp.has_section(sec):
            cp.add_section(sec); added.append(f"[{sec}]")
        for k, v in kv.items():
            if not cp.has_option(sec, k):
                cp.set(sec, k, v); added.append(f"{sec}.{k}")
    # wallet_dir 은 항상 비워 둔다 — 코드가 이 폴더의 wallet/ 을 자동으로 쓴다(이식성)
    if cp.get("db", "wallet_dir", fallback="").strip():
        if not check:
            cp.set("db", "wallet_dir", "")
        added.append("db.wallet_dir(절대경로 제거)")
    # src_workbook 이 사라진 경로를 가리키면 비운다 → make_all 이 후보경로에서 다시 찾는다
    wb = cp.get("report", "src_workbook", fallback="").strip()
    if wb and not os.path.exists(wb):
        if not check:
            cp.set("report", "src_workbook", "")
        added.append("report.src_workbook(없는 경로 제거)")
    if added and not check:
        with open(CONFIG, "w", encoding="utf-8") as f:
            cp.write(f)
        try: os.chmod(CONFIG, 0o600)
        except Exception: pass
    return added


# ------------------------------------------------------------------ Claude Desktop
def claude_config_path():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude_desktop_config.json")
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def venv_python():
    """이 저장소의 가상환경 파이썬. 없으면 현재 실행 중인 파이썬."""
    cand = (os.path.join(HERE, ".venv", "Scripts", "python.exe") if os.name == "nt"
            else os.path.join(HERE, ".venv", "bin", "python"))
    return cand if os.path.exists(cand) else sys.executable


def _find_in_repo(basename):
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", "report")]
        if basename in files:
            return os.path.join(root, basename)
    return None


def fix_claude(check=False):
    """claude_desktop_config.json 의 경로를 '현재 설치 위치' 기준으로 다시 쓴다.

    바꾸는 대상은 두 종류뿐이라 다른 MCP 서버는 건드리지 않는다.
      · 이 저장소의 스크립트를 실행하는 서버 (args 의 .py 파일명이 저장소 안에 있는 경우)
      · TNS_ADMIN 환경변수를 쓰는 서버 (지갑 폴더를 이 저장소의 wallet/ 으로)
    """
    p = claude_config_path()
    if not os.path.exists(p):
        print(f" Claude 설정  : 없음 ({p})"); return []
    try:
        cfg = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(f" Claude 설정  : ❌ JSON 파싱 실패 — 건드리지 않음 ({e})"); return []

    changes = []
    for name, sv in (cfg.get("mcpServers") or {}).items():
        if not isinstance(sv, dict):
            continue
        # 1) args 안의 .py 를 저장소 안에서 다시 찾는다
        new_args = []
        touched = False
        for a in sv.get("args", []) or []:
            if isinstance(a, str) and a.endswith(".py"):
                found = _find_in_repo(os.path.basename(a))
                if found and os.path.abspath(a) != found:
                    changes.append(f"[{name}] args  {a}\n            → {found}")
                    a = found; touched = True
            new_args.append(a)
        if touched:
            if not check: sv["args"] = new_args
            vp = venv_python()
            if sv.get("command") != vp:
                changes.append(f"[{name}] command  {sv.get('command')}\n               → {vp}")
                if not check: sv["command"] = vp
        # 2) TNS_ADMIN 은 무조건 이 저장소의 지갑으로
        env = sv.get("env") or {}
        if "TNS_ADMIN" in env and os.path.normpath(env["TNS_ADMIN"]) != os.path.normpath(WALLET):
            changes.append(f"[{name}] TNS_ADMIN  {env['TNS_ADMIN']}\n                 → {WALLET}")
            if not check:
                env["TNS_ADMIN"] = WALLET; sv["env"] = env

    if changes and not check:
        shutil.copy(p, p + ".bak")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    return changes


def init_claude(check=False):
    """claude_desktop_config.json 에 이 저장소의 MCP 서버를 **새로 등록**한다.

    fix_claude() 는 '이미 있는 항목의 경로를 고치는' 함수라, 항목이 아예 없는 새 PC
    에서는 아무 일도 하지 않는다. 그런데도 진단이 '최신 ✅' 로 보였다(거짓 초록불).
    이 함수가 없는 항목을 만들어 준다. 설정 파일 자체가 없으면 새로 만든다.
    """
    p = claude_config_path()
    cfg = {}
    if os.path.exists(p):
        try:
            cfg = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            return [f"설정 파일 JSON 파싱 실패 — 손대지 않음 ({e})"]
    servers = cfg.setdefault("mcpServers", {})
    vp = venv_python()
    want = {
        "ckp-reports":      os.path.join(REPO, "ckp_reports", "ckp_mcp.py"),
        "balance-outgoing": os.path.join(HERE, "report_only_mcp.py"),
    }
    changes = []
    for name, script in want.items():
        if not os.path.exists(script):
            continue
        entry = {"command": vp, "args": [script], "env": {"TNS_ADMIN": WALLET}}
        if servers.get(name) != entry:
            changes.append(f"[{name}] {'경로 갱신' if name in servers else '신규 등록'} -> {script}")
            if not check:
                servers[name] = entry
    if changes and not check:
        d = os.path.dirname(p)
        if d: os.makedirs(d, exist_ok=True)
        if os.path.exists(p):
            shutil.copy(p, p + ".bak")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    return changes


def diagnose():
    print("=" * 60)
    print(" CS-MES 환경 점검")
    print("=" * 60)
    print(f" 저장소      : {REPO}")
    missing = [f for f in WALLET_FILES if not os.path.isfile(os.path.join(WALLET, f))]
    print(f" 월렛 폴더   : {WALLET}")
    print(f" 월렛 파일   : {'모두 존재 ✅' if not missing else '누락 ❌ → ' + ', '.join(missing)}")
    if " " in WALLET or re.search(r"[^\x00-\x7F]", WALLET):
        print("  ⚠️ 지갑 경로에 공백/한글이 있습니다. SQLcl(자바)이 ORA-17956 을 냅니다.")
        print("     저장소를 공백·한글 없는 경로로 옮기세요(예: ~/CS-MES).")
    tns = os.path.join(WALLET, "tnsnames.ora")
    if os.path.isfile(tns):
        alias = re.findall(r"^\s*([A-Za-z0-9_]+)\s*=",
                           open(tns, encoding="utf-8", errors="replace").read(), re.M)
        print(f" TNS 별칭    : {', '.join(alias[:8]) if alias else '(없음)'}")
    print(f" TNS_ADMIN   : {os.environ.get('TNS_ADMIN', '(미설정 — 코드가 wallet/ 을 자동 사용)')}")
    print(f" SQLcl       : {shutil.which('sql') or os.environ.get('SQLCL') or '❌ PATH 에 없음'}")
    try:
        import oracledb; print(f" oracledb    : {oracledb.__version__} ✅")
    except Exception as e:
        print(f" oracledb    : 없음 ❌ ({e})")
    for mod in ("openpyxl", "mcp"):
        try:
            __import__(mod); print(f" {mod:11s}: 설치됨 ✅")
        except Exception:
            print(f" {mod:11s}: 없음 ❌  → pip install {mod}")
    print(f" sqlnet.ora  : {fix_sqlnet(check=True)}")
    unreg = init_claude(check=True)
    pending = fix_claude(check=True)
    if unreg:
        print(f" Claude MCP  : ❌ 미등록/경로불일치 {len(unreg)}건 → --init-claude 실행")
        for c in unreg: print("   " + c)
    else:
        print(" Claude MCP  : 등록됨 ✅ (ckp-reports / balance-outgoing)")
    if pending:
        print(f" Claude 기타 : ❌ {len(pending)}건 불일치 → --fix-claude 실행")
        for c in pending: print("   " + c.replace("\n", "\n   "))
    print("=" * 60)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--init-claude" in args:
        ch = init_claude()
        if ch:
            print("Claude Desktop MCP 등록 (백업: claude_desktop_config.json.bak)")
            for c in ch: print("  " + c)
            print("\n→ Claude Desktop 을 완전히 종료(트레이/메뉴막대 아이콘까지)했다가 다시 켜야 반영됩니다.")
        else:
            print("Claude Desktop MCP: 이미 등록되어 있습니다 ✅")
        sys.exit(0)

    if "--fix-claude" in args:
        ch = fix_claude()
        if ch:
            print("Claude Desktop 설정 갱신 (백업: claude_desktop_config.json.bak)")
            for c in ch: print("  " + c)
            print("\n→ Claude Desktop 을 완전히 종료(⌘Q / 트레이 아이콘까지)했다가 다시 켜야 반영됩니다.")
        else:
            print("Claude Desktop 설정: 바꿀 것 없음 ✅")
        sys.exit(0)

    check = "--check" in args
    diagnose()
    if check:
        miss = fix_config(check=True)
        if miss: print(f" config.ini 보강 필요: {', '.join(miss)}")
        sys.exit(0)
    print(f" sqlnet.ora  : {fix_sqlnet()}")
    added = fix_config()
    print(f" config.ini  : {'보강함 — ' + ', '.join(added) if added else '변경 없음'}")
