#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기준일 결정 + 데이터 상태 점검 — run_all 이 시작할 때 한 번 부른다.

여기 있는 두 가지는 리포트 숫자를 좌우하는데 눈에 잘 안 띄어서, 매 실행마다
스스로 재고 화면에 적도록 만들었다.

1) 기준일은 **설치된 PC 가 서 있는 지역의 오늘** 이다
   같은 순간에 날짜가 셋으로 갈린다(2026-07-28 실측):
     DB 서버(UTC) 00:19 / 한국(KST) 09:19 / 현장 CKP(WIB, UTC+7) 07:19
   어느 지역에 깔든 그 지역의 '오늘' 로 돌아야 하므로 PC 시간대를 그대로 따른다.
   어느 시계를 썼는지는 매 실행마다 [time] 줄로 화면에 적는다.
   config 의 site_timezone 에 이름을 적으면(예: Asia/Seoul) 지역과 무관하게 고정된다.
   ※ DB 날짜 컬럼은 현장(WIB, UTC+7) 시계다. PC 가 그보다 앞선 시간대면
     자정 직후 몇 시간은 현장이 아직 어제라 하루 어긋난다 — 그때는 경고를 낸다.
   ※ PC 시계 자체가 틀어져 있으면 조용히 틀린 날짜가 나오므로, DB 시각과 대조해
     2시간 넘게 벌어지면 알린다(check 함수).

2) 우리가 보는 DB 는 원장의 **복사본**이다
   최근 며칠이 비어 있는 것은 고장이 아니라 정상. 다만 모르고 지나가면 빈 결과를
   실제 0 으로 오해하므로 최신 데이터일을 항상 알린다.
   또 마감 마스터(MSPD_PROD_GROUP)가 동기화되지 않으면 GMES 정식 마감필터로는
   전 리포트가 0 행이 된다(2026-07-28: 6월 실적 381개 그룹 중 마스터에 0개).
   그래서 커버리지를 재서 loose/strict 를 자동으로 고른다 —
   동기화가 끝나면 설정을 건드리지 않아도 정식 필터로 넘어간다.
"""
import os, io, csv, datetime, configparser


# 시간대 이름 없이도 계산할 수 있는 고정 오프셋. 윈도우는 zoneinfo 에 tzdata 패키지가
# 없는 경우가 많아, 이름을 못 읽어도 이 표로 버틴다(둘 다 서머타임이 없는 지역이다).
_FIXED_OFFSET = {"asia/seoul": 9, "asia/tokyo": 9, "asia/jakarta": 7, "asia/bangkok": 7,
                 "asia/ho_chi_minh": 7, "asia/shanghai": 8, "utc": 0}


def _cfg_tz(cfg=None, cfg_path=None):
    """config [report] site_timezone. 비었거나 auto 면 '' 를 돌려준다(= PC 를 따름)."""
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
    tz = tz or os.environ.get("CSMES_TZ", "").strip()
    return "" if tz.lower() in ("", "auto", "local", "pc") else tz


def clock(cfg=None, cfg_path=None):
    """지금 이 PC 가 서 있는 시각을 알아낸다. 반환 (datetime, 표시이름, UTC오프셋시간).

    기본은 **설치된 PC 의 시간대를 그대로 따른다**. 한국에서 돌리면 한국 날짜,
    인도네시아 현장에서 돌리면 현장 날짜가 나온다 — 어느 지역에 깔든 그 지역의
    '오늘' 로 동작하게 하려는 것이다. config 에 시간대를 적어 두면 그것을 우선한다.
    """
    tz = _cfg_tz(cfg, cfg_path)
    if tz:                                        # 명시 지정 — 지역과 무관하게 그 시간대로 고정
        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo(tz))
            return now, tz, now.utcoffset().total_seconds() / 3600.0
        except Exception:
            off = _FIXED_OFFSET.get(tz.lower())
            if off is not None:                   # tzdata 가 없어도 오프셋으로 계산
                now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=off)
                return now.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=off))), tz, float(off)
            # 모르는 이름이면 PC 를 따른다(조용히 틀린 날짜를 쓰는 것보다 낫다)
    now = datetime.datetime.now().astimezone()    # PC 의 시간대를 OS 에서 그대로 받아온다
    off = (now.utcoffset() or datetime.timedelta()).total_seconds() / 3600.0
    name = now.tzname() or ""
    return now, (name or f"UTC{off:+g}"), off


def site_today(cfg=None, cfg_path=None):
    """리포트 기준 '오늘'."""
    return clock(cfg, cfg_path)[0].date()


def clock_line(cfg=None, cfg_path=None):
    """화면에 적을 한 줄. 어느 시계로 날짜를 정했는지 눈에 보이게 한다."""
    now, name, off = clock(cfg, cfg_path)
    src = "config 지정" if _cfg_tz(cfg, cfg_path) else "이 PC 의 시간대"
    line = f"[time] 기준 시계: {name} (UTC{off:+g}) — {src} · 지금 {now:%Y-%m-%d %H:%M}"
    # DB 날짜 컬럼은 현장(WIB, UTC+7) 시계다. PC 가 그보다 앞선 시간대면
    # 자정 직후 몇 시간 동안 현장은 아직 어제라서 하루 어긋난다.
    gap = off - 7.0
    if gap > 0 and now.hour < gap:
        line += (f"\n[time] ⚠ 지금은 현장(WIB)으로 아직 {(now - datetime.timedelta(hours=gap)):%m-%d} 입니다. "
                 f"기준일을 하루 앞으로 잡아야 할 수 있습니다(매일 00:00~{int(gap):02d}:00 구간).")
    return line


HEALTH_SQL = (
    "SELECT TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') DB_UTC, "
    "(SELECT TO_CHAR(MAX(CREATE_DT),'YYYY-MM-DD') FROM OCI.POP_PCARD_SCAN) LAST_DATA, "
    "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
    "WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{plant}' AND PROD_MOVE_TYPE='PROD')) GRP_ALL, "
    "(SELECT COUNT(*) FROM (SELECT DISTINCT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PCARD_RESULT "
    "WHERE FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND PLANT_CD='{plant}' AND PROD_MOVE_TYPE='PROD') R "
    "JOIN OCI.MSPD_PROD_GROUP M ON M.PROD_GROUP_NO=R.PROD_GROUP_NO AND M.PLANT_CD=R.PLANT_CD) GRP_IN_MASTER "
    "FROM DUAL"
)


def _clock_check(db_utc, msgs):
    """이 PC 의 시계가 실제로 맞는지 DB 로 대조한다.
    PC 시계가 틀어져 있으면 기준일이 조용히 어긋나는데, 그건 아무도 눈치채지 못한다."""
    if not db_utc:
        return
    try:
        real = datetime.datetime.strptime(db_utc.strip(), "%Y-%m-%d %H:%M")
        mine = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        gap  = abs((mine - real).total_seconds()) / 60.0
    except Exception:
        return
    if gap > 120:
        msgs.append(f"[time] ⚠ 이 PC 의 시계가 실제 시각과 {gap/60:.1f}시간 차이납니다 "
                    f"(DB 기준 UTC {db_utc}). 기준일이 틀어질 수 있으니 PC 시간을 맞춰 주세요.")
    elif gap > 10:
        msgs.append(f"[time] 이 PC 의 시계가 {gap:.0f}분 어긋나 있습니다(참고).")


def check(db, cfg, conn, d_from, d_to, plant, sqldir, base_date):
    """(loose 여부, 화면에 적을 메시지들) 반환. 실패해도 리포트 생성은 막지 않는다."""
    msgs = []
    mode_cfg = (cfg.get("report", "closing_filter", fallback="") or "auto").strip().lower()
    try:
        csvp = os.path.join(sqldir, "_health.csv")
        db.run_batch([(csvp, HEALTH_SQL.format(d_from=d_from, d_to=d_to, plant=plant))], conn)
        row = next(csv.DictReader(io.StringIO(open(csvp, encoding="utf-8").read())), {})
        row = {(k or "").strip().upper(): v for k, v in row.items()}
        _clock_check(row.get("DB_UTC"), msgs)
        last = (row.get("LAST_DATA") or "").strip()
        grp_all = int(row.get("GRP_ALL") or 0)
        grp_in = int(row.get("GRP_IN_MASTER") or 0)
    except Exception as e:
        msgs.append(f"[health] 점검 생략(무시하고 진행): {str(e)[:160]}")
        return True, msgs

    if last:
        try:
            d = datetime.datetime.strptime(last, "%Y-%m-%d").date()
            gap = (base_date - d).days          # 양수 = 데이터가 기준일에 못 미침
            if gap >= 2:
                msgs.append(f"[health] ⚠ 데이터 최신일 {last} — 기준일({base_date})보다 {gap}일 이전입니다. "
                            f"복사본이라 최근 날짜는 아직 안 들어와 있습니다. "
                            f"기준일을 {last} 이전으로 잡으면 데이터가 정상적으로 나옵니다.")
            else:
                msgs.append(f"[health] 데이터 최신일 {last} — 기준일({base_date})까지 데이터가 들어와 있습니다.")
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
