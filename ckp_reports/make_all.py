#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — 공식 11개 리포트 한 번에 생성
==================================================
실행 모드 3가지 (환경에 맞게):

  1) 기본(SQLcl 직접)   python make_all.py 2026-07-07
       저장된 SQLcl 연결(기본 changshinincaipoc)로 SQL 실행 → CSV → 빌더.
       Mac/서버처럼 `sql`(SQLcl) 이 있는 곳에서 한 줄로 완결.

  2) Claude Desktop용   python make_all.py 2026-07-07 --plan
       SQL만 sql/noN.sql 로 뽑아둔다. Claude 가 sqlcl MCP 로 실행해 sql/noN.csv 저장.
                        python make_all.py 2026-07-07 --build
       DB 없이 sql/noN.csv 만 읽어 엑셀 11개 생성. (Claude 가 조회 → 스크립트가 엑셀)

  3) 옵션  --src "CKP Manual Report (종합).xlsx 경로"   --conn <SQLcl 연결명>

양식 원칙: 사이즈·날짜(D-offset) 컬럼은 원본 고정 구조로 항상 렌더 → 데이터 0행이어도 열이 안 사라짐.
결과: report/CKP_official/ 에 "NO) 리포트명.xlsx" 11개.
"""
import os, sys, csv, io, re, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BOM_DIR = os.path.join(HERE, "..", "balance_outgoing_mailer")
sys.path.insert(0, HERE); sys.path.insert(0, BOM_DIR)
import balance_sql as BS
import balance_bydate as BD
import balance_outgoing_mailer as BO

# Windows 에서 stdout 이 파일/파이프면 ANSI 코드페이지로 인코딩되어 한글·기호 출력이
# UnicodeEncodeError 로 죽는다. 진입점에서 한 번 UTF-8 로 고정한다.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
SQLDIR = os.path.join(HERE, "sql")
def _find_sqlcl():
    """SQLcl 실행파일. env SQLCL 우선. Windows 는 sql.exe / sql.bat / sql.cmd 를 PATH 에서 찾는다."""
    import shutil
    v = os.environ.get("SQLCL")
    if v: return v
    names = ["sql.exe", "sql.bat", "sql.cmd", "sql"] if os.name == "nt" else ["sql"]
    for n in names:
        p = shutil.which(n)
        if p: return p
    return "sql"   # 못 찾으면 그대로 시도 → 실패 시 아래에서 안내 메시지

SQLCL = _find_sqlcl()
# 지갑(TNS_ADMIN)·자바(JAVA_HOME): 환경변수 우선. 없으면 main()에서 config.ini [db] wallet_dir 로 보완.
# (Claude Desktop 경로에서는 config env 로 주입됨. 터미널 경로에서는 export 하거나 config wallet_dir 사용.)
TNS_ADMIN = os.environ.get("TNS_ADMIN") or None
JAVA_HOME = os.environ.get("JAVA_HOME") or None
# No.2 원본 워크북(존 양식 템플릿): 우선순위  --src  >  env CKP_SRC  >  config [report] src_workbook  >  후보경로
DEFAULT_SRC = os.environ.get("CKP_SRC", "")
_SRC_CANDIDATES = [
    os.path.join(HERE, "..", "CKP Manual Report (종합).xlsx"),
    os.path.join(HERE, "..", "report", "CKP Manual Report (종합).xlsx"),
]
def _find_src():
    for c in _SRC_CANDIDATES:
        if os.path.exists(c): return c
    return ""

BAL_SIZE = {  # no → (모드, 파일명, 시트명)
    "3":  ("ip", "3-2. Balance IP Prod. by size",    "IP Prod by size"),
    "4":  ("ip", "3-2. Balance IP Outgoing by size", "IP Outgoing by size"),
    "11": ("ph", "3-2. Balance PH in Market PH by",  "PH in Market by size"),
}
BAL_DATE = {  # no → (before, after, 타이틀, KET, 파일명, 시트명)  ※ 원본 D-offset 범위
    "7":  (6,  7, "BALANCE CMP",          False, "3-1. Balance CMP",          "CMP"),
    "8":  (10, 7, "BALANCE OUTGOING PH",  True,  "3-1. Balance Outgoing PH",  "Outgoing PH"),
    "9":  (7,  7, "BALANCE PHYLON PRESS", True,  "3-1. Balance PH before UV", "PH before UV"),
    "10": (10, 7, "BALANCE IN MARKET",    True,  "3-1. Balance PH after UV",  "PH after UV"),
}
BAL_MAX_BEFORE, BAL_MAX_AFTER = 10, 7

def ymd(d): return d.strftime("%Y%m%d")
def _int(v):
    try: return int(float(v))
    except (TypeError, ValueError): return 0

def working_days(end, n):
    out=[]; d=end
    while len(out) < n:
        if d.weekday() != 6: out.append(d)
        d -= datetime.timedelta(days=1)
    return sorted(out)

def _sqlcl_env():
    env = dict(os.environ)
    if TNS_ADMIN: env["TNS_ADMIN"] = TNS_ADMIN
    if JAVA_HOME:
        env["JAVA_HOME"] = JAVA_HOME
        env["PATH"] = os.path.join(JAVA_HOME, "bin") + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    return env

def _sqlcl_run(script):
    try:
        # encoding 을 반드시 지정한다. 지정하지 않으면 Windows 에서 로캘 인코딩(cp949 등)으로
        # 디코드해 한글 모델명·색상값에서 UnicodeDecodeError 가 나거나 글자가 깨진다.
        return subprocess.run([SQLCL, "-S", "/nolog"], input=script, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=_sqlcl_env(),
                              shell=(os.name == "nt" and SQLCL.lower().endswith((".bat", ".cmd"))))
    except FileNotFoundError:
        raise RuntimeError(
            f"SQLcl 실행파일을 찾을 수 없습니다 (시도: {SQLCL}).\n"
            "  · SQLcl 설치 후 bin 폴더를 PATH 에 추가하거나,\n"
            "  · 환경변수 SQLCL 에 실행파일 전체 경로를 지정하세요.\n"
            "    (Windows 예: setx SQLCL \"C:\\sqlcl\\bin\\sql.exe\")")

_CONN_CACHE = {"name": None}

def resolve_conn(prefer=""):
    """SQLcl 저장 연결 이름을 결정한다. 이름을 코드에 박지 않는다.
      우선순위: --conn / env CKP_CONN / config [db] sqlcl_conn  >  등록된 연결 목록에서 패턴 매칭
      매칭 우선순위: changshinincaipoc > *changshinincaipoc* > 접속문자열 일치 > *_medium > csi*
      제외: lmes 계열(다른 레거시 DB — OCI 테이블 없음)
    """
    if _CONN_CACHE["name"]: return _CONN_CACHE["name"]
    if prefer:
        _CONN_CACHE["name"] = prefer
        return prefer
    listing = ""
    for cmd in ("connmgr list", "show connections"):
        try:
            r = _sqlcl_run(cmd + "\nexit\n")
            if r.returncode == 0 and r.stdout.strip():
                listing = r.stdout
                break
        except Exception:
            break
    rows = []          # (연결이름, 그 줄 전체) — 접속문자열이 같은 줄에 오는 표 형식도 매칭되도록
    HEADERS = ("sql>", "name", "user", "username", "connection", "connections", "connmgr")
    for l in listing.splitlines():
        # SQLcl 은 연결 목록을 트리(│ ├ └ ─)로 그린다. 앞쪽 장식 문자를 걷어낸 뒤 토큰을 뽑는다.
        s2 = re.sub(r"^[\s\u2500-\u257F|`+*\-]+", "", l).strip()
        if "lmes" in l.lower():
            continue
        for tok in s2.split():
            t = tok.strip('"').strip("'").strip(",")
            if not re.fullmatch(r"[A-Za-z0-9_.\-]+", t or ""):   # 장식·기호 토큰은 이름이 아니다
                continue
            if t.lower() in HEADERS:
                break
            rows.append((t, l.lower()))
            break
    names = [t for t, _ in rows]
    def pick(pred):
        for t, line in rows:
            if pred(t.lower(), line): return t
        return None
    # csi* 보다 *_medium 을 먼저 본다. csi 계열에는 비밀번호가 저장되지 않은 연결
    # (csi_ok / csi)이 섞여 있어 먼저 고르면 비대화형 실행이 조용히 실패한다.
    chosen = (pick(lambda t, l: t == "changshinincaipoc")
              or pick(lambda t, l: "changshinincaipoc" in t)
              or pick(lambda t, l: "changshinincaipoc" in l)      # 이름은 달라도 접속문자열이 맞는 경우
              or pick(lambda t, l: t.endswith(("_medium", "_high", "_low")))
              or pick(lambda t, l: t.startswith("csi")))
    chosen = chosen or "changshinincaipoc"     # 목록을 못 읽으면 표준 이름으로 시도
    if names:
        print(f"[conn] 사용할 SQLcl 연결: {chosen}  (후보 {len(names)}개 중 선택)")
    _CONN_CACHE["name"] = chosen
    return chosen

def sqlcl_csv(sql, out_csv, conn):
    conn = resolve_conn(conn)
    script = (f"connect -name {conn}\nset sqlformat csv\nset feedback off\nset pagesize 0\nset echo off\n"
              + sql.rstrip().rstrip(";") + ";\nexit\n")
    p = _sqlcl_run(script)
    rows=[]; started=False
    for l in p.stdout.splitlines():
        if "ORA-" in l or l.strip().startswith("Error"):
            raise RuntimeError(f"[{os.path.basename(out_csv)}] SQL 오류: {l.strip()}")
        if not started:
            if l.lstrip().startswith('"'): started=True
            else: continue
        if l.strip()=="" or "rows selected" in l: continue
        rows.append(l)
    if not rows: raise RuntimeError(f"[{os.path.basename(out_csv)}] 파싱 실패. stderr={p.stderr[:200]}")
    with open(out_csv,"w",encoding="utf-8") as f: f.write("\n".join(rows)+"\n")
    return len(rows)-1

def fetch(sql, csvp, conn, mode):
    """mode: sqlcl(직접실행) | plan(SQL만 저장) | build(기존 CSV 사용)

    어느 모드든 실행한 SQL 을 CSV 옆에 .sql 로 남긴다. 예전에는 plan 모드에서만 써서
    sql/*.sql 이 며칠 묵은 잔재로 남았고, 그걸 '오늘 실행된 쿼리'로 오해해 없는 버그를
    쫓는 사고가 있었다(2026-07-27). 항상 덮어써서 잔재가 생기지 않게 한다."""
    try:
        with open(csvp[:-4] + ".sql", "w", encoding="utf-8") as f: f.write(sql + "\n")
    except Exception:
        pass
    if mode == "plan":
        return -1
    if mode == "build":
        if not os.path.exists(csvp):
            raise RuntimeError(f"CSV 없음: {csvp}\n  → --plan 으로 SQL 뽑고, sqlcl 로 실행해 이 CSV 를 만들어 주세요.")
        return sum(1 for _ in open(csvp, encoding="utf-8")) - 1
    return sqlcl_csv(sql, csvp, conn)

def run_builder(script, *args):
    subprocess.run([sys.executable, os.path.join(HERE, script), *args], check=True)

def _read_om_rows(csvp):
    rows=[]
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d={(k or "").strip().upper(): v for k,v in d.items()}
        rows.append(((d.get("WCG") or " "), d.get("PLANT_CD"), d.get("ITEM_CLASS"), d.get("FA_WC_CD"),
                     (d.get("MODEL") or " "), (d.get("GEN") or " "), d.get("STYLE_CD"),
                     str(d.get("FA_DATE") or ""), _int(d.get("QTY")), d.get("COLOR")))
    return rows

def _read_scan_map(csvp):
    m={}
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d={(k or "").strip().upper(): v for k,v in d.items()}
        m[(d.get("PLANT_CD"), d.get("FA_WC_CD"), d.get("STYLE_CD"))] = _int(d.get("Q"))
    return m

def main():
    a=list(sys.argv[1:]); src=DEFAULT_SRC; conn=os.environ.get("CKP_CONN","").strip(); mode="sqlcl"
    if "--src" in a:   i=a.index("--src");   src=a[i+1];  del a[i:i+2]
    if "--conn" in a:  i=a.index("--conn");  conn=a[i+1]; del a[i:i+2]
    if "--plan" in a:  mode="plan";  a.remove("--plan")
    if "--build" in a: mode="build"; a.remove("--build")
    date = a[0] if a else BO.site_today().isoformat()   # 실행 PC 가 아니라 현장 기준
    today = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    os.makedirs(OUTDIR, exist_ok=True); os.makedirs(SQLDIR, exist_ok=True)
    out = lambda n, name: os.path.join(OUTDIR, f"{n}) {name}.xlsx")
    BUILD = (mode != "plan")

    cfg = BO.load_config(os.path.join(BOM_DIR, "config.ini"))
    # 이식성: TNS_ADMIN 미설정이면 config 의 지갑 폴더로, 원본 워크북 미지정이면 config/후보로 보완
    global TNS_ADMIN
    if not TNS_ADMIN: TNS_ADMIN = BO.wallet_dir(cfg) or None      # config 비어 있으면 mailer 폴더의 wallet/ 자동
    if not conn: conn = cfg.get("db", "sqlcl_conn", fallback="").strip()
    # 공장 코드를 코드에 박아두면 다른 공장·법인 PC 에서 에러 없이 0행 리포트가 나온다.
    BS.PLANT = (cfg.get("report", "plant", fallback="") or "").strip() or BS.PLANT
    print(f"[plant] 대상 공장: {BS.PLANT}")
    if not src: src = cfg.get("report", "src_workbook", fallback="").strip() or _find_src()
    if src and not os.path.exists(src):
        print(f"[주의] src_workbook 경로가 존재하지 않습니다 → 후보경로로 대체 시도: {src}")
        src = _find_src()
    bal_b = BD.build_buckets(today, BAL_MAX_BEFORE, BAL_MAX_AFTER)
    d_from, d_to = bal_b[0][1], bal_b[-1][1]
    om_buckets = BO.build_buckets(today, cfg.getint("report","window_before",fallback=3),
                                        cfg.getint("report","window_after",fallback=7))
    om_from = min(b[1] for b in om_buckets); om_to = max(b[1] for b in om_buckets)
    scan_dates = [ymd(d) for d in working_days(today, 6)]
    osnd_from = ymd(today - datetime.timedelta(days=14)); osnd_to = ymd(today)
    print(f"=== CKP 11개 [{mode}] {date} 부족분창 {d_from}~{d_to} → {OUTDIR}")

    for no,(m,fname,sheet) in BAL_SIZE.items():
        _, sql = BS.build(no, d_from, d_to)
        c=os.path.join(SQLDIR,f"no{no}.csv"); n=fetch(sql,c,conn,mode)
        if BUILD:
            if m=="ph": run_builder("bysize_v2.py","ph",out(no,fname),sheet,c,"BALANCE IN MARKET")
            else:       run_builder("bysize_v2.py","ip",out(no,fname),sheet,c)
            print(f"  No.{no} {fname}: {n}행")

    for no,(bef,aft,title,ket,fname,sheet) in BAL_DATE.items():
        _, sql = BS.build(no, d_from, d_to)
        c=os.path.join(SQLDIR,f"no{no}.csv"); n=fetch(sql,c,conn,mode)
        if BUILD:
            args=["balance_bydate.py", out(no,fname), f"{sheet}={c}",
                  "--date",date,"--before",str(bef),"--after",str(aft),"--title",title]
            if ket: args.append("--ket")
            run_builder(*args); print(f"  No.{no} {fname}: {n}행 (날짜열 {bef+1+aft})")

    c1=os.path.join(SQLDIR,"no1.csv"); n1=fetch(BS.scan_daily_sql(scan_dates),c1,conn,mode)
    if BUILD:
        dd=",".join(f"{d[4:6]}/{d[6:8]}" for d in scan_dates)
        run_builder("daily_scan.py", out("1","1. DAILY REPORT SCAN"), c1, f"DAILY REPORT SCAN AUTO PHYLON - {date}", dd)
        print(f"  No.1 DAILY REPORT SCAN: {n1}행")

    c6=os.path.join(SQLDIR,"no6.csv"); n6=fetch(BS.osnd_balance_sql(osnd_from,osnd_to),c6,conn,mode)
    if BUILD:
        run_builder("osnd_pivot.py", out("6","3-4. Balance External OS&D IPPH"), "External OS&D", c6)
        print(f"  No.6 External OS&D IPPH: {n6}행")

    plants=[x.strip() for x in cfg.get("report","plants").split(",") if x.strip()]
    scp=os.path.join(SQLDIR,"no5_scan.csv"); fetch(BS.outgoing_market_scan_sql(plants,om_from,om_to),scp,conn,mode)
    shps={}
    for name,fams in BO.SHEETS:
        p=os.path.join(SQLDIR,f"no5_{name}.csv"); fetch(BS.outgoing_market_sheet_sql(fams,plants,om_from,om_to),p,conn,mode); shps[name]=p
    if BUILD:
        sm=_read_scan_map(scp)
        data={name: BO.pivot(_read_om_rows(shps[name]), om_buckets, sm) for name,_ in BO.SHEETS}
        BO.build_workbook(data, om_buckets, today, date).save(out("5","3-3. Balance IP Outgoing Market"))
        print("  No.5 IP Outgoing Market")
        run_builder("no2_zone.py", out("2","3-1. Balance IP Production"), src)
        print("  No.2 IP Production(zone)")
        print("완료: 11개 →", OUTDIR)
    else:
        print(f"SQL 저장 완료 → {SQLDIR}/no*.sql  (sqlcl 로 실행해 no*.csv 를 만든 뒤 --build)")

if __name__ == "__main__":
    main()
