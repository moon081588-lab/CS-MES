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

def probe_site_offset(cfg, conn):
    """현장 타임존을 DB 에서 스스로 알아내 config.ini 에 캐시한다.

    POP_PCARD_SCAN.CREATE_DT 는 현장 벽시계로, DB 서버 시계는 UTC 로 돌아간다.
    둘의 차이가 곧 현장 UTC 오프셋인데, 복제 지연이 섞이면 낮게 나온다.
    그래서 실행할 때마다 관측해 **더 큰 값일 때만** 올린다(BO.learn_site_offset).
    [report] site_timezone 을 명시했으면 학습하지 않는다 — 사람이 지정한 값이 우선.
    """
    if cfg.get("report", "site_timezone", fallback="").strip():
        print("[tz] site_timezone 이 지정되어 있어 자동 학습을 건너뜁니다.")
        return
    csvp = os.path.join(SQLDIR, "site_tz.csv")
    try:
        fetch(BO.SITE_TZ_PROBE_SQL, csvp, conn, "sqlcl")
        row = next(csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())), {})
        row = {(k or "").strip().upper(): v for k, v in row.items()}
        diff = float(row.get("DIFF_H"))
        last = row.get("PLANT_LAST") or "?"
    except Exception as e:
        print(f"[tz] 현장 오프셋 측정 건너뜀: {str(e)[:140]}")
        return
    cur = None
    try:
        v = cfg.get("report", "site_utc_offset_hours", fallback="").strip()
        cur = float(v) if v else None
    except Exception:
        cur = None
    off, msg = BO.learn_site_offset(diff, cur)
    print(f"[tz] 현장 최신 스캔 {last} / 관측 {diff:+.2f}시간 → {msg}")
    if off is not None:
        BO.save_site_offset(off, os.path.join(BOM_DIR, "config.ini"))
        if not cfg.has_section("report"): cfg.add_section("report")
        cfg.set("report", "site_utc_offset_hours", f"{off:g}")


def check_data_health(cfg, conn, d_from, d_to, today):
    """복제 신선도 + 마감 마스터 커버리지를 점검하고, 마감필터(loose/strict)를 결정한다.

    왜 필요한가 (2026-07-28 실측):
      · OCI 는 복제본이고 실제로 07-25(토) 07:00 에 멈춰 있었다. 전 트랜잭션 테이블이
        같은 시점에서 끊겼다 = 개별 테이블이 아니라 복제 잡이 멈춘 것.
        이걸 모르고 '오늘' 리포트를 뽑으면 빈 결과를 실제 0 으로 오해한다.
      · MSPD_PROD_GROUP(마감 마스터)은 04-27 이후 갱신이 없다. 6월 실적에 등장하는
        생산그룹 381 개 중 마스터에 있는 것은 **0 개**. 그래서 GMES 정식 마감필터
        (CLOSING_YN='N' IN 절)로 바꾸면 전 리포트가 0 행이 된다.
    → 사람이 매번 판단하지 않도록, 커버리지를 재서 자동으로 고른다.
      동기화가 정상화되면 별도 작업 없이 정식 필터로 넘어간다.

    반환: (loose 여부, 경고 메시지 리스트)
    """
    mode_cfg = (cfg.get("report", "closing_filter", fallback="") or "auto").strip().lower()
    warns = []
    sql = (
        "SELECT (SELECT TO_CHAR(MAX(CREATE_DT),'YYYY-MM-DD') FROM OCI.POP_PCARD_SCAN) LAST_DATA, "
        "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
        f"WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{BS.PLANT}' AND PROD_MOVE_TYPE='PROD')) GRP_ALL, "
        "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
        f"WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{BS.PLANT}' AND PROD_MOVE_TYPE='PROD') R "
        "JOIN OCI.MSPD_PROD_GROUP M ON M.PROD_GROUP_NO=R.PROD_GROUP_NO AND M.PLANT_CD=R.PLANT_CD) GRP_IN_MASTER "
        "FROM DUAL"
    )
    try:
        csvp = os.path.join(SQLDIR, "health.csv")
        fetch(sql, csvp, conn, "sqlcl")
        row = next(csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())), {})
        row = {(k or "").strip().upper(): v for k, v in row.items()}
        last = (row.get("LAST_DATA") or "").strip()
        grp_all = int(row.get("GRP_ALL") or 0)
        grp_in = int(row.get("GRP_IN_MASTER") or 0)
    except Exception as e:
        warns.append(f"[health] 점검 실패(무시하고 진행): {str(e)[:140]}")
        return (True, warns)

    # 1) 복제 신선도
    if last:
        try:
            lastd = datetime.datetime.strptime(last, "%Y-%m-%d").date()
            days = (BO.site_today(cfg) - lastd).days
            if days >= 2:
                warns.append(f"[health] ⚠ 복제 지연 {days}일 — OCI 최신 실적일 {last}. "
                             f"최근 데이터가 필요한 리포트는 아직 비어 있을 수 있습니다.")
            else:
                print(f"[health] 복제 신선도 정상 (최신 실적일 {last})")
        except Exception:
            pass

    # 2) 마감 마스터 커버리지 → 필터 선택
    cov = (grp_in / grp_all * 100.0) if grp_all else 0.0
    if mode_cfg == "loose":
        loose = True;  why = "config 에서 loose 로 고정"
    elif mode_cfg == "strict":
        loose = False; why = "config 에서 strict 로 고정"
    else:
        loose = cov < 90.0
        why = (f"자동 판정 — 마감 마스터 커버리지 {cov:.0f}% "
               f"({grp_in}/{grp_all} 그룹)" + (" → 정식 필터 사용" if not loose else " → 임시(loose) 필터 유지"))
    print(f"[health] 마감필터: {'loose(임시)' if loose else 'strict(정식)'} — {why}")
    if loose and mode_cfg == "auto" and grp_all:
        warns.append(f"[health] ⚠ MSPD_PROD_GROUP 동기화 미완 (커버리지 {cov:.0f}%). "
                     f"동기화가 끝나면 이 판정이 자동으로 정식 필터로 바뀝니다.")
    return (loose, warns)


def main():
    a=list(sys.argv[1:]); src=DEFAULT_SRC; conn=os.environ.get("CKP_CONN","").strip(); mode="sqlcl"
    if "--src" in a:   i=a.index("--src");   src=a[i+1];  del a[i:i+2]
    if "--conn" in a:  i=a.index("--conn");  conn=a[i+1]; del a[i:i+2]
    if "--plan" in a:  mode="plan";  a.remove("--plan")
    if "--build" in a: mode="build"; a.remove("--build")
    tz_only = "--tz-probe" in a
    if tz_only: a.remove("--tz-probe")
    date_arg = a[0] if a else ""
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
    # 기준일을 우리가 정해야 할 때(=날짜 인자 없음)만 DB 에 현장 타임존을 물어본다.
    # 날짜 인자가 있어도 관측한다 — 학습이 '최댓값 누적'이라 관측이 잦을수록 정확해지고,
    # MCP 경로는 언제나 날짜를 넘기므로 여기서 막으면 영영 학습하지 못한다.
    if mode == "sqlcl":
        probe_site_offset(cfg, conn)
    if tz_only:
        print(f"[tz] 현재 기준으로 본 현장 오늘: {BO.site_today(cfg).isoformat()}")
        return
    date = date_arg or BO.site_today(cfg).isoformat()   # 실행 PC 가 아니라 현장 기준
    today = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    if not src: src = cfg.get("report", "src_workbook", fallback="").strip() or _find_src()
    if src and not os.path.exists(src):
        print(f"[주의] src_workbook 경로가 존재하지 않습니다 → 후보경로로 대체 시도: {src}")
        src = _find_src()
    bal_b = BD.build_buckets(today, BAL_MAX_BEFORE, BAL_MAX_AFTER)
    d_from, d_to = bal_b[0][1], bal_b[-1][1]
    LOOSE, HEALTH_WARNS = (True, [])
    if mode == "sqlcl":
        LOOSE, HEALTH_WARNS = check_data_health(cfg, conn, d_from, d_to, today)
        for w in HEALTH_WARNS: print(w)
    om_buckets = BO.build_buckets(today, cfg.getint("report","window_before",fallback=3),
                                        cfg.getint("report","window_after",fallback=7))
    om_from = min(b[1] for b in om_buckets); om_to = max(b[1] for b in om_buckets)
    scan_dates = [ymd(d) for d in working_days(today, 6)]
    osnd_from = ymd(today - datetime.timedelta(days=14)); osnd_to = ymd(today)
    print(f"=== CKP 11개 [{mode}] {date} 부족분창 {d_from}~{d_to} → {OUTDIR}")

    for no,(m,fname,sheet) in BAL_SIZE.items():
        _, sql = BS.build(no, d_from, d_to, loose=LOOSE)
        c=os.path.join(SQLDIR,f"no{no}.csv"); n=fetch(sql,c,conn,mode)
        if BUILD:
            if m=="ph": run_builder("bysize_v2.py","ph",out(no,fname),sheet,c,"BALANCE IN MARKET")
            else:       run_builder("bysize_v2.py","ip",out(no,fname),sheet,c)
            print(f"  No.{no} {fname}: {n}행")

    for no,(bef,aft,title,ket,fname,sheet) in BAL_DATE.items():
        _, sql = BS.build(no, d_from, d_to, loose=LOOSE)
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
        for w in HEALTH_WARNS: print(w)   # 로그 끝만 보는 경우를 위해 한 번 더
    else:
        print(f"SQL 저장 완료 → {SQLDIR}/no*.sql  (sqlcl 로 실행해 no*.csv 를 만든 뒤 --build)")

if __name__ == "__main__":
    main()
