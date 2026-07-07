#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — Balance 계열 SQL 생성기 (진실의 출처)
=========================================================
공식 보고서 번호(현업 통일 기준) 대비 완료된 부족분(Balance) 리포트의 SQL을 담는다.
데이터 소스 = GMES 프로시저 P_MSPD90000S_Q(Shortage Balance Checking, Outgoing 분기)의
OCI 재현. 색상은 MSPD_BATCH_PLAN BOM 인라인(EXACT + STYLE fallback).

[검증] fn_shortage_screen 로직(END_ROUTING='Y' + CLOSING + BOM 색상)이
       2026-03-01~07 / 3120 / CP / FGA16,FGA19 → G-Total 5,426 과 정확히 일치.

[마감 필터 토글]
  loose=True  : NOT EXISTS(CLOSING_YN='Y')  — OCI 미동기화 임시(현재 운영값).
  loose=False : (PROD_GROUP_NO,PLANT_CD) IN (CLOSING_YN='N') — GMES 정식(동기화 후).

공식 번호 매핑 (완료 7종):
  No.2  3-1. Balance IP Production        = by-date  ICT(II,IP)  DIV=Production
  No.3  3-2. Balance IP Prod. by size     = by-size  ICT(II,IP)  DIV=Production
  No.4  3-2. Balance IP Outgoing by size  = by-size  ICT(II,IP)  DIV=Outgoing
  No.5  3-3. Balance IP Outgoing Market   = balance_outgoing_mailer.fetch_sheet / report_only_mcp._sheet_sql
  No.7  3-1. Balance CMP                  = by-date  ICT(CP)     DIV=Production
  No.8  3-1. Balance Outgoing PH          = by-date  ICT(PH,PP)  DIV=Outgoing
  No.11 3-2. Balance PH in Market PH by   = by-size  ICT(PH,PP,CP) DIV=Production

사용:
  python balance_sql.py 3 20260628 20260709          # No.3 SQL 출력
  python balance_sql.py 8 20260628 20260709 --strict # 정식 마감필터로
"""
import sys

PLANT = "3120"  # CKP 고정

def _inlist(vals):
    return ",".join("'" + v + "'" for v in vals)

def _date_pred(div):
    # DIV=Production → 미생산(PROD_DATE), Outgoing → 미출고(OUT_DATE). 둘 다 END_ROUTING='Y'.
    if div == "Outgoing":
        return "R.OUT_DATE='19991231' AND R.END_ROUTING_YN='Y'"
    return "R.PROD_DATE='19991231' AND R.END_ROUTING_YN='Y'"

def _closing_pred(loose):
    if loose:
        return ("NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g "
                "WHERE g.PROD_GROUP_NO=R.PROD_GROUP_NO AND g.PLANT_CD=R.PLANT_CD AND g.CLOSING_YN='Y')")
    return ("(R.PROD_GROUP_NO,R.PLANT_CD) IN "
            "(SELECT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN='N')")

# 색상 CTE (FILT 그룹 한정) — EXACT(PROD_GROUP_NO,PARENT_ITEM_CD) 우선, 없으면 STYLE fallback
_COLOR_CTES = (
    "GC_EXACT AS (SELECT B.PROD_GROUP_NO,B.PARENT_ITEM_CD,"
    "LISTAGG(DISTINCT B.MCS_COLOR_CD,', ') WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) MCS_COLOR "
    "FROM OCI.MSPD_BATCH_PLAN B WHERE B.MCS_COLOR_CD NOT IN ('NONE',' ') AND B.MCS_COLOR_CD IS NOT NULL "
    "AND B.PROD_GROUP_NO IN (SELECT DISTINCT PROD_GROUP_NO FROM FILT) "
    "GROUP BY B.PROD_GROUP_NO,B.PARENT_ITEM_CD), "
    "GC_STYLE AS (SELECT SUBSTR(B.PARENT_ITEM_CD,1,LENGTH(B.PARENT_ITEM_CD)-4) STYLE_NOHYPHEN,"
    "LISTAGG(DISTINCT B.MCS_COLOR_CD,', ') WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) MCS_COLOR "
    "FROM OCI.MSPD_BATCH_PLAN B WHERE B.MCS_COLOR_CD NOT IN ('NONE',' ') AND B.MCS_COLOR_CD IS NOT NULL "
    "AND B.PROD_GROUP_NO IN (SELECT DISTINCT PROD_GROUP_NO FROM FILT) "
    "GROUP BY SUBSTR(B.PARENT_ITEM_CD,1,LENGTH(B.PARENT_ITEM_CD)-4))"
)
_COLOR_EXPR = ("CASE WHEN SUBSTR(F.ITEM_CLASS,1,2)='FS' THEN NULL "
               "ELSE NVL(E.MCS_COLOR,ST.MCS_COLOR) END")
_COLOR_JOINS = ("LEFT JOIN GC_EXACT E ON E.PROD_GROUP_NO=F.PROD_GROUP_NO AND E.PARENT_ITEM_CD=F.ITEM_CD "
                "LEFT JOIN GC_STYLE ST ON ST.STYLE_NOHYPHEN=REPLACE(F.STYLE_CD,'-','')")

def _filt(ict_list, div, d_from, d_to, loose, with_size):
    cols = "R.FA_WC_CD,R.STYLE_CD,R.ITEM_CD,R.PROD_GROUP_NO,R.ITEM_CLASS,R.ITEM_CLASS_TYPE,R.FA_DATE,R.PCARD_QTY"
    if with_size:
        cols = "R.FA_WC_CD,R.STYLE_CD,R.ITEM_CD,R.PROD_GROUP_NO,R.ITEM_CLASS,R.ITEM_CLASS_TYPE,R.FA_DATE,R.SIZE_CD,R.PCARD_QTY"
    return (
        f"FILT AS (SELECT {cols} FROM OCI.MSPD_PCARD_RESULT R "
        f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD='{PLANT}' "
        f"AND R.PROD_MOVE_TYPE='PROD' AND {_date_pred(div)} "
        f"AND R.ITEM_CLASS_TYPE IN ({_inlist(ict_list)}) AND {_closing_pred(loose)})"
    )

def shortage_bysize_sql(ict_list, div, d_from, d_to, loose=True):
    """No.3/4/11 — 사이즈별(by size). 반환: LINE,MODEL_NAME,STYLE_CD,ITEM_CLASS,MCS_COLOR,FA_DATE,DIV,SIZE_CD,QTY"""
    return (
        "WITH " + _filt(ict_list, div, d_from, d_to, loose, with_size=True) + ", " + _COLOR_CTES + " "
        "SELECT F.FA_WC_CD LINE,S.MODEL_NAME,F.STYLE_CD,F.ITEM_CLASS," + _COLOR_EXPR + " MCS_COLOR,"
        f"F.FA_DATE,'{div}' DIV,NVL(S.GENDER,' ') GEN,F.SIZE_CD,SUM(F.PCARD_QTY) QTY "
        "FROM FILT F LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=F.STYLE_CD " + _COLOR_JOINS + " "
        "GROUP BY F.FA_WC_CD,S.MODEL_NAME,F.STYLE_CD,F.ITEM_CLASS," + _COLOR_EXPR + ",F.FA_DATE,NVL(S.GENDER,' '),F.SIZE_CD "
        "HAVING SUM(F.PCARD_QTY)>0 ORDER BY LINE,STYLE_CD,ITEM_CLASS,FA_DATE,SIZE_CD"
    )

def shortage_bydate_sql(ict_list, div, d_from, d_to, loose=True):
    """No.2/7/8 — 날짜별(by date). 반환: ITEM_CLASS,FA_WC,STYLE_CD,STYLE_NAME,MCS_COLOR,FA_DATE,QTY"""
    return (
        "WITH " + _filt(ict_list, div, d_from, d_to, loose, with_size=False) + ", " + _COLOR_CTES + " "
        "SELECT F.ITEM_CLASS,F.FA_WC_CD FA_WC,F.STYLE_CD,S.MODEL_NAME STYLE_NAME," + _COLOR_EXPR + " MCS_COLOR,"
        "F.FA_DATE,SUM(F.PCARD_QTY) QTY "
        "FROM FILT F LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=F.STYLE_CD " + _COLOR_JOINS + " "
        "GROUP BY F.ITEM_CLASS,F.FA_WC_CD,F.STYLE_CD,S.MODEL_NAME," + _COLOR_EXPR + ",F.FA_DATE "
        "HAVING SUM(F.PCARD_QTY)>0 ORDER BY FA_WC,STYLE_CD,F.FA_DATE"
    )

# 공식 번호 → (설명, 함수, ICT, DIV)
# [원본 item class 범위 검증 2026-07-07] 원본 시트 Item Class 계열 대조 결과 반영:
#   IP Prod(#7)=II만, IP Outgoing(#8)=II+IP, CMP(#11)=CP, Outgoing PH(#12)=PH+PP, PH in Market(#15)=PH+PP.
REPORTS = {
    "2":  ("3-1. Balance IP Production",       shortage_bydate_sql, ["II"],       "Production"),
    "3":  ("3-2. Balance IP Prod. by size",    shortage_bysize_sql, ["II"],       "Production"),
    "4":  ("3-2. Balance IP Outgoing by size", shortage_bysize_sql, ["II", "IP"], "Outgoing"),
    "7":  ("3-1. Balance CMP",                 shortage_bydate_sql, ["CP"],       "Production"),
    "8":  ("3-1. Balance Outgoing PH",         shortage_bydate_sql, ["PH", "PP"], "Outgoing"),
    "11": ("3-2. Balance PH in Market PH by",  shortage_bysize_sql, ["PH", "PP"], "Production"),
}
# No.5 (3-3. Balance IP Outgoing Market) 의 SQL 은 balance_outgoing_mailer.fetch_sheet /
# report_only_mcp._sheet_sql 에 있음(동일 엔진, 동(棟)·라인·일자버킷 양식).

def build(report_no, d_from, d_to, loose=True):
    name, fn, ict, div = REPORTS[report_no]
    return name, fn(ict, div, d_from, d_to, loose=loose)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: python balance_sql.py <No(2,3,4,7,8,11)> <YYYYMMDD from> <YYYYMMDD to> [--strict]")
        print("  완료 보고서:", ", ".join(f"{k}={v[0]}" for k, v in REPORTS.items()))
        sys.exit(0)
    no, df, dt = sys.argv[1], sys.argv[2], sys.argv[3]
    loose = "--strict" not in sys.argv
    name, sql = build(no, df, dt, loose=loose)
    print(f"-- No.{no}  {name}   (마감필터: {'loose' if loose else 'strict'})")
    print(sql)
