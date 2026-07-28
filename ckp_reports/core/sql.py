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
                실측 2026-07-21: CKP 카드 5,095,818건 중 MSPD_PROD_GROUP 매칭 1,533건뿐
                (마스터 CKP 그룹 64개, Y 31/N 33), 마감 Y에 걸리는 카드 0 → 이 필터 실효 제외 0건.
                마스터 동기화 재개 시 대량 마감분이 걸러질 수 있으니 그때 수치 급변 주의.
  loose=False : (PROD_GROUP_NO,PLANT_CD) IN (CLOSING_YN='N') — GMES 정식(동기화 후).

공식 번호 매핑 (완료 7종):
  No.2  3-1. Balance IP Production        = by-date  ICT(II,IP)  DIV=Production
  No.3  3-2. Balance IP Prod. by size     = by-size  ICT(II,IP)  DIV=Production
  No.4  3-2. Balance IP Outgoing by size  = by-size  ICT(II,IP)  DIV=Outgoing
  No.5  3-3. Balance IP Outgoing Market   = outgoing_market_sheet_sql / _dickp_sql / _scan_sql (이 파일)
  No.7  3-1. Balance CMP                  = by-date  ICT(CP)     DIV=Production
  No.8  3-1. Balance Outgoing PH          = by-date  ICT(PH,PP)  DIV=Outgoing
  No.11 3-2. Balance PH in Market PH by   = by-size  ICT(PH,PP)  DIV=Production

사용:
  python balance_sql.py 3 20260628 20260709          # No.3 SQL 출력
  python balance_sql.py 8 20260628 20260709 --strict # 정식 마감필터로
"""
import sys

PLANT = "3120"  # CKP 고정

def _inlist(vals):
    return ",".join("'" + v + "'" for v in vals)

def _date_pred(div, er="Y"):
    # DIV=Production → 미생산(PROD_DATE), Outgoing → 미출고(OUT_DATE).
    # er = END_ROUTING_YN: 'Y'=AFTER SCAN UV(마지막공정), 'N'=BEFORE UV(공정 진행중, 예: PHYLON PRESS).
    if div == "Outgoing":
        return f"R.OUT_DATE='19991231' AND R.END_ROUTING_YN='{er}'"
    return f"R.PROD_DATE='19991231' AND R.END_ROUTING_YN='{er}'"

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

def _filt(ict_list, div, d_from, d_to, loose, with_size, er="Y"):
    # [변경 2026-07] END_ROUTING 조건 미사용, ROUTING_SEQ dedup 채택.
    #   실측(2026-07-21, PLANT_CD=3120 PROD): END_ROUTING_YN 은 값이 존재(Y 2,654,599 / N 1,431,275).
    #   최신 SEQ행의 99.65%가 'Y'지만 한 (PCARD_NAME·ITEM_CLASS·SIZE_CD) 그룹에 'Y'가 복수 존재해
    #   (비최신 행 351,265건이 'Y') dedup 유일키로 부적합. → END_ROUTING 대신 SEQ 최대 1행으로 중복 제거.
    #   대신 (PCARD_NAME·ITEM_CLASS·SIZE_CD)별 ROUTING_SEQ 최대(=최신 공정) 1행만 남겨 공정 중복 제거.
    #   그룹내 PCARD_QTY 상수(변동 0건 검증)라 어느 행을 남겨도 합계 동일. 생산=PROD_DATE, 출고=OUT_DATE 미완료.
    #   (검증: CP 38,289 → 23,255)
    outcols = "FA_WC_CD,STYLE_CD,ITEM_CD,PROD_GROUP_NO,ITEM_CLASS,ITEM_CLASS_TYPE,FA_DATE,PCARD_QTY"
    if with_size:
        outcols = "FA_WC_CD,STYLE_CD,ITEM_CD,PROD_GROUP_NO,ITEM_CLASS,ITEM_CLASS_TYPE,FA_DATE,SIZE_CD,PCARD_QTY"
    date_pred = "R.OUT_DATE='19991231'" if div == "Outgoing" else "R.PROD_DATE='19991231'"
    return (
        "FILT AS (SELECT " + outcols + " FROM ("
        "SELECT R.FA_WC_CD,R.STYLE_CD,R.ITEM_CD,R.PROD_GROUP_NO,R.ITEM_CLASS,R.ITEM_CLASS_TYPE,"
        "R.FA_DATE,R.SIZE_CD,R.PCARD_QTY,"
        "ROW_NUMBER() OVER (PARTITION BY R.PCARD_NAME,R.ITEM_CLASS,R.SIZE_CD "
        "ORDER BY R.ROUTING_SEQ DESC NULLS LAST) rn "
        "FROM OCI.MSPD_PCARD_RESULT R "
        f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD='{PLANT}' "
        f"AND R.PROD_MOVE_TYPE='PROD' AND {date_pred} "
        f"AND R.ITEM_CLASS_TYPE IN ({_inlist(ict_list)}) AND {_closing_pred(loose)}"
        ") WHERE rn=1)"
    )

def shortage_bysize_sql(ict_list, div, d_from, d_to, loose=True, er="Y"):
    """No.3/4/11 — 사이즈별(by size). 반환: LINE,MODEL_NAME,STYLE_CD,ITEM_CLASS,MCS_COLOR,FA_DATE,DIV,SIZE_CD,QTY"""
    return (
        "WITH " + _filt(ict_list, div, d_from, d_to, loose, with_size=True, er=er) + ", " + _COLOR_CTES + " "
        "SELECT F.FA_WC_CD LINE,S.MODEL_NAME,F.STYLE_CD,F.ITEM_CLASS," + _COLOR_EXPR + " MCS_COLOR,"
        f"F.FA_DATE,'{div}' DIV,NVL(S.GENDER,' ') GEN,F.SIZE_CD,SUM(F.PCARD_QTY) QTY "
        "FROM FILT F LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=F.STYLE_CD " + _COLOR_JOINS + " "
        "GROUP BY F.FA_WC_CD,S.MODEL_NAME,F.STYLE_CD,F.ITEM_CLASS," + _COLOR_EXPR + ",F.FA_DATE,NVL(S.GENDER,' '),F.SIZE_CD "
        "HAVING SUM(F.PCARD_QTY)>0 ORDER BY LINE,STYLE_CD,ITEM_CLASS,FA_DATE,SIZE_CD"
    )

def shortage_bydate_sql(ict_list, div, d_from, d_to, loose=True, er="Y"):
    """No.2/7/8/9/10 — 날짜별(by date). 반환: ITEM_CLASS,FA_WC,STYLE_CD,STYLE_NAME,MCS_COLOR,FA_DATE,QTY"""
    return (
        "WITH " + _filt(ict_list, div, d_from, d_to, loose, with_size=False, er=er) + ", " + _COLOR_CTES + " "
        "SELECT F.ITEM_CLASS,F.FA_WC_CD FA_WC,F.STYLE_CD,S.MODEL_NAME STYLE_NAME," + _COLOR_EXPR + " MCS_COLOR,"
        "F.FA_DATE,SUM(F.PCARD_QTY) QTY "
        "FROM FILT F LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=F.STYLE_CD " + _COLOR_JOINS + " "
        "GROUP BY F.ITEM_CLASS,F.FA_WC_CD,F.STYLE_CD,S.MODEL_NAME," + _COLOR_EXPR + ",F.FA_DATE "
        "HAVING SUM(F.PCARD_QTY)>0 ORDER BY FA_WC,STYLE_CD,F.FA_DATE"
    )

def ip_production_zone_sql(d_from, d_to, loose=True):
    """No.2 존 양식용 — II+IP 미생산 부족분 + GEN + MCS + 조립공장(FA_PLANT→JJ/RJ).
    CKP(3120) 생산분을 조립공장(FA_PLANT_CD) JJ(3110)/RJ(3210)로 분리. routing_seq dedup.
    반환: ITEM_CLASS,FA_WC,STYLE_CD,STYLE_NAME,MCS_COLOR,FA_DATE,QTY,GEN,MCS,FAPLANT"""
    mcs_cte = ("GC_MCS AS (SELECT style_cd, MAX(mcs_cd) MCS_CD FROM OCI.MSPD_BATCH_PLAN "
               "WHERE mcs_cd IS NOT NULL GROUP BY style_cd)")
    filt = (
        "FILT AS (SELECT FA_WC_CD,STYLE_CD,ITEM_CD,PROD_GROUP_NO,ITEM_CLASS,ITEM_CLASS_TYPE,FA_DATE,PCARD_QTY,FA_PLANT_CD FROM ("
        "SELECT R.FA_WC_CD,R.STYLE_CD,R.ITEM_CD,R.PROD_GROUP_NO,R.ITEM_CLASS,R.ITEM_CLASS_TYPE,R.FA_DATE,R.PCARD_QTY,R.FA_PLANT_CD,R.SIZE_CD,"
        "ROW_NUMBER() OVER (PARTITION BY R.PCARD_NAME,R.ITEM_CLASS,R.SIZE_CD ORDER BY R.ROUTING_SEQ DESC NULLS LAST) rn "
        "FROM OCI.MSPD_PCARD_RESULT R "
        f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD='{PLANT}' "
        "AND R.PROD_MOVE_TYPE='PROD' AND R.PROD_DATE='19991231' "
        "AND R.ITEM_CLASS_TYPE IN ('II','IP') AND R.FA_PLANT_CD IN ('3110','3210') "
        f"AND {_closing_pred(loose)}"
        ") WHERE rn=1)"
    )
    return (
        "WITH " + filt + ", " + _COLOR_CTES + ", " + mcs_cte + " "
        "SELECT F.ITEM_CLASS,F.FA_WC_CD FA_WC,F.STYLE_CD,S.MODEL_NAME STYLE_NAME," + _COLOR_EXPR + " MCS_COLOR,"
        "F.FA_DATE,SUM(F.PCARD_QTY) QTY,NVL(S.GENDER,' ') GEN,MX.MCS_CD MCS,"
        "CASE F.FA_PLANT_CD WHEN '3110' THEN 'JJ' WHEN '3210' THEN 'RJ' ELSE F.FA_PLANT_CD END FAPLANT "
        "FROM FILT F LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=F.STYLE_CD " + _COLOR_JOINS + " "
        "LEFT JOIN GC_MCS MX ON MX.style_cd=F.STYLE_CD "
        "GROUP BY F.ITEM_CLASS,F.FA_WC_CD,F.STYLE_CD,S.MODEL_NAME," + _COLOR_EXPR + ",F.FA_DATE,NVL(S.GENDER,' '),MX.MCS_CD,F.FA_PLANT_CD "
        "HAVING SUM(F.PCARD_QTY)>0 ORDER BY FAPLANT,FA_WC,STYLE_CD,F.FA_DATE"
    )

# 공식 번호 → (설명, 함수, ICT, DIV)
# [원본 item class 범위 검증 2026-07-07] 원본 시트 Item Class 계열 대조 결과 반영:
#   IP Prod(#7)=II만, IP Outgoing(#8)=II+IP, CMP(#11)=CP, Outgoing PH(#12)=PH+PP, PH in Market(#15)=PH+PP.
# 튜플: (이름, 함수, ICT, DIV, END_ROUTING). before UV=END_ROUTING 'N'(공정중), after UV/기타='Y'.
REPORTS = {
    "2":  ("3-1. Balance IP Production",       shortage_bydate_sql, ["II"],       "Production", "Y"),
    "3":  ("3-2. Balance IP Prod. by size",    shortage_bysize_sql, ["II", "IP"], "Production", "Y"),
    "4":  ("3-2. Balance IP Outgoing by size", shortage_bysize_sql, ["II", "IP"], "Outgoing",   "Y"),
    "7":  ("3-1. Balance CMP",                 shortage_bydate_sql, ["CP"],       "Production", "Y"),
    "8":  ("3-1. Balance Outgoing PH",         shortage_bydate_sql, ["PH", "PP"], "Outgoing",   "Y"),
    "9":  ("3-1. Balance PH before UV",        shortage_bydate_sql, ["PH", "PP"], "Production", "N"),
    "10": ("3-1. Balance PH after UV",         shortage_bydate_sql, ["PH", "PP"], "Production", "Y"),
    "11": ("3-2. Balance PH in Market PH by",  shortage_bysize_sql, ["PH", "PP"], "Production", "Y"),
}
# No.5 (3-3. Balance IP Outgoing Market) 의 SQL 은 이 파일의 outgoing_market_sheet_sql /
# outgoing_market_dickp_sql / outgoing_market_scan_sql 에 있음(엔진은 core/market_engine.py).

def build(report_no, d_from, d_to, loose=True):
    name, fn, ict, div, er = REPORTS[report_no]
    return name, fn(ict, div, d_from, d_to, loose=loose, er=er)


# ===== No.1 DAILY REPORT SCAN (PHH 파일론 스캔) =====
def scan_daily_sql(dates, plant=PLANT):
    """No.1 — POP_PCARD_SCAN op_cd='PHH' NORMAL 을 날짜별 피벗.
    dates=YYYYMMDD 리스트. 반환: LINE,MODELV,COLORV,STYLE,MCS,N1..Nk,WTOT (Nk=날짜별 NORMAL)."""
    dlist = _inlist(dates)
    ncols = ",".join(f"SUM(CASE WHEN scan_ymd='{d}' THEN prod_qty ELSE 0 END) N{i+1}" for i, d in enumerate(dates))
    return (
        "WITH SC AS (SELECT s.fa_wc_cd LINE, s.style_cd STYLE, s.scan_ymd, s.prod_qty "
        f"FROM OCI.POP_PCARD_SCAN s WHERE s.op_cd IN ('PHH','PHM') AND NVL(s.cancel_flag,'N')<>'Y' AND s.plant_cd='{plant}' "
        f"AND s.scan_ymd IN ({dlist})) "
        "SELECT sc.LINE, NVL(it.model_name,' ') MODELV, NVL(cc.color,' ') COLORV, sc.STYLE, NVL(cc.mcs,' ') MCS, "
        + ncols + ", SUM(prod_qty) WTOT "
        "FROM SC LEFT JOIN OCI.MSBS_ITEM_STYLE it ON it.style_cd=sc.STYLE "
        "LEFT JOIN (SELECT style_cd, MAX(mcs_cd) mcs, MAX(mcs_color_cd) color FROM OCI.MSPD_BATCH_PLAN "
        "WHERE mcs_color_cd NOT IN ('NONE',' ') AND mcs_color_cd IS NOT NULL GROUP BY style_cd) cc ON cc.style_cd=sc.STYLE "
        "GROUP BY sc.LINE, it.model_name, cc.color, sc.STYLE, cc.mcs HAVING SUM(prod_qty)>0 ORDER BY sc.LINE, sc.STYLE"
    )


# ===== No.6 External OS&D Balance by size =====
OSND_SIZES = ["1","1T","2","2T","3","3T","4","4T","5","5T","6","6T","7","7T","8","8T","9","9T",
              "10","10T","11","11T","12","12T","13","13T","14","14T","15","15T","16","16T","17"]  # 원본 3-4 고정 33
def osnd_balance_sql(d_from, d_to, plant=PLANT):
    """No.6 — MSPQ_EX_OSND BALANCE(I_SCN_DT IS NULL=미입고) 를 스타일 단위 사이즈 피벗.
    반환: LINE,DT,CMP,MODEL,STYLE,COLORV,TYPE,SUP,STATUSV,TOT,Z1..Z33."""
    zc = ",".join(f"SUM(CASE WHEN SIZE_CD='{s}' AND I_SCN_DT IS NULL THEN OSND_EX_QTY ELSE 0 END)/2 Z{i+1}"
                  for i, s in enumerate(OSND_SIZES))
    win = f"{d_from[4:6]}/{d_from[6:8]}-{d_to[4:6]}/{d_to[6:8]}"
    return (
        "WITH BASE AS (SELECT IP.SUB_WC_CD LINE, SUBSTR(OS.SUPPLY_OP_CD,1,2) CMP, NVL(S.MODEL_NAME,' ') MODEL, "
        "OS.STYLE_CD||' / '||OS.ITEM_CLASS STYLE_DISP, OS.COLOR_CD, NVL(CM.CODE_NAME,OS.OSND_TYPE) TYPE, "
        "NVL(PN.PLANT_NAME,OS.SUPPLY_PLANT_CD) SUPPLY_PLANT, OS.SIZE_CD, OS.OSND_EX_QTY, OS.I_SCN_DT "
        "FROM OCI.MSPQ_EX_OSND OS "
        "LEFT JOIN OCI.MSBS_CODE_MASTER CM ON CM.CODE_CLASS_CD='PQ_OSND_TYPE' AND CM.SUB_CODE=OS.OSND_TYPE "
        "LEFT JOIN OCI.MSBS_PLANT PN ON PN.PLANT_CD=OS.SUPPLY_PLANT_CD "
        "LEFT JOIN OCI.MSPQ_INSPECT_POINT IP ON IP.PLANT_CD=OS.PLANT_CD AND IP.INSPECT_POINT_ID=OS.INSPECT_POINT_ID "
        "LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD=OS.STYLE_CD "
        f"WHERE OS.CANCEL_YN='N' AND OS.CFM_DT IS NOT NULL AND OS.SUPPLY_PLANT_CD='{plant}' "
        f"AND OS.OSND_DATE BETWEEN '{d_from}' AND '{d_to}') "
        f"SELECT LINE, '{win}' DT, CMP, MODEL, STYLE_DISP STYLE, COLOR_CD COLORV, TYPE, SUPPLY_PLANT SUP, 'BALANCE' STATUSV, "
        "SUM(CASE WHEN I_SCN_DT IS NULL THEN OSND_EX_QTY ELSE 0 END)/2 TOT, " + zc + " "
        "FROM BASE GROUP BY LINE,CMP,MODEL,STYLE_DISP,COLOR_CD,TYPE,SUPPLY_PLANT "
        "HAVING SUM(CASE WHEN I_SCN_DT IS NULL THEN OSND_EX_QTY ELSE 0 END)>0 ORDER BY LINE,STYLE"
    )

# ===== No.5 3-3. Balance IP Outgoing Market (동·라인·일자버킷 양식) =====
_OM_COLOR_JOIN = (
    "LEFT JOIN (SELECT style_cd, mcs_color_cd FROM (SELECT style_cd, mcs_color_cd, "
    "ROW_NUMBER() OVER (PARTITION BY style_cd ORDER BY CASE WHEN mcs_color_cd='NONE' THEN 1 ELSE 0 END, COUNT(*) DESC) rn "
    "FROM OCI.MSPD_BATCH_PLAN WHERE mcs_color_cd IS NOT NULL GROUP BY style_cd, mcs_color_cd) WHERE rn=1) cc ON cc.style_cd=o.style_cd"
)
OM_FAMILIES = {"IP": ["II", "IP"], "PH": ["PH", "PP"], "OS": ["OS"]}   # No.5(Outgoing Market) 계열 단일 출처 — market_engine.SHEETS 가 이걸 파생(계열 변경은 여기 한 곳만). PH 는 CP 제외(현업).

def outgoing_market_sheet_sql(families, plants, d_from, d_to, strict=False):
    """No.5 시트(IP/PH/OS)용 미출고 SQL. 반환 10컬럼: WCG,PLANT_CD,ITEM_CLASS,FA_WC_CD,MODEL,GEN,STYLE_CD,FA_DATE,QTY,COLOR.
    strict=False : OCI 미동기화 임시(느슨한 마감 NOT EXISTS, MOVE 게이트 생략) — 기존 운영값.
    strict=True  : GMES 정식 P_MSPD90000S_Q_V14 'O'(Outgoing) 로직 — 엄격 CLOSING_YN='N' +
                   '같은 생산그룹/부품이 다른 창고(BASE_WH)로 나가는 MOVE 실적 존재' EXISTS.
                   [반영] 현업이 MSPD_PCARD_RESULT 에 PROD 만 적재하던 것을 MOVE 도 적재(2026-07)한 뒤 사용 가능.
                   MOVE 실적이 없으면 정식 판정이 0건이 되므로, MOVE 적재 확인 후에만 켤 것."""
    F = _inlist(families); P = _inlist(plants)
    if strict:
        return (
            "SELECT NVL(w2.wc_group_cd,' ') wcg, o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' ') model, "
            "NVL(i.gender,' ') gen, o.style_cd, o.fa_date, SUM(o.out_qty) qty, MAX(cc.mcs_color_cd) color "
            "FROM (SELECT R.FA_WC_CD, R.ITEM_CLASS, R.FA_DATE, R.STYLE_CD, R.PLANT_CD, R.PLAN_PROD_WC_CD, R.PROD_GROUP_NO, SUM(R.PCARD_QTY) out_qty "
            "FROM OCI.MSPD_PCARD_RESULT R "
            f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD IN ({P}) AND R.PROD_MOVE_TYPE='PROD' "
            f"AND R.ITEM_CLASS_TYPE IN ({F}) AND R.END_ROUTING_YN='Y' AND R.OUT_DATE='19991231' "
            "AND (R.PROD_GROUP_NO,R.PLANT_CD) IN (SELECT PROD_GROUP_NO,PLANT_CD FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN='N') "
            "GROUP BY R.FA_WC_CD,R.ITEM_CLASS,R.FA_DATE,R.STYLE_CD,R.PLANT_CD,R.PLAN_PROD_WC_CD,R.PROD_GROUP_NO HAVING SUM(R.PCARD_QTY)>0) o "
            "JOIN OCI.MSBS_WORK_CENTER w ON o.plant_cd=w.plant_cd AND o.plan_prod_wc_cd=w.wc_cd "
            "LEFT JOIN OCI.MSBS_ITEM_STYLE i ON i.style_cd=o.style_cd "
            "LEFT JOIN OCI.MSBS_WORK_CENTER w2 ON w2.plant_cd=o.plant_cd AND w2.wc_cd=o.fa_wc_cd " + _OM_COLOR_JOIN + " "
            "WHERE EXISTS (SELECT 1 FROM OCI.MSPD_PCARD_RESULT I "
            "JOIN OCI.MSBS_WORK_CENTER WC ON I.PLANT_CD=WC.PLANT_CD AND I.PLAN_PROD_WC_CD=WC.WC_CD "
            "WHERE I.PROD_GROUP_NO=o.PROD_GROUP_NO AND I.ITEM_CLASS=o.ITEM_CLASS "
            "AND I.PROD_MOVE_TYPE='MOVE' AND I.END_ROUTING_YN='Y' AND WC.BASE_WH_CD<>w.BASE_WH_CD) "
            "GROUP BY NVL(w2.wc_group_cd,' '), o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' '), NVL(i.gender,' '), o.style_cd, o.fa_date"
        )
    return (
        "SELECT NVL(w.wc_group_cd,' ') wcg, o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' ') model, "
        "NVL(i.gender,' ') gen, o.style_cd, o.fa_date, SUM(o.out_qty) qty, MAX(cc.mcs_color_cd) color "
        "FROM (SELECT R.FA_WC_CD, R.ITEM_CLASS, R.FA_DATE, R.STYLE_CD, R.PLANT_CD, R.PROD_GROUP_NO, SUM(R.PCARD_QTY) out_qty "
        "FROM OCI.MSPD_PCARD_RESULT R "
        f"WHERE R.FA_DATE BETWEEN '{d_from}' AND '{d_to}' AND R.PLANT_CD IN ({P}) AND R.PROD_MOVE_TYPE='PROD' "
        f"AND R.ITEM_CLASS_TYPE IN ({F}) AND R.END_ROUTING_YN='Y' AND R.OUT_DATE='19991231' "
        "AND NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g WHERE g.prod_group_no=R.prod_group_no AND g.plant_cd=R.plant_cd AND g.closing_yn='Y') "
        "GROUP BY R.FA_WC_CD,R.ITEM_CLASS,R.FA_DATE,R.STYLE_CD,R.PLANT_CD,R.PROD_GROUP_NO HAVING SUM(R.PCARD_QTY)>0) o "
        "LEFT JOIN OCI.MSBS_ITEM_STYLE i ON i.style_cd=o.style_cd "
        "LEFT JOIN OCI.MSBS_WORK_CENTER w ON w.plant_cd=o.plant_cd AND w.wc_cd=o.fa_wc_cd " + _OM_COLOR_JOIN + " "
        "GROUP BY NVL(w.wc_group_cd,' '), o.plant_cd, o.item_class, o.fa_wc_cd, NVL(i.model_name,' '), NVL(i.gender,' '), o.style_cd, o.fa_date"
    )

def outgoing_market_scan_sql(plants, d_from, d_to):
    """No.5 SCAN BEM/BEP. 반환: PLANT_CD,FA_WC_CD,STYLE_CD,Q."""
    return (
        "SELECT plant_cd, fa_wc_cd, style_cd, SUM(prod_qty) q FROM OCI.POP_PCARD_SCAN "
        "WHERE op_cd IN ('BEM','BEP') AND NVL(cancel_flag,'N')<>'Y' "
        f"AND plant_cd IN ({_inlist(plants)}) AND scan_ymd BETWEEN '{d_from}' AND '{d_to}' GROUP BY plant_cd, fa_wc_cd, style_cd"
    )

def outgoing_market_dickp_sql(plants, d_from, d_to):
    """No.5 SCAN DI CKP — CKP 출고 스캔(현업 확인: MSPD_PCARD_RESULT 에 존재, SCAN_PSID 미사용).
    생산 출고 스캔(PROD·OUT_DATE) + MOVE 이동 스캔(MOVE·IN_DATE = 현업이 새로 적재한 분) 합산.
    반환: PLANT_CD,FA_WC_CD,STYLE_CD,Q  (outgoing_market_scan_sql 과 동일 포맷 → read_scan_map 재사용)."""
    P = _inlist(plants)
    return (
        "SELECT plant_cd, fa_wc_cd, style_cd, SUM(pcard_qty) q FROM OCI.MSPD_PCARD_RESULT "
        f"WHERE plant_cd IN ({P}) AND result_type='SCAN' AND end_routing_yn='Y' "
        f"AND ((prod_move_type='PROD' AND out_date BETWEEN '{d_from}' AND '{d_to}') "
        f"OR (prod_move_type='MOVE' AND in_date BETWEEN '{d_from}' AND '{d_to}')) "
        "GROUP BY plant_cd, fa_wc_cd, style_cd"
    )


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
