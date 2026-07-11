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
import os, sys, csv, io, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BOM_DIR = os.path.join(HERE, "..", "balance_outgoing_mailer")
sys.path.insert(0, HERE); sys.path.insert(0, BOM_DIR)
import balance_sql as BS
import balance_bydate as BD
import balance_outgoing_mailer as BO

OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
SQLDIR = os.path.join(HERE, "sql")
SQLCL = os.environ.get("SQLCL", "sql")
DEFAULT_SRC = "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (공유)/Google Drive Files/현업 Report Sample/CKP Manual Report (종합).xlsx"

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

def sqlcl_csv(sql, out_csv, conn):
    script = (f"connect -name {conn}\nset sqlformat csv\nset feedback off\nset pagesize 0\nset echo off\n"
              + sql.rstrip().rstrip(";") + ";\nexit\n")
    p = subprocess.run([SQLCL, "-S", "/nolog"], input=script, capture_output=True, text=True)
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
    """mode: sqlcl(직접실행) | plan(SQL만 저장) | build(기존 CSV 사용)"""
    if mode == "plan":
        with open(csvp[:-4] + ".sql", "w", encoding="utf-8") as f: f.write(sql + "\n")
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
    a=list(sys.argv[1:]); src=DEFAULT_SRC; conn="changshinincaipoc"; mode="sqlcl"
    if "--src" in a:   i=a.index("--src");   src=a[i+1];  del a[i:i+2]
    if "--conn" in a:  i=a.index("--conn");  conn=a[i+1]; del a[i:i+2]
    if "--plan" in a:  mode="plan";  a.remove("--plan")
    if "--build" in a: mode="build"; a.remove("--build")
    date = a[0] if a else datetime.date.today().isoformat()
    today = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    os.makedirs(OUTDIR, exist_ok=True); os.makedirs(SQLDIR, exist_ok=True)
    out = lambda n, name: os.path.join(OUTDIR, f"{n}) {name}.xlsx")
    BUILD = (mode != "plan")

    cfg = BO.load_config(os.path.join(BOM_DIR, "config.ini"))
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
