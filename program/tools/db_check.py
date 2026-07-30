#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DB 접속 점검 — CKP.bat 의 3 번이 호출한다. 리포트를 만들지 않고 연결만 확인한다.

수시로 돌려도 되도록 가볍게(질의 3개) 만들었다. 리포트가 이상할 때
'DB 문제인가 코드 문제인가' 를 먼저 가르는 용도.

  python tools\\db_check.py

확인하는 것
  1) 어느 경로로 붙는가        드라이버 직결 / SQLcl
  2) 진짜 그 DB 가 맞는가      OCI 스키마 테이블 개수
  3) 데이터가 어디까지 들어와 있나   최신 스캔일
     ※ 우리가 보는 DB 는 원장의 **복사본**이라 최근 며칠이 비어 있는 것이 정상이다.
"""
import os, sys, csv, io, json, glob, datetime, tempfile, subprocess, platform

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # program 폴더
TOP  = os.path.dirname(ROOT) if os.path.basename(ROOT).lower() == "program" else ROOT
PKG  = os.path.join(ROOT, "ckp_reports")
sys.path.insert(0, PKG)

# 화면에 찍는 것과 똑같은 내용을 파일로도 남긴다.
# 원격으로 남의 PC 를 볼 수 없을 때, 이 파일 하나만 보내면 원인을 짚을 수 있게 하려는 것.
REPORT = os.path.join(TOP, "진단서.txt")
_BUF = []
_print = print
def print(*a, **k):                       # noqa: A001
    _BUF.append(" ".join(str(x) for x in a))
    _print(*a, **k)

def line(c="="): print(c * 62)

SQL = (
    "SELECT (SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER='OCI') OCI_TABLES, "
    "TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI') KST_NOW, "
    "(SELECT MAX(SCAN_YMD) FROM OCI.POP_PCARD_SCAN) LAST_SCAN, "
    "(SELECT TO_CHAR(MAX(UPDATE_DT),'YYYY-MM-DD HH24:MI') FROM OCI.MSPD_PCARD_RESULT) LAST_SYNC "
    "FROM DUAL"
)

def _mask(v):
    """비밀번호처럼 보이는 값은 길이만 남긴다."""
    v = (v or "").strip()
    return f"(설정됨, {len(v)}자)" if v else "(비어있음)"


def _claude_config_path():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    return os.path.expanduser("~/.config/Claude/claude_desktop_config.json")


def environment_report(db=None, cfg=None):
    """이 PC 의 상태를 한 장으로 정리한다. 비밀번호는 절대 적지 않는다."""
    line("-"); print(" 이 PC 상태"); line("-")
    print(f"   OS            : {platform.platform()}")
    print(f"   파이썬        : {sys.version.split()[0]} ({sys.executable})")
    print(f"   프로그램 위치 : {TOP}")
    bad = [x for x, c in (("공백", " " in TOP),
                          ("한글 등 비ASCII", any(ord(c2) > 127 for c2 in TOP)),
                          ("클라우드 동기화", "OneDrive" in TOP or "Google Drive" in TOP)) if c]
    print(f"   경로 문제     : {' / '.join(bad) if bad else '없음'}")

    # 라이브러리
    libs = []
    for m in ("openpyxl", "oracledb", "mcp"):
        try:
            mod = __import__(m)
            libs.append(f"{m} {getattr(mod, '__version__', '?')}")
        except Exception as e:
            libs.append(f"{m} ❌({type(e).__name__})")
    print(f"   라이브러리    : {', '.join(libs)}")

    # 설정
    if cfg is not None:
        print(f"   설정 backend  : {cfg.get('db','backend',fallback='')}")
        print(f"   설정 user     : {cfg.get('db','user',fallback='') or '(비어있음)'}")
        print(f"   설정 password : {_mask(cfg.get('db','password',fallback=''))}")
        print(f"   지갑 비밀번호 : {_mask(cfg.get('db','wallet_password',fallback=''))}")
        print(f"   저장연결 이름 : {cfg.get('db','sqlcl_conn',fallback='')}")

    # 지갑
    wdir = db.wallet_dir(cfg) if db else ""
    print(f"   지갑 폴더     : {wdir or '(못 찾음)'}")
    if wdir and os.path.isdir(wdir):
        fs = sorted(f for f in os.listdir(wdir) if os.path.isfile(os.path.join(wdir, f)))
        print(f"   지갑 파일     : {len(fs)}개 — {', '.join(fs[:10])}")

    # SQLcl 실체 확인
    if db:
        print(f"   SQLcl 경로    : {db.SQLCL}")
        try:
            r = subprocess.run([db.SQLCL, "-V"], capture_output=True, text=True, timeout=60)
            first = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            print(f"   SQLcl -V      : {first[0][:90] if first else '(출력 없음)'}")
        except Exception as e:
            print(f"   SQLcl -V      : 실행 실패 — {type(e).__name__}: {str(e)[:70]}")
    print(f"   환경변수 SQLCL     : {os.environ.get('SQLCL') or '(없음)'}")
    print(f"   환경변수 TNS_ADMIN : {os.environ.get('TNS_ADMIN') or '(없음)'}")

    # Claude 설정 / MCP
    line("-"); print(" Claude 연결"); line("-")
    cp = _claude_config_path()
    print(f"   설정 파일     : {cp}")
    if not os.path.isfile(cp):
        print("   → 파일이 없습니다 (Claude 미설치이거나 아직 설정 전)")
    else:
        try:
            data = json.load(open(cp, encoding="utf-8"))
            servers = data.get("mcpServers") or {}
            print(f"   등록된 서버   : {', '.join(servers) or '(없음)'}")
            for name, ent in servers.items():
                if not isinstance(ent, dict):
                    continue
                cmd = ent.get("command", "")
                args = ent.get("args") or []
                print(f"     [{name}]")
                print(f"       command : {cmd}")
                print(f"       exists  : {os.path.exists(cmd) if cmd else False}")
                if args:
                    print(f"       args[0] : {args[0]}")
                    print(f"       exists  : {os.path.exists(args[0])}")
                env = ent.get("env") or {}
                if "TNS_ADMIN" in env:
                    t = env["TNS_ADMIN"]
                    ok = os.path.isfile(os.path.join(t, "tnsnames.ora"))
                    print(f"       TNS_ADMIN: {t}  ({'정상' if ok else '❌ 없는 폴더'})")
                if name == "ckp-reports" and cmd:
                    try:
                        r = subprocess.run([cmd, "-c", "import mcp; print(mcp.__version__)"],
                                           capture_output=True, text=True, timeout=60)
                        out = (r.stdout or "").strip() or (r.stderr or "").strip().splitlines()[-1:]
                        print(f"       mcp 확인 : {'OK ' + str(out) if r.returncode == 0 else '❌ ' + str(out)}")
                    except Exception as e:
                        print(f"       mcp 확인 : 실행 실패 — {type(e).__name__}")
        except Exception as e:
            print(f"   → 설정 파일을 읽지 못했습니다: {type(e).__name__}: {str(e)[:80]}")
            print("     (JSON 문법 오류면 모든 MCP 서버가 통째로 무시됩니다)")

    # 서버 직접 기동
    mcp_py = os.path.join(PKG, "ckp_mcp.py")
    try:
        r = subprocess.run([sys.executable, mcp_py], cwd=PKG, input=b"",
                           capture_output=True, timeout=8)
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        print(f"   서버 시험기동 : {'❌ ' + err.splitlines()[-1][:100] if 'Traceback' in err else '정상(대기)'}")
    except subprocess.TimeoutExpired:
        print("   서버 시험기동 : 정상(대기)")
    except Exception as e:
        print(f"   서버 시험기동 : 실행 실패 — {type(e).__name__}")


def main():
    line(); print(" DB 접속 점검"); line()
    try:
        from core import db
    except Exception as e:
        print(f" ❌ 코드를 불러오지 못했습니다: {e}")
        print("    CKP.bat 의 2 번(처음 설정)을 먼저 실행하세요."); return 1

    cfg = db.load_cfg()
    environment_report(db, cfg)          # 이 PC 상태 + Claude 연결 상태를 먼저 적는다
    line("-"); print(" DB 접속"); line("-")
    backend, why = db.choose_backend(cfg)
    print(f" 접속 경로 : {backend}")
    print(f"            {why}")
    wdir = db.wallet_dir(cfg)
    print(f" 지갑      : {wdir or '(없음)'}")
    if backend == "sqlcl":
        found = os.path.exists(db.SQLCL) or os.sep not in db.SQLCL
        print(f" SQLcl     : {db.SQLCL}" + ("" if os.path.exists(db.SQLCL) else "   ← PATH 에서 찾은 이름(실제 위치 미확인)"))
    if wdir and not os.path.isfile(os.path.join(wdir, "tnsnames.ora")):
        print("            ⚠ tnsnames.ora 가 없습니다.")

    # 자격증명을 따지기 전에 '길이 뚫려 있는가' 부터 본다.
    # 방화벽 문제를 계정 문제로 오해하면 현장에서 하루가 날아간다.
    dsn = cfg.get("db", "dsn", fallback="changshinincaipoc_medium").strip()
    host, port = db.dsn_endpoint(wdir, dsn)
    _pf  = (cfg.get("db", "preflight", fallback="") or "auto").strip().lower()
    _prx = cfg.get("db", "https_proxy", fallback="").strip()
    if _prx:
        print(f" 프록시    : {_prx}:{cfg.get('db','https_proxy_port',fallback='')}")
    if host and _pf != "off" and not _prx:
        ok, msg = db.preflight(host, port)
        print(f" 네트워크  : {'OK' if ok else 'X'}  {msg}")
        if ok is False:
            print()
            line("-")
            print(" ❌ DB 포트에 닿지 못했습니다. 여기서 멈춥니다.")
            print(f"    사내 방화벽/프록시에서 '{host} {port} 아웃바운드' 를 열어야 합니다.")
            print("    계정·지갑 문제가 아니므로 그쪽은 볼 필요 없습니다.")
            line("-")
            return 1
    print()

    conn = (cfg.get("db", "sqlcl_conn", fallback="") or "changshinincaipoc").strip()
    tmp = os.path.join(tempfile.gettempdir(), "ckp_dbcheck.csv")
    t0 = datetime.datetime.now()
    try:
        db.run_batch([(tmp, SQL)], conn)
    except Exception as e:
        print(" ❌ 접속 실패")
        line("-")
        print(f" {str(e)[:900]}")
        line("-")
        print(f" [원인] {db.classify(str(e), wdir, host if host else '', port if host else 0)}")
        print()
        print(" 참고 — SQLcl 을 못 찾는다는 메시지면, config.ini [db] 에")
        print("        user / password / wallet_password 를 채우면 SQLcl 없이 접속합니다.")
        print("        (CKP.bat 의 2 번을 다시 실행하면 물어봅니다)")
        return 1
    took = (datetime.datetime.now() - t0).total_seconds()

    row = next(csv.DictReader(io.StringIO(open(tmp, encoding="utf-8").read())), {})
    row = {(k or "").strip().upper(): v for k, v in row.items()}
    tables = row.get("OCI_TABLES", "?")
    last   = (row.get("LAST_SCAN") or "").strip()
    sync   = (row.get("LAST_SYNC") or "").strip()

    print(f" ✅ 접속 성공 ({took:.1f}초)")
    print(f" 현재 시각(한국) : {row.get('KST_NOW','?')}")
    print(f" OCI 테이블      : {tables}개", end="")
    try:
        print("  — 정상" if int(tables) >= 40 else "  ⚠ 너무 적습니다. 다른 DB 일 수 있습니다.")
    except ValueError:
        print()
    print()
    line("-"); print(" 데이터가 들어와 있는 범위"); line("-")
    print(f"   최신 스캔일   : {last or '?'}")
    print(f"   최종 반영시각 : {sync or '?'}")
    if last:
        try:
            d = datetime.datetime.strptime(last, "%Y%m%d").date()
            gap = (datetime.date.today() - d).days
            print(f"   오늘과의 차이 : {gap}일")
            print()
            print("   ※ 우리가 보는 DB 는 원장의 복사본입니다. 최근 며칠이 비어 있는 것은")
            print("      고장이 아니라 정상입니다. 리포트 기준일을 위 최신일 이전으로 잡으면")
            print("      데이터가 정상적으로 나옵니다.")
        except ValueError:
            pass
    print()
    return 0

def _save():
    """화면에 나온 내용을 그대로 파일로 남긴다.
    원격으로 화면을 주고받을 수 없을 때 이 파일 하나만 보내면 된다."""
    try:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write(f"CKP 진단서 — {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
            f.write("=" * 62 + "\n")
            f.write("\n".join(_BUF) + "\n")
        _print()
        _print("=" * 62)
        _print(f" 진단서를 만들었습니다 → {REPORT}")
        _print(" 문제가 있으면 이 파일을 그대로 담당자에게 보내 주세요.")
        _print(" (비밀번호는 길이만 적히고 값은 들어가지 않습니다)")
        _print("=" * 62)
    except Exception as e:
        _print(f"[진단서 저장 실패: {e}]")


if __name__ == "__main__":
    try:
        rc = main()
    except KeyboardInterrupt:
        print("\n중단했습니다."); rc = 1
    except Exception as e:
        print(f"\n[예외] {type(e).__name__}: {e}"); rc = 1
    _save()
    sys.exit(rc or 0)
