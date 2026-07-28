# No.5 IP Outgoing Market — 스캔 + IP/PH/OS 시트(동·라인·일자버킷 양식). 인프로세스 빌드.
from core import sql as BS, market_engine as ME, context as C
ID = "5"; NAME = "3-3. Balance IP Outgoing Market"

def _plants(ctx):
    return [x.strip() for x in ctx.cfg.get("report", "plants").split(",") if x.strip()]

def plan(ctx):
    plants = _plants(ctx)
    strict = ctx.cfg.getboolean("report", "strict_outgoing", fallback=False)  # MOVE 정식 게이트(기본 loose)
    items = [("no5_scan.csv",  BS.outgoing_market_scan_sql(plants, ctx.om_from, ctx.om_to)),
             ("no5_dickp.csv", BS.outgoing_market_dickp_sql(plants, ctx.om_from, ctx.om_to))]  # SCAN DI CKP
    for name, fams in ME.SHEETS:
        items.append((f"no5_{name}.csv", BS.outgoing_market_sheet_sql(fams, plants, ctx.om_from, ctx.om_to, strict=strict)))
    return items

def build(ctx):
    sm = C.read_scan_map(ctx.csv("no5_scan.csv"))
    dm = C.read_scan_map(ctx.csv("no5_dickp.csv"))   # SCAN DI CKP (동일 포맷 PLANT_CD,FA_WC_CD,STYLE_CD,Q)
    data = {name: ME.pivot(C.read_om_rows(ctx.csv(f"no5_{name}.csv")), ctx.om_buckets, sm, dm)
            for name, _ in ME.SHEETS}
    ME.build_workbook(data, ctx.om_buckets, ctx.today, ctx.date).save(ctx.out(ID, NAME))
