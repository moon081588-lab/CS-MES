# 리포트 레지스트리 — id → 리포트 모듈. 새 리포트 추가는 파일 하나 + 아래 ALL 에 한 줄.
from . import (
    r01_daily_scan, r02_ip_production, r03_ip_prod_by_size, r04_ip_outgoing_by_size,
    r05_ip_outgoing_market, r06_external_osnd, r07_cmp, r08_outgoing_ph,
    r09_ph_before_uv, r10_ph_after_uv, r11_ph_in_market,
)
ALL = [
    r01_daily_scan, r02_ip_production, r03_ip_prod_by_size, r04_ip_outgoing_by_size,
    r05_ip_outgoing_market, r06_external_osnd, r07_cmp, r08_outgoing_ph,
    r09_ph_before_uv, r10_ph_after_uv, r11_ph_in_market,
]
REGISTRY = {m.ID: m for m in ALL}
ALL_IDS = [m.ID for m in sorted(ALL, key=lambda m: int(m.ID))]

def select(ids):
    """요청 id 리스트(str) → 번호순 리포트 모듈 리스트."""
    return [REGISTRY[i] for i in sorted(set(ids), key=int) if i in REGISTRY]
