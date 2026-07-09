#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — 공식 11개 리포트 한 번에 생성 (SQLcl 저장연결 사용)
======================================================================
사용:  python make_all.py [YYYY-MM-DD] [--src "CKP Manual Report (종합).xlsx 경로"] [--conn 이름]
  예:  python make_all.py 2026-07-07

핵심: Oracle 직접연결(oracledb/Instant Client/월렛비번) 없이, **이미 저장된 SQLcl 연결**
      (기본 'changshinincaipoc', User=ADMIN·비번 저장됨)로 SQL을 실행한다 → 비번 입력 불필요.
      각 리포트 SQL(balance_sql.py) → SQLcl CSV → 빌더 → report/CKP_official/ "NO) 리포트명.xlsx".

전제: 이 PC에 SQLcl(`sql`)이 설치돼 있고, 'changshinincaipoc' 연결이 저장돼 있을 것(현재 환경 충족).
      No.2(존 양식)는 원본 워크북 템플릿 복사 → --src 로 원본 경로 지정(기본값 아래).
빌더: bysize_v2 / balance_bydate / osnd_pivot / daily_scan / no2_zone + balance_outgoing_mailer(No.5).
"""
import os, sys, csv, io, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BOM_DIR = os.path.join(HERE, "..", "balance_outgoing_mailer")
sys.path.insert(0, HERE); sys.path.insert(0, BOM_DIR)
import balance_sql as BS
import balance_outgoing_mailer as BO

OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
SQLDIR = os.path.join(HERE, "sql")
SQLCL = os.environ.get("SQLCL", "sql")
DEFAULT_SRC = "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (공유)/Google Drive Files/현업 Report Sample/CKP Manual Report (종합).xlsx"

BAL = {  # (빌더, 모드, 파일명, 시트명)
    "3":  ("bysize_v2.py",      "ip", "3-2. Balance IP Prod. by size",   "IP Prod by size"),
    "4":  ("bysize_v2.py",      "ip", "3-2. Balance IP Outgoing by size", "IP Outgoing by size"),
    "11": ("bysize_v2.py",      "ph", "3-2. Balance PH in Market PH by",  "PH in Market by size"),
    "7":  ("balance_bydate.py", None, "3-1. Balance CMP",                 "CMP"),
    "8":  ("balance_bydate.py", None, "3-1. Balance Outgoing PH",         "Outgoing PH"),
    "9":  ("balance_bydate.py", None, "3-1. Balance PH before UV",        "PH before UV"),
    "10": ("balance_bydate.py", None, "3-1. Balance PH after UV",         "PH after UV"),
}

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
    """저장된 SQLcl 연결로 SQL 실행 → CSV 파일 저장. 반환 데이터행 수."""
    script = (f"connect -name {conn}\nset sqlformat csv\nset feedback off\nset pagesize 0\nset echo off\n"
              + sql.rstrip().rstrip(";") + ";\nexit\n")
    p = subprocess.run([SQLCL, "-S", "/nolog"], input=script, capture_output=True, text=True)
    lines = p.stdout.splitlines()
    rows=[]; started=False
    for l in lines:
        if "ORA-" in l or l.strip().startswith("Error"):
            raise RuntimeError(f"[{out_csv}] SQL 오류: {l.strip()} :: {p.stderr[:200]}")
        if not started:
            if l.lstrip().startswith('"'): started=True
            else: continue
        if l.strip()=="" or "rows selected" in l: continue
        rows.append(l)
    if not rows:
        raise RuntimeError(f"[{out_csv}] 결과 없음/파싱 실패. stderr={p.stderr[:200]} stdout앞={p.stdout[:200]}")
    with open(out_csv, "w", encoding="utf-8") as f: f.write("\n".join(rows) + "\n")
    return len(rows) - 1

def run_builder(script, *args):
    subprocess.run([sys.executable, os.path.join(HERE, script), *args], check=True)

def _read_om_rows(csvp):
    rows=[]
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d={(k or "").strip().upper(): v for k, v in d.items()}
        rows.append(((d.get("WCG") or " "), d.get("PLANT_CD"), d.get("ITEM_CLASS"), d.get("FA_WC_CD"),
                     (d.get("MODEL") or " "), (d.get("GEN") or " "), d.get("STYLE_CD"),
                     str(d.get("FA_DATE") or ""), _int(d.get("QTY")), d.get("COLOR")))
    return rows

def _read_scan_map(csvp):
    m={}
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d={(k or "").strip().upper(): v for k, v in d.items()}
        m[(d.get("PLANT_CD"), d.get("FA_WC_CD"), d.get("STYLE_CD"))] = _int(d.get("Q"))
    return m

def main():
    args=list(sys.argv[1:]); src=DEFAULT_SRC; conn="changshinincaipoc"
    if "--src" in args:  i=args.index("--src");  src=args[i+1];  del args[i:i+2]
    if "--conn" in args: i=args.index("--conn"); conn=args[i+1]; del args[i:i+2]
    date = args[0] if args else datetime.date.today().isoformat()
    today = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    os.makedirs(OUTDIR, exist_ok=True); os.makedirs(SQLDIR, exist_ok=True)
    out = lambda n, name: os.path.join(OUTDIR, f"{n}) {name}.xlsx")

    cfg = BO.load_config(os.path.join(BOM_DIR, "config.ini"))
    before=cfg.getint("report","window_before",fallback=3); after=cfg.getint("report","window_after",fallback=7)
    buckets = BO.build_buckets(today, before, after)
    d_from = min(b[1] for b in buckets); d_to = max(b[1] for b in buckets)
    scan_dates = [ymd(d) for d in working_days(today, 6)]
    osnd_from = ymd(today - datetime.timedelta(days=14)); osnd_to = ymd(today)
    print(f"=== CKP 11개 생성 {date} (conn={conn}) 창(부족분) {d_from}~{d_to} → {OUTDIR}")

    # No.3/4/11/7/8/9/10
    for no, (script, mode, fname, sheet) in BAL.items():
        _, sql = BS.build(no, d_from, d_to)
        csvp = os.path.join(SQLDIR, f"no{no}.csv"); n = sqlcl_csv(sql, csvp, conn)
        if script == "bysize_v2.py":
            if mode == "ph": run_builder(script, "ph", out(no, fname), sheet, csvp, "BALANCE IN MARKET")
            else:            run_builder(script, "ip", out(no, fname), sheet, csvp)
        else:
            run_builder(script, out(no, fname), f"{sheet}={csvp}")
        print(f"  No.{no} {fname}: {n}행")

    # No.1 DAILY REPORT SCAN
    c1 = os.path.join(SQLDIR, "no1.csv"); n1 = sqlcl_csv(BS.scan_daily_sql(scan_dates), c1, conn)
    dd = ",".join(f"{d[4:6]}/{d[6:8]}" for d in scan_dates)
    run_builder("daily_scan.py", out("1", "1. DAILY REPORT SCAN"), c1, f"DAILY REPORT SCAN AUTO PHYLON - {date}", dd)
    print(f"  No.1 DAILY REPORT SCAN: {n1}행")

    # No.6 External OS&D
    c6 = os.path.join(SQLDIR, "no6.csv"); n6 = sqlcl_csv(BS.osnd_balance_sql(osnd_from, osnd_to), c6, conn)
    run_builder("osnd_pivot.py", out("6", "3-4. Balance External OS&D IPPH"), "External OS&D", c6)
    print(f"  No.6 External OS&D IPPH: {n6}행")

    # No.5 Balance IP Outgoing Market
    plants=[x.strip() for x in cfg.get("report","plants").split(",") if x.strip()]
    scp = os.path.join(SQLDIR, "no5_scan.csv"); sqlcl_csv(BS.outgoing_market_scan_sql(plants, d_from, d_to), scp, conn)
    sm = _read_scan_map(scp); data={}
    for name, fams in BO.SHEETS:
        shp = os.path.join(SQLDIR, f"no5_{name}.csv"); sqlcl_csv(BS.outgoing_market_sheet_sql(fams, plants, d_from, d_to), shp, conn)
        data[name] = BO.pivot(_read_om_rows(shp), buckets, sm)
    BO.build_workbook(data, buckets, today, date).save(out("5", "3-3. Balance IP Outgoing Market"))
    print("  No.5 IP Outgoing Market")

    # No.2 존 양식 (원본 템플릿 복사, DB 불필요)
    run_builder("no2_zone.py", out("2", "3-1. Balance IP Production"), src)
    print("  No.2 IP Production(zone)")
    print("완료: 11개 →", OUTDIR)

if __name__ == "__main__":
    main()
