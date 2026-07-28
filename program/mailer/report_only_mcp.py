#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BALANCE OUTGOING 레포트 '생성 전용' 로컬 MCP 서버  (Claude Desktop용)
======================================================================
이 서버는 DB에 직접 붙지 않는다. Claude Desktop이 이미 띄워둔 'sqlcl' MCP가
조회를 맡고, 이 서버는 balance_outgoing_mailer 의 로직(pivot/build_workbook)으로
'원본 양식 엑셀'만 만든다(메일 발송 안 함). 생성물은 OneDrive 의 report/ 폴더에
저장되고, 메일 본문에 넣을 공유 링크를 함께 돌려준다.

[Claude Desktop 한마디 흐름]  "오늘 outgoing 리포트 만들어서 보내줘"
  1) outgoing_query_plan(date)        : 날짜창에 맞춘 IP/PH/OS/SCAN SQL 4개
  2) sqlcl MCP 로 각 SQL 실행          : 권장 run-sqlcl + 'set sqlformat csv'(CSV). JSON도 가능.
  3) build_outgoing_report(...)       : sqlcl 결과로 report/ 에 xlsx 저장 + 요약 + 공유링크 반환
  4) Zapier Gmail(send email)          : 위 요약 + 공유 링크를 수신자에게 발송(첨부 대신 링크)

필요 패키지:  pip install mcp openpyxl   (csmes.sh 가 .venv 에 자동 설치)
설정값(공장/날짜창/저장폴더/공유링크/수신자)은 같은 폴더의 config.ini [report] 를 따른다.
"""
import os, sys, json, csv, io, datetime, configparser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # 같은 폴더의 원본 모듈 import 보장
import balance_outgoing_mailer as bo           # 원본 로직 재사용 (send_mail 은 호출 안 함)

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("balance-outgoing")


def _cfg():
    # [report] 만 읽으므로(비밀번호 없음) 인라인 주석(;)을 안전하게 무시 → config.ini.example 도 그대로 OK
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    cp.read(os.path.join(HERE, "config.ini"), encoding="utf-8")
    return cp

def _settings():
    cp = _cfg()
    plants = [x.strip() for x in cp.get("report", "plants", fallback="3110,3120,3210").split(",") if x.strip()]
    before = cp.getint("report", "window_before", fallback=3)
    after  = cp.getint("report", "window_after", fallback=7)
    return cp, plants, before, after

def _today(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d").date() if s else bo.site_today()

def _inlist(vals):
    return ",".join("'" + v + "'" for v in vals)

_COLOR_JOIN = (
    "LEFT JOIN (SELECT style_cd, mcs_color_cd FROM ("
    " SELECT style_cd, mcs_color_cd, ROW_NUMBER() OVER (PARTITION BY style_cd "
    " ORDER BY CASE WHEN mcs_color_cd='NONE' THEN 1 ELSE 0 END, COUNT(*) DESC) rn "
    " FROM OCI.MSPD_BATCH_PLAN WHERE mcs_color_cd IS NOT NULL GROUP BY style_cd, mcs_color_cd"
    ") WHERE rn=1) cc ON cc.style_cd=o.style_cd"
)

def _sheet_sql(families, plants, d_from, d_to, strict=True):
    """GMES P_MSPD90000S_Q_V14 'O'(Outgoing) 분기 로직을 리터럴 인라인.
    strict=True: 엄격 CLOSING_YN='N' + '다른 창고 MOVE 존재' EXISTS (정식, OCI 동기화 전제).
    strict=False: 느슨한 마감·EXISTS 생략(OCI 미동기화 임시)."""
    F=_inlist(families); P=_inlist(plants)
    if strict:
        return (
            "SELECT NVL(w2.wc_group_cd,' ') wcg, o.plant_cd, o.item_class, o.fa_wc_cd, "
            "NVL(i.model_name,' ') model, NVL(i.gender,' ') gen, o.style_cd, o.fa_date, "
            "SUM(o.out_qty) qty, MAX(cc.mcs_color_cd) color "
            "FROM (SELECT R.FA_WC_CD, R.ITEM_CLASS, R.FA_DATE, R.STYLE_CD, R.PLANT_CD, R.PLAN_PROD_WC_CD, R.PROD_GROUP_NO, SUM(R.PCARD_QTY) out_qty "
            "FROM OCI.MSPD_PCARD_RESULT R "
            f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD IN ({P}) AND R.PROD_MOVE_TYPE='PROD' "
            f"AND R.ITEM_CLASS_TYPE IN ({F}) "
            "AND (R.PROD_GROUP_NO, R.PLANT_CD) IN (SELECT PROD_GROUP_NO, PLANT_CD FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN='N') "
            "AND R.END_ROUTING_YN='Y' AND R.OUT_DATE='19991231' "
            "GROUP BY R.FA_WC_CD,R.ITEM_CLASS,R.FA_DATE,R.STYLE_CD,R.PLANT_CD,R.PLAN_PROD_WC_CD,R.PROD_GROUP_NO HAVING SUM(R.PCARD_QTY)>0) o "
            "JOIN OCI.MSBS_WORK_CENTER w ON o.plant_cd=w.plant_cd AND o.plan_prod_wc_cd=w.wc_cd "
            "LEFT JOIN OCI.MSBS_ITEM_STYLE i ON i.style_cd=o.style_cd "
            "LEFT JOIN OCI.MSBS_WORK_CENTER w2 ON w2.plant_cd=o.plant_cd AND w2.wc_cd=o.fa_wc_cd "
            + _COLOR_JOIN + " "
            "WHERE EXISTS (SELECT 1 FROM OCI.MSPD_PCARD_RESULT I JOIN OCI.MSBS_WORK_CENTER WC ON I.PLANT_CD=WC.PLANT_CD AND I.PLAN_PROD_WC_CD=WC.WC_CD "
            "WHERE I.PROD_GROUP_NO=o.PROD_GROUP_NO AND I.ITEM_CLASS=o.ITEM_CLASS AND I.PROD_MOVE_TYPE='MOVE' AND I.END_ROUTING_YN='Y' AND WC.BASE_WH_CD<>w.BASE_WH_CD) "
            "GROUP BY NVL(w2.wc_group_cd,' '), o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' '), NVL(i.gender,' '), o.style_cd, o.fa_date"
        )
    return (
        "SELECT NVL(w.wc_group_cd,' ') wcg, o.plant_cd, o.item_class, o.fa_wc_cd, "
        "NVL(i.model_name,' ') model, NVL(i.gender,' ') gen, o.style_cd, o.fa_date, "
        "SUM(o.out_qty) qty, MAX(cc.mcs_color_cd) color "
        "FROM (SELECT R.FA_WC_CD, R.ITEM_CLASS, R.FA_DATE, R.STYLE_CD, R.PLANT_CD, R.PROD_GROUP_NO, SUM(R.PCARD_QTY) out_qty "
        "FROM OCI.MSPD_PCARD_RESULT R "
        f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD IN ({P}) AND R.PROD_MOVE_TYPE='PROD' "
        f"AND R.ITEM_CLASS_TYPE IN ({F}) AND R.END_ROUTING_YN='Y' AND R.OUT_DATE='19991231' "
        "AND NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g WHERE g.prod_group_no=R.prod_group_no AND g.plant_cd=R.plant_cd AND g.closing_yn='Y') "
        "GROUP BY R.FA_WC_CD,R.ITEM_CLASS,R.FA_DATE,R.STYLE_CD,R.PLANT_CD,R.PROD_GROUP_NO HAVING SUM(R.PCARD_QTY)>0) o "
        "LEFT JOIN OCI.MSBS_ITEM_STYLE i ON i.style_cd=o.style_cd "
        "LEFT JOIN OCI.MSBS_WORK_CENTER w ON w.plant_cd=o.plant_cd AND w.wc_cd=o.fa_wc_cd "
        + _COLOR_JOIN + " "
        "GROUP BY NVL(w.wc_group_cd,' '), o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' '), NVL(i.gender,' '), o.style_cd, o.fa_date"
    )

def _scan_sql(plants, d_from, d_to):
    return (
        "SELECT plant_cd, fa_wc_cd, style_cd, SUM(prod_qty) q FROM OCI.POP_PCARD_SCAN "
        "WHERE op_cd IN ('BEM','BEP') AND NVL(cancel_flag,'N')<>'Y' "
        f"AND plant_cd IN ({_inlist(plants)}) AND scan_ymd BETWEEN '{d_from}' AND '{d_to}' "
        "GROUP BY plant_cd, fa_wc_cd, style_cd"
    )

def _records(s):
    """sqlcl 결과 텍스트 → dict 리스트(키 대문자). JSON 배열/객체 또는 CSV(헤더 포함) 자동 인식."""
    if not s:
        return []
    if isinstance(s, list):
        data = s
    else:
        s = s.strip()
        if not s:
            return []
        if s[0] in "[{":
            data = json.loads(s)
            if isinstance(data, dict):
                data = [data]
        else:
            data = list(csv.DictReader(io.StringIO(s)))
    return [{(k or "").strip().upper(): v for k, v in r.items()} for r in data]

def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0

def _rows(s):
    """sqlcl 결과 → pivot 입력 튜플 (wcg, plant, ic, line, model, gen, style, fa, qty)."""
    out = []
    for d in _records(s):
        out.append((
            (d.get("WCG") or " "), d.get("PLANT_CD"), d.get("ITEM_CLASS"), d.get("FA_WC_CD"),
            (d.get("MODEL") or " "), (d.get("GEN") or " "), d.get("STYLE_CD"),
            str(d.get("FA_DATE") or ""), _num(d.get("QTY")), d.get("COLOR"),
        ))
    return out

def _scan(s):
    m = {}
    for d in _records(s):
        m[(d.get("PLANT_CD"), d.get("FA_WC_CD"), d.get("STYLE_CD"))] = _num(d.get("Q"))
    return m


@mcp.tool()
def outgoing_query_plan(date: str = "") -> str:
    """STEP 1. 실DB 레포트용 SQL을 날짜창에 맞춰 돌려준다.

    반환된 IP/PH/OS/SCAN 4개 SQL을 sqlcl MCP 로 실행한 뒤(권장: run-sqlcl 에
    'set sqlformat csv' 를 같은 호출에 붙여 CSV로 받기; JSON도 가능),
    각 결과 텍스트를 build_outgoing_report 에 그대로 넘겨라.
    date: 'YYYY-MM-DD'(생략 시 오늘). 버킷은 작업일 기준 D+3 … DD … D-7.
    """
    cp, plants, before, after = _settings()
    strict = cp.getboolean("report", "strict_outgoing", fallback=True)
    today = _today(date)
    buckets = bo.build_buckets(today, before, after)
    d_from = min(b[1] for b in buckets); d_to = max(b[1] for b in buckets)
    fams = {n: f for n, f in bo.SHEETS}
    plan = {
        "date": today.isoformat(),
        "window": {"d_from": d_from, "d_to": d_to, "buckets": [b[0] + ":" + b[1] for b in buckets]},
        "plants": plants,
        "selection": ("strict(정식 GMES 로직: 엄격 CLOSING_YN='N' + 다른창고 MOVE EXISTS)" if strict
                      else "loose(OCI 미동기화 임시)"),
        "queries": {
            "IP":   _sheet_sql(fams["IP"], plants, d_from, d_to, strict),
            "PH":   _sheet_sql(fams["PH"], plants, d_from, d_to, strict),
            "OS":   _sheet_sql(fams["OS"], plants, d_from, d_to, strict),
            "SCAN": _scan_sql(plants, d_from, d_to),
        },
        "next": ("각 SQL을 sqlcl 로 실행(권장: run-sqlcl 에 'set sqlformat csv' 붙여 CSV; JSON도 됨). "
                 "결과 텍스트를 build_outgoing_report(date, ip_rows, ph_rows, os_rows, scan_rows) 에 그대로 넣어라. "
                 "빌더가 CSV/JSON 자동 인식."),
    }
    return json.dumps(plan, ensure_ascii=False, indent=2)


@mcp.tool()
def build_outgoing_report(date: str = "", ip_rows: str = "", ph_rows: str = "",
                          os_rows: str = "", scan_rows: str = "") -> str:
    """STEP 2. sqlcl 결과로 BALANCE OUTGOING 엑셀을 생성한다(메일 발송 안 함).

    report/ 폴더(OneDrive)에 저장하고, 요약 + 공유 링크 + 다음 단계(Zapier 발송) 안내를 반환.
    ip_rows/ph_rows/os_rows/scan_rows : 해당 SQL을 sqlcl 로 실행한 결과(JSON 또는 CSV 텍스트).
    date : 'YYYY-MM-DD' (query_plan 과 동일 날짜).
    """
    cp, plants, before, after = _settings()
    today = _today(date)
    buckets = bo.build_buckets(today, before, after)
    sm = _scan(scan_rows)
    data = {
        "IP": bo.pivot(_rows(ip_rows), buckets, sm),
        "PH": bo.pivot(_rows(ph_rows), buckets, sm),
        "OS": bo.pivot(_rows(os_rows), buckets, sm),
    }
    wb = bo.build_workbook(data, buckets, today, today.strftime("%Y-%m-%d"))
    out = os.path.join(bo.report_dir(cp), f"BALANCE_OUTGOING_{today.strftime('%Y%m%d')}.xlsx")
    wb.save(out)
    link = cp.get("report", "share_link", fallback="").strip()
    recips = cp.get("report", "recipients", fallback="").strip()
    return (
        "실데이터 레포트 생성 완료 (OneDrive report/ 저장, 메일 발송 안 함):\n"
        f"{out}\n\n{bo.build_body_summary(data)}\n\n"
        f"공유 링크: {link or '(config.ini [report] share_link 미설정)'}\n\n"
        "[다음 단계] Zapier 의 Gmail 'Send Email' 로 위 요약 + 공유 링크를 발송하세요"
        f"{(' (수신자: ' + recips + ')') if recips else ''}. 첨부 대신 본문에 링크를 넣습니다."
    )


@mcp.tool()
def make_demo_report(date: str = "") -> str:
    """(DB 불필요) 데모 샘플 데이터로 양식만 확인용 엑셀 생성. 실데이터가 아니다."""
    cp, plants, before, after = _settings()
    today = _today(date)
    buckets = bo.build_buckets(today, before, after)
    data = bo.make_demo_data(buckets)
    wb = bo.build_workbook(data, buckets, today, today.strftime("%Y-%m-%d"))
    out = os.path.join(bo.report_dir(cp), f"BALANCE_OUTGOING_DEMO_{today.strftime('%Y%m%d')}.xlsx")
    wb.save(out)
    link = cp.get("report", "share_link", fallback="").strip()
    return (f"데모 레포트 생성 완료 (샘플 데이터, 메일 발송 안 함):\n{out}\n\n"
            f"{bo.build_body_summary(data)}\n\n공유 링크: {link}")


if __name__ == "__main__":
    mcp.run()
