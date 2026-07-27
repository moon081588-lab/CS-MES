# Functions — Quality (External OS&D)

품질 관리 도메인 SQL 골격 모음. 두 화면을 커버:

| 화면 | 프로시저 | 메인 테이블 |
|---|---|---|
| **SCR-005** External OS&D Balance by Size | `LMES.P_MSPQ38100S_Q` | `OCI.MSPQ_EX_OSND` |
| **SCR-006** External OS&D Return Rate (New) | `LMES.SP_GMES00142_Q_JJ_V5` | `LMES.V_PQ_EX_OSND_V3` (OCI 부재) |

`workflows/quality-osnd.md` 가 절차·함정·검증을 다루고, 이 파일은 **SQL 골격** 만 모은다.

> ⚠️ **`V_PQ_EX_OSND_V3` 뷰는 OCI 스키마에 배포되어 있지 않다.** 원본 정의는 LMES 스키마의 LMES 뷰. SCR-006 분석을 OCI 에서 수행하려면 뷰를 직접 호출하지 말고 **부록 §V 의 재현 CTE 패턴** 또는 각 함수 안의 `_OCI` 변형 SQL 을 사용해야 한다. 뷰 원본 정의는 §V 참조.

**바인드 변수 규약**:

| 변수 | 의미 | 비고 |
|---|---|---|
| `:V_DATE_F`, `:V_DATE_T` | OSND_DATE 범위 (YYYYMMDD VARCHAR8) | SCR-005 |
| `:V_IN_DATE_F`, `:V_IN_DATE_T` | IN_DATE 범위 (YYYYMMDD VARCHAR8) | SCR-006 (실제 입고일 기준) |
| `:V_PLANT_CD` | 메인 Plant (단일) — 화면 재현은 단일 plant | 3110/3120/3210/3220 |
| `:V_PB_CD` | PB Plant 코드 (콤마 구분 다중 가능) | NULL 가능 |
| `:V_FA_WC_CD` / `:V_LINE_CD` | 라인 (FA Work Center) | NULL 가능 |
| `:V_SUPPLY_PLANT` | 공급 plant (LIKE 매칭, 단일) | 미지정 시 '' |
| `:V_SUPPLY_OP_CD` | 공급 공정 (콤마 구분 다중) | NULL 가능 |
| `:V_OSND_TYPE` | OSND 타입 (콤마 구분 다중, D/I/L/O/S) [확정: DB 직접 조회 2026-03-05] | NULL 가능 |
| `:V_STYLE` | 스타일 LIKE 매칭 | NULL 가능 |

**공통 룰**:
- `CANCEL_YN = 'N'` 필수 (취소된 OS&D 제외) — SCR-005 모든 함수
- `CFM_DT IS NOT NULL` — **SCR-005 화면 재현 시 필수** (확인 완료된 OS&D만, 프로시저 라인 104/208/294/378). 자유 분석은 생략 가능하나, 화면 숫자와 맞추려면 포함
- 출고 판정: `O_SCN_DT IS NOT NULL`
- 입고 판정: `I_SCN_DT IS NOT NULL`
- Balance = REQUEST − INCOMING (입고 안 된 것 = 처리 미완료)
- **SCR-005 사이즈별 PIVOT 은 `OSND_EX_QTY / 2`** — L/R 합산해 켤레로 환산 (라인 161-198 등)
- **SCR-005 의 LINE 은 `IP.SUB_WC_CD`** — `MSPQ_INSPECT_POINT` 의 `SUB_WC_CD` 컬럼 ([확정: 라인 80, 122])
- **SCR-005 의 CMP** = `SUBSTR(SUPPLY_OP_CD, 1, 2)` — 공정 그룹 2 글자 (IP/PH/UP 등)
- **SCR-006 의 `V_PQ_EX_OSND_V3` 는 OCI 에 없음** — 뷰 정의(§V) 를 그대로 본떠 만든 재현 CTE `OSND_V3_REPLICA` 를 함수 안에서 사용. `OCI.MSPQ_EX_OSND` + `OCI.MSPD_PCARD_RESULT` + `OCI.MSPQ_RPT_IP` + `OCI.MSPQ_MATERIAL_MOVE` 의 UNION 으로 재구성

---

## 목차

### SCR-005 — External OS&D Balance by Size

| 함수 | 분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_osnd_summary`](#fn_osnd_summary) | A. OS&D 종합 (4 Status, 단일 수치) | §3-A |
| [`fn_osnd_by_type`](#fn_osnd_by_type) | B. 타입별 (D/L/I/S) | §3-B |
| [`fn_osnd_daily_trend`](#fn_osnd_daily_trend) | C. 일자별 추이 | §3-C |
| [`fn_osnd_balance_detail`](#fn_osnd_balance_detail) | D. 후보충 잔량 상세 | §3-D |
| [`fn_osnd_plant_flow`](#fn_osnd_plant_flow) | E. 공장 간 보충 흐름 | §3-E |
| [`fn_osnd_screen_pivot`](#fn_osnd_screen_pivot) | **F. SCR-005 화면 그대로 (사이즈 PIVOT, 4 STATUS UNION)** | §3-F |
| [`fn_osnd_request_by_size`](#fn_osnd_request_by_size) | F-1. REQUEST 만 사이즈별 | §3-F |
| [`fn_osnd_outgoing_by_size`](#fn_osnd_outgoing_by_size) | F-2. OUTGOING 만 사이즈별 | §3-F |
| [`fn_osnd_incoming_by_size`](#fn_osnd_incoming_by_size) | F-3. INCOMING 만 사이즈별 | §3-F |
| [`fn_osnd_style_list`](#fn_osnd_style_list) | G. STYLE 드롭다운 리스트 | §3-G |

### 색상 (Color) Lookup — `_common.md §10` 구현체

| 함수 | 용도 | 출처 |
|---|---|---|
| [`fn_color_lookup_cte`](#fn_color_lookup_cte) | 박제 15개 색상 코드 → 색상명 CTE (즉시 join 가능) | _common.md §10-3 |
| [`fn_color_dynamic_extract`](#fn_color_dynamic_extract) | 신규 색상 코드를 `MSBS_ITEM.MCS_COLOR_CD` 텍스트 파싱으로 동적 추출 | _common.md §10-4 |
| [`fn_osnd_screen_pivot_with_color`](#fn_osnd_screen_pivot_with_color) | **SCR-005 화면 + Color 컬럼 통합 버전** (Style 별 색상 자동 매핑) | F + §10 결합 |

### SCR-006 — External OS&D Return Rate (New)

| 함수 | 분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_return_rate_daily`](#fn_return_rate_daily) | H. 일자별 Return Rate (메인 그리드, CV_2) — DEFECT 분기만 (경량) | §3-H |
| [`fn_return_rate_daily_full`](#fn_return_rate_daily_full) | H'. **화면 하단표 6행 풀 재현** — Incoming/OS&D/Replen/Rate/OS&D Rate (4분기 UNION) | §3-H |
| [`fn_return_rate_target`](#fn_return_rate_target) | I. Target 값 (차트 기준선, CV_4) | §3-I |
| [`fn_return_rate_calendar`](#fn_return_rate_calendar) | J. 달력 일자 컬럼 (피벗용, CV_1) | §3-J |
| [`fn_return_rate_break_max`](#fn_return_rate_break_max) | K. 차트 break 설정 (CV_3) | §3-K |
| [`fn_combo_plant`](#fn_combo_plant) | L. 콤보박스 — Plant | §3-L |
| [`fn_combo_process`](#fn_combo_process) | M. 콤보박스 — Process | §3-M |

---

## `fn_osnd_summary`

**용도**: REQUEST / OUTGOING / INCOMING / BALANCE 한 번에 (전체 합계 한 줄).

**사용 metric**: `osnd_request_qty`, `osnd_outgoing_qty`, `osnd_incoming_qty`, `osnd_balance_qty`

```sql
SELECT 
  -- REQUEST: 전체 발생
  SUM(CASE WHEN CANCEL_YN = 'N' 
           THEN OSND_EX_QTY ELSE 0 END)                             AS REQUEST_QTY,
  
  -- OUTGOING: 출고 완료 (O_SCN_DT IS NOT NULL)
  SUM(CASE WHEN CANCEL_YN = 'N' AND O_SCN_DT IS NOT NULL 
           THEN OSND_EX_QTY ELSE 0 END)                             AS OUTGOING_QTY,
  
  -- INCOMING: 입고 완료 (I_SCN_DT IS NOT NULL)
  SUM(CASE WHEN CANCEL_YN = 'N' AND I_SCN_DT IS NOT NULL 
           THEN OSND_EX_QTY ELSE 0 END)                             AS INCOMING_QTY,
  
  -- BALANCE: REQUEST - INCOMING (입고 안 된 것 = 처리 미완료)
  SUM(CASE WHEN CANCEL_YN = 'N' 
           THEN OSND_EX_QTY ELSE 0 END)
  - SUM(CASE WHEN CANCEL_YN = 'N' AND I_SCN_DT IS NOT NULL 
           THEN OSND_EX_QTY ELSE 0 END)                             AS BALANCE_QTY
  
FROM OCI.MSPQ_EX_OSND
WHERE OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND (OSND_TYPE IN ( :V_TYPE_LIST ) OR :V_TYPE_LIST IS NULL)
  AND ( SUPPLY_PLANT_CD IN ( :V_PLANT_LIST ) 
     OR DEMAND_PLANT_CD IN ( :V_PLANT_LIST )
     OR :V_PLANT_LIST IS NULL );
```

**참고**: 화면 그대로 재현하려면 `CFM_DT IS NOT NULL` 추가 + Plant 필터를 `OS.PLANT_CD = :V_PLANT_CD` (단일) 로 변경.

[확정: P_MSPQ38100S_Q 라인 133-415 검증]

---

## `fn_osnd_by_type`

**용도**: OSND_TYPE 별 metric. [확정: OCI DB 직접 조회 2026-03-05] D=Defective, I=Inline Defect, L=Lot Closing Shortage, O=Overrun, S=Shortage. MSBS_CODE_MASTER 로 코드 → 이름 변환.

**사용 metric**: `osnd_defective_qty`, `osnd_inline_defect_qty`, `osnd_lot_closing_shortage_qty`, `osnd_overrun_qty`, `osnd_shortage_qty`

```sql
SELECT 
  EX.OSND_TYPE,
  CM.CODE_NAME                              AS TYPE_NAME,    -- Defective/Inline Defect/Lot Closing Shortage/Overrun/Shortage
  COUNT(*)                                  AS EVENT_COUNT,
  SUM(EX.OSND_EX_QTY)                       AS REQUEST_QTY,
  SUM(CASE WHEN EX.O_SCN_DT IS NOT NULL 
           THEN EX.OSND_EX_QTY ELSE 0 END)  AS OUTGOING_QTY,
  SUM(CASE WHEN EX.I_SCN_DT IS NOT NULL 
           THEN EX.OSND_EX_QTY ELSE 0 END)  AS INCOMING_QTY
FROM OCI.MSPQ_EX_OSND EX
LEFT JOIN OCI.MSBS_CODE_MASTER CM 
  ON CM.CODE_CLASS_CD = 'PQ_OSND_TYPE'
 AND CM.SUB_CODE      = EX.OSND_TYPE
 AND CM.USE_YN        = 'Y'
WHERE EX.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND EX.CANCEL_YN = 'N'
GROUP BY EX.OSND_TYPE, CM.CODE_NAME
ORDER BY EX.OSND_TYPE;
```

**참고**: OSND_TYPE 코드 의미는 `MSBS_CODE_MASTER.CODE_CLASS_CD='PQ_OSND_TYPE'` 에서 lookup. [확정: OCI DB 직접 조회 2026-03-05] D=Defective, I=Inline Defect, L=Lot Closing Shortage, O=Overrun, S=Shortage. 비활성(USE_YN='N'): M=Miss Packing, Z=Migration. ※ 기존 기록(D=Damage, L=Lost, I=Issue)은 오류였음.

---

## `fn_osnd_daily_trend`

**용도**: OSND_DATE 별 발생량 (일자별 추이).

**사용 metric**: `osnd_request_qty`, `osnd_event_count`

```sql
WITH DATE_RANGE AS (
  SELECT TO_CHAR(TO_DATE(:V_DATE_F, 'YYYYMMDD') + LEVEL - 1, 'YYYYMMDD') AS DT
    FROM DUAL 
   CONNECT BY LEVEL <= TO_DATE(:V_DATE_T, 'YYYYMMDD') - TO_DATE(:V_DATE_F, 'YYYYMMDD') + 1
),
EVENT_DT AS (
  SELECT 
    OSND_DATE,
    COUNT(*)                       AS EVENT_COUNT,
    SUM(OSND_EX_QTY)               AS REQUEST_QTY,
    SUM(CASE WHEN OSND_TYPE='D' THEN OSND_EX_QTY ELSE 0 END) AS DAMAGE_QTY,
    SUM(CASE WHEN OSND_TYPE='L' THEN OSND_EX_QTY ELSE 0 END) AS LOST_QTY,
    SUM(CASE WHEN OSND_TYPE='I' THEN OSND_EX_QTY ELSE 0 END) AS ISSUE_QTY,
    SUM(CASE WHEN OSND_TYPE='S' THEN OSND_EX_QTY ELSE 0 END) AS SHORTAGE_QTY
  FROM OCI.MSPQ_EX_OSND
  WHERE OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND CANCEL_YN = 'N'
  GROUP BY OSND_DATE
)
SELECT 
  DR.DT                       AS OSND_DATE,
  NVL(ED.EVENT_COUNT, 0)      AS EVENT_COUNT,
  NVL(ED.REQUEST_QTY, 0)      AS REQUEST_QTY,
  NVL(ED.DAMAGE_QTY, 0)       AS DAMAGE_QTY,
  NVL(ED.LOST_QTY, 0)         AS LOST_QTY,
  NVL(ED.ISSUE_QTY, 0)        AS ISSUE_QTY,
  NVL(ED.SHORTAGE_QTY, 0)     AS SHORTAGE_QTY
FROM DATE_RANGE DR
LEFT JOIN EVENT_DT ED ON DR.DT = ED.OSND_DATE
ORDER BY DR.DT;
```

---

## `fn_osnd_balance_detail`

**용도**: 처리 안 된 OS&D (Balance > 0). 출고 미완 vs 입고 미완 구분.

**사용 metric**: `osnd_balance_qty`

**참고**: "출고는 됐고 입고는 미완" 인 게 진짜 in-transit (배송 중). "출고도 미완" 은 아직 보내지도 않은 것.

```sql
SELECT 
  EX.OSND_ID,
  EX.OSND_DATE,
  EX.OSND_TYPE,
  EX.SUPPLY_PLANT_CD,
  EX.PLANT_CD                              AS DEMAND_PLANT_CD,  -- PLANT_CD = 수요 plant
  EX.STYLE_CD, EX.SIZE_CD, EX.LR_CD,
  EX.OSND_EX_QTY,
  EX.O_SCN_DT, EX.I_SCN_DT,
  CASE 
    WHEN EX.O_SCN_DT IS NULL              THEN '출고 미완'
    WHEN EX.O_SCN_DT IS NOT NULL 
     AND EX.I_SCN_DT IS NULL              THEN '입고 미완'
    ELSE '완료'
  END                                      AS STATUS
FROM OCI.MSPQ_EX_OSND EX
WHERE EX.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND EX.CANCEL_YN = 'N'
  AND EX.I_SCN_DT IS NULL                  -- 입고 미완 = Balance > 0
ORDER BY EX.OSND_DATE, EX.OSND_ID;
```

---

## `fn_osnd_plant_flow`

**용도**: SUPPLY_PLANT_CD → PLANT_CD(수요 plant) 흐름별 수량.

```sql
SELECT 
  EX.SUPPLY_PLANT_CD,
  EX.PLANT_CD                                            AS DEMAND_PLANT_CD,
  COUNT(*)                                               AS EVENT_COUNT,
  SUM(EX.OSND_EX_QTY)                                    AS TOTAL_QTY,
  SUM(CASE WHEN EX.I_SCN_DT IS NOT NULL 
           THEN EX.OSND_EX_QTY ELSE 0 END)               AS COMPLETED_QTY,
  SUM(CASE WHEN EX.I_SCN_DT IS NULL 
           THEN EX.OSND_EX_QTY ELSE 0 END)               AS PENDING_QTY
FROM OCI.MSPQ_EX_OSND EX
WHERE EX.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND EX.CANCEL_YN = 'N'
GROUP BY EX.SUPPLY_PLANT_CD, EX.PLANT_CD
ORDER BY TOTAL_QTY DESC;
```

---

## `fn_osnd_screen_pivot`

**용도**: **SCR-005 화면을 그대로 재현** — 4 STATUS (REQUEST/OUTGOING/INCOMING/BALANCE) × 사이즈 PIVOT.

**핵심 룰**:
- 4 STATUS UNION ALL 구조 (프로시저 라인 133-405)
- `OSND_EX_QTY / 2` — L/R 합산해 켤레 환산 ([확정: 라인 161-198 등])
- `IP.SUB_WC_CD` = LINE ([확정: 라인 80, 150, 236, 322])
- `SUBSTR(SUPPLY_OP_CD, 1, 2)` = CMP (공정 그룹) ([확정: 라인 82, 124])
- `FN_GET_STYLE_MODEL('MODEL_NAME', STYLE_CD)` = MODEL_NAME
- `CFM_DT IS NOT NULL` 필수 ([확정: 라인 104, 208, 294, 378])
- BALANCE 행은 REQUEST 행에서 INCOMING 행을 빼서 outer-join 으로 계산 (라인 79-148, 406-415)

**사용 metric**: `osnd_request_qty_screen`, `osnd_outgoing_qty_screen`, `osnd_incoming_qty_screen`, `osnd_balance_qty_screen`

```sql
-- SCR-005 화면 완전 재현
-- L/R 합산 → 켤레 (OSND_EX_QTY / 2)
WITH BASE AS (
  SELECT 
    IP.SUB_WC_CD                                                    AS LINE,
    OS.OSND_DATE                                                    AS OSND_DATE,
    SUBSTR(OS.SUPPLY_OP_CD, 1, 2)                                   AS CMP,
    FN_GET_STYLE_MODEL('MODEL_NAME', OS.STYLE_CD)                   AS MODEL_NAME,
    OS.STYLE_CD || ' / ' || OS.ITEM_CLASS                           AS STYLE_CD_DISP,
    OS.STYLE_CD                                                     AS STYLE_CD,
    OS.ITEM_CLASS,
    CM.CODE_NAME                                                    AS TYPE,
    OS.SUPPLY_PLANT_CD,
    PN.PLANT_NAME                                                   AS SUPPLY_PLANT_NAME,
    OS.SIZE_CD,
    OS.OSND_EX_QTY,
    OS.O_SCN_DT,
    OS.I_SCN_DT
  FROM OCI.MSPQ_EX_OSND OS
  JOIN OCI.MSBS_CODE_MASTER CM
    ON CM.CODE_CLASS_CD = 'PQ_OSND_TYPE' 
   AND CM.SUB_CODE      = OS.OSND_TYPE
  JOIN OCI.MSBS_PLANT PN
    ON PN.PLANT_CD = OS.SUPPLY_PLANT_CD
  JOIN OCI.MSPQ_INSPECT_POINT IP
    ON IP.PLANT_CD         = OS.PLANT_CD
   AND IP.INSPECT_POINT_ID = OS.INSPECT_POINT_ID
  WHERE OS.PLANT_CD     = :V_PLANT_CD
    AND OS.CANCEL_YN    = 'N'
    AND OS.CFM_DT       IS NOT NULL
    AND OS.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND ( OS.PB_CD       = :V_PB_CD       OR :V_PB_CD       IS NULL )
    AND ( OS.FA_WC_CD    = :V_FA_WC_CD    OR :V_FA_WC_CD    IS NULL )
    AND ( OS.OSND_TYPE   IN ( :V_OSND_TYPE_LIST ) OR :V_OSND_TYPE_LIST IS NULL )
    AND ( OS.STYLE_CD    LIKE '%' || :V_STYLE || '%' OR :V_STYLE IS NULL )
    AND OS.SUPPLY_PLANT_CD LIKE NVL(:V_SUPPLY_PLANT, '') || '%'
    AND ( OS.SUPPLY_OP_CD IN ( :V_SUPPLY_OP_LIST ) OR :V_SUPPLY_OP_LIST IS NULL )
),
PIVOTED AS (
  -- REQUEST: 전체 발생 (필터만 통과)
  SELECT LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME,
         'REQUEST'  AS STATUS, 0 AS SORT_INDEX,
         SUM(CASE WHEN SIZE_CD='1'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_1,
         SUM(CASE WHEN SIZE_CD='1T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_1T,
         SUM(CASE WHEN SIZE_CD='2'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_2,
         SUM(CASE WHEN SIZE_CD='2T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_2T,
         SUM(CASE WHEN SIZE_CD='3'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_3,
         SUM(CASE WHEN SIZE_CD='3T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_3T,
         SUM(CASE WHEN SIZE_CD='4'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_4,
         SUM(CASE WHEN SIZE_CD='4T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_4T,
         SUM(CASE WHEN SIZE_CD='5'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_5,
         SUM(CASE WHEN SIZE_CD='5T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_5T,
         SUM(CASE WHEN SIZE_CD='6'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6,
         SUM(CASE WHEN SIZE_CD='6T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6T,
         SUM(CASE WHEN SIZE_CD='7'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_7,
         SUM(CASE WHEN SIZE_CD='7T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_7T,
         SUM(CASE WHEN SIZE_CD='8'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_8,
         SUM(CASE WHEN SIZE_CD='8T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_8T,
         SUM(CASE WHEN SIZE_CD='9'   THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_9,
         SUM(CASE WHEN SIZE_CD='9T'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_9T,
         SUM(CASE WHEN SIZE_CD='10'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_10,
         SUM(CASE WHEN SIZE_CD='10T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_10T,
         SUM(CASE WHEN SIZE_CD='11'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_11,
         SUM(CASE WHEN SIZE_CD='11T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_11T,
         SUM(CASE WHEN SIZE_CD='12'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_12,
         SUM(CASE WHEN SIZE_CD='12T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_12T,
         SUM(CASE WHEN SIZE_CD='13'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_13,
         SUM(CASE WHEN SIZE_CD='13T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_13T,
         SUM(CASE WHEN SIZE_CD='14'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_14,
         SUM(CASE WHEN SIZE_CD='14T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_14T,
         SUM(CASE WHEN SIZE_CD='15'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_15,
         SUM(CASE WHEN SIZE_CD='15T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_15T,
         SUM(CASE WHEN SIZE_CD='16'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_16,
         SUM(CASE WHEN SIZE_CD='16T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_16T,
         SUM(CASE WHEN SIZE_CD='17'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_17,
         SUM(CASE WHEN SIZE_CD='18'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_18,
         SUM(CASE WHEN SIZE_CD='19'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_19,
         SUM(CASE WHEN SIZE_CD='20'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_20,
         SUM(CASE WHEN SIZE_CD='21'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_21,
         SUM(CASE WHEN SIZE_CD='22'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_22
    FROM BASE
   GROUP BY LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME

  UNION ALL
  -- OUTGOING: O_SCN_DT IS NOT NULL 인 행만 (라인 379)
  SELECT LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME,
         'OUTGOING' AS STATUS, 1 AS SORT_INDEX,
         SUM(CASE WHEN SIZE_CD='1'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='1T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='2'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='2T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='3'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='3T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='4'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='4T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='5'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='5T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='6'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='6T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='7'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='7T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='8'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='8T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='9'   AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='9T'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='10'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='10T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='11'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='11T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='12'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='12T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='13'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='13T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='14'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='14T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='15'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='15T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='16'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='16T' AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='17'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='18'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='19'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='20'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='21'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='22'  AND O_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END)
    FROM BASE
   GROUP BY LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME

  UNION ALL
  -- INCOMING: I_SCN_DT IS NOT NULL 인 행만 (라인 295)
  SELECT LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME,
         'INCOMING' AS STATUS, 2 AS SORT_INDEX,
         SUM(CASE WHEN SIZE_CD='1'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='1T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='2'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='2T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='3'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='3T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='4'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='4T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='5'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='5T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='6'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='6T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='7'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='7T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='8'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='8T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='9'   AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='9T'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='10'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='10T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='11'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='11T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='12'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='12T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='13'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='13T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='14'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='14T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='15'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='15T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='16'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='16T' AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='17'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='18'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='19'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='20'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='21'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END),
         SUM(CASE WHEN SIZE_CD='22'  AND I_SCN_DT IS NOT NULL THEN OSND_EX_QTY/2 ELSE 0 END)
    FROM BASE
   GROUP BY LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE, SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME
)
SELECT LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, TYPE,
       SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME, STATUS, SORT_INDEX,
       FX_SIZE_1, FX_SIZE_1T, FX_SIZE_2, FX_SIZE_2T, FX_SIZE_3, FX_SIZE_3T,
       FX_SIZE_4, FX_SIZE_4T, FX_SIZE_5, FX_SIZE_5T, FX_SIZE_6, FX_SIZE_6T,
       FX_SIZE_7, FX_SIZE_7T, FX_SIZE_8, FX_SIZE_8T, FX_SIZE_9, FX_SIZE_9T,
       FX_SIZE_10, FX_SIZE_10T, FX_SIZE_11, FX_SIZE_11T, FX_SIZE_12, FX_SIZE_12T,
       FX_SIZE_13, FX_SIZE_13T, FX_SIZE_14, FX_SIZE_14T, FX_SIZE_15, FX_SIZE_15T,
       FX_SIZE_16, FX_SIZE_16T, FX_SIZE_17, FX_SIZE_18, FX_SIZE_19, FX_SIZE_20,
       FX_SIZE_21, FX_SIZE_22
  FROM PIVOTED
 ORDER BY LINE, CMP, OSND_DATE, MODEL_NAME, STYLE_CD_DISP, TYPE,
          SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME, SORT_INDEX;
```

**참고**:
- BALANCE 행은 위 결과의 REQUEST 와 INCOMING 의 사이즈별 차이로 산출. 단일 SQL 로는 4 STATUS 모두 표현 어렵고 화면처럼 OUTER JOIN 패턴 (프로시저 라인 79-148 참조) 또는 클라이언트 측 계산 필요. 대안: 자유 분석에서 `FX_SIZE_X = REQUEST_FX_SIZE_X - INCOMING_FX_SIZE_X` 식으로 BALANCE 추가 row 생성.
- `EPBS_MOLD_MASTER@JJEDIF` + `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` 의 COLOR_NAME 은 DB link 의존이라 OCI 환경에서 누락 가능. 누락 시 빈 문자열로 처리.

[확정: P_MSPQ38100S_Q 라인 49-415 검증]

---

## `fn_osnd_request_by_size`

**용도**: SCR-005 의 REQUEST 행만 사이즈 PIVOT 으로. F 의 부분 — 화면 1/4 만 빠르게 보기.

```sql
SELECT 
  IP.SUB_WC_CD                                    AS LINE,
  OS.OSND_DATE,
  SUBSTR(OS.SUPPLY_OP_CD, 1, 2)                   AS CMP,
  FN_GET_STYLE_MODEL('MODEL_NAME', OS.STYLE_CD)   AS MODEL_NAME,
  OS.STYLE_CD,
  OS.ITEM_CLASS,
  CM.CODE_NAME                                    AS TYPE,
  OS.SUPPLY_PLANT_CD,
  PN.PLANT_NAME                                   AS SUPPLY_PLANT_NAME,
  SUM(CASE WHEN OS.SIZE_CD='6'  THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6,
  SUM(CASE WHEN OS.SIZE_CD='6T' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6T,
  SUM(CASE WHEN OS.SIZE_CD='7'  THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_7,
  SUM(CASE WHEN OS.SIZE_CD='7T' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_7T,
  SUM(CASE WHEN OS.SIZE_CD='8'  THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_8,
  SUM(CASE WHEN OS.SIZE_CD='8T' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_8T,
  SUM(CASE WHEN OS.SIZE_CD='9'  THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_9,
  SUM(CASE WHEN OS.SIZE_CD='9T' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_9T,
  SUM(CASE WHEN OS.SIZE_CD='10' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_10,
  SUM(CASE WHEN OS.SIZE_CD='10T' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_10T,
  SUM(CASE WHEN OS.SIZE_CD='11' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_11,
  SUM(CASE WHEN OS.SIZE_CD='12' THEN OS.OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_12,
  -- ... 필요한 사이즈만 — 전체는 fn_osnd_screen_pivot 사용
  SUM(OS.OSND_EX_QTY/2)                                           AS TOTAL_QTY
FROM OCI.MSPQ_EX_OSND OS
JOIN OCI.MSBS_CODE_MASTER CM
  ON CM.CODE_CLASS_CD = 'PQ_OSND_TYPE' AND CM.SUB_CODE = OS.OSND_TYPE
JOIN OCI.MSBS_PLANT PN
  ON PN.PLANT_CD = OS.SUPPLY_PLANT_CD
JOIN OCI.MSPQ_INSPECT_POINT IP
  ON IP.PLANT_CD = OS.PLANT_CD AND IP.INSPECT_POINT_ID = OS.INSPECT_POINT_ID
WHERE OS.PLANT_CD       = :V_PLANT_CD
  AND OS.CANCEL_YN      = 'N'
  AND OS.CFM_DT         IS NOT NULL
  AND OS.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
  AND ( OS.OSND_TYPE IN ( :V_OSND_TYPE_LIST ) OR :V_OSND_TYPE_LIST IS NULL )
  AND OS.SUPPLY_PLANT_CD LIKE NVL(:V_SUPPLY_PLANT, '') || '%'
  AND ( OS.SUPPLY_OP_CD IN ( :V_SUPPLY_OP_LIST ) OR :V_SUPPLY_OP_LIST IS NULL )
GROUP BY IP.SUB_WC_CD, OS.OSND_DATE, SUBSTR(OS.SUPPLY_OP_CD, 1, 2),
         FN_GET_STYLE_MODEL('MODEL_NAME', OS.STYLE_CD), OS.STYLE_CD,
         OS.ITEM_CLASS, CM.CODE_NAME, OS.SUPPLY_PLANT_CD, PN.PLANT_NAME
ORDER BY LINE, CMP, OSND_DATE, MODEL_NAME, STYLE_CD;
```

---

## `fn_osnd_outgoing_by_size`

**용도**: SCR-005 OUTGOING 행만. `fn_osnd_request_by_size` 와 동일하되 `AND OS.O_SCN_DT IS NOT NULL` 추가.

**핵심**: 위 함수에 다음 줄 추가:
```sql
  AND OS.O_SCN_DT IS NOT NULL    -- 프로시저 라인 379
```

---

## `fn_osnd_incoming_by_size`

**용도**: SCR-005 INCOMING 행만. `fn_osnd_request_by_size` 와 동일하되 `AND OS.I_SCN_DT IS NOT NULL` 추가.

**핵심**: 위 함수에 다음 줄 추가:
```sql
  AND OS.I_SCN_DT IS NOT NULL    -- 프로시저 라인 295
```

---

## `fn_osnd_style_list`

**용도**: SCR-005 화면의 STYLE 드롭다운/콤보박스용. `V_P_WORK_TYPE='STYLE'` 분기.

```sql
SELECT STYLE_CD
  FROM OCI.MSPQ_EX_OSND OS
 WHERE OS.PLANT_CD = :V_PLANT_CD
   AND OS.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND ( OS.PB_CD = :V_PB_CD OR :V_PB_CD IS NULL )
   AND OS.SUPPLY_PLANT_CD LIKE NVL(:V_SUPPLY_PLANT, '') || '%'
 GROUP BY STYLE_CD
 ORDER BY STYLE_CD;
```

[확정: P_MSPQ38100S_Q 라인 431-443]

---

## `fn_color_lookup_cte`

**용도**: `MSPQ_EX_OSND.COLOR_CD` 끝 3자리 → 색상명 변환. `_common.md §10-3` 박제 15개를 CTE로 즉시 사용.

**대상 컬럼**: `OS.COLOR_CD` (5자리, 예: `1010A`) — **끝 3자리가 색상 키**

**박제 매핑** (검증된 15개, OS&D 분석에서 90% 이상 커버):

| 코드 | 색상명 | 코드 | 색상명 | 코드 | 색상명 |
|---|---|---|---|---|---|
| 00A | BLACK | 22Z | BAROQUE BROWN | 84V | TURF ORANGE |
| 10A | WHITE | 14A | OFF WHITE | 73B | CASHMERE |
| 01V | WOLF GREY | 2CQ | VELVET BROWN | 06H | FLINT GREY |
| 11K | SAIL | 29E | CREAM II | | |
| 12J | SUMMIT WHITE | 3QG | CUCUMBER CALM | | |
| 06F | ANTHRACITE | | | | |
| 0BB | PHOTON DUST | | | | |

**즉시 사용 가능한 CTE + JOIN 패턴**:

```sql
WITH COLOR_MAP AS (
  SELECT '00A' AS K, 'BLACK' AS N FROM DUAL UNION ALL
  SELECT '10A', 'WHITE'           FROM DUAL UNION ALL
  SELECT '01V', 'WOLF GREY'       FROM DUAL UNION ALL
  SELECT '11K', 'SAIL'            FROM DUAL UNION ALL
  SELECT '12J', 'SUMMIT WHITE'    FROM DUAL UNION ALL
  SELECT '06F', 'ANTHRACITE'      FROM DUAL UNION ALL
  SELECT '0BB', 'PHOTON DUST'     FROM DUAL UNION ALL
  SELECT '22Z', 'BAROQUE BROWN'   FROM DUAL UNION ALL
  SELECT '14A', 'OFF WHITE'       FROM DUAL UNION ALL
  SELECT '2CQ', 'VELVET BROWN'    FROM DUAL UNION ALL
  SELECT '29E', 'CREAM II'        FROM DUAL UNION ALL
  SELECT '3QG', 'CUCUMBER CALM'   FROM DUAL UNION ALL
  SELECT '84V', 'TURF ORANGE'     FROM DUAL UNION ALL
  SELECT '73B', 'CASHMERE'        FROM DUAL UNION ALL
  SELECT '06H', 'FLINT GREY'      FROM DUAL
)
-- ... 본 쿼리 ...
SELECT 
  OS.STYLE_CD,
  SUBSTR(OS.COLOR_CD, -3)  AS COLOR_KEY,
  CM.N                     AS COLOR_NAME,
  ...
FROM OCI.MSPQ_EX_OSND OS
LEFT JOIN COLOR_MAP CM ON CM.K = SUBSTR(OS.COLOR_CD, -3)
WHERE ...
```

**사용 시 흐름**:
1. 분석 SQL 작성 직전 — 등장 코드 확인:
   ```sql
   SELECT DISTINCT SUBSTR(COLOR_CD, -3) AS COLOR_KEY
   FROM OCI.MSPQ_EX_OSND
   WHERE PLANT_CD = :V_PLANT_CD AND OSND_DATE = :V_DATE ...
   ```
2. 박제 15개에 다 있으면 → 위 CTE 그대로 사용
3. **모르는 코드가 있으면** → `fn_color_dynamic_extract` 로 추출 후 CTE 에 UNION ALL 로 추가

[확정: _common.md §10-3 + 2026-03-05 JJ/CKP/IP+PH 데이터 등장 코드 15개 중 12개 매칭 검증]

---

## `fn_color_dynamic_extract`

**용도**: 박제에 없는 신규 색상 코드를 `MSBS_ITEM.MCS_COLOR_CD` 텍스트 파싱으로 동적 추출. `_common.md §10-4` 구현체.

**원리**: `MSBS_ITEM.MCS_COLOR_CD` 컬럼에는 `"VAST GREY(0AE)"` 또는 `"BLACK(00A)/WHITE(10A)"` 형식의 텍스트가 들어있음 → `/` 로 split → `(코드)` 추출 → key-value 매핑 생성. 같은 코드에 여러 이름 매핑되면 등장 횟수 1위 채택.

```sql
-- 신규 코드 → 색상명 동적 lookup
-- 사용 시 :V_NEW_COLOR_KEYS 위치에 콤마 구분 코드 목록 (예: '0AE','10J','05I') 넣기
WITH SPLIT AS (
  SELECT TRIM(REGEXP_SUBSTR(MCS_COLOR_CD, '[^/]+', 1, LEVEL)) AS PART
  FROM (
    SELECT DISTINCT MCS_COLOR_CD 
    FROM OCI.MSBS_ITEM
    WHERE MCS_COLOR_CD LIKE '%(%' AND MCS_COLOR_CD <> 'NONE'
  )
  CONNECT BY REGEXP_SUBSTR(MCS_COLOR_CD, '[^/]+', 1, LEVEL) IS NOT NULL
        AND PRIOR MCS_COLOR_CD = MCS_COLOR_CD
        AND PRIOR SYS_GUID() IS NOT NULL
),
PARSED AS (
  SELECT 
    TRIM(SUBSTR(PART, INSTR(PART,'(')+1, 
                INSTR(PART,')') - INSTR(PART,'(') - 1))     AS COLOR_KEY,
    TRIM(SUBSTR(PART, 1, INSTR(PART,'(')-1))                AS COLOR_NAME
  FROM SPLIT
  WHERE PART LIKE '%(%' AND PART LIKE '%)%'
),
RANKED AS (
  SELECT COLOR_KEY, COLOR_NAME, COUNT(*) cnt,
         ROW_NUMBER() OVER (PARTITION BY COLOR_KEY ORDER BY COUNT(*) DESC) rn
  FROM PARSED
  WHERE LENGTH(COLOR_KEY)=3 AND LENGTH(COLOR_NAME)>0
  GROUP BY COLOR_KEY, COLOR_NAME
)
SELECT COLOR_KEY, COLOR_NAME, cnt AS RELIABILITY
FROM RANKED 
WHERE rn = 1
  AND COLOR_KEY IN ( :V_NEW_COLOR_KEYS )
ORDER BY cnt DESC;
```

**RELIABILITY 해석**:
- 그 코드가 `MSBS_ITEM` 에 등장한 횟수
- **3 미만**이면 답변에 `[추정]` 표시 권장
- **10 이상**이면 신뢰 가능 (예: 0AE=120, 10J=76, 05I=43 등 검증됨)

**검증된 신규 코드** (2026-03-05 분석 시 추출):

| 코드 | 색상명 | RELIABILITY |
|---|---|---|
| 0AE | VAST GREY | 120 |
| 10J | LT OREWOOD BRN | 76 |
| 05I | COLLEGE GREY | 43 |

**raw 데이터 직접 확인 패턴** (검증용):

```sql
SELECT DISTINCT MCS_COLOR_CD
FROM OCI.MSBS_ITEM
WHERE MCS_COLOR_CD LIKE '%(0AE)%'
  AND MCS_COLOR_CD <> 'NONE'
  AND ROWNUM <= 5;
```

[확정: _common.md §10-4 + 2026-03-05 신규 코드 3개 추출 및 raw 데이터 매칭 검증]

---

## `fn_osnd_screen_pivot_with_color`

**용도**: `fn_osnd_screen_pivot` (SCR-005 화면 재현) + **Color 컬럼 자동 매핑** 통합 버전. 화면에 색상명이 필요한 모든 SCR-005 분석에 디폴트로 사용.

**`fn_osnd_screen_pivot` 와의 차이점**:
- `fn_color_lookup_cte` 의 박제 CTE 를 인라인으로 포함
- BASE CTE 에 `SUBSTR(OS.COLOR_CD, -3) AS COLOR_KEY` 와 `CM.N AS COLOR_NAME` 추가
- 모든 STATUS UNION 분기에 색상 컬럼 추가
- GROUP BY 에 색상 추가 — 같은 STYLE 도 색상이 다르면 별도 행 (예: 849559-101 의 IP=WOLF GREY vs PH=WHITE)

**핵심 룰**: `fn_osnd_screen_pivot` 의 모든 룰 + 색상 매핑 룰 (`fn_color_lookup_cte` 참고)

**사용 metric**: `osnd_request_qty_screen`, `osnd_outgoing_qty_screen`, `osnd_incoming_qty_screen`, `osnd_balance_qty_screen` + Color 차원

**전체 SQL** (REQUEST 분기 + 색상 lookup. OUTGOING/INCOMING 도 동일 패턴):

```sql
WITH COLOR_MAP AS (
  -- fn_color_lookup_cte 의 박제 15개 (전체 코드는 해당 함수 참조)
  SELECT '00A' AS K, 'BLACK' AS N FROM DUAL UNION ALL
  SELECT '10A', 'WHITE'           FROM DUAL UNION ALL
  SELECT '01V', 'WOLF GREY'       FROM DUAL UNION ALL
  SELECT '11K', 'SAIL'            FROM DUAL UNION ALL
  SELECT '12J', 'SUMMIT WHITE'    FROM DUAL UNION ALL
  SELECT '06F', 'ANTHRACITE'      FROM DUAL UNION ALL
  SELECT '0BB', 'PHOTON DUST'     FROM DUAL UNION ALL
  SELECT '22Z', 'BAROQUE BROWN'   FROM DUAL UNION ALL
  SELECT '14A', 'OFF WHITE'       FROM DUAL UNION ALL
  SELECT '2CQ', 'VELVET BROWN'    FROM DUAL UNION ALL
  SELECT '29E', 'CREAM II'        FROM DUAL UNION ALL
  SELECT '3QG', 'CUCUMBER CALM'   FROM DUAL UNION ALL
  SELECT '84V', 'TURF ORANGE'     FROM DUAL UNION ALL
  SELECT '73B', 'CASHMERE'        FROM DUAL UNION ALL
  SELECT '06H', 'FLINT GREY'      FROM DUAL
  -- 신규 코드 등장 시 fn_color_dynamic_extract 로 추출 후 여기에 UNION ALL 추가:
  -- UNION ALL SELECT '0AE', 'VAST GREY'      FROM DUAL
  -- UNION ALL SELECT '10J', 'LT OREWOOD BRN' FROM DUAL
  -- UNION ALL SELECT '05I', 'COLLEGE GREY'   FROM DUAL
),
BASE AS (
  SELECT 
    IP.SUB_WC_CD                                                    AS LINE,
    OS.OSND_DATE                                                    AS OSND_DATE,
    SUBSTR(OS.SUPPLY_OP_CD, 1, 2)                                   AS CMP,
    FN_GET_STYLE_MODEL('MODEL_NAME', OS.STYLE_CD)                   AS MODEL_NAME,
    OS.STYLE_CD || ' / ' || OS.ITEM_CLASS                           AS STYLE_CD_DISP,
    OS.STYLE_CD                                                     AS STYLE_CD,
    OS.ITEM_CLASS,
    SUBSTR(OS.COLOR_CD, -3)                                         AS COLOR_KEY,
    NVL(CM.N, '(미매핑)')                                           AS COLOR_NAME,
    CMT.CODE_NAME                                                   AS TYPE,
    OS.SUPPLY_PLANT_CD,
    PN.PLANT_NAME                                                   AS SUPPLY_PLANT_NAME,
    OS.SIZE_CD,
    OS.OSND_EX_QTY,
    OS.O_SCN_DT,
    OS.I_SCN_DT
  FROM OCI.MSPQ_EX_OSND OS
  JOIN OCI.MSBS_CODE_MASTER CMT
    ON CMT.CODE_CLASS_CD = 'PQ_OSND_TYPE' 
   AND CMT.SUB_CODE      = OS.OSND_TYPE
  JOIN OCI.MSBS_PLANT PN
    ON PN.PLANT_CD = OS.SUPPLY_PLANT_CD
  JOIN OCI.MSPQ_INSPECT_POINT IP
    ON IP.PLANT_CD         = OS.PLANT_CD
   AND IP.INSPECT_POINT_ID = OS.INSPECT_POINT_ID
  LEFT JOIN COLOR_MAP CM
    ON CM.K = SUBSTR(OS.COLOR_CD, -3)
  WHERE OS.PLANT_CD     = :V_PLANT_CD
    AND OS.CANCEL_YN    = 'N'
    AND OS.CFM_DT       IS NOT NULL
    AND OS.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
    AND ( OS.PB_CD       = :V_PB_CD       OR :V_PB_CD       IS NULL )
    AND ( OS.FA_WC_CD    = :V_FA_WC_CD    OR :V_FA_WC_CD    IS NULL )
    AND ( OS.OSND_TYPE   IN ( :V_OSND_TYPE_LIST ) OR :V_OSND_TYPE_LIST IS NULL )
    AND ( OS.STYLE_CD    LIKE '%' || :V_STYLE || '%' OR :V_STYLE IS NULL )
    AND OS.SUPPLY_PLANT_CD LIKE NVL(:V_SUPPLY_PLANT, '') || '%'
    AND ( OS.SUPPLY_OP_CD IN ( :V_SUPPLY_OP_LIST ) OR :V_SUPPLY_OP_LIST IS NULL )
)
-- REQUEST 분기 (OUTGOING/INCOMING 도 fn_osnd_screen_pivot 패턴 그대로, GROUP BY 에 COLOR_KEY, COLOR_NAME 추가)
SELECT 
  LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, COLOR_KEY, COLOR_NAME, TYPE,
  SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME,
  'REQUEST'  AS STATUS, 0 AS SORT_INDEX,
  SUM(CASE WHEN SIZE_CD='6'  THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6,
  SUM(CASE WHEN SIZE_CD='6T' THEN OSND_EX_QTY/2 ELSE 0 END) AS FX_SIZE_6T,
  -- ... 전체 사이즈 컬럼은 fn_osnd_screen_pivot 동일 ...
  SUM(OSND_EX_QTY/2)                                         AS FX_TOTAL
FROM BASE
GROUP BY LINE, OSND_DATE, CMP, MODEL_NAME, STYLE_CD_DISP, COLOR_KEY, COLOR_NAME, TYPE,
         SUPPLY_PLANT_CD, SUPPLY_PLANT_NAME
ORDER BY LINE, CMP, OSND_DATE, MODEL_NAME, STYLE_CD_DISP, COLOR_NAME, TYPE;
```

**검증 — 사용 전 확인 절차**:

1. 분석 대상 데이터의 등장 색상 코드 먼저 확인:
   ```sql
   SELECT DISTINCT SUBSTR(OS.COLOR_CD, -3) AS COLOR_KEY
   FROM OCI.MSPQ_EX_OSND OS
   WHERE OS.PLANT_CD = :V_PLANT_CD
     AND OS.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
     AND ... ;
   ```
2. 박제 15개 외 코드 있으면 `fn_color_dynamic_extract` 로 추출
3. 추출 결과를 COLOR_MAP CTE 에 UNION ALL 로 추가
4. 본 함수 실행

**미매핑 처리**: `NVL(CM.N, '(미매핑)')` → 박제·추출 모두 못 가져온 경우 `(미매핑)` 으로 표시 (NULL 회피)

**주의사항**:
- 색상 매핑이 **`MCS_COLOR_CD` 텍스트 파싱 결과** [추정] — 회사 코드 마스터 문서와 100% 일치 미확인
- 복합색 (`BLACK(00A)/WHITE(10A)`) 의 경우 OSND 는 단일 코드만 들어옴 (예: `1010A` 끝 3자리 = `10A` = WHITE) — 주색만 반영하는 듯 [추정]
- **같은 Style 도 색상이 다르면 별도 행** — 예: 849559-101 의 FGA10 라인에서 IP 공정 = WOLF GREY, PH 공정 = WHITE

[확정: fn_osnd_screen_pivot 패턴 + _common.md §10 색상 lookup 통합 + 2026-03-05 JJ/CKP/IP+PH 검증]

---

## `fn_return_rate_daily`

**용도**: **SCR-006 의 메인 그리드** — 일자별 Return Rate %.

**환경 분기**:
- LMES 스키마 직접 접근 가능 시 → 원본 `LMES.V_PQ_EX_OSND_V3` 호출 (§V-1)
- **OCI 스키마만 접근 가능 시 (디폴트)** → 뷰 정의를 그대로 본뜬 **재현 CTE `OSND_V3_REPLICA`** 를 인라인 사용 (§V-2)
- 뷰가 없거나 재현이 곤란하면 워크플로 §5-5 "SCR-006 처리 불가" 응답

**핵심 룰**:
- `OSND_TYPE IN ('D', 'S')` — Damage + Shortage 만 ([확정: 프로시저 라인 115, 2025.09.22 it.fikri])
- `IN_DATE` 기준 (입고 일자 — OSND_DATE 아님)
- Return Rate = `REPLEN_QTY / DEFECT_QTY * 100` (소수점 둘째 자리)
- ITEM_CLASS_TYPE 콤마 다중 (NULL 시 전체)
- SUPPLY_PLANT_CD 콤마 다중 (필수)

**사용 metric**: `osnd_return_rate`, `osnd_replen_qty`, `osnd_defect_qty`

### 변형 A — LMES 원본 뷰 호출 (가능 시)

```sql
SELECT 
  IN_DATE,
  '-'                  AS ITEM_CLASS_TYPE,
  SUM(IN_QTY)          AS PROD_QTY,
  SUM(DEFECT_QTY)      AS DEFECT_QTY,
  SUM(REPLEN_QTY)      AS REPLEN_QTY,
  SUM(DEFECT_O_QTY)    AS DEFECT_O_QTY,
  SUM(DEFECT_S_QTY)    AS DEFECT_S_QTY,
  SUM(DEFECT_D_QTY)    AS DEFECT_D_QTY,
  SUM(DEFECT_I_QTY)    AS DEFECT_I_QTY,
  SUM(DEFECT_L_QTY)    AS DEFECT_L_QTY,
  SUM(REPLEN_O_QTY)    AS REPLEN_O_QTY,
  SUM(REPLEN_S_QTY)    AS REPLEN_S_QTY,
  SUM(REPLEN_D_QTY)    AS REPLEN_D_QTY,
  SUM(REPLEN_I_QTY)    AS REPLEN_I_QTY,
  SUM(REPLEN_L_QTY)    AS REPLEN_L_QTY,
  MAX(REPLEN_DATE)     AS REPLEN_DT,
  TO_CHAR(TO_DATE(IN_DATE, 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH')
    || ' - ' ||
  TO_CHAR(TO_DATE(MAX(REPLEN_DATE), 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH') AS YMD,
  ROUND(DECODE(SUM(DEFECT_QTY), 0, 0, 
               SUM(REPLEN_QTY) / SUM(DEFECT_QTY) * 100), 2)                              AS PER
FROM LMES.V_PQ_EX_OSND_V3
WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
  AND (OSND_TYPE IN ('D', 'S') OR OSND_TYPE IS NULL)
  AND PLANT_CD = :V_PLANT_CD
  AND ITEM_CLASS_TYPE IN (
        SELECT TRIM(REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL) IS NOT NULL
      )
  AND SUPPLY_PLANT_CD IN (
        SELECT TRIM(REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL) IS NOT NULL
      )
GROUP BY IN_DATE
ORDER BY IN_DATE ASC;
```

### 변형 B — OCI 환경에서 뷰 재현 (디폴트)

`OSND_V3_REPLICA` CTE 안에 뷰 정의(§V) 의 4개 UNION 분기를 그대로 옮긴다. 핵심 4 분기 중 DEFECT 만 Return Rate 계산에 필요하므로, 본 함수의 간소 버전은 DEFECT 분기만 사용한다. IN_QTY 통합이 필요할 때만 4 분기 전체 사용.

```sql
-- OCI 전용: 뷰 재현 CTE (DEFECT 분기만, Return Rate 계산용)
WITH OSND_V3_DEFECT AS (
  SELECT 
    B.PLANT_CD                                                AS PLANT_CD,
    B.SUPPLY_PLANT_CD                                         AS SUPPLY_PLANT_CD,
    SUBSTR(B.ITEM_CD, 10, 2)                                  AS ITEM_CLASS_TYPE,
    B.OSND_DATE                                               AS IN_DATE,
    B.OSND_TYPE                                               AS OSND_TYPE,
    B.OSND_EX_QTY / 2                                         AS DEFECT_QTY,
    DECODE(B.OSND_TYPE, 'O', B.OSND_EX_QTY / 2, 0)            AS DEFECT_O_QTY,
    DECODE(B.OSND_TYPE, 'S', B.OSND_EX_QTY / 2, 0)            AS DEFECT_S_QTY,
    DECODE(B.OSND_TYPE, 'D', B.OSND_EX_QTY / 2, 0)            AS DEFECT_D_QTY,
    DECODE(B.OSND_TYPE, 'I', B.OSND_EX_QTY / 2, 0)            AS DEFECT_I_QTY,
    DECODE(B.OSND_TYPE, 'L', B.OSND_EX_QTY / 2, 0)            AS DEFECT_L_QTY,
    DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2            AS REPLEN_QTY,
    DECODE(B.OSND_TYPE, 'O', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_O_QTY,
    DECODE(B.OSND_TYPE, 'S', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_S_QTY,
    DECODE(B.OSND_TYPE, 'D', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_D_QTY,
    DECODE(B.OSND_TYPE, 'I', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_I_QTY,
    DECODE(B.OSND_TYPE, 'L', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_L_QTY,
    B.I_SCN_DT                                                AS REPLEN_DT
  FROM OCI.MSPQ_EX_OSND B
       INNER JOIN OCI.MSPQ_RPT_IP IP
          ON B.PLANT_CD          = IP.PLANT_CD
         AND B.INSPECT_POINT_ID  = IP.INSPECT_POINT_ID
       INNER JOIN OCI.MSBS_CODE_MASTER CM
          ON B.OSND_TYPE         = CM.SUB_CODE
         AND CM.CODE_CLASS_CD    = 'PQ_OSND_TYPE'
         AND CM.USE_YN           = 'Y'
  WHERE B.CFM_DT     IS NOT NULL
    AND B.CANCEL_YN  = 'N'
)
SELECT 
  IN_DATE,
  '-'                                AS ITEM_CLASS_TYPE,
  0                                  AS PROD_QTY,           -- 본 변형은 DEFECT 분기만, IN_QTY 미반영
  SUM(DEFECT_QTY)                    AS DEFECT_QTY,
  SUM(REPLEN_QTY)                    AS REPLEN_QTY,
  SUM(DEFECT_O_QTY)                  AS DEFECT_O_QTY,
  SUM(DEFECT_S_QTY)                  AS DEFECT_S_QTY,
  SUM(DEFECT_D_QTY)                  AS DEFECT_D_QTY,
  SUM(DEFECT_I_QTY)                  AS DEFECT_I_QTY,
  SUM(DEFECT_L_QTY)                  AS DEFECT_L_QTY,
  SUM(REPLEN_O_QTY)                  AS REPLEN_O_QTY,
  SUM(REPLEN_S_QTY)                  AS REPLEN_S_QTY,
  SUM(REPLEN_D_QTY)                  AS REPLEN_D_QTY,
  SUM(REPLEN_I_QTY)                  AS REPLEN_I_QTY,
  SUM(REPLEN_L_QTY)                  AS REPLEN_L_QTY,
  TO_CHAR(MAX(REPLEN_DT), 'YYYYMMDD') AS REPLEN_DT,
  TO_CHAR(TO_DATE(IN_DATE, 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH')
    || ' - ' ||
  TO_CHAR(MAX(REPLEN_DT), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH') AS YMD,
  ROUND(DECODE(SUM(DEFECT_QTY), 0, 0,
               SUM(REPLEN_QTY) / SUM(DEFECT_QTY) * 100), 2)  AS PER
FROM OSND_V3_DEFECT
WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
  AND (OSND_TYPE IN ('D', 'S') OR OSND_TYPE IS NULL)
  AND PLANT_CD = :V_PLANT_CD
  AND ITEM_CLASS_TYPE IN (
        SELECT TRIM(REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL) IS NOT NULL
      )
  AND SUPPLY_PLANT_CD IN (
        SELECT TRIM(REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL) IS NOT NULL
      )
GROUP BY IN_DATE
ORDER BY IN_DATE ASC;
```

**참고**:
- **IN_QTY 가 필요한 경우** (PROD_QTY 분자 표시 등) → 위 CTE 를 §V-2 의 4 분기 전체 UNION 으로 확장. 4 분기 중 분기 2~4 가 모두 IN_QTY 만 채우는 입고 분기.
- 2022/11/18 까지는 `OSND_TYPE = 'D' OR NULL` 이었음 → 2025/09/22 부터 `'D','S'` 둘 다 (it.fikri).
- `OCI.MSPQ_RPT_IP` 가 OCI 에 없으면 LINE 분해 불가 — DEFECT 분기 단순 집계까지만 가능.

[확정: SP_GMES00142_Q_JJ_V5 라인 85-127 + V_PQ_EX_OSND_V3 정의 라인 63-117 검증]

---

## `fn_return_rate_daily_full`

**용도**: **SCR-006 화면 하단 6행 표 풀 재현** — Incoming Quantity / OS&D Quantity / Replenishment / Replenishment Rate (%) / OS&D Rate (%) 모두 한 번에 산출.

**언제 사용**:
- `fn_return_rate_daily` 는 DEFECT 분기 1 만 사용해 Return Rate 와 DEFECT/REPLEN 만 산출 (경량).
- 화면 하단표 첫 행 **Incoming Quantity** 와 마지막 행 **OS&D Rate (%)** 는 분기 2~4 의 IN_QTY 가 필요 — 이 함수 사용.

**환경 분기**:
- LMES 스키마 직접 접근 가능 시 → 원본 `LMES.V_PQ_EX_OSND_V3` 호출 (변형 A)
- **OCI 스키마만 접근 가능 시 (디폴트)** → §V-2 의 4분기 UNION 재현 CTE 사용 (변형 B)

**핵심 룰**:
- `OSND_TYPE IN ('D', 'S')` — DEFECT 분기에만 적용. IN_QTY 분기들은 OSND_TYPE='' 이므로 `OR OSND_TYPE IS NULL` 필요.
- `IN_DATE` 기준 (입고 일자 — `OSND_DATE` 아님)
- Return Rate = `REPLEN_QTY / DEFECT_QTY * 100` (소수점 둘째 자리)
- OS&D Rate = `DEFECT_QTY / IN_QTY * 100` (소수점 둘째 자리) — [추측: 화면 표기 역산]
- ITEM_CLASS_TYPE 콤마 다중 (NULL 시 전체)
- SUPPLY_PLANT_CD 콤마 다중 (필수)

**사용 metric**: `osnd_defect_qty`, `osnd_replen_qty`, `osnd_return_rate`, `osnd_in_qty`, `osnd_rate_pct`

**용어 매핑 (화면 ↔ 컬럼)**:

| 화면 표기 | 차트 라벨 | 프로시저 CV_2 컬럼 | metric |
|---|---|---|---|
| Incoming Quantity (Prs) | — | `PROD_QTY` (=`SUM(IN_QTY)`) | `osnd_in_qty` |
| OS&D Quantity (Prs) | **C.GRADE RETURN** (왼쪽 막대) | `DEFECT_QTY` | `osnd_defect_qty` |
| Replenishment (Prs) | **REPLENISHMENT** (오른쪽 막대) | `REPLEN_QTY` | `osnd_replen_qty` |
| Replenishment Rate (%) | **%** (자주색 라인) | `PER` | `osnd_return_rate` |
| OS&D Rate (%) | — | (없음 — 클라이언트 표현식 [추측]) | `osnd_rate_pct` |

> "C.GRADE RETURN" 은 OS&D Quantity (= `DEFECT_QTY`) 의 화면 별칭. 별도 컬럼 아님.
> [확정: SP_GMES00142_Q_JJ_V5 라인 87-110 직접 검증]

### 변형 A — LMES 원본 뷰 호출 (프로시저 CV_2 와 동일)

> **출처 확정**: `LMES.SP_GMES00142_Q_JJ_V5` 프로시저 CV_2 (라인 85-126). 컬럼 별칭은 프로시저 원본을 따른다.
> `PROD_QTY` = 화면 "Incoming Quantity (Prs)", `DEFECT_QTY` = "OS&D Quantity (Prs)", 등.
> 프로시저는 `PER` (Replenishment Rate) 만 산출하고 OS&D Rate 는 산출하지 않음 — 마지막 컬럼 `OSND_RATE_PCT` 는 본 함수에서 추가한 것 ([추측: 클라이언트 표현식 역산]).

```sql
SELECT
  IN_DATE,
  TO_CHAR(TO_DATE(IN_DATE, 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH')
    || ' - ' ||
  TO_CHAR(TO_DATE(MAX(REPLEN_DATE), 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH')
                                                                AS YMD,
  SUM(IN_QTY)                                                   AS PROD_QTY,          -- 화면 Incoming Quantity
  SUM(DEFECT_QTY)                                               AS DEFECT_QTY,        -- 화면 OS&D Quantity / 차트 C.GRADE RETURN
  SUM(REPLEN_QTY)                                               AS REPLEN_QTY,        -- 화면 Replenishment / 차트 REPLENISHMENT
  ROUND(DECODE(SUM(DEFECT_QTY), 0, 0,
               SUM(REPLEN_QTY) / SUM(DEFECT_QTY) * 100), 2)     AS PER,               -- 화면 Replenishment Rate / 차트 % 라인
  ROUND(DECODE(SUM(IN_QTY),     0, 0,
               SUM(DEFECT_QTY) / SUM(IN_QTY)     * 100), 2)     AS OSND_RATE_PCT      -- 화면 OS&D Rate [추측: 클라이언트 표현식]
FROM LMES.V_PQ_EX_OSND_V3
WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
  AND (OSND_TYPE IN ('D', 'S') OR OSND_TYPE IS NULL)
  AND PLANT_CD = :V_PLANT_CD
  AND ITEM_CLASS_TYPE IN (
        SELECT TRIM(REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL) IS NOT NULL
      )
  AND SUPPLY_PLANT_CD IN (
        SELECT TRIM(REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL) IS NOT NULL
      )
GROUP BY IN_DATE
ORDER BY IN_DATE ASC;
```

**프로시저 파라미터 매핑**:

| 함수 변수 | 프로시저 파라미터 | 비고 |
|---|---|---|
| `:V_IN_DATE_F` | `V_P_START_DT` | YYYYMMDD VARCHAR8 |
| `:V_IN_DATE_T` | `V_P_END_DT`   | YYYYMMDD VARCHAR8 |
| `:V_PLANT_CD`  | `V_P_PLANT_CD` | 단일 값 (3110 등 — 화면 Plant 드롭다운) |
| `:V_SUPPLY_PLANT` | `V_P_SUPPLYING_PLANT` | 콤마 다중 ('3120,3220' 등) |
| `:V_SUPPLY_OP_CD` | `V_P_SUPPLYING_OP_CD` | 콤마 다중. NULL 이면 전체 |

**프로시저가 받지만 사용하지 않는 파라미터** (CV_2 의 WHERE 절에 없음):
- `V_P_PB_CD` — PB 코드 필터. 라인 31 에서 `'%'` 와 concat 만 하고 실제 사용 안 됨
- `V_P_LINE_CD` — 라인 코드 필터. 정의되어 있으나 어디서도 안 씀
- `V_P_OSND_TYPE` — 동적 OSND_TYPE 필터. CV_2 는 라인 115 에서 `'D','S'` 하드코딩
- `V_P_SEL_OPTION` — 셀렉트 옵션. 정의되어 있으나 안 씀

→ 위 4개는 호환성을 위한 슬롯이거나 향후 확장용. 함수에서 무시해도 무방.

### 변형 B — OCI 환경에서 4분기 UNION 재현 (디폴트)

§V-2 의 4분기 UNION CTE 전체를 그대로 옮긴 뒤, 6행 표를 위한 집계만 다시 한다. CTE 본체는 §V-2 의 `WITH FT AS ... DEFECT_BR ... MOVE_BR ... PCARD_AFTER_CLOSE_BR ... PCARD_EX_BR ... OSND_V3_REPLICA` 를 그대로 사용 (분량 절약 — 여기서는 최종 SELECT 만 표시).

```sql
WITH
  /* §V-2 의 4분기 UNION CTE 본체를 그대로 포함 — 분량 절약을 위해 생략 */
  FT AS                       ( /* §V-2 FT 분기 */ ),
  DEFECT_BR AS                ( /* §V-2 분기 1 */ ),
  MOVE_BR AS                  ( /* §V-2 분기 2 */ ),
  PCARD_AFTER_CLOSE_BR AS     ( /* §V-2 분기 3 */ ),
  PCARD_EX_BR AS              ( /* §V-2 분기 4 */ ),
  OSND_V3_REPLICA AS (
    SELECT * FROM DEFECT_BR
    UNION ALL SELECT * FROM MOVE_BR
    UNION ALL SELECT * FROM PCARD_AFTER_CLOSE_BR
    UNION ALL SELECT * FROM PCARD_EX_BR
  )
SELECT
  IN_DATE,
  TO_CHAR(TO_DATE(IN_DATE, 'YYYYMMDD'), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH')
    || ' - ' ||
  TO_CHAR(MAX(REPLEN_DT), 'DD Mon', 'NLS_DATE_LANGUAGE=ENGLISH') AS YMD,
  SUM(IN_QTY)                                                    AS PROD_QTY,         -- 화면 Incoming Quantity
  SUM(DEFECT_QTY)                                                AS DEFECT_QTY,       -- 화면 OS&D Quantity
  SUM(REPLEN_QTY)                                                AS REPLEN_QTY,       -- 화면 Replenishment
  ROUND(DECODE(SUM(DEFECT_QTY), 0, 0,
               SUM(REPLEN_QTY) / SUM(DEFECT_QTY) * 100), 2)      AS PER,              -- 화면 Replenishment Rate
  ROUND(DECODE(SUM(IN_QTY),     0, 0,
               SUM(DEFECT_QTY) / SUM(IN_QTY)     * 100), 2)      AS OSND_RATE_PCT     -- 화면 OS&D Rate [추측]
FROM OSND_V3_REPLICA
WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
  AND (OSND_TYPE IN ('D', 'S') OR OSND_TYPE IS NULL)
  AND PLANT_CD = :V_PLANT_CD
  AND ITEM_CLASS_TYPE IN (
        SELECT TRIM(REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(NVL(:V_SUPPLY_OP_CD, ITEM_CLASS_TYPE), '[^,]+', 1, LEVEL) IS NOT NULL
      )
  AND SUPPLY_PLANT_CD IN (
        SELECT TRIM(REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL) IS NOT NULL
      )
GROUP BY IN_DATE
ORDER BY IN_DATE ASC;
```

**주의사항**:
- **OSND_TYPE 필터** — DEFECT 분기는 'D'/'S' 값을 가지고, IN_QTY 분기 2~4 는 `'' AS OSND_TYPE` (§V-2 라인 1352, 1388, 1422) 으로 채움. Oracle 에서는 빈 문자열 `''` = NULL 이므로 `OSND_TYPE IS NULL` 한 조건만으로 분기 2~4 가 모두 잡힘. **프로시저 원본 (라인 115) 과 동일한 필터로 충분**.
  - 비-Oracle 호환 시 `OR OSND_TYPE = ''` 추가 (안전망).
- IN_QTY 가 0 인 일자가 있을 수 있음 (그 날 입고는 없고 OS&D 만 있는 경우). 그러면 OS&D Rate = 0 으로 표시.
- 4분기 UNION 사용으로 쿼리 비용 ↑ — Return Rate 만 필요하면 `fn_return_rate_daily` (DEFECT 분기 단독) 가 충분.
- 의존 사용자 정의 함수 `FN_GET_STYLE_INFO`, `FN_GET_PCARD_PLANT` 가 OCI 에 없으면 §V-2 의 분기 3/4 일부 실패 — §V-5 의 대체 방안 참조.

**검증 (필수)**:
- `PROD_QTY > 0` (그 날 입고 있는 모든 일자)
- `DEFECT_QTY ≤ PROD_QTY` (보통 — 같은 IN_DATE 의 입고량 대비 OS&D 일반적으로 1% 미만)
  - 단, OS&D 의 IN_DATE 와 일반 입고의 IN_DATE 가 정확히 같지 않을 수 있어 일자별 비교 시 어긋날 수 있음. 위반 시 데이터 분기 누락 확인.
- `0 ≤ PER ≤ 100`, `0 ≤ OSND_RATE_PCT ≤ 100`
- `REPLEN_QTY ≤ DEFECT_QTY` 항상 성립

[확정: SP_GMES00142_Q_JJ_V5 라인 87-126 + V_PQ_EX_OSND_V3 정의 라인 4-117 검증]
[확정: 프로시저 컬럼명 PROD_QTY/DEFECT_QTY/REPLEN_QTY/PER/YMD 직접 파일 검증]
[추측: OS&D Rate (%) 산식 — 프로시저 CV_2 에 OS&D Rate 컬럼 부재. 클라이언트 그리드 셀 표현식 추정. 실제 화면 결과와 한 번 대조 필요]

---

## `fn_return_rate_target`

**용도**: SCR-006 차트의 Target % 기준선 (CV_4).

```sql
SELECT NVL(TO_NUMBER(EXTRA_COLUMN1), 0)  AS TARGET_VALUE
  FROM OCI.MSBS_CODE_MASTER
 WHERE CODE_CLASS_CD = 'PQ_INSPECT_TYPE'
   AND SUB_CODE      = 'EX';
```

[확정: SP_GMES00142_Q_JJ_V5 라인 67-70]

---

## `fn_return_rate_calendar`

**용도**: SCR-006 의 일자 컬럼 헤더 생성용 (CV_1) — 피벗 그리드의 컬럼 captions.

```sql
SELECT CAL_DATE,
       'D' || CAL_DATE                                                       AS CAL_DATE_COL,
       TO_CHAR(TO_DATE(CAL_DATE, 'YYYYMMDD'), 'Mon', 'NLS_DATE_LANGUAGE=ENGLISH') 
         || CAL_DAY                                                          AS CAL_DATE_CAPTION
  FROM OCI.MSBS_CALENDAR
 WHERE PLANT_CD = '3110'
   AND CAL_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
 ORDER BY CAL_DATE ASC;
```

**참고**: 프로시저는 PLANT_CD 를 하드코딩으로 '3110' (JJ) 으로 고정. 다른 plant 분석 시 변경 필요.

[확정: SP_GMES00142_Q_JJ_V5 라인 44-50]

---

## `fn_return_rate_break_max`

**용도**: SCR-006 차트의 AutoScaleBreaks_MaxCount 설정 (CV_3) — 차트 시각화 옵션 값.

```sql
SELECT EXTRA_COLUMN1                       AS AUTO_SCALE_BREAKS_MAX_COUNT
  FROM OCI.MSBS_CODE_MASTER
 WHERE CODE_CLASS_CD = 'PQ_REPORT'
   AND SUB_CODE      = 'BREAK_EX';
```

[확정: SP_GMES00142_Q_JJ_V5 라인 144-147]

---

## `fn_combo_plant`

**용도**: Plant 드롭다운 — `V_P_WORK_TYPE='COMBO_PLANT'`.

```sql
SELECT DISTINCT 
       PLANT_CD                          AS CODE,
       PLANT_CD || ' - ' || 
       CASE PLANT_CD
         WHEN '3110' THEN 'JJ'
         WHEN '3120' THEN 'CKP'
         WHEN '3210' THEN 'RJ'
         WHEN '3220' THEN 'JJS'
       END                               AS NAME
  FROM OCI.MSBS_WORK_CENTER
 ORDER BY 1;
```

[확정: SP_GMES00142_Q_JJ_V5 라인 159-170]

---

## `fn_combo_process`

**용도**: Process 드롭다운 — `V_P_WORK_TYPE='COMBO_PROCESS'`. 공급 plant 별 필터.

```sql
SELECT 
  CASE 
    WHEN A.EXTRA_COLUMN3 IN ('OSP','PUR','SLM','IPI','UPS','PHH','PHM') 
         THEN SUBSTR(A.EXTRA_COLUMN3, 1, 2)
    WHEN A.EXTRA_COLUMN3 = 'IPI_EXC' THEN 'II'
    WHEN A.EXTRA_COLUMN3 = 'PHH_EXC' THEN 'PP'
  END                                          AS CODE,
  B.CODE_NAME                                  AS NAME
FROM OCI.MSBS_CODE_MASTER A
LEFT JOIN OCI.MSBS_CODE_MASTER B
  ON A.EXTRA_COLUMN3   = B.SUB_CODE
 AND B.CODE_CLASS_CD   = 'PQ_OP_PCARD'
WHERE A.CODE_CLASS_CD  = 'PQ_EX_OSND_SUPPLY_OP_CD'
  AND SUBSTR(A.CODE_NAME, 1, 4) = '3110'
  AND SUBSTR(A.CODE_NAME, 7, 4) IN (
        SELECT TRIM(REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL))
          FROM DUAL
       CONNECT BY REGEXP_SUBSTR(:V_SUPPLY_PLANT, '[^,]+', 1, LEVEL) IS NOT NULL
      );
```

[확정: SP_GMES00142_Q_JJ_V5 라인 173-191]

---

## 부록 — 프로시저 컬럼 매핑 요약

### SCR-005 (P_MSPQ38100S_Q) 화면 컬럼 ↔ 테이블 컬럼

| 화면 컬럼 | 출처 | 비고 |
|---|---|---|
| LINE | `MSPQ_INSPECT_POINT.SUB_WC_CD` | `OS.INSPECT_POINT_ID` 로 조인 |
| OSND_DATE | `MSPQ_EX_OSND.OSND_DATE` | YYYYMMDD |
| CMP | `SUBSTR(SUPPLY_OP_CD, 1, 2)` | 공정 그룹 2 글자 |
| MODEL_NAME | `FN_GET_STYLE_MODEL('MODEL_NAME', STYLE_CD)` | 사용자 정의 함수 |
| STYLE_CD | `STYLE_CD \|\| ' / ' \|\| ITEM_CLASS \|\| ' / ' \|\| ITEM_CLASS_NAME` | 표시용 결합 |
| COLOR_NAME | `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` JOIN | DB link 의존 |
| TYPE | `MSBS_CODE_MASTER.CODE_NAME` (CLASS='PQ_OSND_TYPE') | [확정: DB 직접 조회 2026-03-05] D=Defective, I=Inline Defect, L=Lot Closing Shortage, O=Overrun, S=Shortage |
| SUPPLY_PLANT_CD | `MSPQ_EX_OSND.SUPPLY_PLANT_CD` | 공급 plant |
| SUPPLY_PLANT_NAME | `MSBS_PLANT.PLANT_NAME` | |
| STATUS | UNION 으로 생성 ('REQUEST'/'OUTGOING'/'INCOMING'/'BALANCE') | 화면 4 줄 |
| FX_SIZE_X | `SUM(CASE WHEN SIZE_CD='X' THEN OSND_EX_QTY/2 ELSE 0 END)` | L/R 켤레 환산 |

### SCR-006 (SP_GMES00142_Q_JJ_V5) 컬럼

| 화면 컬럼 | 출처 | 비고 |
|---|---|---|
| IN_DATE | `V_PQ_EX_OSND_V3.IN_DATE` | 입고일자 (OSND_DATE 아님!) |
| DEFECT_QTY | `V_PQ_EX_OSND_V3.DEFECT_QTY` | 'D' + 'S' 합산 (필터 적용) |
| REPLEN_QTY | `V_PQ_EX_OSND_V3.REPLEN_QTY` | 후보충 수량 |
| PER (Return Rate %) | `ROUND(REPLEN/DEFECT * 100, 2)` | 0 으로 나누기 보호 |
| YMD | `TO_CHAR(IN_DATE, 'DD Mon') \|\| ' - ' \|\| TO_CHAR(MAX(REPLEN_DATE), 'DD Mon')` | 표시용 라벨 |

---

## 부록 — 함정 정리

### F-1. CFM_DT 필터 누락
SCR-005 화면을 재현하려는데 숫자가 안 맞으면 `CFM_DT IS NOT NULL` 빠뜨린 경우가 대부분. 자유 분석에서는 생략 가능하지만 화면 일치 확인 시 필수.

### F-2. OSND_EX_QTY ÷ 2
화면의 사이즈별 컬럼은 모두 `OSND_EX_QTY / 2`. 한 카드가 L/R 두 행으로 들어오므로 켤레 단위로 환산하기 위함. 합계 (TOTAL) 만 보면 ÷ 2 가 불필요해 보이지만, 화면 컬럼 단위 정확도 위해 유지.

### F-3. SCR-005 의 PLANT_CD vs SCR-006 의 SUPPLY_PLANT_CD
- SCR-005: `OS.PLANT_CD = V_P_PLANT_CD` (단일, 메인 plant 한 곳)
- SCR-006: `PLANT_CD = V_P_PLANT_CD` + `SUPPLY_PLANT_CD IN (콤마 다중)` (수요 단일 + 공급 다중)

### F-4. SCR-006 의 IN_DATE 의미
`IN_DATE` = 실제 입고 완료된 날짜. `OSND_DATE` 와 다름. Return Rate 는 "이 날 입고된 양 중 후보충 완료된 비율" 이므로 IN_DATE 기준.

### F-5. V_PQ_EX_OSND_V3 부재
**OCI 스키마에 뷰가 배포되어 있지 않음**. LMES 스키마의 원본 뷰가 진실의 출처이며, OCI 에서 동일 결과를 얻으려면 §V 의 재현 SQL 사용. 또는 LMES 직접 접근 권한이 있으면 `LMES.V_PQ_EX_OSND_V3` 호출.

### F-6. DB Link 컬럼 (`@JJEDIF`)
`EPBS_MOLD_MASTER@JJEDIF`, `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` 는 OCI 환경에서 DB link 미설정일 가능성 — COLOR_NAME 분석은 빈 값 처리하거나 분석 범위에서 제외.

**색상명 대안**: `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` 대신 [`fn_color_lookup_cte`](#fn_color_lookup_cte) (박제 15개) + [`fn_color_dynamic_extract`](#fn_color_dynamic_extract) (`MSBS_ITEM.MCS_COLOR_CD` 텍스트 파싱) 조합으로 OCI 내에서 매핑 가능. 통합 사용은 [`fn_osnd_screen_pivot_with_color`](#fn_osnd_screen_pivot_with_color) 참조.

### F-7. V_PQ_EX_OSND_V3 재현 시 분기 누락
뷰는 4 개 UNION ALL 분기로 구성 (§V-2 참조):
1. DEFECT 분기 — `MSPQ_EX_OSND` 의 결함 (DEFECT_QTY, REPLEN_QTY)
2. 마감 IN_QTY 분기 — `MSPQ_MATERIAL_MOVE` (마감일자 이전 입고)
3. 마감 후 IN_QTY 분기 — `MSPD_PCARD_RESULT` (마감일자 이후, PROD_MOVE_TYPE='MOVE')
4. EX% 항목 추가 IN_QTY 분기 — `MSPD_PCARD_RESULT` + `PQ_EX_ITEM_CLASS` 매핑

**Return Rate 계산만 필요하면 분기 1 만 사용 (DEFECT_QTY, REPLEN_QTY 가 분기 1 에서만 채워짐)**. PROD_QTY (IN_QTY) 가 필요하면 4 분기 전체.

---

## 부록 §V — V_PQ_EX_OSND_V3 뷰 정의 및 OCI 재현

> **OCI 스키마에 이 뷰가 없으므로 SCR-006 함수에서 직접 호출하지 못한다.** 아래 §V-1 은 원본 정의, §V-2 는 OCI 재현 패턴이다.

### V-1. 원본 뷰 컬럼 시그니처 (LMES.V_PQ_EX_OSND_V3)

| 컬럼 | 출처 | 의미 |
|---|---|---|
| COMPANY_CD, COMPANY_NAME | `MSPQ_RPT_IP.COMPANY_CD/NAME` | 회사 |
| PLANT_CD, PLANT_NAME | `MSPQ_RPT_IP.PLANT_CD/NAME` | 수요 Plant |
| PB_CD, PB_NAME | `MSPQ_RPT_IP.PB_CD/NAME` | PB 코드 |
| SUPPLY_PLANT_CD | `MSPQ_EX_OSND.SUPPLY_PLANT_CD` 또는 PCARD 분기에서는 `FN_GET_PCARD_PLANT()` | 공급 Plant |
| ITEM_CLASS_TYPE | `SUBSTR(ITEM_CD, 10, 2)` | 아이템 클래스 (2 글자) |
| IN_DATE | DEFECT 분기: `OSND_DATE` / IN_QTY 분기: `MOVE_DATE` 또는 `IN_DATE` | 입고일 |
| LN | `SUBSTR(RES_CD, 4, 3)` 또는 `SUBSTR(ERP_WC_TO, 4, 3)` | 라인 |
| MODEL_CD, MODEL_NAME | `FN_GET_STYLE_INFO('MODEL_CD'/'MODEL_NAME', STYLE_CD)` | 모델 |
| STYLE_CD | `SUBSTR(ITEM_CD, 1, 6) \|\| '-' \|\| SUBSTR(ITEM_CD, 7, 3)` | 스타일 (재조립) |
| REASON_CD | DEFECT 분기: `MSPQ_EX_OSND.REASON_CD` / IN_QTY 분기: `'IN_QTY'` | 사유 코드 |
| OSND_TYPE | DEFECT 분기: `MSPQ_EX_OSND.OSND_TYPE` (D/L/I/S/O) / IN_QTY 분기: `''` | OS&D 타입 |
| REASON_NAME | `FN_GET_DEFECT_REASON(PLANT_CD, REASON_CD)` | 사유명 |
| IN_QTY | DEFECT 분기: 0 / 입고 분기: `MOVE_QTY` 또는 `PCARD_QTY` | 입고 수량 |
| DEFECT_QTY | DEFECT 분기: `OSND_EX_QTY / 2` / 그 외: 0 | 결함 수량 (L/R 켤레 환산) |
| DEFECT_{O/S/D/I/L}_QTY | `DECODE(OSND_TYPE, 'X', OSND_EX_QTY/2, 0)` | 타입별 결함 (켤레) |
| REPLEN_QTY | `DECODE(I_SCN_DT, NULL, 0, OSND_EX_QTY) / 2` | 후보충 수량 (입고 완료만) |
| REPLEN_{O/S/D/I/L}_QTY | 위 식 + `DECODE(OSND_TYPE, 'X', ...)` 결합 | 타입별 후보충 |
| SEND_QTY | `DECODE(O_SCN_DT, NULL, 0, OSND_EX_QTY) / 2` | 출고 수량 |
| PREPARE_QTY | `DECODE(P_SCN_DT, NULL, 0, OSND_EX_QTY) / 2` | 생산 스캔 수량 |
| REPLEN_{DATE/O_DATE/S_DATE/D_DATE/I_DATE/L_DATE} | `TO_CHAR(MAX(I_SCN_DT), 'YYYYMMDD')` | 후보충 일자 (타입별) |

[확정: V_PQ_EX_OSND_V3 정의 파일 라인 4-11 검증]

### V-2. OCI 재현 — 전체 4 분기 CTE

DEFECT 분기 1 + IN_QTY 분기 2 ~ 4 를 모두 옮긴 풀 재현. 자유 분석이나 IN_QTY/SEND_QTY/PREPARE_QTY 통합 시 사용.

**의존 OCI 테이블**:
- `OCI.MSPQ_EX_OSND` (DEFECT 분기 1)
- `OCI.MSPQ_RPT_IP` (모든 분기, Inspection Point + Plant 정보)
- `OCI.MSBS_CODE_MASTER` (분기 1: PQ_OSND_TYPE, 분기 4: PQ_EX_ITEM_CLASS)
- `OCI.MSPQ_OP_DEFECT` (분기 1 OUTER, REASON_NAME 채우기 — 없어도 결과 가능)
- `OCI.MSPQ_MATERIAL_MOVE` (분기 2)
- `OCI.MSPD_PCARD_RESULT` (분기 3, 4)
- `OCI.MSBS_PLANT` (분기 2)

```sql
WITH
-- 마감 일자 산정 (뷰 라인 13-24)
FT AS (
  SELECT PLANT_TO,
         WC_TO              AS ERP_WC_TO,
         SUBSTR(ITEM_CD, 10, 2) AS ITEM_CLASS_TYPE,
         MAX(CLOSING_DATE)  AS CLOSE_END_DATE
    FROM OCI.MSPQ_MATERIAL_MOVE
   WHERE WC_TO LIKE 'F%' OR WC_TO LIKE 'UPS%'
   GROUP BY PLANT_TO, WC_TO, SUBSTR(ITEM_CD, 10, 2)
),
-- 분기 1: DEFECT (MSPQ_EX_OSND)
DEFECT_BR AS (
  SELECT 
    IP.COMPANY_CD, IP.COMPANY_NAME, IP.PLANT_CD, IP.PLANT_NAME, IP.PB_CD, IP.PB_NAME,
    B.SUPPLY_PLANT_CD,
    SUBSTR(B.ITEM_CD, 10, 2)                                  AS ITEM_CLASS_TYPE,
    B.OSND_DATE                                               AS IN_DATE,
    SUBSTR(IP.RES_CD, 4, 3)                                   AS LN,
    SUBSTR(B.ITEM_CD, 1, 6) || '-' || SUBSTR(B.ITEM_CD, 7, 3) AS STYLE_CD,
    B.REASON_CD, B.OSND_TYPE,
    0                                                         AS IN_QTY,
    B.OSND_EX_QTY / 2                                         AS DEFECT_QTY,
    DECODE(B.OSND_TYPE, 'O', B.OSND_EX_QTY / 2, 0)            AS DEFECT_O_QTY,
    DECODE(B.OSND_TYPE, 'S', B.OSND_EX_QTY / 2, 0)            AS DEFECT_S_QTY,
    DECODE(B.OSND_TYPE, 'D', B.OSND_EX_QTY / 2, 0)            AS DEFECT_D_QTY,
    DECODE(B.OSND_TYPE, 'I', B.OSND_EX_QTY / 2, 0)            AS DEFECT_I_QTY,
    DECODE(B.OSND_TYPE, 'L', B.OSND_EX_QTY / 2, 0)            AS DEFECT_L_QTY,
    DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2            AS REPLEN_QTY,
    DECODE(B.OSND_TYPE, 'O', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_O_QTY,
    DECODE(B.OSND_TYPE, 'S', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_S_QTY,
    DECODE(B.OSND_TYPE, 'D', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_D_QTY,
    DECODE(B.OSND_TYPE, 'I', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_I_QTY,
    DECODE(B.OSND_TYPE, 'L', DECODE(B.I_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2, 0) AS REPLEN_L_QTY,
    DECODE(B.O_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2            AS SEND_QTY,
    DECODE(B.P_SCN_DT, NULL, 0, B.OSND_EX_QTY) / 2            AS PREPARE_QTY,
    B.I_SCN_DT                                                AS REPLEN_DT
  FROM OCI.MSPQ_EX_OSND B
       INNER JOIN OCI.MSPQ_RPT_IP IP
          ON B.PLANT_CD         = IP.PLANT_CD
         AND B.INSPECT_POINT_ID = IP.INSPECT_POINT_ID
       INNER JOIN OCI.MSBS_CODE_MASTER CM
          ON B.OSND_TYPE        = CM.SUB_CODE
         AND CM.CODE_CLASS_CD   = 'PQ_OSND_TYPE'
         AND CM.USE_YN          = 'Y'
  WHERE B.CFM_DT     IS NOT NULL
    AND B.CANCEL_YN  = 'N'
),
-- 분기 2: 마감 IN_QTY (MSPQ_MATERIAL_MOVE)
MOVE_BR AS (
  SELECT 
    IP.COMPANY_CD, IP.COMPANY_NAME, IP.PLANT_CD, IP.PLANT_NAME, IP.PB_CD, IP.PB_NAME,
    MV.PLANT_CD                                               AS SUPPLY_PLANT_CD,
    SUBSTR(MV.ITEM_CD, 10, 2)                                 AS ITEM_CLASS_TYPE,
    MV.MOVE_DATE                                              AS IN_DATE,
    SUBSTR(MV.ERP_WC_TO, 4, 3)                                AS LN,
    SUBSTR(MV.ITEM_CD, 1, 6) || '-' || SUBSTR(MV.ITEM_CD, 7, 3) AS STYLE_CD,
    'IN_QTY' AS REASON_CD, '' AS OSND_TYPE,
    MV.MOVE_QTY                                               AS IN_QTY,
    0 AS DEFECT_QTY, 0 AS DEFECT_O_QTY, 0 AS DEFECT_S_QTY, 0 AS DEFECT_D_QTY, 0 AS DEFECT_I_QTY, 0 AS DEFECT_L_QTY,
    0 AS REPLEN_QTY, 0 AS REPLEN_O_QTY, 0 AS REPLEN_S_QTY, 0 AS REPLEN_D_QTY, 0 AS REPLEN_I_QTY, 0 AS REPLEN_L_QTY,
    0 AS SEND_QTY, 0 AS PREPARE_QTY, NULL AS REPLEN_DT
  FROM OCI.MSPQ_MATERIAL_MOVE MV
       INNER JOIN (
         SELECT COMPANY_CD, COMPANY_NAME, PLANT_CD, PLANT_NAME, PB_CD, PB_NAME, RES_CD AS ERP_WC_CD
           FROM OCI.MSPQ_RPT_IP
          WHERE PLANT_CD LIKE '%' AND INSPECT_POINT_ID LIKE 'EX%'
          UNION ALL
         SELECT COMPANY_CD, COMPANY_NAME, PLANT_CD, PLANT_NAME, PB_CD, PB_NAME,
                'FSS' || SUBSTR(RES_CD, 4, 2) AS ERP_WC_CD
           FROM OCI.MSPQ_RPT_IP
          WHERE PLANT_CD IN (SELECT PLANT_CD FROM OCI.MSBS_PLANT WHERE USE_YN = 'Y')
            AND INSPECT_POINT_ID LIKE 'EX%'
       ) IP
          ON MV.PLANT_TO   = IP.PLANT_CD
         AND MV.ERP_WC_TO  = IP.ERP_WC_CD
       INNER JOIN FT
          ON MV.PLANT_TO   = FT.PLANT_TO
         AND MV.ERP_WC_TO  = FT.ERP_WC_TO
         AND SUBSTR(MV.ITEM_CD, 10, 2) = FT.ITEM_CLASS_TYPE
  WHERE MV.MOVE_DATE    <= FT.CLOSE_END_DATE
    AND MV.ERP_WH_TO    LIKE '5%'
    AND MV.RESULT_TYPE  = 'SCAN'
),
-- 분기 3: 마감 후 IN_QTY (MSPD_PCARD_RESULT, MOVE)
PCARD_AFTER_CLOSE_BR AS (
  SELECT 
    IP.COMPANY_CD, IP.COMPANY_NAME, IP.PLANT_CD, IP.PLANT_NAME, IP.PB_CD, IP.PB_NAME,
    FN_GET_PCARD_PLANT(IP.PLANT_CD, MV.PCARD_NAME, MV.ITEM_CLASS) AS SUPPLY_PLANT_CD,
    SUBSTR(MV.ITEM_CD, 10, 2)                                 AS ITEM_CLASS_TYPE,
    MV.IN_DATE                                                AS IN_DATE,
    SUBSTR(MV.ERP_IN_WC_CD, 4, 3)                             AS LN,
    SUBSTR(MV.ITEM_CD, 1, 6) || '-' || SUBSTR(MV.ITEM_CD, 7, 3) AS STYLE_CD,
    'IN_QTY' AS REASON_CD, '' AS OSND_TYPE,
    MV.PCARD_QTY                                              AS IN_QTY,
    0,0,0,0,0,0,  0,0,0,0,0,0,  0,0, NULL
  FROM OCI.MSPD_PCARD_RESULT MV
       INNER JOIN (
         SELECT COMPANY_CD, COMPANY_NAME, PLANT_CD, PLANT_NAME, PB_CD, PB_NAME, RES_CD AS ERP_WC_CD
           FROM OCI.MSPQ_RPT_IP
          WHERE PLANT_CD LIKE '%' AND INSPECT_POINT_ID LIKE 'EX%'
          UNION ALL
         SELECT COMPANY_CD, COMPANY_NAME, PLANT_CD, PLANT_NAME, PB_CD, PB_NAME,
                'FSS' || SUBSTR(RES_CD, 4, 2) AS ERP_WC_CD
           FROM OCI.MSPQ_RPT_IP
          WHERE PLANT_CD IN (SELECT PLANT_CD FROM OCI.MSBS_PLANT WHERE USE_YN = 'Y')
            AND INSPECT_POINT_ID LIKE 'EX%'
       ) IP
          ON MV.ITPO_WC_PLANT_CD = IP.PLANT_CD
         AND MV.ERP_IN_WC_CD     = IP.ERP_WC_CD
       INNER JOIN FT
          ON MV.ITPO_WC_PLANT_CD = FT.PLANT_TO
         AND MV.ERP_IN_WC_CD     = FT.ERP_WC_TO
         AND SUBSTR(MV.ITEM_CD, 10, 2) = FT.ITEM_CLASS_TYPE
  WHERE MV.IN_DATE        > FT.CLOSE_END_DATE
    AND MV.IN_WH_CD       LIKE '5%'
    AND MV.PROD_MOVE_TYPE = 'MOVE'
),
-- 분기 4: EX% 항목 추가 IN_QTY (MSPD_PCARD_RESULT + PQ_EX_ITEM_CLASS)
PCARD_EX_BR AS (
  SELECT 
    IP.COMPANY_CD, IP.COMPANY_NAME, IP.PLANT_CD, IP.PLANT_NAME, IP.PB_CD, IP.PB_NAME,
    FN_GET_PCARD_PLANT(IP.PLANT_CD, MV.PCARD_NAME, MV.ITEM_CLASS) AS SUPPLY_PLANT_CD,
    SUBSTR(MV.ITEM_CD, 10, 2)                                 AS ITEM_CLASS_TYPE,
    MV.IN_DATE                                                AS IN_DATE,
    SUBSTR(MV.ERP_IN_WC_CD, 4, 3)                             AS LN,
    SUBSTR(MV.ITEM_CD, 1, 6) || '-' || SUBSTR(MV.ITEM_CD, 7, 3) AS STYLE_CD,
    'IN_QTY' AS REASON_CD, '' AS OSND_TYPE,
    MV.PCARD_QTY                                              AS IN_QTY,
    0,0,0,0,0,0,  0,0,0,0,0,0,  0,0, NULL
  FROM OCI.MSPD_PCARD_RESULT MV
       INNER JOIN (
         SELECT COMPANY_CD, COMPANY_NAME, PLANT_CD, PLANT_NAME, PB_CD, PB_NAME, RES_CD AS ERP_WC_CD
           FROM OCI.MSPQ_RPT_IP
          WHERE PLANT_CD LIKE '%' AND INSPECT_POINT_ID LIKE 'EX%'
       ) IP
          ON MV.ITPO_WC_PLANT_CD = IP.PLANT_CD
         AND ( MV.ERP_IN_WC_CD   = IP.ERP_WC_CD
            OR MV.ERP_FA_WC_CD   = IP.ERP_WC_CD )
  WHERE MV.IN_WH_CD       LIKE '5%'
    AND MV.PROD_MOVE_TYPE = 'MOVE'
    AND MV.ITEM_CLASS_TYPE IN (
          SELECT SUB_CODE FROM OCI.MSBS_CODE_MASTER
           WHERE CODE_CLASS_CD = 'PQ_EX_ITEM_CLASS' AND USE_YN = 'Y'
        )
),
-- 4 분기 UNION
OSND_V3_REPLICA AS (
  SELECT * FROM DEFECT_BR
  UNION ALL SELECT * FROM MOVE_BR
  UNION ALL SELECT * FROM PCARD_AFTER_CLOSE_BR
  UNION ALL SELECT * FROM PCARD_EX_BR
)
-- 최종 집계 (뷰 라인 26-62 GROUP BY 와 동일)
SELECT 
  MAX(COMPANY_CD) AS COMPANY_CD, MAX(COMPANY_NAME) AS COMPANY_NAME,
  PLANT_CD, MAX(PLANT_NAME) AS PLANT_NAME,
  PB_CD, MAX(PB_NAME) AS PB_NAME,
  SUPPLY_PLANT_CD, ITEM_CLASS_TYPE, IN_DATE, LN,
  FN_GET_STYLE_INFO('MODEL_CD',   STYLE_CD) AS MODEL_CD,
  FN_GET_STYLE_INFO('MODEL_NAME', STYLE_CD) AS MODEL_NAME,
  STYLE_CD, REASON_CD, OSND_TYPE,
  SUM(IN_QTY) AS IN_QTY,
  SUM(DEFECT_QTY) AS DEFECT_QTY,
  SUM(DEFECT_O_QTY) AS DEFECT_O_QTY, SUM(DEFECT_S_QTY) AS DEFECT_S_QTY,
  SUM(DEFECT_D_QTY) AS DEFECT_D_QTY, SUM(DEFECT_I_QTY) AS DEFECT_I_QTY,
  SUM(DEFECT_L_QTY) AS DEFECT_L_QTY,
  SUM(REPLEN_QTY) AS REPLEN_QTY,
  SUM(REPLEN_O_QTY) AS REPLEN_O_QTY, SUM(REPLEN_S_QTY) AS REPLEN_S_QTY,
  SUM(REPLEN_D_QTY) AS REPLEN_D_QTY, SUM(REPLEN_I_QTY) AS REPLEN_I_QTY,
  SUM(REPLEN_L_QTY) AS REPLEN_L_QTY,
  SUM(SEND_QTY) AS SEND_QTY,
  SUM(PREPARE_QTY) AS PREPARE_QTY,
  TO_CHAR(MAX(REPLEN_DT), 'YYYYMMDD') AS REPLEN_DATE
FROM OSND_V3_REPLICA
WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
GROUP BY PLANT_CD, PB_CD, SUPPLY_PLANT_CD, ITEM_CLASS_TYPE,
         IN_DATE, LN, STYLE_CD, REASON_CD, OSND_TYPE;
```

### V-3. OCI 재현 검증 체크리스트

원본 뷰 vs 재현 결과 일치 검증 (LMES 직접 접근 가능할 때):

```sql
-- 1) 같은 날짜·plant 의 row count 비교
WITH ORIG AS (
  SELECT COUNT(*) AS CNT FROM LMES.V_PQ_EX_OSND_V3
   WHERE IN_DATE BETWEEN :V_IN_DATE_F AND :V_IN_DATE_T
     AND PLANT_CD = :V_PLANT_CD
), REP AS (
  SELECT COUNT(*) AS CNT FROM ( /* §V-2 OSND_V3_REPLICA 의 최종 SELECT */ )
)
SELECT ORIG.CNT, REP.CNT, ORIG.CNT - REP.CNT AS DIFF FROM ORIG, REP;

-- 2) DEFECT_QTY 합계 검증 — 분기 1 만 영향
SELECT SUM(DEFECT_QTY) FROM LMES.V_PQ_EX_OSND_V3 WHERE ...
SELECT SUM(DEFECT_QTY) FROM (/* §V-2 */)  WHERE ...
-- 두 값이 같아야 함

-- 3) REPLEN_QTY 합계 검증
-- 두 값이 같아야 함

-- 4) IN_QTY 검증 — 분기 2~4 모두 합쳐서 비교
```

### V-4. OCI 의존 테이블 존재 확인

재현 SQL 실행 전 다음 테이블이 OCI 에 있는지 먼저 확인:

```sql
SELECT TABLE_NAME, 
       (SELECT COUNT(*) FROM USER_TABLES UT WHERE UT.TABLE_NAME = T.TABLE_NAME) AS EXISTS_FLAG
FROM (
  SELECT 'MSPQ_EX_OSND'        AS TABLE_NAME FROM DUAL UNION ALL
  SELECT 'MSPQ_RPT_IP'         FROM DUAL UNION ALL
  SELECT 'MSBS_CODE_MASTER'    FROM DUAL UNION ALL
  SELECT 'MSPQ_OP_DEFECT'      FROM DUAL UNION ALL
  SELECT 'MSPQ_MATERIAL_MOVE'  FROM DUAL UNION ALL
  SELECT 'MSPD_PCARD_RESULT'   FROM DUAL UNION ALL
  SELECT 'MSBS_PLANT'          FROM DUAL
) T;

-- 또는 ALL_TABLES 로:
SELECT TABLE_NAME FROM ALL_TABLES
 WHERE OWNER = 'OCI'
   AND TABLE_NAME IN ('MSPQ_EX_OSND','MSPQ_RPT_IP','MSBS_CODE_MASTER',
                      'MSPQ_OP_DEFECT','MSPQ_MATERIAL_MOVE','MSPD_PCARD_RESULT','MSBS_PLANT');
```

테이블 누락 시:
- `MSPQ_RPT_IP` 없음 → LN 분해 불가, DEFECT 분기 단순 집계까지만 가능
- `MSPQ_MATERIAL_MOVE` 없음 → 분기 2 생략, 마감 전 IN_QTY 미반영
- `MSPD_PCARD_RESULT` 없음 → 분기 3, 4 생략, 마감 후 IN_QTY 미반영
- `MSPQ_EX_OSND` 없음 → SCR-006 자체 불가

### V-5. 함수 `FN_GET_STYLE_INFO`, `FN_GET_PCARD_PLANT`, `FN_GET_DEFECT_REASON` 부재 시

이들은 사용자 정의 함수이며 OCI 환경에 없을 수 있다. 부재 시 대체:

| 함수 | 의도 | OCI 대체 |
|---|---|---|
| `FN_GET_STYLE_INFO('MODEL_CD', STYLE_CD)` | 스타일에서 모델 코드 추출 | `SUBSTR(STYLE_CD, 1, 6)` (앞 6 자리) |
| `FN_GET_STYLE_INFO('MODEL_NAME', STYLE_CD)` | 스타일에서 모델명 | 함수 없으면 NULL, 또는 `MSBS_ITEM_CLASS` 등 별도 join 필요 |
| `FN_GET_PCARD_PLANT(PLANT, PCARD_NAME, ITEM_CLASS)` | PCARD 로 공급 plant 찾기 | 단순 대체 어려움 — `MSPD_PCARD_RESULT` 의 다른 컬럼 (`ITPO_WC_PLANT_CD` 등) 사용 검토 |
| `FN_GET_DEFECT_REASON(PLANT_CD, REASON_CD)` | 사유명 lookup | `MSPQ_OP_DEFECT` 또는 `MSBS_CODE_MASTER` join 으로 대체 |

함수가 없으면 해당 컬럼은 NULL 또는 raw 값으로 두고, 답변에 `[추정: 함수 부재로 모델명 미반영]` 명시.
