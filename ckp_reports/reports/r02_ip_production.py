# No.2 IP Production — 존(zone) 양식 복사 + 데이터 채우기 (Option A).
#   빌더 = build_zone_fill.py ('3-1. Balance IP Production' 시트 서식 100% 유지)
#   템플릿 = no2_template.xlsx (종합에서 No.2 시트만 추출·청소한 클린본; make_no2_template.py 로 생성)
#     └ 종합에 낀 외부링크·정의된이름(Excel 손상 원인)을 미리 제거해 둔 것. 종합 양식이 바뀌면
#        `python make_no2_template.py` 로 재생성할 것(안 하면 옛 양식으로 드리프트).
#   데이터 = ip_production_zone_sql(['II','IP'])  (routing_seq dedup, FA_PLANT JJ/RJ 2행)
#   날짜창 = 기준일(D-Day) ~ D-7 (앞으로만, D+ 열은 숨김)
#   채움: Item Class·LINE·MODEL·Style·color·날짜별 수량·PROD Total
#   빈칸(소스 미확정): PLANT·SPRAY·PAD·MCS·YIELD·Gen·TOTAL KG·REMARKS·Hasil·STOCK
import os
from core import sql as BS, db
ID = "2"; NAME = "3-1. Balance IP Production"
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "no2_template.xlsx")

def plan(ctx):
    d_from = ctx.today.strftime("%Y%m%d")   # D-Day = 기준일
    return [("no2.csv", BS.ip_production_zone_sql(d_from, ctx.d_to))]

def build(ctx):
    src = TEMPLATE if os.path.exists(TEMPLATE) else ctx.src   # 클린 템플릿 우선, 없으면 종합 폴백
    db.run_builder("build_zone_fill.py", ctx.out(ID, NAME), src, ctx.csv("no2.csv"), ctx.date)
