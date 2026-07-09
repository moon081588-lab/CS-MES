#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — 공식 11개 리포트 한 번에 생성 (오케스트레이터)
==================================================================
사용:  python make_all.py [YYYY-MM-DD] [--src "CKP Manual Report (종합).xlsx 경로"]
  예:  python make_all.py 2026-07-07

동작: config.ini([db])로 Oracle 직접 연결 → 리포트별 SQL 실행 → CSV 저장 → 각 빌더 실행.
      결과는 report/CKP_official/ 에 "NO) 리포트명.xlsx" 11개로 저장.

전제:
  · balance_outgoing_mailer/config.ini 의 [db] 접속정보(thick+Instant Client 또는 thin+월렛비번) 설정.
  · No.2(존 양식)는 원본 워크북을 템플릿으로 복사 → --src 로 원본 경로 지정(기본값 아래).
SQL 출처: balance_sql.py (No.2~11 부족분·No.1 스캔·No.6 OS&D). 빌더: bysize_v2/balance_bydate/osnd_pivot/daily_scan/no2_zone + balance_outgoing_mailer(No.5).
"""
import os, sys, csv, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BOM_DIR = os.path.join(HERE, "..", "balance_outgoing_mailer")
sys.path.insert(0, HERE); sys.path.insert(0, BOM_DIR)
import balance_sql as BS
import balance_outgoing_mailer as BO

OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
SQLDIR = os.path.join(HERE, "sql")
DEFAULT_SRC = "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/연구참여 (공유)/Google Drive Files/현업 Report Sample/CKP Manual Report (종합).xlsx"

# 부족분 by-size / by-date 리포트: (빌더, 모드, 파일명, 시트명)
BAL = {
    "3":  ("bysize_v2.py",     "ip", "3-2. Balance IP Prod. by size",    "IP Prod by size"),
    "4":  ("bysize_v2.py",     "ip", "3-2. Balance IP Outgoing by size",  "IP Outgoing by size"),
    "11": ("bysize_v2.py",     "ph", "3-2. Balance PH in Market PH by",   "PH in Market by size"),
    "7":  ("balance_bydate.py", None, "3-1. Balance CMP",                 "CMP"),
    "8":  ("balance_bydate.py", None, "3-1. Balance Outgoing PH",         "Outgoing PH"),
    "9":  ("balance_bydate.py", None, "3-1. Balance PH before UV",        "PH before UV"),
    "10": ("balance_bydate.py", None, "3-1. Balance PH after UV",         "PH after UV"),
}

def ymd(d): return d.strftime("%Y%m%d")

def working_days(end, n):
    """end(포함) 이전 작업일 n개(일요일 제외), 오름차순."""
    out=[]; d=end
    while len(out) < n:
        if d.weekday() != 6: out.append(d)
        d -= datetime.timedelta(days=1)
    return sorted(out)

def run_csv(cur, sql, path):
    cur.execute(sql)
    cols=[c[0] for c in cur.description]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(cols)
        for row in cur: w.writerow(["" if v is None else v for v in row])
    return sum(1 for _ in open(path, encoding="utf-8")) - 1

def run_builder(script, *args):
    subprocess.run([sys.executable, os.path.join(HERE, script), *args], check=True)

def main():
    args=[a for a in sys.argv[1:]]
    src=DEFAULT_SRC
    if "--src" in args:
        i=args.index("--src"); src=args[i+1]; del args[i:i+2]
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

    conn = BO.db_connect(cfg); cur = conn.cursor()
    print(f"=== CKP 11개 생성 {date}  창(부족분) {d_from}~{d_to} → {OUTDIR}")

    # No.3/4/11/7/8/9/10 — balance_sql
    for no, (script, mode, fname, sheet) in BAL.items():
        _, sql = BS.build(no, d_from, d_to)
        csvp = os.path.join(SQLDIR, f"no{no}.csv"); n = run_csv(cur, sql, csvp)
        if script == "bysize_v2.py":
            if mode == "ph": run_builder(script, "ph", out(no, fname), sheet, csvp, "BALANCE IN MARKET")
            else:            run_builder(script, "ip", out(no, fname), sheet, csvp)
        else:
            run_builder(script, out(no, fname), f"{sheet}={csvp}")
        print(f"  No.{no} {fname}: {n}행")

    # No.1 — DAILY REPORT SCAN
    c1 = os.path.join(SQLDIR, "no1.csv"); run_csv(cur, BS.scan_daily_sql(scan_dates), c1)
    dd = ",".join(f"{d[4:6]}/{d[6:8]}" for d in scan_dates)
    run_builder("daily_scan.py", out("1", "1. DAILY REPORT SCAN"), c1,
                f"DAILY REPORT SCAN AUTO PHYLON - {date}", dd); print("  No.1 DAILY REPORT SCAN")

    # No.6 — External OS&D
    c6 = os.path.join(SQLDIR, "no6.csv"); run_csv(cur, BS.osnd_balance_sql(osnd_from, osnd_to), c6)
    run_builder("osnd_pivot.py", out("6", "3-4. Balance External OS&D IPPH"), "External OS&D", c6)
    print("  No.6 External OS&D IPPH")

    # No.5 — Balance IP Outgoing Market (balance_outgoing_mailer 파이프라인)
    plants = [x.strip() for x in cfg.get("report", "plants").split(",") if x.strip()]
    strict = cfg.getboolean("report", "strict_outgoing", fallback=False)
    sm = BO.fetch_scan_bembep(conn, plants, d_from, d_to)
    data = {name: BO.pivot(BO.fetch_sheet(conn, fams, plants, d_from, d_to, strict=strict), buckets, sm)
            for name, fams in BO.SHEETS}
    BO.build_workbook(data, buckets, today, date).save(out("5", "3-3. Balance IP Outgoing Market"))
    print("  No.5 IP Outgoing Market")

    cur.close(); conn.close()

    # No.2 — 존(zone) 양식 (원본 템플릿 복사, DB 불필요)
    run_builder("no2_zone.py", out("2", "3-1. Balance IP Production"), src); print("  No.2 IP Production(zone)")

    print("완료: 11개 →", OUTDIR)

if __name__ == "__main__":
    main()
