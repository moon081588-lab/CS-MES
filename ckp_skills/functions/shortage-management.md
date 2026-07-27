# Functions — Shortage Management

부족분 관리 도메인 (SCR-001, P_MSPD90000S_Q_V14) 의 SQL 골격 모음.

`workflows/shortage-management.md` 가 절차·함정·검증을 다루고, 이 파일은 **SQL 골격** 만 모은다.

**바인드 변수 규약**:
- `:V_DATE_F`, `:V_DATE_T` — FA_DATE 범위 (YYYYMMDD VARCHAR8)
- `:V_PLANT_LIST` — IN 절용 PLANT_CD 리스트
- `:V_OP_LIST` — IN 절용 OP_CD 리스트 (예: 'IPI','IPU','PHH','PHM','PHU')

**공통 룰**:
- Plant 필터는 **`PLANT_CD`** (실적 컬럼 `ITPO_WC_PLANT_CD` 가 아님 — 부족분은 계획 책임 공장 기준)
- `MSPD_PROD_GROUP.CLOSING_YN = 'N'` 필수 — 마감된 그룹 제외
- `PROD_MOVE_TYPE = 'PROD'`
- 미생산 판정: `PROD_DATE = '19991231'`
- 미출고 판정: `OUT_DATE = '19991231'` + `END_ROUTING_YN = 'Y'`

---

## 목차

| 함수 | 분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_shortage_balance`](#fn_shortage_balance) | A. 부족분 잔량 (현재 시점) | §3-A |
| [`fn_shortage_by_line_style_size`](#fn_shortage_by_line_style_size) | B. 라인 × 스타일 × 사이즈별 분포 | §3-B |
| [`fn_shortage_screen`](#fn_shortage_screen) | E. 화면 그대로 재현 (BALANCE IP PH PRODUCTION AFTER SCAN UV by size) | §3-E |
| [`fn_shortage_daily_trend`](#fn_shortage_daily_trend) | C. 일자별 추이 | §3-C |
| [`fn_shortage_by_op`](#fn_shortage_by_op) | D. 공정별 (OP_CD) | §3-D |
| [`fn_mcs_color_inline_oci`](#fn_mcs_color_inline_oci) | `FN_MCS_COLOR` 의 OCI 대체 (BOM 부재 시 우회) | §X |
| [`fn_mcs_color_match_check`](#fn_mcs_color_match_check) | MCS_COLOR 매칭률 진단 | §X-6 |

---

## `fn_shortage_balance`

**용도**: Production / Outgoing 부족분 전체 합계 (화면 상단 요약).

**사용 metric**: `production_shortage_qty`, `outgoing_shortage_qty`, `total_shortage_qty`, `fg_production_shortage_qty`

```sql
WITH PROD_SHORTAGE AS (
  SELECT 
    SUM(R.PCARD_QTY) AS QTY
  FROM OCI.MSPD_PCARD_RESULT R
  WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND R.PLANT_CD IN ( :V_PLANT_LIST )
    AND R.PROD_MOVE_TYPE = 'PROD'
    AND R.ITEM_CLASS_TYPE <> 'FG'              -- FG 별도
    AND R.OP_CD IN ( :V_OP_LIST )
    AND R.PROD_DATE = '19991231'                -- ★ 미생산 sentinel
    AND R.PROD_GROUP_NO IN (
      SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N'
    )
),
OUT_SHORTAGE AS (
  SELECT 
    SUM(R.PCARD_QTY) AS QTY
  FROM OCI.MSPD_PCARD_RESULT R
  WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND R.PLANT_CD IN ( :V_PLANT_LIST )
    AND R.PROD_MOVE_TYPE = 'PROD'
    AND R.ITEM_CLASS_TYPE <> 'FG'
    AND R.OP_CD IN ( :V_OP_LIST )
    AND R.END_ROUTING_YN = 'Y'                  -- 라인 마지막만
    AND R.OUT_DATE = '19991231'                 -- ★ 미출고 sentinel
    AND R.PROD_GROUP_NO IN (
      SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N'
    )
)
SELECT 
  NVL((SELECT QTY FROM PROD_SHORTAGE), 0) AS PROD_SHORTAGE,
  NVL((SELECT QTY FROM OUT_SHORTAGE), 0)  AS OUT_SHORTAGE,
  NVL((SELECT QTY FROM PROD_SHORTAGE), 0) 
    + NVL((SELECT QTY FROM OUT_SHORTAGE), 0)  AS TOTAL_SHORTAGE
FROM DUAL;
```

[확정: P_MSPD90000S_Q_V14 라인 32-205 검증]

> ⚠ 주의: 위 §3-A 합계는 **공정별 작업 잔량 개념**(END_ROUTING 무관)이라 화면 그리드의 켤레 기준과 다르다. 화면 by-size 그리드를 재현하려면 §fn_shortage_screen 을 쓸 것.

---

## `fn_shortage_by_line_style_size`

**용도**: 라인(FA_WC_CD) → 스타일 → 사이즈별 부족분 수량 (분석 능력 B, 행 단위 tidy).

**Production 기준 예시** — Outgoing 기준은 `PROD_DATE='19991231'` 줄을 `OUT_DATE='19991231' AND END_ROUTING_YN='Y'` 로 교체.

```sql
SELECT 
  R.FA_WC_CD                                        AS LINE_CD,
  ITEM.MODEL_NAME                                    AS MODEL,
  R.STYLE_CD,
  R.OP_CD,
  R.ITEM_CLASS                                       AS CMP_CD,
  FN_MCS_COLOR(R.PROD_GROUP_NO, R.ITEM_CLASS)       AS MCS_COLOR,
  R.SIZE_CD,
  SUM(R.PCARD_QTY)                                   AS SHORTAGE_QTY
FROM OCI.MSPD_PCARD_RESULT R
LEFT JOIN OCI.MSBS_ITEM_STYLE ITEM 
  ON ITEM.STYLE_CD = R.STYLE_CD
WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND R.PLANT_CD IN ( :V_PLANT_LIST )
  AND R.PROD_MOVE_TYPE = 'PROD'
  AND R.ITEM_CLASS_TYPE <> 'FG'
  AND R.OP_CD IN ( :V_OP_LIST )
  AND R.PROD_DATE = '19991231'                      -- Production Shortage
  -- 또는 R.OUT_DATE='19991231' AND END_ROUTING_YN='Y' (Outgoing Shortage)
  AND R.PROD_GROUP_NO IN (
    SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N'
  )
GROUP BY R.FA_WC_CD, ITEM.MODEL_NAME, R.STYLE_CD, R.OP_CD, R.ITEM_CLASS, 
         FN_MCS_COLOR(R.PROD_GROUP_NO, R.ITEM_CLASS), R.SIZE_CD
HAVING SUM(R.PCARD_QTY) > 0
ORDER BY R.FA_WC_CD, R.STYLE_CD, R.SIZE_CD;
```

**참고**: 화면처럼 사이즈를 컬럼(15개) 으로 PIVOT 하려면 추가 처리 — 디폴트는 행 단위.
**⚠ 화면(by size) 재현용이 아님**: 이 함수는 OP_CD 별로 GROUP BY 하고 END_ROUTING 조건이 없어 카드가 여러 공정 행으로 중복 집계된다. **화면 그리드 재현은 `fn_shortage_screen` 사용**.

---

## `fn_shortage_screen`

**용도**: **BALANCE IP PH - PRODUCTION (AFTER SCAN UV) by size** 화면 그대로 재현 (분석 능력 E).
라인 × 모델 × 스타일 × Item Class × MCS Color × FA Date × Size 부족분. SQL은 tidy(행) 형태로 반환하고, Size 컬럼 PIVOT 은 답변 단계에서 동적으로 펼친다.

**바꾸는 값 3개** (나머지 고정):
- `:FA_FROM` / `:FA_TO` — FA_DATE 범위 (YYYYMMDD)
- `:FA_WC_CSV` — FA W/C 목록 콤마 1문자열 (예: `'FGA16,FGA19'`). 비우면(NULL) 전체 라인.
- `:ICT_CSV` — Item Class Type 목록 콤마 (예: `'CP'`, `'CP,II'`). 비우면 전체(FG 제외).
  - 화면에서 **FG** 선택 시 프로시저는 내부적으로 **UP** 으로 변환 → `:ICT_CSV`에 `UP` 입력.

**고정 룰 (검증됨 — 이게 화면 숫자 재현의 조건)**:
- `PLANT_CD='3120'`(CKP) · `PROD_MOVE_TYPE='PROD'`
- `PROD_DATE='19991231'` (미생산 = **Production**, DIV='Production')
- **`END_ROUTING_YN='Y'`** ★ = 화면명의 **"AFTER SCAN UV"**(마지막 공정/UV 스캔). 카드 1장=1행으로 압축. **OP_CD 로 합치지 말 것**(빠뜨리면 약 4~5배 부풀어 화면 불일치: 5,426 → ~26,556).
- `MSPD_PROD_GROUP.CLOSING_YN='N'` 그룹만 (마감 제외)
- MCS Color: `MSPD_BATCH_PLAN` 인라인 BOM 조인 — EXACT(PROD_GROUP_NO+ITEM_CD) 우선, 없으면 STYLE fallback, FS 계열 NULL. (§fn_mcs_color_inline_oci 동일 로직, FILT 그룹으로 한정)

> Outgoing 필요 시 `PROD_DATE='19991231'` → `OUT_DATE='19991231'`, DIV 라벨 'Outgoing'. (END_ROUTING='Y' 동일 유지)

```sql
WITH FILT AS (
  SELECT R.FA_WC_CD, R.STYLE_CD, R.ITEM_CD, R.PROD_GROUP_NO,
         R.ITEM_CLASS, R.ITEM_CLASS_TYPE, R.FA_DATE, R.SIZE_CD, R.PCARD_QTY
  FROM OCI.MSPD_PCARD_RESULT R
  WHERE R.FA_DATE BETWEEN :FA_FROM AND :FA_TO          -- ① FA Date
    AND R.PLANT_CD = '3120'                            --   Plant 고정(CKP)
    AND R.PROD_MOVE_TYPE = 'PROD'
    AND R.PROD_DATE = '19991231'                       --   미생산(Production)
    AND R.END_ROUTING_YN = 'Y'                         --   ★ AFTER SCAN UV = 마지막 공정 1행
    AND ( :FA_WC_CSV IS NULL                           -- ② FA W/C (CSV, 비우면 전체)
          OR INSTR(','||:FA_WC_CSV||',', ','||R.FA_WC_CD||',') > 0 )
    AND ( :ICT_CSV IS NULL                             -- ③ Item Class Type (CSV, 비우면 전체)
          OR INSTR(','||:ICT_CSV||',', ','||R.ITEM_CLASS_TYPE||',') > 0 )
    AND R.PROD_GROUP_NO IN (SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN='N')
),
GC_EXACT AS (                                          -- MCS 컬러 1단: 정확 매칭
  SELECT B.PROD_GROUP_NO, B.PARENT_ITEM_CD,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ') WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
  FROM OCI.MSPD_BATCH_PLAN B
  WHERE B.MCS_COLOR_CD NOT IN ('NONE',' ') AND B.MCS_COLOR_CD IS NOT NULL
    AND B.PROD_GROUP_NO IN (SELECT DISTINCT PROD_GROUP_NO FROM FILT)   -- FILT 그룹 한정 → 빠름
  GROUP BY B.PROD_GROUP_NO, B.PARENT_ITEM_CD
),
GC_STYLE AS (                                          -- MCS 컬러 2단: STYLE fallback(Packing류)
  SELECT SUBSTR(B.PARENT_ITEM_CD,1,LENGTH(B.PARENT_ITEM_CD)-4) AS STYLE_NOHYPHEN,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ') WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
  FROM OCI.MSPD_BATCH_PLAN B
  WHERE B.MCS_COLOR_CD NOT IN ('NONE',' ') AND B.MCS_COLOR_CD IS NOT NULL
    AND B.PROD_GROUP_NO IN (SELECT DISTINCT PROD_GROUP_NO FROM FILT)
  GROUP BY SUBSTR(B.PARENT_ITEM_CD,1,LENGTH(B.PARENT_ITEM_CD)-4)
)
SELECT F.FA_WC_CD                        AS LINE,
       S.MODEL_NAME,
       F.STYLE_CD,
       F.ITEM_CLASS,
       CASE WHEN SUBSTR(F.ITEM_CLASS,1,2)='FS' THEN NULL           -- FS계열 색상 NULL(원본 사양)
            ELSE NVL(E.MCS_COLOR, ST.MCS_COLOR) END  AS MCS_COLOR, -- EXACT 우선, 없으면 STYLE
       F.FA_DATE,
       'Production'                      AS DIV,
       F.SIZE_CD,
       SUM(F.PCARD_QTY)                  AS QTY
FROM FILT F
LEFT JOIN OCI.MSBS_ITEM_STYLE S ON S.STYLE_CD = F.STYLE_CD
LEFT JOIN GC_EXACT E  ON E.PROD_GROUP_NO = F.PROD_GROUP_NO AND E.PARENT_ITEM_CD = F.ITEM_CD
LEFT JOIN GC_STYLE ST ON ST.STYLE_NOHYPHEN = REPLACE(F.STYLE_CD,'-','')
GROUP BY F.FA_WC_CD, S.MODEL_NAME, F.STYLE_CD, F.ITEM_CLASS,
         CASE WHEN SUBSTR(F.ITEM_CLASS,1,2)='FS' THEN NULL ELSE NVL(E.MCS_COLOR, ST.MCS_COLOR) END,
         F.FA_DATE, F.SIZE_CD
HAVING SUM(F.PCARD_QTY) > 0
ORDER BY LINE, STYLE_CD, ITEM_CLASS, FA_DATE, SIZE_CD;
```

**반환 컬럼**: `LINE, MODEL_NAME, STYLE_CD, ITEM_CLASS, MCS_COLOR, FA_DATE, DIV, SIZE_CD, QTY`

**화면 그리드로 가공 (답변 단계)**:
- `SIZE_CD` 를 컬럼으로 동적 PIVOT. 사이즈 종류는 데이터마다 다름(예: GS 스타일은 `3T` 추가) → 등장한 사이즈만 컬럼화.
- 행(Line×Style×ItemClass×Color×FA_Date) 별 합계 = `Shortage` 컬럼.
- 소계: (LINE, STYLE) 단위 `Total`, 맨 아래 MODEL_NAME 단위 `G-Total`, 맨 위 전체 `G-Total`.
- "엑셀/리포트" 요청 → §workflow §6 의 리포트화 경로(`xlsx` / `data-analysis-report`) 연계.

**검증**: `:FA_FROM='20260301' :FA_TO='20260307' :FA_WC_CSV='FGA16,FGA19' :ICT_CSV='CP'`
→ G-Total **5,426** / AIR MAX DAWN(M) 108 / P-6000 CNCPT(W) 5,318 / BV1021-020 CP01 646·150·648, CP06 634·150·648, 색상 PURE PLATINUM(04Z)·PINK RISE(6JA).

[확정: 2026-06 changshinincaipoc 검증 — END_ROUTING='Y'(AFTER SCAN UV) + CLOSING_YN='N' + BOM 컬러로 화면 by-size 그리드 정확 일치]

---

## `fn_shortage_daily_trend`

**용도**: FA_DATE 별 부족분 일자별 합계 (분석 능력 C — 추이).

**구조**:
- `DATE_RANGE` CTE 로 빈 일자도 포함 (LEFT JOIN)
- 기본 7 일 — 사용자 표현 "지난 N일"이면 `LEVEL <= N`
- 증감 분석은 LAG() 윈도우 함수 추가 가능

```sql
WITH DATE_RANGE AS (
  SELECT TO_CHAR(SYSDATE - LEVEL + 1, 'YYYYMMDD') AS FA_DATE
    FROM DUAL CONNECT BY LEVEL <= 7
),
SHORTAGE_DT AS (
  SELECT 
    R.FA_DATE,
    SUM(CASE WHEN R.PROD_DATE = '19991231' 
             AND R.ITEM_CLASS_TYPE <> 'FG'
             THEN R.PCARD_QTY ELSE 0 END) AS PROD_SHORTAGE,
    SUM(CASE WHEN R.OUT_DATE = '19991231' 
             AND R.END_ROUTING_YN = 'Y'
             AND R.ITEM_CLASS_TYPE <> 'FG'
             THEN R.PCARD_QTY ELSE 0 END) AS OUT_SHORTAGE
  FROM OCI.MSPD_PCARD_RESULT R
  WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND R.PLANT_CD IN ( :V_PLANT_LIST )
    AND R.PROD_MOVE_TYPE = 'PROD'
    AND R.OP_CD IN ( :V_OP_LIST )
    AND R.PROD_GROUP_NO IN (
      SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N'
    )
  GROUP BY R.FA_DATE
)
SELECT 
  DR.FA_DATE,
  NVL(SD.PROD_SHORTAGE, 0)  AS PROD_SHORTAGE,
  NVL(SD.OUT_SHORTAGE, 0)   AS OUT_SHORTAGE,
  NVL(SD.PROD_SHORTAGE, 0) + NVL(SD.OUT_SHORTAGE, 0) AS TOTAL_SHORTAGE
FROM DATE_RANGE DR
LEFT JOIN SHORTAGE_DT SD ON DR.FA_DATE = SD.FA_DATE
ORDER BY DR.FA_DATE;
```

---

## `fn_shortage_by_op`

**용도**: OP_CD 별 부족분 (IP/PH 공정 비교).

```sql
SELECT 
  R.OP_CD,
  CASE 
    WHEN R.OP_CD IN ('IPI','IPU')        THEN 'IP'
    WHEN R.OP_CD IN ('PHH','PHM','PHU')  THEN 'PH'
    ELSE 'ETC'
  END AS OP_GROUP,
  SUM(CASE WHEN R.PROD_DATE = '19991231' THEN R.PCARD_QTY ELSE 0 END) AS PROD_SHORTAGE,
  SUM(CASE WHEN R.OUT_DATE = '19991231' AND R.END_ROUTING_YN = 'Y'
           THEN R.PCARD_QTY ELSE 0 END) AS OUT_SHORTAGE
FROM OCI.MSPD_PCARD_RESULT R
WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND R.PLANT_CD IN ( :V_PLANT_LIST )
  AND R.PROD_MOVE_TYPE = 'PROD'
  AND R.ITEM_CLASS_TYPE <> 'FG'
  AND R.PROD_GROUP_NO IN (
    SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N'
  )
GROUP BY R.OP_CD
ORDER BY R.OP_CD;
```

---

# DB 함수 Reference — Shortage 전용

이 도메인 SQL 골격에서 호출하는 PL/SQL 함수. 도메인 횡단 공용 함수는 `functions/_common.md` 참조.

## `FN_MCS_COLOR`

**종류**: Scalar Function
**시그니처**: `FN_MCS_COLOR(v_p_prod_group_no VARCHAR2, v_p_item_class VARCHAR2) RETURN VARCHAR2`
**입력**:
- `v_p_prod_group_no`: `MSPD_PROD_GROUP.PROD_GROUP_NO`
- `v_p_item_class`: ITEM_CLASS 코드 (예: `'BE'`, `'UP'`, `'FS01'`)

**출력**: `MSPD_BATCH_PLAN.MCS_COLOR_CD` 들을 쉼표로 결합한 문자열 (`'BLK,WHT,RED'` 형식). 매칭 없거나 `item_class` 가 `'FS'` 로 시작하면 NULL.
**OCI 적용 상태**: ✗ 미적용 (2026-05-15 확인, `MSPD_PROD_ORDER_BOM` 부재) — 대체: [`fn_mcs_color_inline_oci`](#fn_mcs_color_inline_oci) 사용
**역할**: 부족분 결과 표에 MCS 컬러 정보 붙임. 같은 PROD_GROUP 안에 여러 컬러 있을 수 있음.

호출 위치 (기존 SQL 골격 안):
- `fn_shortage_by_line_style_size` (§3-B 등)

### 호출 방식 (OCI 적용 시)

```sql
SELECT R.PROD_GROUP_NO,
       R.ITEM_CLASS,
       FN_MCS_COLOR(R.PROD_GROUP_NO, R.ITEM_CLASS) AS MCS_COLOR
  FROM OCI.MSPD_PCARD_RESULT R
 WHERE R.PROD_DATE = :V_DATE
 GROUP BY R.PROD_GROUP_NO, R.ITEM_CLASS;
```

### 인라인 풀이 (현재 권장)

원본 함수는 `MSPD_BATCH_PLAN` + `MSPD_PROD_ORDER_BOM` 서브쿼리 + `XMLAGG` 문자열 집계. Oracle 11gR2+ 에선 `LISTAGG` 가 가독성 좋음.

```sql
-- 인라인: LISTAGG 로 동일 결과
SELECT R.PROD_GROUP_NO,
       R.ITEM_CLASS,
       CASE
         WHEN SUBSTR(R.ITEM_CLASS, 1, 2) = 'FS' THEN NULL    -- FS 계열은 NULL
         ELSE (
           SELECT LISTAGG(MCS_COLOR_CD, ',') WITHIN GROUP (ORDER BY MCS_COLOR_CD)
             FROM (
                SELECT DISTINCT P.MCS_COLOR_CD
                  FROM OCI.MSPD_BATCH_PLAN P
                 WHERE P.PROD_GROUP_NO = R.PROD_GROUP_NO
                   AND P.MCS_COLOR_CD <> 'NONE'
                   AND P.PARENT_ITEM_CD IN (
                     SELECT B.CHILD_ITEM_CD
                       FROM OCI.MSPD_PROD_ORDER_BOM B
                      WHERE B.PROD_GROUP_NO = R.PROD_GROUP_NO
                        AND B.ITEM_PATH LIKE '%' || R.ITEM_CLASS || '%'
                   )
              )
         )
       END AS MCS_COLOR
  FROM OCI.MSPD_PCARD_RESULT R
 WHERE R.PROD_DATE = :V_DATE
 GROUP BY R.PROD_GROUP_NO, R.ITEM_CLASS;
```

대량 행 호출 회피 — CTE 로 한 번에 build:

```sql
WITH GROUP_COLORS AS (
  SELECT P.PROD_GROUP_NO,
         B.ITEM_PATH,
         LISTAGG(DISTINCT P.MCS_COLOR_CD, ',') 
            WITHIN GROUP (ORDER BY P.MCS_COLOR_CD) AS MCS_COLOR
    FROM OCI.MSPD_BATCH_PLAN P
    INNER JOIN OCI.MSPD_PROD_ORDER_BOM B
       ON B.PROD_GROUP_NO = P.PROD_GROUP_NO
      AND P.PARENT_ITEM_CD = B.CHILD_ITEM_CD
   WHERE P.MCS_COLOR_CD <> 'NONE'
   GROUP BY P.PROD_GROUP_NO, B.ITEM_PATH
)
SELECT R.PROD_GROUP_NO,
       R.ITEM_CLASS,
       CASE WHEN SUBSTR(R.ITEM_CLASS,1,2) = 'FS' THEN NULL
            ELSE GC.MCS_COLOR END AS MCS_COLOR
  FROM OCI.MSPD_PCARD_RESULT R
  LEFT JOIN GROUP_COLORS GC
    ON GC.PROD_GROUP_NO = R.PROD_GROUP_NO
   AND GC.ITEM_PATH LIKE '%' || R.ITEM_CLASS || '%'
 WHERE R.PROD_DATE = :V_DATE
 GROUP BY R.PROD_GROUP_NO, R.ITEM_CLASS, GC.MCS_COLOR;
```

주의:
- 원본 함수는 `XMLAGG(XMLELEMENT(...))` 사용. 같은 결과를 `LISTAGG` 로 대체 — 더 빠르고 깔끔. 단 결과 길이 4000 자 초과 시 `LISTAGG` 가 에러. 그 경우는 `XMLAGG` 유지.
- **`'FS'` 로 시작하는 ITEM_CLASS 는 항상 NULL** — 원본 함수의 마지막 조건 `SUBSTR(V_P_ITEM_CLASS,1,2) <> 'FS'`. 인라인에서 빠뜨리지 말 것.
- 함수는 NO_DATA_FOUND 시 NULL — 인라인의 서브쿼리도 매칭 없으면 NULL. 동일.

### 원본 DDL

<details>
<summary>LMES.FN_MCS_COLOR 원본</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_MCS_COLOR
(
   V_P_PROD_GROUP_NO     IN VARCHAR2
  ,V_P_ITEM_CLASS  IN VARCHAR2
)
RETURN  VARCHAR2
AS
   V_MCS_COLOR   VARCHAR2(100);
BEGIN
    SELECT SUBSTR(XMLAGG(XMLELEMENT(COL,',', B.MCS_COLOR_CD )).EXTRACT('//text()').GETSTRINGVAL(), 2) AS MSC_COLOR
    INTO V_MCS_COLOR
      FROM (SELECT DISTINCT P.MCS_COLOR_CD
              FROM MSPD_BATCH_PLAN P
             WHERE P.PROD_GROUP_NO = V_P_PROD_GROUP_NO
               AND P.PARENT_ITEM_CD IN (SELECT B.CHILD_ITEM_CD
                                          FROM MSPD_PROD_ORDER_BOM B
                                         WHERE B.PROD_GROUP_NO = V_P_PROD_GROUP_NO
                                           AND B.ITEM_PATH LIKE '%' || V_P_ITEM_CLASS || '%'
                                        )
               AND P.MCS_COLOR_CD <> 'NONE'
               AND SUBSTR(V_P_ITEM_CLASS,1,2)  <> 'FS' 
           ) B
    ;
     RETURN V_MCS_COLOR;  
 EXCEPTION WHEN NO_DATA_FOUND THEN      
     RETURN NULL;
END;
/
```

</details>

---

## `fn_mcs_color_inline_oci`

**용도**: `FN_MCS_COLOR` 의 **OCI 환경용 대체 인라인 풀이**. `MSPD_PROD_ORDER_BOM` 부재 시 사용. PCARD ↔ BATCH_PLAN 의 BOM 키 직접 매칭 + STYLE 레벨 fallback 으로 100% 매칭 보장.

**사용 metric**: `production_shortage_qty`, `outgoing_shortage_qty`, `total_shortage_qty` 중 컬러 차원이 필요한 분석 (§3-B 라인 × 스타일 × 사이즈, §3-E 화면 재현 등)

**OCI 적용 상태**: ✓ 적용 가능 (2026-05-20 검증)

**워크플로우 참조**: [`workflows/shortage-management.md §X. MCS_COLOR 인라인 풀이`](../workflows/shortage-management.md)

```sql
-- CTE 두 개 + 본 쿼리 LEFT JOIN 구조
WITH GC_EXACT AS (
  -- 1 단: 정확 매칭 (PROD_GROUP_NO, PARENT_ITEM_CD) 단위 컬러 LISTAGG
  SELECT B.PROD_GROUP_NO,
         B.PARENT_ITEM_CD,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ')
            WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
    FROM OCI.MSPD_BATCH_PLAN B
   WHERE B.MCS_COLOR_CD NOT IN ('NONE', ' ')
     AND B.MCS_COLOR_CD IS NOT NULL
   GROUP BY B.PROD_GROUP_NO, B.PARENT_ITEM_CD
),
GC_STYLE AS (
  -- 2 단 fallback: STYLE 단위 컬러 (PARENT_ITEM_CD 끝 4 자 = ITEM_CLASS 제거)
  SELECT SUBSTR(B.PARENT_ITEM_CD, 1, LENGTH(B.PARENT_ITEM_CD)-4) AS STYLE_NOHYPHEN,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ')
            WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
    FROM OCI.MSPD_BATCH_PLAN B
   WHERE B.MCS_COLOR_CD NOT IN ('NONE', ' ')
     AND B.MCS_COLOR_CD IS NOT NULL
   GROUP BY SUBSTR(B.PARENT_ITEM_CD, 1, LENGTH(B.PARENT_ITEM_CD)-4)
)
SELECT R.PROD_GROUP_NO,
       R.ITEM_CD,
       R.ITEM_CLASS,
       R.STYLE_CD,
       CASE
         WHEN SUBSTR(R.ITEM_CLASS, 1, 2) = 'FS' THEN NULL              -- FS 계열은 항상 NULL
         ELSE NVL(GC_EXACT.MCS_COLOR, GC_STYLE.MCS_COLOR)               -- EXACT 우선, fallback STYLE
       END AS MCS_COLOR
  FROM OCI.MSPD_PCARD_RESULT R
  LEFT JOIN GC_EXACT
    ON GC_EXACT.PROD_GROUP_NO = R.PROD_GROUP_NO
   AND GC_EXACT.PARENT_ITEM_CD = R.ITEM_CD
  LEFT JOIN GC_STYLE
    ON GC_STYLE.STYLE_NOHYPHEN = REPLACE(R.STYLE_CD, '-', '')
 WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND R.PLANT_CD IN ( :V_PLANT_LIST )
   /* 나머지 본 쿼리 필터 */;
```

**핵심 룰**:
- 두 CTE 모두 `MCS_COLOR_CD NOT IN ('NONE', ' ') AND IS NOT NULL` 필수 — 빈 코드 3 종 제외
- `GC_EXACT` join 키 = `(PROD_GROUP_NO, PARENT_ITEM_CD)` ↔ `(R.PROD_GROUP_NO, R.ITEM_CD)`
- `GC_STYLE` join 키 = `SUBSTR(PARENT_ITEM_CD, 1, LENGTH-4)` ↔ `REPLACE(R.STYLE_CD, '-', '')`
- `NVL(GC_EXACT, GC_STYLE)` 순서 중요 — EXACT 가 더 세밀하므로 우선
- FS 계열은 매칭 결과와 무관하게 강제 NULL — 원본 함수 사양 보존
- LISTAGG 결과 4000 자 초과 위험 시 `XMLAGG(XMLELEMENT(...)).EXTRACT('//text()').GETSTRINGVAL()` 패턴으로 교체 (§FN_MCS_COLOR 주의사항 참조)

**결과 형식**: `"BLACK(00A)"`, `"WHITE(10A)"`, `"BLACK(00A), CARGO KHAKI(3HR)"` (멀티 컬러는 콤마 결합). 화면 표시 그대로 사용 가능.

색상 키 (예: `00A`) 만 필요하면:
```sql
REGEXP_SUBSTR(MCS_COLOR, '\(([^)]+)\)', 1, 1, NULL, 1) AS COLOR_KEY
```

[확정: 2026-05-20 검증 — FA_DATE 20260308~20260314 / Plant 3120 / OP IPI,IPU,PHH,PHM,PHU 조건에서 127/127 (100%) 매칭, EXACT 87 + STYLE_FALLBACK 40, FS 제외 0]

---

## `fn_mcs_color_match_check`

**용도**: 신규 기간/조건 분석 시작 전 `fn_mcs_color_inline_oci` 의 매칭률 진단. EXACT / STYLE_FALLBACK / UNMATCHED / FS_EXCLUDED 분포 확인 → 100% 매칭 보장 여부 사전 검증.

**언제 사용**:
- 신규 기간 분석 시작 시 (1회)
- UNMATCHED 가 0 이 아니면 신규 ITEM_CLASS 패턴 의심 → workflows §X-5 함정 재점검

```sql
WITH PR_KEYS AS (
  SELECT DISTINCT R.PROD_GROUP_NO, R.ITEM_CD, R.ITEM_CLASS, R.STYLE_CD
    FROM OCI.MSPD_PCARD_RESULT R
   WHERE R.FA_DATE BETWEEN :V_DATE_F AND :V_DATE_T
     AND R.PLANT_CD IN ( :V_PLANT_LIST )
     AND R.PROD_MOVE_TYPE = 'PROD'
     AND R.ITEM_CLASS_TYPE <> 'FG'
     AND R.OP_CD IN ( :V_OP_LIST )
     AND R.PROD_GROUP_NO IN (
       SELECT PROD_GROUP_NO FROM OCI.MSPD_PROD_GROUP WHERE CLOSING_YN = 'N')
     AND (R.PROD_DATE = '19991231'
       OR (R.OUT_DATE = '19991231' AND R.END_ROUTING_YN = 'Y'))
),
GC_EXACT AS (
  SELECT B.PROD_GROUP_NO, B.PARENT_ITEM_CD,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ')
            WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
    FROM OCI.MSPD_BATCH_PLAN B
   WHERE B.MCS_COLOR_CD NOT IN ('NONE', ' ') AND B.MCS_COLOR_CD IS NOT NULL
   GROUP BY B.PROD_GROUP_NO, B.PARENT_ITEM_CD
),
GC_STYLE AS (
  SELECT SUBSTR(B.PARENT_ITEM_CD, 1, LENGTH(B.PARENT_ITEM_CD)-4) AS STYLE_NOHYPHEN,
         LISTAGG(DISTINCT B.MCS_COLOR_CD, ', ')
            WITHIN GROUP (ORDER BY B.MCS_COLOR_CD) AS MCS_COLOR
    FROM OCI.MSPD_BATCH_PLAN B
   WHERE B.MCS_COLOR_CD NOT IN ('NONE', ' ') AND B.MCS_COLOR_CD IS NOT NULL
   GROUP BY SUBSTR(B.PARENT_ITEM_CD, 1, LENGTH(B.PARENT_ITEM_CD)-4)
)
SELECT
  COUNT(*) AS TOTAL_KEYS,
  SUM(CASE WHEN SUBSTR(PR.ITEM_CLASS,1,2)='FS' THEN 1 ELSE 0 END) AS FS_EXCLUDED,
  SUM(CASE WHEN SUBSTR(PR.ITEM_CLASS,1,2)<>'FS'
                AND GC_EXACT.MCS_COLOR IS NOT NULL THEN 1 ELSE 0 END) AS EXACT_MATCH,
  SUM(CASE WHEN SUBSTR(PR.ITEM_CLASS,1,2)<>'FS'
                AND GC_EXACT.MCS_COLOR IS NULL
                AND GC_STYLE.MCS_COLOR IS NOT NULL THEN 1 ELSE 0 END) AS STYLE_FALLBACK,
  SUM(CASE WHEN SUBSTR(PR.ITEM_CLASS,1,2)<>'FS'
                AND GC_EXACT.MCS_COLOR IS NULL
                AND GC_STYLE.MCS_COLOR IS NULL THEN 1 ELSE 0 END) AS UNMATCHED
FROM PR_KEYS PR
LEFT JOIN GC_EXACT ON GC_EXACT.PROD_GROUP_NO = PR.PROD_GROUP_NO
                  AND GC_EXACT.PARENT_ITEM_CD = PR.ITEM_CD
LEFT JOIN GC_STYLE ON GC_STYLE.STYLE_NOHYPHEN = REPLACE(PR.STYLE_CD, '-', '');
```

**기대치**:

| 컬럼 | 정상 범위 | 의미 |
|---|---|---|
| TOTAL_KEYS | 데이터에 따라 가변 | 분석 기간의 고유 (PROD_GROUP, ITEM_CD, ITEM_CLASS) 키 수 |
| FS_EXCLUDED | TOTAL 의 0~소량 | 원본 사양 NULL — 매칭 계산 제외 |
| EXACT_MATCH | TOTAL 의 60~75% | BOM 자식 부품 있는 공정 (CP/II/UP 등) |
| STYLE_FALLBACK | TOTAL 의 25~40% | Packing 공정 (PP01/PP02/PP03/PP06) — 같은 스타일에서 보충 |
| UNMATCHED | **0** | 0 이 아니면 §X-5 함정 점검 |

**UNMATCHED > 0 일 때 진단**:

```sql
-- 매칭 안 된 키 패턴 확인 — BATCH_PLAN 에 부모-자식 관계 자체가 있는지 점검
WITH PR_KEYS AS ( /* 위와 동일 */ )
SELECT PR.STYLE_CD, PR.ITEM_CD, PR.ITEM_CLASS,
       (SELECT COUNT(*) FROM OCI.MSPD_BATCH_PLAN B
         WHERE B.PROD_GROUP_NO=PR.PROD_GROUP_NO
           AND B.PARENT_ITEM_CD=PR.ITEM_CD) AS BATCH_HIT_TOTAL
  FROM PR_KEYS PR
 WHERE SUBSTR(PR.ITEM_CLASS,1,2) <> 'FS'
   AND NOT EXISTS (
     SELECT 1 FROM OCI.MSPD_BATCH_PLAN B
      WHERE B.PROD_GROUP_NO = PR.PROD_GROUP_NO
        AND B.PARENT_ITEM_CD = PR.ITEM_CD
        AND B.MCS_COLOR_CD NOT IN ('NONE',' ')
        AND B.MCS_COLOR_CD IS NOT NULL
   );
```

해석:
- `BATCH_HIT_TOTAL = 0` → BATCH_PLAN 에 부모-자식 관계 자체가 없음. 신규 공정 코드 등장 가능성. STYLE fallback 으로도 안 잡히면 데이터 적재 시점 차이 의심.
- `BATCH_HIT_TOTAL > 0` → MCS_COLOR_CD 가 모두 'NONE'/공백/NULL. 컬러 미할당 스타일 (예: 샘플 단계, 컬러 코드 부여 전).

[확정: 2026-05-20 검증 — TOTAL 127, EXACT 87, STYLE_FALLBACK 40, UNMATCHED 0, FS_EXCLUDED 0]
