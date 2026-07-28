#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기준일 결정 + 데이터 상태 점검 — run_all 이 시작할 때 한 번 부른다.

여기 있는 두 가지는 리포트 숫자를 좌우하는데 눈에 잘 안 띄어서, 매 실행마다
스스로 재고 화면에 적도록 만들었다.

1) 기준일이 '실행 PC 의 오늘' 이면 안 된다
   같은 순간에 날짜가 셋으로 갈린다(2026-07-28 실측):
     DB 서버(UTC) 00:19 / 한국(KST) 09:19 / 현장 CKP(WIB, UTC+7) 07:19
   조직 표준은 **한국시간**. 어느 PC 에서 돌리든 같은 날짜가 나와야 한다.
   ※ DB 날짜 컬럼은 현장(WIB) 시계라, KST 00:00~01:59 두 시간만 하루 어긋난다.
     그 시간대 실행은 피할 것(기본 스케줄 08:00 은 안전).

2) 우리가 보는 DB 는 원장의 **복사본**이다
   최근 며칠이 비어 있는 것은 고장이 아니라 정상. 다만 모르고 지나가면 빈 결과를
   실제 0 으로 오해하므로 최신 데이터일을 항상 알린다.
   또 마감 마스터(MSPD_PROD_GROUP)가 동기화되지 않으면 GMES 정식 마감필터로는
   전 리포트가 0 행이 된다(2026-07-28: 6월 실적 381개 그룹 중 마스터에 0개).
   그래서 커버리지를 재서 loose/strict 를 자동으로 고른다 —
   동기화가 끝나면 설정을 건드리지 않아도 정식 필터로 넘어간다.
"""
import os, io, csv, datetime, configparser


def site_today(cfg=None, cfg_path=None):
    """리포트 기준 '오늘'. 우선순위: config [report] site_timezone > env CSMES_TZ > Asia/Seoul."""
    tz = ""
    try:
        if cfg is not None:
            tz = cfg.get("report", "site_timezone", fallback="").strip()
        elif cfg_path:
            c = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
            c.read(cfg_path, encoding="utf-8")
            tz = c.get("report", "site_timezone", fallback="").strip()
    except Exception:
        tz = ""
    tz = tz or os.environ.get("CSMES_TZ", "").strip() or "Asia/Seoul"
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz)).date()
    except Exception:
        # Windows 는 zoneinfo 에 tzdata 패키지가 필요하다. 없으면 실행 PC 날짜로 폴백.
        return datetime.date.today()


HEALTH_SQL = (
    "SELECT (SELECT TO_CHAR(MAX(CREATE_DT),'YYYY-MM-DD') FROM OCI.POP_PCARD_SCAN) LAST_DATA, "
    "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
    "WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{plant}' AND PROD_MOVE_TYPE='PROD')) GRP_ALL, "
    "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
    "WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{plant}' AND PROD_MOVE_TYPE='PROD') R "
    "JOIN OCI.MSPD_PROD_GROUP M ON M.PROD_GROUP_NO=R.PROD_GROUP_NO AND M.PLANT_CD=R.PLANT_CD) GRP_IN_MASTER "
    "FROM DUAL"
)


def check(db, cfg, conn, d_from, d_to, plant, sqldir, base_date):
    """(loose 여부, 화면에 적을 메시지들) 반환. 실패해도 리포트 생성은 막지 않는다."""
    msgs = []
    mode_cfg = (cfg.get("report", "closing_filter", fallback="") or "auto").strip().lower()
    try:
        csvp = os.path.join(sqldir, "_health.csv")
        db.run_batch([(csvp, HEALTH_SQL.format(d_from=d_from, d_to=d_to, plant=plant))], conn)
        row = next(csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())), {})
        row = {(k or "").strip().upper(): v for k, v in row.items()}
        last = (row.get("LAST_DATA") or "").strip()
        grp_all = int(row.get("GRP_ALL") or 0)
        grp_in = int(row.get("GRP_IN_MASTER") or 0)
    except Exception as e:
        msgs.append(f"[health] 점검 생략(무시하고 진행): {str(e)[:160]}")
        return True, msgs

    if last:
        try:
            d = datetime.datetime.strptime(last, "%Y-%m-%d").date()
            gap = (base_date - d).days
            if gap >= 2:
                msgs.append(f"[health] 데이터 최신일 {last} (기준일보다 {gap}일 이전). "
                            f"복사본이라 최근 날짜는 아직 안 들어와 있습니다 — 그 구간이 비면 정상입니다.")
            else:
                msgs.append(f"[health] 데이터 최신일 {last} — 기준일과 거의 같습니다.")
        except ValueError:
            pass

    cov = (grp_in / grp_all * 100.0) if grp_all else 0.0
    if mode_cfg == "loose":
        loose, why = True, "config 에서 loose 고정"
    elif mode_cfg == "strict":
        loose, why = False, "config 에서 strict 고정"
    else:
        loose = cov < 90.0
        why = (f"자동 판정 — 마감 마스터 커버리지 {cov:.0f}% ({grp_in}/{grp_all} 그룹)"
               + (" → 정식 필터" if not loose else " → 임시(loose) 필터 유지"))
    msgs.append(f"[health] 마감필터: {'loose(임시)' if loose else 'strict(정식)'} — {why}")
    return loose, msgs
