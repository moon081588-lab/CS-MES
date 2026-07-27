#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환경 준비 헬퍼 — csmes.bat / csmes.sh 가 호출한다. 단독 실행도 가능.

    python setup_env.py            # 월렛 경로 교정 + config.ini 기본값 보강
    python setup_env.py --check    # 진단만 (파일을 고치지 않음)

하는 일 (전부 '이 폴더 기준'으로만 동작 — 절대경로를 코드에 박지 않는다):
  1) wallet/sqlnet.ora 의 WALLET_LOCATION DIRECTORY 를 이 PC 의 실제 wallet 폴더로 교정
     → 다른 PC 에서 복사해 온 월렛의 ORA-12154 / ORA-28759 / ORA-29024 를 예방
  2) config.ini 에 없는 키만 기본값으로 채움 (기존 값·비밀번호는 절대 건드리지 않음)
  3) 진단 출력 — 월렛 파일 9종, TNS 별칭, Instant Client, 파이썬 패키지
"""
import os, re, sys, configparser

HERE = os.path.dirname(os.path.abspath(__file__))
WALLET = os.path.join(HERE, "wallet")
CONFIG = os.path.join(HERE, "config.ini")
WALLET_FILES = ["cwallet.sso", "ewallet.p12", "ewallet.pem", "keystore.jks",
                "truststore.jks", "ojdbc.properties", "sqlnet.ora", "tnsnames.ora"]

DEFAULTS = {
    "db":     {"user": "ADMIN", "password": "", "dsn": "changshinincaipoc_medium",
               "wallet_dir": "", "wallet_password": "", "mode": "auto",
               "oracle_client_lib": "", "sqlcl_conn": ""},
    "smtp":   {"host": "", "port": "587", "use_tls": "true", "user": "", "password": "", "from": ""},
    "report": {"plants": "3110,3120,3210", "window_before": "3", "window_after": "7",
               "recipients": "", "output_dir": "", "share_link": "",
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
    if added and not check:
        with open(CONFIG, "w", encoding="utf-8") as f:
            cp.write(f)
        try: os.chmod(CONFIG, 0o600)
        except Exception: pass
    return added


def diagnose():
    print("=" * 56)
    print(" CS-MES 환경 점검")
    print("=" * 56)
    print(f" 폴더        : {HERE}")
    missing = [f for f in WALLET_FILES if not os.path.isfile(os.path.join(WALLET, f))]
    print(f" 월렛 폴더   : {WALLET}")
    print(f" 월렛 파일   : {'모두 존재 ✅' if not missing else '누락 ❌ → ' + ', '.join(missing)}")
    tns = os.path.join(WALLET, "tnsnames.ora")
    if os.path.isfile(tns):
        alias = re.findall(r"^\s*([A-Za-z0-9_]+)\s*=", open(tns, encoding="utf-8", errors="replace").read(), re.M)
        print(f" TNS 별칭    : {', '.join(alias[:8]) if alias else '(없음)'}")
    print(f" TNS_ADMIN   : {os.environ.get('TNS_ADMIN', '(미설정 — 코드가 wallet/ 을 자동 사용)')}")
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
    print("=" * 56)


if __name__ == "__main__":
    check = "--check" in sys.argv
    diagnose()
    if check:
        miss = fix_config(check=True)
        if miss: print(f" config.ini 보강 필요: {', '.join(miss)}")
        sys.exit(0)
    print(f" sqlnet.ora  : {fix_sqlnet()}")
    added = fix_config()
    print(f" config.ini  : {'보강함 — ' + ', '.join(added) if added else '변경 없음'}")
