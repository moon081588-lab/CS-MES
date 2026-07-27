# Functions — Production Status

생산 실적 도메인 (SCR-002, P_MSPD29000S_Q_V06) 의 SQL 골격 모음.

`workflows/production-status.md` 가 절차·함정·검증을 다루고, 이 파일은 **SQL 골격** 만 모은다.
workflow 의 각 단계에서 이 파일의 해당 함수를 참조한다.

**바인드 변수 규약**:
- `:V_DATE` — YYYYMMDD VARCHAR8 (예: '20260326')
- `:V_PLANT` — PLANT_CD 단일 (예: '3110')
- `:V_PLANT_LIST` — IN 절용 멀티 (예: '3110','3120')
- `:V_COUNTRY` — COUNTRY_CD (예: '3000' = Indonesia)
- `:V_OP` — OP_CD 단일 (예: 'IPI')
- `:V_OP_LIST` — IN 절용 멀티 (예: 'IPI','IPU','PHH','PHM','PHU')
- `:V_ICT` — ITEM_CLASS_TYPE 단일 (예: 'UP', 'CP', 'II')

---

## 목차

| 함수 | 분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_main_tree`](#fn_main_tree) | A. Process 트리 | §3-A |
| [`fn_country_from_plant`](#fn_country_from_plant) | B 전제 | §3-B 전제 |
| [`fn_detail_line_hourly`](#fn_detail_line_hourly) | B. 라인별 시간/시프트 | §3-B |
| [`fn_wc_group_subtotal`](#fn_wc_group_subtotal) | B-2. W/C Group 소계 | §3-B-2 |
| [`fn_op_group_breakdown`](#fn_op_group_breakdown) | OP 묶음 분해 (옵션 A) | §3-B 부록 |
| [`fn_op_group_distinct_card`](#fn_op_group_distinct_card) | OP 묶음 카드 중복 제거 (옵션 B) | §3-B 부록 |
| [`fn_detail_style_size_pivot`](#fn_detail_style_size_pivot) | C. 스타일별 사이즈 PIVOT | §3-C |
| [`fn_shift_mapping`](#fn_shift_mapping) | D. 시프트 시간대 메타 | §3-D |
| [`fn_item_class_type_candidates`](#fn_item_class_type_candidates) | DETAIL 분석 전 ICT 후보 조회 | §5-6 |

---

## `fn_main_tree`

**용도**: ITPO_TYPE × ITEM_CLASS × OP_CD 별 PRODUCT/OUTGOING 합계 (화면 좌측 Process 트리).

**사용 metric**: `production_qty`, `outgoing_qty`

**핵심 룰**:
- 실적: `PROD_DATE` 기준
- 출고: `OUT_DATE` 기준
- 둘 다 `ITPO_WC_PLANT_CD` 로 Plant 필터 (실제 작업 발생)
- MAIN 분기는 ITEM_CLASS_TYPE 필터 **박지 말 것** (트리가 일부만 보임)

```sql
WITH PRODUCTION_DT AS (
  SELECT 
    'PRODUCT'           AS ITPO_TYPE,
    ITEM_CLASS_TYPE,
    ITEM_CLASS,
    OP_CD,
    SUM(PCARD_QTY)      AS QTY
  FROM OCI.MSPD_PCARD_RESULT
  WHERE PROD_DATE         = :V_DATE
    AND PROD_MOVE_TYPE    = 'PROD'
    AND ITPO_WC_PLANT_CD IN ( :V_PLANT_LIST )
    AND OP_CD            IN ( :V_OP_LIST )
  GROUP BY ITEM_CLASS_TYPE, ITEM_CLASS, OP_CD
),
OUTGOING_DT AS (
  SELECT 
    'OUTGOING'          AS ITPO_TYPE,
    ITEM_CLASS_TYPE,
    ITEM_CLASS,
    OP_CD,
    SUM(PCARD_QTY)      AS QTY
  FROM OCI.MSPD_PCARD_RESULT
  WHERE OUT_DATE          = :V_DATE
    AND PROD_MOVE_TYPE    = 'PROD'
    AND ITPO_WC_PLANT_CD IN ( :V_PLANT_LIST )
    AND OP_CD            IN ( :V_OP_LIST )
  GROUP BY ITEM_CLASS_TYPE, ITEM_CLASS, OP_CD
)
SELECT * FROM PRODUCTION_DT
UNION ALL
SELECT * FROM OUTGOING_DT
ORDER BY ITPO_TYPE, OP_CD, ITEM_CLASS_TYPE, ITEM_CLASS;
```

[확정: P_MSPD29000S_Q_V06 라인 130-205 검증]

---

## `fn_country_from_plant`

**용도**: PLANT_CD 로부터 COUNTRY_CD 조회. `fn_detail_line_hourly` 의 WC_LIST CTE 가 PLANT 필터가 아닌 COUNTRY 필터를 쓰므로 사전 변환 필요.

```sql
SELECT ORG_CD AS COUNTRY_CD
  FROM OCI.MSBS_ORGANIZATION_SUB
 WHERE SUB_ORG_TYPE = 'GMES_PLANT' AND SUB_ORG_CD = :V_PLANT;
-- 현재 환경 4 PLANT 모두 COUNTRY 3000 (Indonesia)
```

---

## `fn_detail_line_hourly`

**용도**: 화면 그리드 재현 — W/C Group × Line × Plan / Sum / Shift1/2/3 / HH_06~05 / %.

**사용 metric**: `plan_qty`, `sum_qty`, `shift1/2/3_qty`, `achievement_rate`

**구조**: 3 CTE + 마스터 LEFT JOIN
1. `WC_LIST` — COUNTRY 단위 라인 마스터 (그날 활동 0인 라인도 표시)
2. `PLAN_DT` — 계획 LEG (`PLANT_CD` + `PLAN_PROD_DATE` 기준)
3. `PROD_DT` — 실적 LEG (`ITPO_WC_PLANT_CD` + `PROD_DATE` 기준, sentinel 제외)

**핵심 룰**:
- **Plant 컬럼 두 개**: Plan→`PLANT_CD`, 실적→`ITPO_WC_PLANT_CD`
- COUNTRY 변환 선행 (`fn_country_from_plant`)
- DETAIL 분기는 ITEM_CLASS_TYPE 강제 동등
- 실적 sentinel 제외: `PROD_DT > TO_DATE('20010101','YYYYMMDD')`
- PROD_RT 는 **raw_level_form** (라인별 ROUND 후 ×100). 그룹 소계/총계는 `fn_wc_group_subtotal` 의 final_form

```sql
WITH WC_LIST AS (
  -- COUNTRY 단위 라인 마스터 (PLANT 필터 없음 — 그날 생산 0 라인도 표시)
  SELECT
    SGW.WC_CD,
    SGW.VIEW_GROUP_CD,                  -- 화면 'Line' (예: 'L 03')
    SGW.SUB_TOTAL_CD,                   -- 화면 'W/C Group' (예: 'A1')
    SGV.SUM_GROUP_MAME AS LINE_NAME,
    SGV.SORT_SEQ       AS LINE_SORT_SEQ,
    SGT.SUM_GROUP_MAME AS WC_GROUP_NAME,
    SGT.SORT_SEQ       AS GROUP_SORT_SEQ
  FROM      OCI.MSBS_SUM_GROUP_WC SGW
  LEFT JOIN OCI.MSBS_SUM_GROUP_CD SGV
         ON SGV.COUNTRY_CD     = SGW.COUNTRY_CD
        AND SGV.FORM_ID        = SGW.FORM_ID
        AND SGV.SUM_GROUP_CD   = SGW.VIEW_GROUP_CD
        AND SGV.SUM_GROUP_TYPE = 'VIEW_GROUP'
        AND SGV.USE_YN = 'Y'
  LEFT JOIN OCI.MSBS_SUM_GROUP_CD SGT
         ON SGT.COUNTRY_CD     = SGW.COUNTRY_CD
        AND SGT.FORM_ID        = SGW.FORM_ID
        AND SGT.SUM_GROUP_CD   = SGW.SUB_TOTAL_CD
        AND SGT.SUM_GROUP_TYPE = 'SUB_TOTAL'
        AND SGT.USE_YN = 'Y'
  WHERE SGW.COUNTRY_CD = :V_COUNTRY
    AND SGW.FORM_ID    = 'MSPD22000S'
),
PLAN_DT AS (
  -- 계획: PLAN_PROD_DATE / PLANT_CD 기준 (실적과 다름!)
  SELECT FA_WC_CD, SUM(PCARD_QTY) AS PLAN_QTY
    FROM OCI.MSPD_PCARD_RESULT
   WHERE PLAN_PROD_DATE = :V_DATE
     AND PROD_MOVE_TYPE = 'PROD'
     AND ITEM_CLASS_TYPE = :V_ICT       -- DETAIL 에서만 강제 동등
     AND PLANT_CD = :V_PLANT
     AND OP_CD = :V_OP                  -- DETAIL: 단일 OP
   GROUP BY FA_WC_CD
),
PROD_DT AS (
  -- 실적: PROD_DATE / ITPO_WC_PLANT_CD 기준 + sentinel 제외
  SELECT
    FA_WC_CD,
    SUM(CASE WHEN PROD_DT > TO_DATE('20010101','YYYYMMDD')
             THEN PCARD_QTY ELSE 0 END) AS SUM_QTY,
    SUM(CASE WHEN FN_GET_BT_SHIFT(SUBSTR(PROD_WH_CD,3,2), PROD_DATE, TO_CHAR(PROD_DT,'HH24MISS'))='S1'
             THEN PCARD_QTY ELSE 0 END) AS SHIFT1,
    SUM(CASE WHEN FN_GET_BT_SHIFT(SUBSTR(PROD_WH_CD,3,2), PROD_DATE, TO_CHAR(PROD_DT,'HH24MISS'))='S2'
             THEN PCARD_QTY ELSE 0 END) AS SHIFT2,
    SUM(CASE WHEN FN_GET_BT_SHIFT(SUBSTR(PROD_WH_CD,3,2), PROD_DATE, TO_CHAR(PROD_DT,'HH24MISS'))='S3'
             THEN PCARD_QTY ELSE 0 END) AS SHIFT3,
    -- 24개 시간대 (06→05 순서, 화면 컬럼 순서 그대로)
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='06' THEN PCARD_QTY ELSE 0 END) AS HH_06,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='07' THEN PCARD_QTY ELSE 0 END) AS HH_07,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='08' THEN PCARD_QTY ELSE 0 END) AS HH_08,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='09' THEN PCARD_QTY ELSE 0 END) AS HH_09,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='10' THEN PCARD_QTY ELSE 0 END) AS HH_10,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='11' THEN PCARD_QTY ELSE 0 END) AS HH_11,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='12' THEN PCARD_QTY ELSE 0 END) AS HH_12,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='13' THEN PCARD_QTY ELSE 0 END) AS HH_13,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='14' THEN PCARD_QTY ELSE 0 END) AS HH_14,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='15' THEN PCARD_QTY ELSE 0 END) AS HH_15,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='16' THEN PCARD_QTY ELSE 0 END) AS HH_16,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='17' THEN PCARD_QTY ELSE 0 END) AS HH_17,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='18' THEN PCARD_QTY ELSE 0 END) AS HH_18,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='19' THEN PCARD_QTY ELSE 0 END) AS HH_19,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='20' THEN PCARD_QTY ELSE 0 END) AS HH_20,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='21' THEN PCARD_QTY ELSE 0 END) AS HH_21,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='22' THEN PCARD_QTY ELSE 0 END) AS HH_22,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='23' THEN PCARD_QTY ELSE 0 END) AS HH_23,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='00' THEN PCARD_QTY ELSE 0 END) AS HH_00,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='01' THEN PCARD_QTY ELSE 0 END) AS HH_01,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='02' THEN PCARD_QTY ELSE 0 END) AS HH_02,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='03' THEN PCARD_QTY ELSE 0 END) AS HH_03,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='04' THEN PCARD_QTY ELSE 0 END) AS HH_04,
    SUM(CASE WHEN PROD_DT>TO_DATE('20010101','YYYYMMDD') AND TO_CHAR(PROD_DT,'HH24')='05' THEN PCARD_QTY ELSE 0 END) AS HH_05
  FROM OCI.MSPD_PCARD_RESULT
  WHERE PROD_DATE = :V_DATE
    AND PROD_MOVE_TYPE = 'PROD'
    AND ITEM_CLASS_TYPE = :V_ICT
    AND ITPO_WC_PLANT_CD = :V_PLANT
    AND OP_CD = :V_OP
  GROUP BY FA_WC_CD
)
SELECT
  W.SUB_TOTAL_CD     AS WC_GROUP_CD,
  W.WC_GROUP_NAME,
  W.GROUP_SORT_SEQ,
  W.VIEW_GROUP_CD    AS LINE_CD,
  W.LINE_NAME,
  W.LINE_SORT_SEQ,
  NVL(PL.PLAN_QTY,0) AS PLAN_QTY,
  NVL(PR.SUM_QTY,0)  AS SUM_QTY,
  NVL(PR.SHIFT1,0)   AS SHIFT1,
  NVL(PR.SHIFT2,0)   AS SHIFT2,
  NVL(PR.SHIFT3,0)   AS SHIFT3,
  NVL(PR.HH_06,0) AS HH_06, NVL(PR.HH_07,0) AS HH_07, NVL(PR.HH_08,0) AS HH_08,
  NVL(PR.HH_09,0) AS HH_09, NVL(PR.HH_10,0) AS HH_10, NVL(PR.HH_11,0) AS HH_11,
  NVL(PR.HH_12,0) AS HH_12, NVL(PR.HH_13,0) AS HH_13, NVL(PR.HH_14,0) AS HH_14,
  NVL(PR.HH_15,0) AS HH_15, NVL(PR.HH_16,0) AS HH_16, NVL(PR.HH_17,0) AS HH_17,
  NVL(PR.HH_18,0) AS HH_18, NVL(PR.HH_19,0) AS HH_19, NVL(PR.HH_20,0) AS HH_20,
  NVL(PR.HH_21,0) AS HH_21, NVL(PR.HH_22,0) AS HH_22, NVL(PR.HH_23,0) AS HH_23,
  NVL(PR.HH_00,0) AS HH_00, NVL(PR.HH_01,0) AS HH_01, NVL(PR.HH_02,0) AS HH_02,
  NVL(PR.HH_03,0) AS HH_03, NVL(PR.HH_04,0) AS HH_04, NVL(PR.HH_05,0) AS HH_05,
  -- raw_level_form: 라인별 셀 % (화면 % 컬럼)
  CASE WHEN NVL(PL.PLAN_QTY,0) <> 0
       THEN ROUND( NVL(PR.SUM_QTY,0) / PL.PLAN_QTY, 2 ) * 100
       ELSE 0 END AS PROD_RT
FROM      WC_LIST W
LEFT JOIN PLAN_DT PL ON W.WC_CD = PL.FA_WC_CD
LEFT JOIN PROD_DT PR ON W.WC_CD = PR.FA_WC_CD
-- 그날 활동 0 라인도 표시 (화면 캡처와 일치). 숨기고 싶으면 아래 WHERE 추가:
--   WHERE NVL(PL.PLAN_QTY,0) + NVL(PR.SUM_QTY,0) > 0
ORDER BY W.GROUP_SORT_SEQ, W.SUB_TOTAL_CD, W.LINE_SORT_SEQ, W.VIEW_GROUP_CD;
```

[확정: P_MSPD29000S_Q_V06 라인 291/313/343-446 + WC_LIST CTE 검증]

---

## `fn_wc_group_subtotal`

**용도**: `fn_detail_line_hourly` 결과를 `SUB_TOTAL_CD` (W/C Group) 단위로 한 번 더 묶음 (화면 그리드 회색 헤더 행). PROD_RT 는 **final_form** 사용.

```sql
SELECT
  W.SUB_TOTAL_CD,
  SUM(PLAN_QTY) AS PLAN_QTY,
  SUM(SUM_QTY)  AS SUM_QTY,
  SUM(SHIFT1)   AS SHIFT1,
  SUM(SHIFT2)   AS SHIFT2,
  SUM(SHIFT3)   AS SHIFT3,
  -- HH_06~HH_05 동일
  CAST(CASE WHEN SUM(PLAN_QTY)=0 THEN 0
            ELSE SUM(SUM_QTY)/SUM(PLAN_QTY)*100 END
       AS NUMBER(19,5)) AS PROD_RT          -- ← final_form
FROM ( /* fn_detail_line_hourly 본문 결과 */ )
GROUP BY SUB_TOTAL_CD
ORDER BY MIN(GROUP_SORT_SEQ), SUB_TOTAL_CD;
```

[확정: PROD_RT 그룹 단위는 final_form 사용]

---

## `fn_op_group_breakdown`

**용도**: 자유 분석 옵션 A — OP 묶음을 OP 별로 따로 행으로 분해. 사용자 표현 "각각/별로/분해".

```sql
SELECT FA_WC_CD, OP_CD, SUM(PCARD_QTY) AS SUM_QTY
  FROM OCI.MSPD_PCARD_RESULT
 WHERE PROD_DATE = :V_DATE
   AND PROD_MOVE_TYPE = 'PROD'
   AND ITPO_WC_PLANT_CD = :V_PLANT
   AND OP_CD IN (:V_OP_LIST)
   AND PROD_DT > TO_DATE('20010101','YYYYMMDD')
 GROUP BY FA_WC_CD, OP_CD
 ORDER BY FA_WC_CD, OP_CD;
```

---

## `fn_op_group_distinct_card`

**용도**: 자유 분석 옵션 B — OP 묶음에서 카드(BARCODE_KEY) 중복 제거. 사용자 표현 "합쳐서/묶어서/총량". `distinct_card_qty` metric 으로 노출.

**왜 필요**: 같은 카드가 라우팅 따라 여러 OP row 로 분산되고 PCARD_QTY 가 모든 row 동일 → 단순 SUM 시 묶음 안 카드별 row 수만큼 부풀림.

```sql
SELECT FA_WC_CD, SUM(card_qty) AS DISTINCT_CARD_QTY
  FROM ( SELECT FA_WC_CD, BARCODE_KEY, MAX(PCARD_QTY) AS card_qty
           FROM OCI.MSPD_PCARD_RESULT
          WHERE PROD_DATE = :V_DATE
            AND PROD_MOVE_TYPE = 'PROD'
            AND ITPO_WC_PLANT_CD = :V_PLANT
            AND OP_CD IN (:V_OP_LIST)
            AND PROD_DT > TO_DATE('20010101','YYYYMMDD')
          GROUP BY FA_WC_CD, BARCODE_KEY )
 GROUP BY FA_WC_CD
 ORDER BY FA_WC_CD;
```

[확정: 2026-03-02 / FGA03 실측 검증]

---

## `fn_detail_style_size_pivot`

**용도**: 라인 × 스타일 × 시프트별 사이즈 분포 (화면 하단 Prod. Status of Size).

**사용 metric**: `production_qty` (또는 `sum_qty`)

**Size 컬럼 하드코딩 40개** (화면 PIVOT 순서 그대로, 줄이지 말 것):
```
"0T","1","1T","2","2T","3","3T","4","4T","5","5T","6","6T","7","7T",
"8","8T","9","9T","10","10T","11","11T","12","12T","13","13T","14","14T",
"15","15T","16","16T","17","17T","18","19","20","21","22"
```

```sql
SELECT 
  FA_WC_CD,
  STYLE_CD,
  FN_GET_BT_SHIFT(SUBSTR(PROD_WH_CD,3,2), PROD_DATE, TO_CHAR(PROD_DT,'HH24MISS')) AS SHIFT_CD,
  SIZE_CD,
  SUM(PCARD_QTY) AS QTY
FROM OCI.MSPD_PCARD_RESULT
WHERE PROD_DATE = :V_DATE
  AND PROD_MOVE_TYPE = 'PROD'
  AND ITEM_CLASS_TYPE = :V_ICT
  AND ITPO_WC_PLANT_CD IN ( :V_PLANT_LIST )
  AND OP_CD = :V_OP
  AND PROD_DT > TO_DATE('20010101','YYYYMMDD')
GROUP BY FA_WC_CD, STYLE_CD, 
         FN_GET_BT_SHIFT(SUBSTR(PROD_WH_CD,3,2), PROD_DATE, TO_CHAR(PROD_DT,'HH24MISS')),
         SIZE_CD
ORDER BY FA_WC_CD, STYLE_CD, SHIFT_CD, SIZE_CD;
```

**Pivot 전환**: Oracle PIVOT 절 사용 가능. 단 사이즈 종류가 많아서 동적 PIVOT 필요.
디폴트는 사이즈를 행으로 두고 답변 시 LLM 이 표로 정리.

[확정: P_MSPD29000S_Q_V06 Size PIVOT 컬럼 순서 검증]

---

## `fn_shift_mapping`

**용도**: Plant·요일별 Shift 시작/종료 시각 메타데이터 조회 (실데이터 집계 아님).

```sql
SELECT DISTINCT
  WSM.PLANT_CD,
  WSM.SHIFT_CD,
  SM.WORK_ON_HHMM,
  SM.WORK_OFF_HHMM
FROM OCI.MSBS_WC_SHIFT_MAPPING WSM
JOIN OCI.MSBS_SHIFT_MASTER SM ON WSM.PLANT_CD = SM.PLANT_CD
                             AND WSM.SHIFT_CD = SM.SHIFT_CD
JOIN OCI.MSBS_WORK_CENTER WC ON WSM.PLANT_CD = WC.PLANT_CD
                            AND WSM.WC_CD    = WC.WC_CD
WHERE WC.WC_TYPE = 'IP'
  AND WSM.PLANT_CD IN ( :V_PLANT_LIST )
  AND SM.DAY_TYPE = (CASE 
        WHEN TO_CHAR(TO_DATE(:V_DATE,'YYYYMMDD'),'d') = '6' THEN 'FRI'
        WHEN TO_CHAR(TO_DATE(:V_DATE,'YYYYMMDD'),'d') = '7' THEN 'SAT'
        ELSE 'NOR' END)
ORDER BY PLANT_CD, SHIFT_CD;
```

[확정: P_MSPD29000S_Q_V06 라인 89-117 검증]

---

## `fn_item_class_type_candidates`

**용도**: DETAIL 분석 전, 그날 해당 OP 의 ITEM_CLASS_TYPE 후보 조회 (사용자가 ICT 미지정 시 되묻기용).

**왜 필요**: DETAIL (라인별/사이즈) 은 ITEM_CLASS_TYPE 강제 동등 필수. BUA 등 일부 OP 는 CP/II 두 종류 가능.

```sql
SELECT DISTINCT ITEM_CLASS_TYPE
  FROM OCI.MSPD_PCARD_RESULT
 WHERE PROD_DATE = :V_DATE
   AND ITPO_WC_PLANT_CD = :V_PLANT
   AND OP_CD = :V_OP
   AND PROD_MOVE_TYPE = 'PROD'
   AND PROD_DT > TO_DATE('20010101','YYYYMMDD');
```

---

# DB 함수 Reference — Production Status 전용

이 도메인 SQL 골격에서 호출하는 PL/SQL 함수. 도메인 횡단 공용 함수는 `functions/_common.md` 참조.

## `FN_GET_BT_SHIFT`

**종류**: Scalar Function
**시그니처**: `FN_GET_BT_SHIFT(arg_plant VARCHAR2, arg_date VARCHAR2, arg_hh24miss VARCHAR2) RETURN VARCHAR2`
**입력**:
- `arg_plant`: Plant 약어 (`'IP'`, `'BT'`, `'51IP'`, `'51BT'`) — **PLANT_CD 전체 (`'3110'`) 가 아님**
- `arg_date`: `'YYYYMMDD'` 8 자리
- `arg_hh24miss`: `'HHMISS'` 6 자리

**출력**: `'S1'` / `'S2'` / `'S3'`. 위 Plant 약어 외 입력 시 `0` 반환.
**OCI 적용 상태**: ✗ 미적용 (2026-05-15 확인) — 인라인 풀이 사용
**역할**: 시각 → 시프트 분류 (Production Status 의 시프트 분석)

호출 위치 (기존 SQL 골격 안):
- `fn_detail_line_hourly` (§3-B)
- `fn_shift_mapping` (§3-D)
- `fn_op_group_breakdown` (§3-B 부록)

### 호출 방식 (OCI 적용 시)

```sql
FN_GET_BT_SHIFT(
  SUBSTR(PROD_WH_CD, 3, 2),    -- 'IP' 또는 'BT' 추출
  PROD_DATE,
  TO_CHAR(PROD_DT, 'HH24MISS')
)
```

### 인라인 풀이 (현재 권장)

함수 본문은 `DAY_TYPE(NOR/FRI/SAT) × PLANT(IP/BT) × SHIFT(S1/S2/S3)` 의 시간대 매핑 테이블 lookup. 인라인은 큰 CASE WHEN.

토요일 BT 의 S3 가 자정을 넘어 익일 06:29 까지 가는 게 함정. PROD_DATE 는 시프트 시작일 기준이라 인라인 결정 시에도 그날의 day_type 으로 판정.

```sql
-- IP / BT 공통 인라인 (Plant 약어 추출 → SHIFT 결정)
WITH BASE AS (
  SELECT R.*,
         SUBSTR(R.PROD_WH_CD, 3, 2)        AS PLANT_ABBR,    -- 'IP' or 'BT'
         TO_CHAR(R.PROD_DT, 'HH24MISS')    AS HHMM,
         CASE WHEN TO_CHAR(TO_DATE(R.PROD_DATE,'YYYYMMDD'),'DY','NLS_DATE_LANGUAGE=ENGLISH')
                   IN ('FRI','SAT')
              THEN TO_CHAR(TO_DATE(R.PROD_DATE,'YYYYMMDD'),'DY','NLS_DATE_LANGUAGE=ENGLISH')
              ELSE 'NOR' END               AS DAY_TYPE
    FROM OCI.MSPD_PCARD_RESULT R
   WHERE R.PROD_DATE = :V_DATE
     AND R.PROD_MOVE_TYPE = 'PROD'
)
SELECT B.*,
       CASE
         -- IP / 51IP : 평일 시프트 6:30~14:29 / 14:30~22:29 / 22:30~익일 06:29
         WHEN B.PLANT_ABBR IN ('IP') AND B.DAY_TYPE = 'NOR' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '142959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '143000' AND '222959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '223000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
         -- IP / 51IP : FRI (S1 종료 15:00 로 연장)
         WHEN B.PLANT_ABBR IN ('IP') AND B.DAY_TYPE = 'FRI' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '145959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '150000' AND '225959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '230000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
         -- IP / 51IP : SAT (단축 — S1=06:30~11:29, S2=11:30~16:29, S3=16:30~익일 06:29)
         WHEN B.PLANT_ABBR IN ('IP') AND B.DAY_TYPE = 'SAT' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '112959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '113000' AND '162959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '163000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
         -- BT / 51BT : NOR / FRI 는 IP 와 동일
         WHEN B.PLANT_ABBR IN ('BT') AND B.DAY_TYPE = 'NOR' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '142959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '143000' AND '222959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '223000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
         WHEN B.PLANT_ABBR IN ('BT') AND B.DAY_TYPE = 'FRI' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '145959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '150000' AND '225959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '230000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
         -- BT / 51BT : SAT (5 working hours: S1=06:30~11:29, S2=11:30~16:29, S3=16:30~익일 06:29)
         WHEN B.PLANT_ABBR IN ('BT') AND B.DAY_TYPE = 'SAT' THEN
              CASE WHEN B.HHMM BETWEEN '063000' AND '112959' THEN 'S1'
                   WHEN B.HHMM BETWEEN '113000' AND '162959' THEN 'S2'
                   WHEN B.HHMM BETWEEN '163000' AND '235959'
                     OR B.HHMM BETWEEN '000000' AND '062959' THEN 'S3' END
       END AS SHIFT_CD
  FROM BASE B;
```

주의:
- 위 시간대는 LMES 운영계 함수 시점 (2026-05-15 추출 DDL 기준). 시프트 정책이 바뀌면 인라인도 수정 필요.
- **자정 넘김 (S3)**: BT 토요일 S3 는 16:30~익일 06:29. PROD_DATE 는 시프트 시작일 기준 (즉 토요일 23:30 작업은 PROD_DATE='토요일'). 따라서 인라인 판정 시 DAY_TYPE 도 시작일 기준 — 함수와 동일.
- **51IP / 51BT 처리**: 원본 함수가 `PLANT IN ('IP','51IP')` 그리고 `('BT','51BT')` 로 4 개 모두 받지만, `SUBSTR(PROD_WH_CD,3,2)` 는 2 자리만 추출하므로 실제로 들어오는 값은 `'IP'` / `'BT'`. 인라인도 2 자리 기준으로 통일.
- 함수가 매칭 없을 때 `NO_DATA_FOUND` 가능 (예: 시각이 시프트 범위 밖) — 인라인은 그 경우 NULL 반환. 답변 시 NULL 처리 명시.

### 원본 DDL

<details>
<summary>LMES.FN_GET_BT_SHIFT 원본 (긴 PL/SQL)</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_GET_BT_SHIFT
(
    ARG_PLANT      IN VARCHAR2,
    ARG_DATE       IN VARCHAR2,
    ARG_HH24MISS   IN VARCHAR2
)
  RETURN VARCHAR2 AS RTN VARCHAR2(3);
  ARG_DAY_TYPE      VARCHAR2(3);
BEGIN
    SELECT TO_CHAR(TO_DATE(ARG_DATE, 'YYYYMMDD'), 'DY', 'NLS_DATE_LANGUAGE = ENGLISH')
      INTO ARG_DAY_TYPE FROM DUAL;

    IF  ARG_DAY_TYPE NOT IN ('FRI','SAT') THEN ARG_DAY_TYPE := 'NOR'; END IF;

    IF ARG_PLANT IN ('IP', '51IP') THEN
        SELECT SHIFT INTO RTN
          FROM (
            SELECT 'NOR' AS DAY, 'S1' AS SHIFT, '063000' AS START_TIME, '142959' AS END_TIME FROM DUAL UNION ALL
            SELECT 'NOR', 'S2', '143000', '222959' FROM DUAL UNION ALL
            SELECT 'NOR', 'S3', '223000', '235959' FROM DUAL UNION ALL
            SELECT 'NOR', 'S3', '000000', '062959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S1', '063000', '145959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S2', '150000', '225959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S3', '230000', '235959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S3', '000000', '062959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S1', '063000', '112959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S2', '113000', '162959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '163000', '212959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '213000', '235959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '000000', '062959' FROM DUAL
          )
         WHERE DAY = ARG_DAY_TYPE
           AND ARG_HH24MISS BETWEEN START_TIME AND END_TIME;
        RETURN RTN;
    END IF;

    IF ARG_PLANT IN ('BT', '51BT') THEN
        -- 동일한 NOR/FRI 매핑 + SAT 단축 5h 매핑 (2023.11.14 변경, 2025.03.03 S3 종료 자정 넘김 연장)
        -- (원본 코드의 SAT 부분은 5 working hours 활성화. 7h 버전은 주석 처리)
        SELECT SHIFT INTO RTN
          FROM (
            SELECT 'NOR' AS DAY, 'S1' AS SHIFT, '063000' AS START_TIME, '142959' AS END_TIME FROM DUAL UNION ALL
            SELECT 'NOR', 'S2', '143000', '222959' FROM DUAL UNION ALL
            SELECT 'NOR', 'S3', '223000', '235959' FROM DUAL UNION ALL
            SELECT 'NOR', 'S3', '000000', '062959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S1', '063000', '145959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S2', '150000', '225959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S3', '230000', '235959' FROM DUAL UNION ALL
            SELECT 'FRI', 'S3', '000000', '062959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S1', '063000', '112959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S2', '113000', '162959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '163000', '212959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '213000', '235959' FROM DUAL UNION ALL
            SELECT 'SAT', 'S3', '000000', '062959' FROM DUAL
          )
         WHERE DAY = ARG_DAY_TYPE
           AND ARG_HH24MISS BETWEEN START_TIME AND END_TIME;
        RETURN RTN;
    END IF;

    IF ARG_PLANT NOT IN ('IP','BT') THEN
        RETURN 0;
    END IF;
END;
/
```

(원본 파일 `/mnt/user-data/uploads/FN_GET_BT_SHIFT.txt` 의 주석/비활성 분기 다수 제거. 활성 로직만 보존.)

</details>
