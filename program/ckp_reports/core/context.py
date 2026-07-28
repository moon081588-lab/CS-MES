#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실행 맥락(Ctx) — 한 번의 생성에서 모든 리포트가 공유하는 날짜창·버킷·설정·경로.
원본 make_all.py main() 의 날짜/버킷 계산과 CSV 리더 헬퍼를 그대로 이동."""
import os, io, csv, datetime

from core import build_bydate            # by-date 버킷(부족분창)
from core import market_engine as ME     # market 버킷·설정

# by-date 부족분창 폭(원본 BAL_MAX_BEFORE, BAL_MAX_AFTER)
BAL_MAX_BEFORE, BAL_MAX_AFTER = 10, 7


def ymd(d):
    return d.strftime("%Y%m%d")


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def working_days(end, n):
    out = []; d = end
    while len(out) < n:
        if d.weekday() != 6:      # 일요일 제외
            out.append(d)
        d -= datetime.timedelta(days=1)
    return sorted(out)


def read_om_rows(csvp):
    rows = []
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d = {(k or "").strip().upper(): v for k, v in d.items()}
        rows.append(((d.get("WCG") or " "), d.get("PLANT_CD"), d.get("ITEM_CLASS"), d.get("FA_WC_CD"),
                     (d.get("MODEL") or " "), (d.get("GEN") or " "), d.get("STYLE_CD"),
                     str(d.get("FA_DATE") or ""), _int(d.get("QTY")), d.get("COLOR")))
    return rows


def read_scan_map(csvp):
    m = {}
    for d in csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())):
        d = {(k or "").strip().upper(): v for k, v in d.items()}
        m[(d.get("PLANT_CD"), d.get("FA_WC_CD"), d.get("STYLE_CD"))] = _int(d.get("Q"))
    return m


class Ctx:
    """생성 1회의 공유 맥락. reports/*.py 가 이 값들만 보고 SQL·빌드를 구성한다."""
    def __init__(self, date, outdir, sqldir, src, cfg):
        self.date = date
        self.today = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.OUTDIR = outdir
        self.SQLDIR = sqldir
        self.src = src            # No.2 존 양식 템플릿 워크북 경로
        self.cfg = cfg            # market_engine.load_config 결과

        # by-date 부족분창 (원본 BD.build_buckets(today, 10, 7))
        bal_b = build_bydate.build_buckets(self.today, BAL_MAX_BEFORE, BAL_MAX_AFTER)
        self.d_from, self.d_to = bal_b[0][1], bal_b[-1][1]

        # market(No.5) 버킷·창 (원본 BO.build_buckets(today, window_before, window_after))
        self.om_buckets = ME.build_buckets(
            self.today,
            cfg.getint("report", "window_before", fallback=3),
            cfg.getint("report", "window_after", fallback=7))
        self.om_from = min(b[1] for b in self.om_buckets)
        self.om_to = max(b[1] for b in self.om_buckets)

        # No.1 스캔 대상일(영업일 6개), No.6 OS&D 창(today-14..today)
        self.scan_dates = [ymd(d) for d in working_days(self.today, 6)]
        self.osnd_from = ymd(self.today - datetime.timedelta(days=14))
        self.osnd_to = ymd(self.today)

    def out(self, n, name):
        return os.path.join(self.OUTDIR, f"{n}) {name}.xlsx")

    def csv(self, name):
        return os.path.join(self.SQLDIR, name)
