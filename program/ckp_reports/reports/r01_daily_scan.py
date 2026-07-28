# No.1 DAILY REPORT SCAN — PHH 파일론 스캔을 날짜별 피벗
from core import sql as BS, db
ID = "1"; NAME = "1. DAILY REPORT SCAN"

def plan(ctx):
    return [("no1.csv", BS.scan_daily_sql(ctx.scan_dates))]

def build(ctx):
    dd = ",".join(f"{d[4:6]}/{d[6:8]}" for d in ctx.scan_dates)
    db.run_builder("build_daily_scan.py", ctx.out(ID, NAME), ctx.csv("no1.csv"),
                   f"DAILY REPORT SCAN AUTO PHYLON - {ctx.date}", dd)
