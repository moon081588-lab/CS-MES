# Functions — In-Out Cross Check

수불 관리 도메인 (SCR-003 P-O + SCR-004 O-I) 의 SQL 골격 모음.

`workflows/inout-cross-check.md` 가 절차·함정·검증을 다루고, 이 파일은 **SQL 골격** 만 모은다.

**바인드 변수 규약**:
- `:V_DATE` — YYYYMMDD VARCHAR8
- `:V_DATE_F`, `:V_DATE_T` — 범위 조회용
- `:V_COUNTRY` — COUNTRY_CD 1 개 (예: '3000' = Indonesia). 프로시저 입력 `V_P_COUNTRY_CD`
- `:V_COMPANY` — COMPANY_CD (콤마 구분 멀티 가능). 프로시저 입력 `V_P_COMPANY_CD`
- `:V_FORM_ID` — 화면 form id (P-O = 'MSPD51000S' / O-I = 'MSPD52000S' 추정). 프로시저 입력 `V_P_FORM_ID`
- `:V_LINE_CD` — DETAIL_SIZE_DETAIL 의 라인 1 개 (`MSBS_SUM_GROUP_CD.VIEW_GROUP_CD`)
- `:V_CHECK_GROUP_CD` — 'OS','PP','PH','PU','II','IP','IPJ','CF','FS','UP','SL' 중 1 개. 프로시저 입력 `V_P_ITEM_CLASS_TYPE`
- `:V_STYLE`, `:V_SIZE`, `:V_ITEM_CLASS` — DETAIL_SIZE_DETAIL 의 추가 필터
- `:V_IO_TYPE` — DETAIL_SIZE_DETAIL 분기 분류 (P-O: 'P'/'P1'/'O'/'O1', O-I: 'OI'/'O'/'I'/'IN')
- `:V_FIRST_ITEM` — 'Y'/'N'. 카드별 ITEM_CLASS 중복 처리 (Y=첫 ITEM_CLASS row 만, N=전체)
- `:V_PCARD_LIST` — PCARD_NAME 리스트 (SCAN_DATA 용)

**공통 룰**:
- 모든 분기: `RESULT_TYPE = 'SCAN'` 필수
- 모든 분기: `END_ROUTING_YN = 'Y'` (라인 마지막 공정)
- P-O Cross: 생산도 출고도 `PROD_MOVE_TYPE = 'PROD'`
- O-I Cross: 출고는 `'PROD'`, 입고는 `'MOVE'` ← 다름
- IPI/PHH 의 Cross-plant MOVE EXISTS 룰 (양쪽 모두 적용, O-I 는 `ITEM_CLASS LIKE 'II9%'` 예외 추가)
- PROD_ORDER_TYPE 'ZCP'/'ZSH'/'ZST' + BOMLEVEL=0 제외 (양쪽 모두)
- JJ Insole 표시 제외: `FA_PLANT_CD='3110' AND ITEM_CLASS_TYPE='SL'` 인 row 제외 (O-I 만 명시. P-O 도 적용해야 정합)
- 카드 중복 제거: `ROW_NUMBER() OVER (PARTITION BY PCARD_NAME, ITEM_CLASS_TYPE ...) AS FIRST_ITEM` 후 `:V_FIRST_ITEM` 으로 필터

---

## 사용 Oracle 헬퍼 함수

| 함수 | 호출 위치 | 역할 | OCI 호환 |
|---|---|---|---|
| `FN_GET_CH_PLAN(date, wc_cd)` | 양쪽 MAIN (WC_LIST CTE) | 라인별 Cutting House 계획 수량 | ⚠️ MSBS_SHIFT 부재 → 항상 0 반환 가능. 답변에 "[참고] CH Plan 은 OCI 에서 0/NULL" 명시 |
| `TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', cnt_cd, 'GMES_PLANT'))` | **SCR-003** DETAIL / DETAIL_SIZE / DETAIL_SIZE_DETAIL 의 `PLANT_CD IN (...)` 필터 | COUNTRY → 자식 PLANT 리스트 pipelined | ✓ MSBS_ORGANIZATION_SUB + MSBS_ORGANIZATION 존재 |
| `FN_GET_STYLE_MODEL('', style_cd)` | 양쪽 DETAIL / DETAIL_SIZE / DETAIL_SIZE_DETAIL / SCAN_DATA 의 SELECT | STYLE_CD → STYLE_NAME | ⚠️ MSBS_ITEM 미 yaml 정의 (표시용이라 영향 작음) |
| `FN_GET_DATE_FORMAT(YMD)` | 양쪽 SCAN_DATA | 'YYYYMMDD' → 'YYYY-MM-DD' | ✓ pure substr, 안전 |
| `FN_GET_TIME_FORMAT(HMS)` | 양쪽 SCAN_DATA | 'HHMMSS' → 'HH:MI:SS' | ✓ pure substr, 안전 |

`FN_GET_BT_SHIFT`, `FN_MCS_COLOR` 는 이 도메인에서 호출되지 않음 (각각 SCR-002, SCR-001 전용).

---

## ★ P-O 와 O-I 의 Plant 필터 비대칭

같은 `MSPD_PCARD_RESULT` 테이블을 보지만 두 프로시저가 COUNTRY → PLANT 펼침을 다르게 짠다.

| 분기 | SCR-003 (P-O, P_MSPD51000S_Q_V24) | SCR-004 (O-I, P_MSPD52000S_Q_V39) |
|---|---|---|
| **MAIN** | `WITH W_ORG AS (SELECT ... FROM MSBS_ORGANIZATION_SUB ...)` 인라인 CTE | 동일하게 `WITH W_ORG AS (...)` 인라인 CTE |
| **DETAIL / DETAIL_SIZE / DETAIL_SIZE_DETAIL** | W_ORG CTE 와 `PLANT_CD IN (SELECT ORG.ORG_CD FROM TABLE(FN_GET_CHILD_ORG_LIST(...)))` **둘 다 사용** | W_ORG/ORG CTE **만** 사용 (FN_GET_CHILD_ORG_LIST 호출 없음) |

**의미**: 결과는 같지만 구현이 다르다. 자유 분석 시 정확도 검증 차원에서:
- P-O 의 plant 필터를 재현하려면 `TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', :V_COUNTRY, 'GMES_PLANT'))` 그대로 또는 `MSBS_ORGANIZATION_SUB` JOIN 둘 다 가능
- O-I 의 plant 필터를 재현하려면 `MSBS_ORGANIZATION_SUB` JOIN 만 사용

수불 도메인 답변 시 두 화면을 한 묶음으로 다루면서도 SQL 은 반드시 분기 분리.

[확정: P_MSPD51000S_Q_V24 L615/L658/L673/L900/L941/L956/L1230/L1273/L1288 vs P_MSPD52000S_Q_V39 전 분기 grep 결과 (FN_GET_CHILD_ORG_LIST 호출 없음) 대조 검증]

---

## ★ OCI 환경 한정 SQL 단순화 — `fn_po_cross_main` / `fn_oi_cross_main` 공통

원본 프로시저를 OCI 에서 그대로 실행하면 **240 초+ 타임아웃**. 다음 3 가지 단순화를 적용하면 **수 초 ~ 30 초** 로 떨어진다. 결과 값은 동일.

[확정: 2026-05-19 / 2026-03-02 ~ 03-06 5 일치 / Country=3000 전체 / P-O · O-I 양쪽 검증 — 단순화 SQL 결과가 화면 캡쳐와 100% 일치]

### 단순화 (1) IPI/PHH Cross-plant EXISTS 룰 → 단순 NOT IN

★★★ **적용 범위 — OUT leg 전용. PROD leg 에는 적용 금지** ★★★

원본 IPI/PHH Cross-plant EXISTS 룰은 **출고 (OUT) leg 에만 존재** (P-O 의 MOVE/OUT leg, O-I 의 INOUT_OK·ONLY_OUT leg). PRODUCTION leg 의 원본 조건은 단순히 `OP_CD <> 'UPC'` 만 존재 — IPI/PHH 는 PROD 으로 정상 카운트됨.

[확정: P_MSPD51000S_Q_V24 — PROD leg (L233-296) WHERE 절은 `OP_CD <> 'UPC'`. OUT leg (L297-321) 만 EXISTS 룰 적용.]

원본 OUT leg 조건:
```sql
AND ( PO_T.OP_CD NOT IN ('IPI','PHH')
   OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                WHERE RES.PCARD_NAME = PO_T.PCARD_NAME
                  AND RES.ITEM_CD    = PO_T.ITEM_CD
                  AND RES.PROD_MOVE_TYPE = 'MOVE'
                  AND RES.PLANT_CD  <> PO_T.PLANT_CD) )
```

**OCI 환경에서는 모든 IPI/PHH 출고가 EXISTS 조건 불만족** → 결국 `AND OP_CD NOT IN ('IPI','PHH')` 와 동일.

검증:
```sql
-- OCI 에서 직접 확인 (2026-03-02 기준)
SELECT OP_CD, SUM(PCARD_QTY) FROM OCI.MSPD_PCARD_RESULT PO_T
 WHERE OUT_DATE='20260302' AND PROD_MOVE_TYPE='PROD' AND END_ROUTING_YN='Y' AND RESULT_TYPE='SCAN'
   AND OP_CD IN ('IPI','PHH')
   AND EXISTS (SELECT 1 FROM OCI.MSPD_PCARD_RESULT RES
                WHERE RES.PCARD_NAME=PO_T.PCARD_NAME AND RES.ITEM_CD=PO_T.ITEM_CD
                  AND RES.PROD_MOVE_TYPE='MOVE' AND RES.PLANT_CD<>PO_T.PLANT_CD)
 GROUP BY OP_CD
-- 결과: 0 rows (모든 IPI/PHH 출고가 cross-plant MOVE 없음)
```

→ 권장 대체 (**OUT leg 한정**):
```sql
-- OUT leg (OUT_DATE 필터 사용하는 leg)
AND PO_T.OP_CD NOT IN ('UPC','IPI','PHH')   -- UPC 는 본래 제외 룰과 합침
```

→ PRODUCTION leg 는 **원본 그대로 유지**:
```sql
-- PROD leg (PROD_DATE 필터 사용하는 leg)
AND PO_T.OP_CD <> 'UPC'   -- ★ IPI/PHH 는 제외 안 함! 생산은 모든 OP 포함
```

**효과**: EXISTS subquery scan 제거 → 가장 큰 성능 개선. 240 초+ 타임아웃 → 수 초.

#### ★ 흔한 오용 사례 (2026-05-19 fresh 검증에서 발견)

검증자가 단순화 (1) 을 **PROD leg 와 OUT leg 양쪽에 적용**하면 PROD leg 에서 IPI/PHH 카드가 부당하게 제외되어 **Summary Prod undercount 발생**. 결과:

| 일자 | 잘못 적용 시 Bottom Sum Prod | 캡쳐 | 차이 |
|---|---:|---:|---:|
| 2026-03-02 | 317,678 | 349,475 | -31,797 |
| 2026-03-03 | 330,966 | 366,435 | -35,469 |
| 2026-03-04 | 330,331 | 364,939 | -34,608 |
| 2026-03-05 | 319,350 | 347,601 | -28,251 |
| 2026-03-06 | 310,301 | 344,475 | -34,174 |

**올바르게 적용 시 (PROD leg `<> 'UPC'`, OUT leg `NOT IN ('UPC','IPI','PHH')`, 그리고 ★ 단일 :V_DATE 로 실행)**:

| 일자 | Bottom Sum Prod | 캡쳐 | 정합 |
|---|---:|---:|---:|
| 2026-03-02 | 349,475 | 349,475 | ✓ |
| 2026-03-03 | 366,435 | 366,435 | ✓ |
| 2026-03-04 | 364,939 | 364,939 | ✓ |
| 2026-03-05 | 347,601 | 347,601 | ✓ |
| 2026-03-06 | 344,475 | 344,475 | ✓ |

[확정: 2026-05-19 진단 SQL — PROD leg `<> 'UPC'` + 단일 :V_DATE 실행 시 5 일치 100% 정합]

### 단순화 (1) 잘못 적용의 또 다른 증상 — multi-date OR 쿼리 (★ 주의)

여러 일자를 한 SQL 로 측정 (예: 추세 분석 시 `WHERE PROD_DATE IN ('20260302','20260303',...)`) 하면 ROW_NUMBER OVER (PARTITION BY PCARD_NAME, ITEM_CLASS_TYPE) 의 PARTITION 에 여러 날짜 row 가 포함되어 **FI=1 의 경합이 달라짐** → 일자별 합이 단일 일자 실행 결과와 차이 발생.

원본 프로시저는 항상 single :V_DATE 로 실행 — 그래서 다른 일자 row 가 PARTITION 에 들어올 일 없음. 자유 분석에서 multi-date 추세를 보고 싶으면 다음 중 하나:
1. 일자별로 SQL 5 회 실행 후 외부 결합 (정확)
2. PARTITION BY 에 PROD_DATE 추가 (예: `ROW_NUMBER() OVER (PARTITION BY PCARD_NAME, ITEM_CLASS_TYPE, PROD_DATE ORDER BY ...)`) — 그러나 프로시저 룰과 다른 의미가 될 수 있음

[확정: 2026-05-19 진단 — 5 일치 OR 쿼리 결과가 5 회 단일 일자 결과와 일자당 -608 ~ -8,453 차이. 원본 프로시저 룰과 multi-date 분석의 의미 차이일 뿐 결함 아님.]

#### ★ O-I (SCR-004) 에 단순화 (1) 적용 시 II9% 예외 추가 검증 필수

P-O 와 달리 O-I 의 IPI/PHH 룰에는 `OR ITEM_CLASS LIKE 'II9%'` **예외 조건이 추가로** 있다:
```sql
-- 원본 (SCR-004 라인 209, 269)
AND ( OUT_T.OP_CD NOT IN ('IPI','PHH')
   OR EXISTS (cross-plant MOVE)
   OR OUT_T.ITEM_CLASS LIKE 'II9%' )
```

단순화 (1) 의 `AND OP_CD NOT IN ('IPI','PHH')` 를 그대로 적용하면 'II9%' 예외 케이스가 제외된다. 적용 전 다음 검증 SQL 로 영향 없음을 먼저 확인:

```sql
-- 결과 > 0 이면 단순화 (1) 적용 시 카드 손실 발생 — Summary 화면 cell 영향 여부 별도 판단
SELECT COUNT(*) AS II9_LOSS_CNT, SUM(PCARD_QTY) AS II9_LOSS_QTY
  FROM OCI.MSPD_PCARD_RESULT
 WHERE OUT_DATE = :V_DATE
   AND OP_CD IN ('IPI','PHH')
   AND ITEM_CLASS LIKE 'II9%'
   AND PROD_MOVE_TYPE = 'PROD'
   AND END_ROUTING_YN = 'Y'
   AND RESULT_TYPE = 'SCAN'
   AND PLANT_CD IN ('3110','3120','3210','3220');
```

[확정: 2026-03-02 ~ 03-06 5 일치 — II9_LOSS_CNT 매일 700~930 row, II9_LOSS_QTY 매일 7,625 ~ 9,955 켤레 손실 실재.
 단, ITEM_CLASS 'II9%' 는 모두 CHECK_GROUP_CD = 'IPF' 로 매핑되고 (OCI.MSBS_CHECKGROUP_WC, FORM_ID='MSPD52000S'), IPF 는 Summary 'TOT' aggregation 에서 제외 룰 (§ Summary 'TOT' 산식) 에 포함되어 있음. 따라서 손실된 II9% 카드는 화면 Summary 컬럼 결과에 **영향 없음** — 결과적으로 Summary 동일.
 다만 **자유 분석에서 IPF CHECK_GROUP 단독 조회 / PCARD 상세 추적 / 사이즈 분포** 시에는 II9% 분이 누락됨. 이런 분석에서는 단순화 (1) 대신 원본 EXISTS+II9% OR 룰 유지 필수.]

### 단순화 (2) W_ORG CTE → 인라인 PLANT_CD 리스트

`W_ORG` CTE 는 `COUNTRY='3000'` → `('3110','3120','3210','3220')` 4 개 PLANT 로 항상 동일 펼침.

원본:
```sql
W_ORG AS (
  SELECT A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE=B.ORG_TYPE AND A.SUB_ORG_CD=B.ORG_CD
   WHERE A.ORG_TYPE='COUNTRY' AND A.ORG_CD='3000' AND A.SUB_ORG_TYPE='GMES_PLANT'
)
```

→ 권장 대체 (Country=3000 인 경우):
```sql
-- W_ORG CTE 생략 + PCARD 조회 시 직접 인라인
AND PO_T.PLANT_CD IN ('3110','3120','3210','3220')
```

**효과**: CTE 1 개 + JOIN 2 개 절약. 다른 COUNTRY 사용 시 해당 PLANT 리스트로 교체. 미세 개선이지만 가독성도 향상.

### 단순화 (3) CH PLAN 함수 호출 → 인라인 서브쿼리

`FN_GET_CH_PLAN(:V_DATE, BS_WC.WC_CD)` 는 OCI 에 없음 → `ORA-00904`.
하지만 함수가 참조하는 `MSBS_SHIFT` 테이블은 OCI 에 **존재**.

→ 권장 대체 (`metrics/po_cross_check.yml#ch_plan_qty` 와 동일):
```sql
WC_LIST AS (
  SELECT /*+ materialize */
         BS_WC.WC_CD,
         NVL((SELECT DECODE(MAX(CST.DESCRIPTION),'0',NULL,MAX(CST.DESCRIPTION))
                FROM OCI.MSBS_SHIFT CST
               WHERE CST.PLAN_DATE        = :V_DATE
                 AND CST.SHIFT_TYPE       = '1'
                 AND CST.PROCESSSEGMENTID = 'FGA'
                 AND CST.ISUSABLE         = 'Usable'
                 AND 'FGA'||SUBSTR(CST.LINE_CD,-2) = BS_WC.WC_CD), 0) AS CH_PLAN,
         ...
)
```

**효과**: 함수 부재 에러 회피 + 실측 검증 결과 화면 CH PLAN 컬럼과 100% 일치.

### 적용 전후 비교 (예: 2026-03-02 Country 전체 P-O MAIN)

| 버전 | 실행 시간 | 결과 행 수 | 화면 일치 |
|---|---|---|---|
| 원본 procedure-grade (EXISTS + W_ORG CTE + FN_GET_CH_PLAN) | 240 초+ (타임아웃) | — | — |
| 단순화 (1)+(2)+(3) 모두 적용 | ~30 초 | 187 행 (CHECK_GROUP × WC) | ✓ 100% |

원본 룰 의미는 100% 보존하면서 OCI 환경 특성에 맞춘 변환. 다른 환경 (예: LMES 직접 접근, MSBS_SHIFT 가 다른 분포) 으로 가면 원본 룰로 복귀.

---

## 목차

| 함수 | 분기/분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_po_cross_main`](#fn_po_cross_main) | SCR-003 MAIN — 라인별 P/O/매칭률 | §3-A |
| [`fn_oi_cross_main`](#fn_oi_cross_main) | SCR-004 MAIN — 라인별 OK/Out Only/In Only/매칭률 | §3-B |
| [`fn_integrated_flow`](#fn_integrated_flow) | 통합 흐름 (P-O + O-I FULL OUTER JOIN) ★ | §3-C |
| [`fn_anomaly_pcard_out_only`](#fn_anomaly_pcard_out_only) | 특이사항 PCARD 단위 추출 | §3-D |
| [`fn_size_match`](#fn_size_match) | 사이즈별 정합성 (DETAIL_SIZE 분기 베이스) | §3-E |
| [`fn_pcard_scan_history`](#fn_pcard_scan_history) | SCR-003/004 SCAN_DATA — PCARD 스캔 이력 | §3-F |
| [`fn_po_size_cell_pcard`](#fn_po_size_cell_pcard) | SCR-003 DETAIL_SIZE_DETAIL — 사이즈 셀 PCARD 상세 | (신규) |
| [`fn_oi_size_cell_pcard`](#fn_oi_size_cell_pcard) | SCR-004 DETAIL_SIZE_DETAIL — 사이즈 셀 PCARD 상세 | (신규) |

---

## `fn_po_cross_main`

**용도**: 라인(WC_CD)별 PROD_QTY / OUT_QTY / PROD_ONLY_QTY / OUT_ONLY_QTY / 매칭률 + ITEM_CLASS_TYPE 별 PIVOT (P-O Cross 화면 메인 그리드 재현).

**사용 metric** (`metrics/po_cross_check.yml`): `prod_qty`, `out_qty`, `prod_only_qty`, `out_only_qty`, `po_match_rate`

**구조 — 6 CTE + PIVOT**:
1. `DT_GROUP` — MSBS_CHECKGROUP × MSBS_CHECKGROUP_WC 로 (ITEM_CLASS, CHECK_GROUP_CD, WC_CD) 매핑
2. `W_ORG` — COUNTRY → PLANT 인라인 펼침
3. `WC_LIST` — 라인 마스터 + `FN_GET_CH_PLAN` 으로 CH 계획 수량 (활동 0 라인도 표시)
4. `DT` — PRODUCTION leg + MOVE leg UNION ALL (각각 PROD_DATE / OUT_DATE 기준)
5. `SD` — DT 를 (CHECK_GROUP_CD, WC_CD) 별 SUM/COUNT 집계
6. `RET_DT` — WC_LIST LEFT JOIN SD + 'TOT' 가산 + WC_GROUP 레벨 row_type=2 추가 (PIVOT 4 row 유형)
7. PIVOT — CHECK_GROUP_CD 를 OS/PP/PH/PU/II/IP/IPJ/CF/FS/UP/SL 컬럼으로 펼침

**핵심 룰**:
- WC_LIST 는 COUNTRY 단위 (그날 활동 0 라인도 표시) → COUNTRY 변환 선행 필수
- DT 의 PRODUCTION leg 는 `PROD_DATE = :V_DATE` + `JOIN PROD_WC_CD = DT_GROUP.WC_CD`
- DT 의 MOVE leg 는 `OUT_DATE = :V_DATE` + `JOIN OUT_WC_CD = DT_GROUP.WC_CD` + IPI/PHH Cross-plant EXISTS
- `OP_CD <> 'UPC'` 양쪽 leg 공통
- `ROW_NUMBER()` + `:V_FIRST_ITEM` 으로 카드별 ITEM_CLASS 중복 처리
- 매칭률 = `100 - (O1_QTY / O_QTY) × 100` (출고 기준 분모)

```sql
WITH DT_GROUP AS (
  -- 화면에서 정의된 (ITEM_CLASS, WC_CD) 매핑 + CHECK_GROUP 분류
  SELECT /*+ materialize */ DISTINCT
         CHK_WC.ITEM_CLASS, CHK_GRP.CHECK_GROUP_CD, CHK_WC.WC_CD
    FROM MSBS_CHECKGROUP CHK_GRP
    JOIN MSBS_CHECKGROUP_WC CHK_WC
      ON CHK_GRP.COUNTRY_CD     = CHK_WC.COUNTRY_CD
     AND CHK_GRP.FORM_ID        = CHK_WC.FORM_ID
     AND CHK_GRP.CHECK_GROUP_CD = CHK_WC.CHECK_GROUP_CD
   WHERE CHK_GRP.COUNTRY_CD = :V_COUNTRY
     AND CHK_GRP.FORM_ID    = :V_FORM_ID
     AND CHK_GRP.USE_YN     = 'Y'
),
W_ORG AS (
  -- COUNTRY → 자식 PLANT 인라인 펼침 (DETAIL+ 에서는 FN_GET_CHILD_ORG_LIST 도 병용)
  SELECT /*+ materialize */ A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B
      ON A.SUB_ORG_TYPE = B.ORG_TYPE
     AND A.SUB_ORG_CD   = B.ORG_CD
   WHERE A.ORG_TYPE     = 'COUNTRY'
     AND A.ORG_CD       = :V_COUNTRY
     AND A.SUB_ORG_TYPE = 'GMES_PLANT'
),
WC_LIST AS (
  -- 라인 마스터 + 화면 LINE/WC_GROUP 표시명 + CH_PLAN
  SELECT /*+ materialize */
         BS_WC.PLANT_CD,
         BS_WC.WC_CD,
         FN_GET_CH_PLAN(:V_DATE, BS_WC.WC_CD)             AS CH_PLAN,
         NVL(V_GR.VIEW_GROUP_CD, BS_WC.WC_CD)             AS LINE_CD,
         NVL(V_NM.SUM_GROUP_MAME, BS_WC.WC_NAME)          AS LINE_NAME,
         NVL(V_GR.SUB_TOTAL_CD, BS_WC.WC_GROUP_CD)        AS WC_GROUP_CD,
         NVL(S_NM.SUM_GROUP_MAME, BS_WCGRP.WC_GROUP_NAME) AS WC_GROUP_NAME,
         NVL(S_NM.SORT_SEQ, '0') AS GROUP_SEQ,
         NVL(V_NM.SORT_SEQ, '0') AS WC_SEQ
    FROM      MSBS_WORK_CENTER BS_WC
    JOIN      MSBS_WC_GROUP BS_WCGRP ON BS_WC.PLANT_CD = BS_WCGRP.PLANT_CD AND BS_WC.WC_GROUP_CD = BS_WCGRP.WC_GROUP_CD
    JOIN      MSBS_SUM_GROUP_WC V_GR ON V_GR.COUNTRY_CD = :V_COUNTRY AND BS_WC.WC_CD = V_GR.WC_CD AND V_GR.FORM_ID = :V_FORM_ID
    JOIN      MSBS_SUM_GROUP_CD V_NM ON V_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND V_NM.SUM_GROUP_CD = V_GR.VIEW_GROUP_CD
                                    AND V_NM.FORM_ID = :V_FORM_ID AND V_NM.SUM_GROUP_TYPE = 'VIEW_GROUP' AND V_NM.USE_YN = 'Y'
    JOIN      MSBS_SUM_GROUP_CD S_NM ON S_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND S_NM.SUM_GROUP_CD = V_GR.SUB_TOTAL_CD
                                    AND S_NM.FORM_ID = :V_FORM_ID AND S_NM.SUM_GROUP_TYPE = 'SUB_TOTAL' AND S_NM.USE_YN = 'Y'
    JOIN      MSBS_PLANT BS_PT ON BS_WC.PLANT_CD = BS_PT.PLANT_CD
    JOIN      W_ORG ON BS_WC.PLANT_CD = W_ORG.ORG_CD
   WHERE BS_WC.USE_YN     = 'Y'
     AND BS_PT.COMPANY_CD IN (SELECT TO_CHAR(VALUE) FROM TABLE(SPLITTABLEVARCHAR2(:V_COMPANY, ',')))
),
DT AS (
  -- PRODUCTION leg: PROD_DATE 기준
  SELECT '1' AS SEQ, DT_GROUP.CHECK_GROUP_CD,
         DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD) AS WC_CD,
         PO_T.PCARD_NAME, PO_T.ITEM_CLASS, PO_T.ITEM_CLASS_TYPE,
         CASE WHEN PO_T.PROD_DATE = :V_DATE THEN PO_T.PCARD_QTY ELSE 0 END AS PROD_QTY,
         0 AS OUT_QTY,
         CASE WHEN PO_T.PROD_DATE = :V_DATE AND PO_T.OUT_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END AS PROD_ONLY_QTY,
         0 AS OUT_ONLY_QTY,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.PROD_WC_CD = DT_GROUP.WC_CD
    JOIN      W_ORG    ON PO_T.PLANT_CD   = W_ORG.ORG_CD
   WHERE PO_T.PROD_DATE      = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.OP_CD         <> 'UPC'
     AND PO_T.RESULT_TYPE    = 'SCAN'
  UNION ALL
  -- MOVE/OUT leg: OUT_DATE 기준 + IPI/PHH Cross-plant EXISTS 룰
  SELECT '1', DT_GROUP.CHECK_GROUP_CD,
         DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD),
         PO_T.PCARD_NAME, PO_T.ITEM_CLASS, PO_T.ITEM_CLASS_TYPE,
         0, PO_T.PCARD_QTY, 0,
         CASE WHEN PO_T.PROD_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.OUT_WC_CD = DT_GROUP.WC_CD
    JOIN      W_ORG    ON PO_T.PLANT_CD   = W_ORG.ORG_CD
   WHERE PO_T.OUT_DATE       = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.OP_CD         <> 'UPC'
     AND PO_T.RESULT_TYPE    = 'SCAN'
     AND ( PO_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = PO_T.PCARD_NAME
                      AND RES.ITEM_CD    = PO_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE'
                      AND RES.PLANT_CD  <> PO_T.PLANT_CD) )
),
SD AS (
  SELECT DT.CHECK_GROUP_CD, DT.WC_CD,
         SUM(CASE WHEN PROD_QTY      > 0 THEN PROD_QTY      ELSE 0 END) AS P_QTY,
         SUM(CASE WHEN PROD_QTY      > 0 THEN 1             ELSE 0 END) AS P_CNT,
         SUM(CASE WHEN OUT_QTY       > 0 THEN OUT_QTY       ELSE 0 END) AS O_QTY,
         SUM(CASE WHEN OUT_QTY       > 0 THEN 1             ELSE 0 END) AS O_CNT,
         SUM(CASE WHEN PROD_ONLY_QTY > 0 THEN PROD_ONLY_QTY ELSE 0 END) AS P1_QTY,
         SUM(CASE WHEN PROD_ONLY_QTY > 0 THEN 1             ELSE 0 END) AS P1_CNT,
         SUM(CASE WHEN OUT_ONLY_QTY  > 0 THEN OUT_ONLY_QTY  ELSE 0 END) AS O1_QTY,
         SUM(CASE WHEN OUT_ONLY_QTY  > 0 THEN 1             ELSE 0 END) AS O1_CNT
    FROM DT
   WHERE ( (:V_FIRST_ITEM = 'Y' AND FIRST_ITEM = 1)
        OR (:V_FIRST_ITEM = 'N' AND FIRST_ITEM > 0) )
   GROUP BY DT.CHECK_GROUP_CD, DT.WC_CD
)
SELECT W.WC_GROUP_CD, W.WC_GROUP_NAME, W.LINE_CD, W.LINE_NAME, W.CH_PLAN,
       SD.CHECK_GROUP_CD,
       SD.P_QTY, SD.P_CNT, SD.O_QTY, SD.O_CNT, SD.P1_QTY, SD.P1_CNT, SD.O1_QTY, SD.O1_CNT,
       CAST(CASE WHEN SD.O_QTY <> 0
                 THEN (100.00 - (SD.O1_QTY / SD.O_QTY) * 100)
                 ELSE NULL END AS NUMBER(9,5)) AS PO_MATCH_RATE
  FROM      WC_LIST W
  LEFT JOIN SD ON W.WC_CD = SD.WC_CD
 ORDER BY W.GROUP_SEQ, W.WC_GROUP_CD, W.WC_SEQ, W.LINE_CD;

-- 화면 PIVOT 컬럼 (FX_OS_*, FX_PP_*, ..., TOTAL_*) 이 필요하면 위 결과를 PIVOT 절로 감싼다.
-- PIVOT FOR CHECK_GROUP_CD IN ('TOT' AS TOTAL, 'OS' AS FX_OS, 'PP' AS FX_PP, 'PH' AS FX_PH,
--                              'PU' AS FX_PU, 'II' AS FX_II, 'IP' AS FX_IP, 'IPJ' AS FX_IPJ,
--                              'CF' AS FX_CF, 'FS' AS FX_FS, 'UP' AS FX_UP, 'SL' AS FX_SL)
```

[확정: P_MSPD51000S_Q_V24 MAIN 분기 (L87-476) 본문 대조 검증]

---

## `fn_oi_cross_main`

**용도**: 라인별 OUT_IN_OK / OUT_ONLY / IN_ONLY / IN / 매칭률 + ITEM_CLASS_TYPE 별 PIVOT (O-I Cross 화면 메인 그리드 재현).

**사용 metric** (`metrics/oi_cross_check.yml`): `out_in_ok_qty`, `out_only_qty` (P-O 와 의미 다름!), `in_only_qty`, `in_qty`, `oi_match_rate`

**구조 — 6 CTE + 4 UNION ALL leg**:
1. `W_ORG` (= P-O 와 동일 인라인 펼침, **FN_GET_CHILD_ORG_LIST 호출 없음**)
2. `LDT` — FG 타입 WC 라인 마스터 (BS_WC.WC_TYPE='FG' 필터)
3. `LGRP` — 라인 그룹 코드 마스터
4. `LG_LIST` — 라인 마스터 + `FN_GET_CH_PLAN` (P-O 의 WC_LIST 와 같은 역할)
5. `DT_GROUP` — (ITEM_CLASS, CHECK_GROUP_CD, WC_CD) 매핑 (= P-O 와 같은 식)
6. `DT` — 4 UNION ALL leg:
   - **INOUT_OK** (CHECK_TIME_YN='N'): 출고와 입고 매칭 완료 (EXISTS 입고)
   - **ONLY_OUT** (CHECK_TIME_YN='N'): 출고만, 입고 NOT EXISTS
   - **ONLY_IN** (CHECK_TIME_YN='N'): 입고 + 출고 매칭이지만 `OUT_DATE < '20010101'` (출고 미발생)
   - **INCOMING** (CHECK_TIME_YN='Y'): 입고는 됐고 출고도 있는 케이스 → IN_QTY 카운트

**핵심 룰**:
- 출고 leg 는 `PROD_MOVE_TYPE='PROD'` + `OUT_DATE=:V_DATE`, 입고 leg 는 `PROD_MOVE_TYPE='MOVE'` + `IN_DATE=:V_DATE` (★ P-O 와 가장 큰 차이)
- IPI/PHH Cross-plant EXISTS 룰 + **`ITEM_CLASS LIKE 'II9%'` 예외** (P-O 에는 없음)
- ZCP/ZSH/ZST 의 BOMLEVEL=0 제외
- JJ Insole 표시 제외 명시: `(FA_PLANT_CD='3210') OR (FA_PLANT_CD='3110' AND ITEM_CLASS_TYPE <> 'SL')` ★ P-O 에는 명시 안 됨
- 특정 PROD_GROUP_NO ('S191105001') 강제 제외 (ONLY_OUT leg) — 과거 시스템 마이그레이션 흔적
- 매칭률 = `OI_PR / (OI_PR + O_PR + I_PR) × 100` (P-O 와 공식 다름)

```sql
WITH W_ORG AS (
  -- COUNTRY → PLANT 인라인 (★ SCR-004 는 FN_GET_CHILD_ORG_LIST 호출 없이 CTE 만 사용)
  SELECT /*+ materialize */ A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE = B.ORG_TYPE AND A.SUB_ORG_CD = B.ORG_CD
   WHERE A.ORG_TYPE = 'COUNTRY' AND A.ORG_CD = :V_COUNTRY
     AND A.SUB_ORG_TYPE = 'GMES_PLANT'
),
LG_LIST AS (
  -- 라인 마스터 + CH_PLAN. P-O 의 WC_LIST 와 같은 역할 (단 BS_WCGRP 조인 구조만 다름)
  SELECT /*+ materialize */
         BS_WC.WC_CD,
         NVL(V_GR.VIEW_GROUP_CD, BS_WC.WC_CD)             AS LINE_CD,
         FN_GET_CH_PLAN(:V_DATE, BS_WC.WC_CD)             AS CH_PLAN,
         NVL(V_NM.SUM_GROUP_MAME, BS_WC.WC_NAME)          AS LINE_NAME,
         NVL(V_GR.SUB_TOTAL_CD, BS_WC.WC_GROUP_CD)        AS WC_GROUP_CD,
         NVL(S_NM.SUM_GROUP_MAME, BS_WCGRP.WC_GROUP_NAME) AS WC_GROUP_NAME,
         NVL(S_NM.SORT_SEQ, '0') AS GROUP_SEQ,
         NVL(V_NM.SORT_SEQ, '0') AS WC_SEQ
    FROM      MSBS_WORK_CENTER BS_WC
    JOIN      MSBS_WC_GROUP BS_WCGRP ON BS_WC.PLANT_CD = BS_WCGRP.PLANT_CD AND BS_WC.WC_GROUP_CD = BS_WCGRP.WC_GROUP_CD
    JOIN      MSBS_SUM_GROUP_WC V_GR ON V_GR.COUNTRY_CD = :V_COUNTRY AND BS_WC.WC_CD = V_GR.WC_CD AND V_GR.FORM_ID = :V_FORM_ID
    JOIN      MSBS_SUM_GROUP_CD V_NM ON V_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND V_NM.SUM_GROUP_CD = V_GR.VIEW_GROUP_CD
                                    AND V_NM.FORM_ID = :V_FORM_ID AND V_NM.SUM_GROUP_TYPE = 'VIEW_GROUP' AND V_NM.USE_YN = 'Y'
    JOIN      MSBS_SUM_GROUP_CD S_NM ON S_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND S_NM.SUM_GROUP_CD = V_GR.SUB_TOTAL_CD
                                    AND S_NM.FORM_ID = :V_FORM_ID AND S_NM.SUM_GROUP_TYPE = 'SUB_TOTAL' AND S_NM.USE_YN = 'Y'
    JOIN      MSBS_PLANT BS_PT ON BS_WC.PLANT_CD = BS_PT.PLANT_CD
    JOIN      W_ORG ON BS_WC.PLANT_CD = W_ORG.ORG_CD
   WHERE BS_WC.USE_YN = 'Y'
     AND BS_PT.COMPANY_CD IN (SELECT TO_CHAR(VALUE) FROM TABLE(SPLITTABLEVARCHAR2(:V_COMPANY, ',')))
),
DT_GROUP AS (
  SELECT /*+ materialize */ DISTINCT
         CHK_WC.ITEM_CLASS, CHK_GRP.CHECK_GROUP_CD, CHK_WC.WC_CD
    FROM MSBS_CHECKGROUP CHK_GRP
    JOIN MSBS_CHECKGROUP_WC CHK_WC
      ON CHK_GRP.COUNTRY_CD = CHK_WC.COUNTRY_CD AND CHK_GRP.FORM_ID = CHK_WC.FORM_ID
     AND CHK_GRP.CHECK_GROUP_CD = CHK_WC.CHECK_GROUP_CD
   WHERE CHK_GRP.COUNTRY_CD = :V_COUNTRY AND CHK_GRP.FORM_ID = :V_FORM_ID AND CHK_GRP.USE_YN = 'Y'
),
DT AS (
  -- INOUT_OK: 출고와 입고 매칭 완료
  SELECT '1' AS SEQ, ICT.CHECK_GROUP_CD, IO_T.ITEM_CLASS,
         IO_T.FA_WC_CD, IO_T.PCARD_NAME, IO_T.ITEM_CLASS_TYPE,
         IO_T.PCARD_QTY AS OUT_PCARD_QTY, IO_T.PCARD_QTY AS IN_PCARD_QTY, 0 AS IN_QTY,
         ROW_NUMBER() OVER (PARTITION BY IO_T.PCARD_NAME, IO_T.ITEM_CLASS_TYPE
                            ORDER BY IO_T.PCARD_NAME, IO_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT IO_T
    JOIN      DT_GROUP ICT ON IO_T.ITEM_CLASS = ICT.ITEM_CLASS AND IO_T.OUT_WC_CD = ICT.WC_CD
    JOIN      W_ORG ON IO_T.PLANT_CD = W_ORG.ORG_CD
   WHERE IO_T.OUT_DATE       = :V_DATE
     AND IO_T.PROD_MOVE_TYPE = 'PROD'
     AND IO_T.END_ROUTING_YN = 'Y'
     AND IO_T.RESULT_TYPE    = 'SCAN'
     AND ( IO_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = IO_T.PCARD_NAME AND RES.ITEM_CD = IO_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> IO_T.PLANT_CD)
        OR IO_T.ITEM_CLASS LIKE 'II9%' )
     AND ( IO_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (IO_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND IO_T.BOMLEVEL <> 0) )
     AND ( (1 = DECODE(IO_T.FA_PLANT_CD,'3210',1,0))
        OR (1 = DECODE(IO_T.FA_PLANT_CD,'3110',1,0) AND IO_T.ITEM_CLASS_TYPE <> 'SL') )  -- JJ Insole 제외
     AND EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT IN_T
                  WHERE IN_T.PCARD_NAME = IO_T.PCARD_NAME AND IN_T.ITEM_CD = IO_T.ITEM_CD
                    AND IN_T.PROD_MOVE_TYPE = 'MOVE' AND IN_T.END_ROUTING_YN = 'Y'
                    AND IN_T.IN_DATE > '20010101' AND IN_T.RESULT_TYPE = 'SCAN')
  UNION ALL
  -- ONLY_OUT: 출고만, 입고 NOT EXISTS
  SELECT '1', ICT.CHECK_GROUP_CD, OUT_T.ITEM_CLASS,
         OUT_T.FA_WC_CD, OUT_T.PCARD_NAME, OUT_T.ITEM_CLASS_TYPE,
         OUT_T.PCARD_QTY, 0, 0,
         ROW_NUMBER() OVER (PARTITION BY OUT_T.PCARD_NAME, OUT_T.ITEM_CLASS_TYPE
                            ORDER BY OUT_T.PCARD_NAME, OUT_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT OUT_T
    JOIN      DT_GROUP ICT ON OUT_T.ITEM_CLASS = ICT.ITEM_CLASS AND OUT_T.OUT_WC_CD = ICT.WC_CD
    JOIN      W_ORG ON OUT_T.PLANT_CD = W_ORG.ORG_CD
   WHERE OUT_T.OUT_DATE       = :V_DATE
     AND OUT_T.PROD_MOVE_TYPE = 'PROD'
     AND OUT_T.END_ROUTING_YN = 'Y'
     AND OUT_T.RESULT_TYPE    = 'SCAN'
     AND OUT_T.PROD_GROUP_NO <> 'S191105001'   -- 과거 마이그레이션 흔적
     AND ( OUT_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = OUT_T.PCARD_NAME AND RES.ITEM_CD = OUT_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> OUT_T.PLANT_CD)
        OR OUT_T.ITEM_CLASS LIKE 'II9%' )
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
     AND ( (1 = DECODE(OUT_T.FA_PLANT_CD,'3210',1,0))
        OR (1 = DECODE(OUT_T.FA_PLANT_CD,'3110',1,0) AND OUT_T.ITEM_CLASS_TYPE <> 'SL') )
     AND NOT EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT IN_T
                      WHERE IN_T.PCARD_NAME = OUT_T.PCARD_NAME AND IN_T.ITEM_CD = OUT_T.ITEM_CD
                        AND IN_T.PROD_MOVE_TYPE = 'MOVE' AND IN_T.END_ROUTING_YN = 'Y'
                        AND IN_T.IN_DATE > '20010101' AND IN_T.RESULT_TYPE = 'SCAN')
  UNION ALL
  -- ONLY_IN: 입고는 됐지만 매칭된 출고가 실제로는 미발생 (OUT_DATE < '20010101')
  SELECT '1', ICT.CHECK_GROUP_CD, IN_T.ITEM_CLASS,
         IN_T.FA_WC_CD, IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE,
         0, IN_T.PCARD_QTY, 0,
         ROW_NUMBER() OVER (PARTITION BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE
                            ORDER BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT IN_T
    JOIN      MSPD_PCARD_RESULT OUT_T
              ON OUT_T.PCARD_NAME = IN_T.PCARD_NAME AND OUT_T.ITEM_CD = IN_T.ITEM_CD
             AND OUT_T.PROD_MOVE_TYPE = 'PROD' AND OUT_T.END_ROUTING_YN = 'Y'
             AND OUT_T.OUT_DATE < '20010101' AND OUT_T.RESULT_TYPE = 'SCAN'
    JOIN      DT_GROUP ICT ON OUT_T.ITEM_CLASS = ICT.ITEM_CLASS AND OUT_T.PLAN_PROD_WC_CD = ICT.WC_CD
    JOIN      W_ORG ON IN_T.PLANT_CD = W_ORG.ORG_CD
   WHERE IN_T.IN_DATE        = :V_DATE
     AND IN_T.PROD_MOVE_TYPE  = 'MOVE'
     AND IN_T.END_ROUTING_YN  = 'Y'
     AND IN_T.RESULT_TYPE     = 'SCAN'
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
     AND ( (1 = DECODE(IN_T.FA_PLANT_CD,'3210',1,0))
        OR (1 = DECODE(IN_T.FA_PLANT_CD,'3110',1,0) AND IN_T.ITEM_CLASS_TYPE <> 'SL') )
  UNION ALL
  -- INCOMING: 입고 발생 + 매칭 출고 있음 → IN_QTY 카운트
  SELECT '1', ICT.CHECK_GROUP_CD, IN_T.ITEM_CLASS,
         IN_T.FA_WC_CD, IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE,
         0, 0, IN_T.PCARD_QTY,
         ROW_NUMBER() OVER (PARTITION BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE
                            ORDER BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT IN_T
    JOIN      MSPD_PCARD_RESULT OUT_T
              ON OUT_T.PCARD_NAME = IN_T.PCARD_NAME AND OUT_T.ITEM_CD = IN_T.ITEM_CD
             AND OUT_T.PROD_MOVE_TYPE = 'PROD' AND OUT_T.END_ROUTING_YN = 'Y'
             AND OUT_T.RESULT_TYPE = 'SCAN'
    JOIN      DT_GROUP ICT ON OUT_T.ITEM_CLASS = ICT.ITEM_CLASS AND OUT_T.PLAN_PROD_WC_CD = ICT.WC_CD
    JOIN      W_ORG ON IN_T.PLANT_CD = W_ORG.ORG_CD
   WHERE IN_T.IN_DATE        = :V_DATE
     AND IN_T.PROD_MOVE_TYPE  = 'MOVE'
     AND IN_T.END_ROUTING_YN  = 'Y'
     AND IN_T.RESULT_TYPE     = 'SCAN'
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
     AND ( (1 = DECODE(IN_T.FA_PLANT_CD,'3210',1,0))
        OR (1 = DECODE(IN_T.FA_PLANT_CD,'3110',1,0) AND IN_T.ITEM_CLASS_TYPE <> 'SL') )
),
SD AS (
  SELECT DT.CHECK_GROUP_CD, DT.FA_WC_CD,
         SUM(CASE WHEN OUT_PCARD_QTY > 0 AND OUT_PCARD_QTY = IN_PCARD_QTY AND IN_QTY = 0
                  THEN OUT_PCARD_QTY ELSE 0 END) AS OI_PR,    -- OUT_IN_OK
         SUM(CASE WHEN OUT_PCARD_QTY > 0 AND IN_PCARD_QTY = 0 AND IN_QTY = 0
                  THEN OUT_PCARD_QTY ELSE 0 END) AS O_PR,     -- ONLY_OUT
         SUM(CASE WHEN OUT_PCARD_QTY = 0 AND IN_PCARD_QTY > 0 AND IN_QTY = 0
                  THEN IN_PCARD_QTY  ELSE 0 END) AS I_PR,     -- ONLY_IN
         SUM(CASE WHEN IN_QTY > 0 THEN IN_QTY ELSE 0 END)     AS IN_PR  -- INCOMING (입고 발생 + 매칭)
    FROM DT
   WHERE ( (:V_FIRST_ITEM = 'Y' AND FIRST_ITEM = 1)
        OR (:V_FIRST_ITEM = 'N' AND FIRST_ITEM > 0) )
   GROUP BY DT.CHECK_GROUP_CD, DT.FA_WC_CD
)
SELECT LG.WC_GROUP_CD, LG.WC_GROUP_NAME, LG.LINE_CD, LG.LINE_NAME, LG.CH_PLAN,
       SD.CHECK_GROUP_CD,
       SD.OI_PR AS OUT_IN_OK_QTY,
       SD.O_PR  AS OUT_ONLY_QTY,
       SD.I_PR  AS IN_ONLY_QTY,
       SD.IN_PR AS IN_QTY,
       CAST(CASE WHEN (SD.OI_PR + SD.O_PR + SD.I_PR) <> 0
                 THEN SD.OI_PR / (SD.OI_PR + SD.O_PR + SD.I_PR) * 100
                 ELSE 0 END AS NUMBER(9,5)) AS OI_MATCH_RATE
  FROM      LG_LIST LG
  LEFT JOIN SD ON LG.WC_CD = SD.FA_WC_CD
 ORDER BY LG.GROUP_SEQ, LG.WC_GROUP_CD, LG.WC_SEQ, LG.LINE_CD;

-- 화면 PIVOT 컬럼 (FX_*_RT, TOTAL_RT 등) 은 P-O 와 동일한 방식으로 위 결과를 PIVOT 절로 감쌈.
```

### ★ Summary ('TOT') aggregation — II/PP/IPF 제외 룰

위 SELECT 는 CHECK_GROUP × WC 단위 결과. 화면 Summary 컬럼 (rightmost 'Summary' 영역) 은 별도의 'TOT' aggregation row 로 만들며 **II / PP / IPF CHECK_GROUP 을 제외**한다.

[확정: P_MSPD52000S_Q_V39 라인 456 + 504 — `LEFT OUTER JOIN SD ON LG_LIST.WC_CD = SD.FA_WC_CD AND SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF')`]
[확정: 2026-03-02 ~ 03-06 5 일치 캡쳐 검증 — L 03 Summary OK 7,878 / Bottom Total Summary OK 199,677 100% 일치]

★ P-O (P_MSPD51000S_Q_V24) 에는 이 제외 룰이 없음. 두 화면 비대칭.

**산출 SQL (라인별 Summary)**:
```sql
SELECT LG.LINE_CD,
       SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.OI_PR ELSE 0 END) AS SUM_OUT_IN_OK,
       SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.O_PR  ELSE 0 END) AS SUM_OUT_ONLY,
       SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.I_PR  ELSE 0 END) AS SUM_IN_ONLY,
       SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.IN_PR ELSE 0 END) AS SUM_IN,
       CAST(CASE WHEN SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.OI_PR + SD.O_PR + SD.I_PR ELSE 0 END) <> 0
                 THEN SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.OI_PR ELSE 0 END)
                    / SUM(CASE WHEN SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN SD.OI_PR + SD.O_PR + SD.I_PR ELSE 0 END) * 100
                 ELSE 0 END AS NUMBER(9,5)) AS SUM_MATCH_RATE
  FROM      LG_LIST LG
  LEFT JOIN SD ON LG.WC_CD = SD.FA_WC_CD
 GROUP BY LG.LINE_CD;
```

**Bottom Total 의 경우 LINE_CD GROUP BY 빼고 전체 합**.

[확정: P_MSPD52000S_Q_V39 MAIN 분기 (L88-698) 본문 대조 검증]

---

## `fn_integrated_flow`

**용도**: 같은 라인+일자에서 생산→출고→입고 전체 metric (★ 핵심 분석).

**전략**: `fn_po_cross_main` 과 `fn_oi_cross_main` 결과를 라인 단위로 FULL OUTER JOIN.

**주의**: `PO_OUT_ONLY_QTY` 와 `OI_OUT_ONLY` 는 이름 비슷하지만 의미 다름:
- `PO_OUT_ONLY_QTY`: 생산 없는 출고 (P-O 의 O1)
- `OI_OUT_ONLY`: 입고 없는 출고 (O-I 의 O_PR)

답변 시 컬럼명을 명확히 구분 (예: "출고만 있고 생산 없음" vs "출고만 있고 입고 없음").

```sql
WITH PO_DT AS (
  /* fn_po_cross_main 의 본문 — WC_LIST + DT + SD 까지의 결과 */
  ...
),
OI_DT AS (
  /* fn_oi_cross_main 의 본문 — LG_LIST + DT (4 leg) + SD 까지의 결과 */
  ...
)
SELECT 
  COALESCE(PO.LINE_CD, OI.LINE_CD)        AS LINE_CD,
  -- P-O metric (생산 vs 출고)
  NVL(PO.P_QTY,  0)                       AS PROD_QTY,
  NVL(PO.O_QTY,  0)                       AS OUT_QTY,
  NVL(PO.P1_QTY, 0)                       AS PROD_ONLY_QTY,
  NVL(PO.O1_QTY, 0)                       AS PO_OUT_ONLY_QTY,  -- P-O 의 Out Only (생산 없는 출고)
  NVL(PO.PO_MATCH_RATE, 0)                AS PO_MATCH_RATE,
  -- O-I metric (출고 vs 입고)
  NVL(OI.OUT_IN_OK_QTY, 0)                AS OUT_IN_OK_QTY,
  NVL(OI.OUT_ONLY_QTY,  0)                AS OI_OUT_ONLY_QTY,  -- O-I 의 Out Only (입고 없는 출고) — 의미 다름!
  NVL(OI.IN_ONLY_QTY,   0)                AS IN_ONLY_QTY,
  NVL(OI.IN_QTY,        0)                AS IN_QTY,
  NVL(OI.OI_MATCH_RATE, 0)                AS OI_MATCH_RATE
FROM PO_DT PO
FULL OUTER JOIN OI_DT OI ON PO.LINE_CD = OI.LINE_CD
ORDER BY LINE_CD;
```

[확정: 두 프로시저 MAIN 결과 결합 — 프로시저 본체에 없는 자유 분석용 합성 fn]

---

## `fn_anomaly_pcard_out_only`

**용도**: 라인 클릭 시 그 라인 안의 특이사항 PCARD 들 — 매칭 안 된 카드 (Out Only / Prod Only / Out / Prod) 의 상세. 사용자 표현 "라인 03 의 매칭 안 된 카드", "라인 03 의 Out Only PCARD 어느 거?".

사이즈 좁힘이 명확한 경우엔 `fn_po_size_cell_pcard` / `fn_oi_size_cell_pcard` 가 더 적합. 본 fn 은 라인 단위에서 사이즈 무관하게 PCARD 전체 뽑을 때 사용.

**입력**: `:V_DATE`, `:V_COUNTRY`, `:V_FORM_ID`, `:V_LINE_CD`, `:V_CHECK_GROUP_CD`, `:V_IO_TYPE` ('P'/'P1'/'O'/'O1'), `:V_FIRST_ITEM`

**구조**: P-O DETAIL 분기 (P_MSPD51000S_Q_V24 L477-765) 1:1. `fn_po_size_cell_pcard` 와 동일한 DT CTE 이지만 STYLE/SIZE/ITEM_CLASS 필터를 적용하지 않음 — 즉 라인 전체 PCARD 출력.

```sql
WITH DT_GROUP AS (
  SELECT DISTINCT
         T_WC.ITEM_CLASS, T_GR.CHECK_GROUP_CD, T_WC.WC_CD
    FROM MSBS_CHECKGROUP_WC T_WC
    JOIN MSBS_CHECKGROUP T_GR
      ON T_GR.COUNTRY_CD = T_WC.COUNTRY_CD AND T_GR.FORM_ID = T_WC.FORM_ID
     AND T_GR.CHECK_GROUP_CD = T_WC.CHECK_GROUP_CD
   WHERE T_GR.COUNTRY_CD = :V_COUNTRY AND T_GR.FORM_ID = :V_FORM_ID AND T_GR.USE_YN = 'Y'
),
W_ORG AS (
  SELECT A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE = B.ORG_TYPE AND A.SUB_ORG_CD = B.ORG_CD
   WHERE A.ORG_TYPE = 'COUNTRY' AND A.ORG_CD = :V_COUNTRY AND A.SUB_ORG_TYPE = 'GMES_PLANT'
),
WC_LIST AS (
  -- 단일 라인 좁힘 (VIEW_GROUP_CD = :V_LINE_CD)
  SELECT BS_WC.WC_CD, NVL(V_GR.VIEW_GROUP_CD, BS_WC.WC_CD) AS LINE_CD,
         NVL(V_NM.SUM_GROUP_MAME, BS_WC.WC_NAME) AS LINE_NAME,
         NVL(V_NM.SORT_SEQ, '0') AS WC_SEQ
    FROM      MSBS_WORK_CENTER BS_WC
    JOIN      MSBS_WC_GROUP BS_WCGRP ON BS_WC.PLANT_CD = BS_WCGRP.PLANT_CD AND BS_WC.WC_GROUP_CD = BS_WCGRP.WC_GROUP_CD
    JOIN      MSBS_SUM_GROUP_WC V_GR ON V_GR.COUNTRY_CD = :V_COUNTRY AND BS_WC.WC_CD = V_GR.WC_CD AND V_GR.FORM_ID = :V_FORM_ID
    JOIN      MSBS_SUM_GROUP_CD V_NM ON V_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND V_NM.SUM_GROUP_CD = V_GR.VIEW_GROUP_CD
                                    AND V_NM.FORM_ID = :V_FORM_ID AND V_NM.SUM_GROUP_TYPE = 'VIEW_GROUP' AND V_NM.USE_YN = 'Y'
    JOIN      W_ORG ON BS_WC.PLANT_CD = W_ORG.ORG_CD
   WHERE BS_WC.USE_YN = 'Y'
     AND V_GR.VIEW_GROUP_CD = :V_LINE_CD
),
DT AS (
  -- PRODUCTION leg
  SELECT '1' AS SEQ, DT_GROUP.CHECK_GROUP_CD,
         PO_T.ITEM_CLASS_TYPE, PO_T.FA_DATE, PO_T.FA_WC_CD,
         WC_LIST.LINE_CD, WC_LIST.LINE_NAME,
         PO_T.STYLE_CD, PO_T.SIZE_CD, PO_T.PROD_ORDER_TYPE,
         PO_T.PCARD_NAME, PO_T.BARCODE_KEY,
         PO_T.PROD_DT, PO_T.OUT_DT, PO_T.PROD_DATE, PO_T.OUT_DATE,
         PO_T.ITEM_CLASS, PO_T.OP_CD, PO_T.PROD_WC_CD, PO_T.OUT_WC_CD,
         CASE WHEN PO_T.PROD_DATE = :V_DATE THEN PO_T.PCARD_QTY ELSE 0 END                                    AS P_QTY,
         0                                                                                                    AS O_QTY,
         CASE WHEN PO_T.PROD_DATE = :V_DATE AND PO_T.OUT_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END    AS P1_QTY,
         0                                                                                                    AS O1_QTY,
         PO_T.DAY_SEQ, PO_T.PLAN_PROD_WC_CD, PO_T.ITEM_CD,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.PROD_WC_CD = DT_GROUP.WC_CD
    JOIN      WC_LIST  ON WC_LIST.WC_CD = DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD)
   WHERE PO_T.PROD_DATE      = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.PLANT_CD IN (SELECT ORG.ORG_CD FROM TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', :V_COUNTRY, 'GMES_PLANT')) ORG)
     AND PO_T.OP_CD          <> 'UPC'
     AND DT_GROUP.CHECK_GROUP_CD = :V_CHECK_GROUP_CD
     AND PO_T.RESULT_TYPE    = 'SCAN'
  UNION ALL
  -- MOVE/OUT leg + IPI/PHH Cross-plant EXISTS
  SELECT '1', DT_GROUP.CHECK_GROUP_CD,
         PO_T.ITEM_CLASS_TYPE, PO_T.FA_DATE, PO_T.FA_WC_CD,
         WC_LIST.LINE_CD, WC_LIST.LINE_NAME,
         PO_T.STYLE_CD, PO_T.SIZE_CD, PO_T.PROD_ORDER_TYPE,
         PO_T.PCARD_NAME, PO_T.BARCODE_KEY,
         PO_T.PROD_DT, PO_T.OUT_DT, PO_T.PROD_DATE, PO_T.OUT_DATE,
         PO_T.ITEM_CLASS, PO_T.OP_CD, PO_T.PROD_WC_CD, PO_T.OUT_WC_CD,
         0, PO_T.PCARD_QTY, 0,
         CASE WHEN PO_T.PROD_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END,
         PO_T.DAY_SEQ, PO_T.PLAN_PROD_WC_CD, PO_T.ITEM_CD,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.OUT_WC_CD = DT_GROUP.WC_CD
    JOIN      WC_LIST  ON WC_LIST.WC_CD = DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD)
   WHERE PO_T.OUT_DATE       = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.PLANT_CD IN (SELECT ORG.ORG_CD FROM TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', :V_COUNTRY, 'GMES_PLANT')) ORG)
     AND PO_T.OP_CD          <> 'UPC'
     AND DT_GROUP.CHECK_GROUP_CD = :V_CHECK_GROUP_CD
     AND PO_T.RESULT_TYPE    = 'SCAN'
     AND ( PO_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = PO_T.PCARD_NAME AND RES.ITEM_CD = PO_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> PO_T.PLANT_CD) )
)
SELECT
  DT.LINE_CD, DT.LINE_NAME, DT.FA_DATE, DT.FA_WC_CD,
  DT.CHECK_GROUP_CD, DT.ITEM_CLASS_TYPE, DT.ITEM_CLASS,
  ICLS.ITEM_CLASS_NAME,
  DT.SIZE_CD, DT.STYLE_CD,
  FN_GET_STYLE_MODEL('', DT.STYLE_CD)               AS STYLE_NAME,
  DT.PROD_ORDER_TYPE,
  DT.BARCODE_KEY, DT.PCARD_NAME,
  TO_CHAR(DT.PROD_DT, 'YYYYMMDDHH24MISS')           AS PROD_SCAN_DT,
  TO_CHAR(DT.OUT_DT,  'YYYYMMDDHH24MISS')           AS OUT_SCAN_DT,
  DT.PROD_DATE, DT.OUT_DATE, DT.DAY_SEQ AS HH,
  DT.OP_CD AS PROD_OP_CD, DT.OP_CD AS OUT_OP_CD,
  NVL(DT.PROD_WC_CD, DT.PLAN_PROD_WC_CD) AS PROD_WC_CD,
  NVL(DT.OUT_WC_CD,  DT.PLAN_PROD_WC_CD) AS OUT_WC_CD,
  DT.PLAN_PROD_WC_CD, DT.ITEM_CD,
  -- IO_TYPE 별 PCARD_QTY (Out Only = O1, Prod Only = P1, 출고/생산 = O/P)
  CASE WHEN :V_IO_TYPE = 'P'  THEN DT.P_QTY
       WHEN :V_IO_TYPE = 'P1' THEN DT.P1_QTY
       WHEN :V_IO_TYPE = 'O'  THEN DT.O_QTY
       WHEN :V_IO_TYPE = 'O1' THEN DT.O1_QTY
       ELSE 0 END                                  AS PCARD_QTY,
  -- 라벨링
  CASE WHEN :V_IO_TYPE = 'O1' THEN '출고됐는데 생산 없음'
       WHEN :V_IO_TYPE = 'P1' THEN '생산됐는데 출고 없음'
       WHEN :V_IO_TYPE = 'O'  THEN '출고'
       WHEN :V_IO_TYPE = 'P'  THEN '생산'
       END                                          AS IO_LABEL
FROM      DT
JOIN      MSBS_ITEM_CLASS ICLS ON DT.ITEM_CLASS = ICLS.ITEM_CLASS
WHERE ( (:V_IO_TYPE = 'O1' AND DT.O1_QTY > 0)
     OR (:V_IO_TYPE = 'P1' AND DT.P1_QTY > 0)
     OR (:V_IO_TYPE = 'P'  AND DT.P_QTY  > 0)
     OR (:V_IO_TYPE = 'O'  AND DT.O_QTY  > 0) )
  AND ( (:V_FIRST_ITEM = 'Y' AND DT.FIRST_ITEM = 1)
     OR (:V_FIRST_ITEM = 'N' AND DT.FIRST_ITEM > 0) )
ORDER BY DT.PROD_DT NULLS LAST, DT.PCARD_NAME;
```

**O-I 측 동등 골격**: P_MSPD52000S_Q_V39 DETAIL 분기 (L699-1289) — 4 leg (INOUT_OK/ONLY_OUT/ONLY_IN/INCOMING) 구조이며 IO_TYPE 매핑이 'OI'/'O'/'I'/'IN'. SQL 본문은 `fn_oi_size_cell_pcard` 의 DT CTE 에서 STYLE/SIZE 필터만 빼면 동일.

[확정: P_MSPD51000S_Q_V24 DETAIL 분기 (L477-765) 본문 대조 검증. O-I 측은 P_MSPD52000S_Q_V39 DETAIL 분기 (L699-1289) 의 4 leg 구조 — fn_oi_size_cell_pcard 본체에서 STYLE/SIZE 필터 제거 시 등가.]

---

## `fn_size_match`

**용도**: 라인 × 스타일 × ITEM_CLASS 별로 사이즈 분포 PIVOT (P-O Cross 화면의 "Size 별 분포" 패널 재현). 사용자 표현 "사이즈별 매칭", "스타일별 사이즈 분포".

**입력**: `:V_DATE`, `:V_COUNTRY`, `:V_FORM_ID`, `:V_LINE_CD` (단일 라인), `:V_CHECK_GROUP_CD`, `:V_IO_TYPE` ('P'/'P1'/'O'/'O1'), `:V_FIRST_ITEM`

**구조**: DETAIL_SIZE 분기 (P_MSPD51000S_Q_V24 L766-1091) 그대로:
- `fn_po_size_cell_pcard` 의 DT CTE 와 동일 구조 (PRODUCTION + MOVE leg UNION ALL, 라인 단일 좁힘, FN_GET_CHILD_ORG_LIST 사용)
- 거기서 (LINE_CD, ITEM_CLASS, STYLE_CD, SIZE_CD) 별 SUM 후 PIVOT FOR SIZE_CD
- 사이즈 컬럼 40 개 하드코딩 (FX_SIZE_0T ~ FX_SIZE_22)

**P-O 와 O-I 의 출처 차이**:
- P-O 패턴: P_MSPD51000S_Q_V24 L766-1091 — 사이즈 컬럼 40 종 (0T, 1, 1T, ..., 22)
- O-I 패턴: P_MSPD52000S_Q_V39 L1290-1898 — 같은 PIVOT 구조이지만 4 leg (OI/O/I/IN) 베이스

아래는 P-O 기준 SQL. O-I 기준은 DT 의 leg 와 IO_TYPE 매핑만 `fn_oi_cross_main` 패턴으로 바꾸면 됨.

```sql
WITH DT_GROUP AS ( /* fn_po_size_cell_pcard 와 동일 */ ),
W_ORG     AS ( /* 동일 */ ),
WC_LIST   AS ( /* 동일 — :V_LINE_CD 로 단일 라인 좁힘 */ ),
DT AS (
  -- fn_po_size_cell_pcard 의 DT 와 동일 (PRODUCTION leg + MOVE leg UNION ALL,
  -- FN_GET_CHILD_ORG_LIST + IPI/PHH Cross-plant EXISTS 룰)
  /* ... */
),
DT_LIST AS (
  -- 사이즈 셀별 합계 (IO_TYPE 분기로 어느 측정값을 더할지 결정)
  SELECT DT.LINE_CD, DT.ITEM_CLASS, ICLS.ITEM_CLASS_NAME,
         DT.SIZE_CD, DT.STYLE_CD,
         FN_GET_STYLE_MODEL('', DT.STYLE_CD) AS STYLE_NAME,
         CASE WHEN :V_IO_TYPE = 'P'  THEN SUM(DT.P_QTY)
              WHEN :V_IO_TYPE = 'P1' THEN SUM(DT.P1_QTY)
              WHEN :V_IO_TYPE = 'O'  THEN SUM(DT.O_QTY)
              WHEN :V_IO_TYPE = 'O1' THEN SUM(DT.O1_QTY)
              ELSE 0 END AS PCARD_QTY
    FROM      DT
    JOIN      MSBS_ITEM_CLASS ICLS ON DT.ITEM_CLASS = ICLS.ITEM_CLASS
   WHERE ( (:V_IO_TYPE = 'O1' AND DT.O1_QTY > 0)
        OR (:V_IO_TYPE = 'P1' AND DT.P1_QTY > 0)
        OR (:V_IO_TYPE = 'P'  AND DT.P_QTY  > 0)
        OR (:V_IO_TYPE = 'O'  AND DT.O_QTY  > 0) )
     AND ( (:V_FIRST_ITEM = 'Y' AND DT.FIRST_ITEM = 1)
        OR (:V_FIRST_ITEM = 'N' AND DT.FIRST_ITEM > 0) )
   GROUP BY DT.LINE_CD, DT.ITEM_CLASS, ICLS.ITEM_CLASS_NAME, DT.SIZE_CD, DT.STYLE_CD
),
DT_LIST2 AS (
  -- 스타일 × ITEM_CLASS 단위 TOTAL_QTY 부착 (사이즈 모든 셀 합산)
  SELECT DT_LIST.LINE_CD, DT_LIST.ITEM_CLASS, DT_LIST.ITEM_CLASS_NAME,
         DT_LIST.SIZE_CD, DT_LIST.STYLE_CD, DT_LIST.STYLE_NAME,
         (SELECT SUM(SUB.PCARD_QTY) FROM DT_LIST SUB
           WHERE SUB.STYLE_CD = DT_LIST.STYLE_CD
             AND SUB.ITEM_CLASS = DT_LIST.ITEM_CLASS) AS TOTAL_QTY,
         DT_LIST.PCARD_QTY
    FROM DT_LIST
),
PIVOT_DT AS (
  SELECT * FROM DT_LIST2
   PIVOT (SUM(PCARD_QTY)
          FOR SIZE_CD IN (
            '0T'  AS FX_SIZE_0T,  '1'   AS FX_SIZE_1,   '1T'  AS FX_SIZE_1T,
            '2'   AS FX_SIZE_2,   '2T'  AS FX_SIZE_2T,  '3'   AS FX_SIZE_3,
            '3T'  AS FX_SIZE_3T,  '4'   AS FX_SIZE_4,   '4T'  AS FX_SIZE_4T,
            '5'   AS FX_SIZE_5,   '5T'  AS FX_SIZE_5T,  '6'   AS FX_SIZE_6,
            '6T'  AS FX_SIZE_6T,  '7'   AS FX_SIZE_7,   '7T'  AS FX_SIZE_7T,
            '8'   AS FX_SIZE_8,   '8T'  AS FX_SIZE_8T,  '9'   AS FX_SIZE_9,
            '9T'  AS FX_SIZE_9T,  '10'  AS FX_SIZE_10,  '10T' AS FX_SIZE_10T,
            '11'  AS FX_SIZE_11,  '11T' AS FX_SIZE_11T, '12'  AS FX_SIZE_12,
            '12T' AS FX_SIZE_12T, '13'  AS FX_SIZE_13,  '13T' AS FX_SIZE_13T,
            '14'  AS FX_SIZE_14,  '14T' AS FX_SIZE_14T, '15'  AS FX_SIZE_15,
            '15T' AS FX_SIZE_15T, '16'  AS FX_SIZE_16,  '16T' AS FX_SIZE_16T,
            '17'  AS FX_SIZE_17,  '17T' AS FX_SIZE_17T, '18'  AS FX_SIZE_18,
            '19'  AS FX_SIZE_19,  '20'  AS FX_SIZE_20,  '21'  AS FX_SIZE_21,
            '22'  AS FX_SIZE_22)
         )
)
SELECT LINE_CD, ITEM_CLASS, ITEM_CLASS_NAME, STYLE_CD, STYLE_NAME,
       SUM(TOTAL_QTY) AS TOTAL_QTY,
       SUM(FX_SIZE_0T)  AS FX_SIZE_0T,  SUM(FX_SIZE_1)   AS FX_SIZE_1,
       SUM(FX_SIZE_1T)  AS FX_SIZE_1T,  SUM(FX_SIZE_2)   AS FX_SIZE_2,
       -- (이하 40 컬럼 같은 패턴, 가독성 위해 생략)
       SUM(FX_SIZE_22)  AS FX_SIZE_22
  FROM PIVOT_DT
 GROUP BY LINE_CD, STYLE_CD, STYLE_NAME, ITEM_CLASS, ITEM_CLASS_NAME;
```

[확정: P_MSPD51000S_Q_V24 DETAIL_SIZE 분기 (L766-1091) 본문 대조 검증. O-I 측은 P_MSPD52000S_Q_V39 DETAIL_SIZE 분기 (L1290-1898) 가 같은 PIVOT 구조이며 DT 의 leg 만 O-I 패턴 4 종으로 교체하면 됨.]

---

## `fn_pcard_scan_history`

**용도**: 특정 PCARD 의 스캔 시각·디바이스·결과 (POP_PCARD_SCAN 추적). SCR-003 SCAN_DATA (L1383-1466) + SCR-004 SCAN_DATA (L2496-2579) 두 분기 공통.

**프로시저 차이**:
- 두 분기는 동일한 컬럼 셋을 반환 (PCARD_NAME, SCAN_DT, WC_CD, PROD_MOVE_TYPE, RESULT_TYPE, DEVICE_NAME, LOG_MESSAGE)
- `FN_GET_DATE_FORMAT(SCAN_YMD)` / `FN_GET_TIME_FORMAT(SCAN_HMS)` 로 표시 포맷 적용
- `FN_GET_STYLE_MODEL('', STYLE_CD)` 로 STYLE_NAME 부착

**참고**: `LOG_MESSAGE` 는 CLOB. 길면 `DBMS_LOB.SUBSTR(LOG_MESSAGE, 200, 1)` 사용.

```sql
SELECT 
  PS.PCARD_NAME,
  PS.SCAN_DT,
  FN_GET_DATE_FORMAT(TO_CHAR(PS.SCAN_DT,'YYYYMMDD')) AS SCAN_YMD_FMT,
  FN_GET_TIME_FORMAT(TO_CHAR(PS.SCAN_DT,'HH24MISS')) AS SCAN_HMS_FMT,
  PS.WC_CD,
  PS.PROD_MOVE_TYPE,
  PS.RESULT_TYPE,
  PD.DEVICE_NAME,
  PS.STYLE_CD,
  FN_GET_STYLE_MODEL('', PS.STYLE_CD) AS STYLE_NAME,
  DBMS_LOB.SUBSTR(PS.LOG_MESSAGE, 200, 1) AS LOG_MESSAGE
FROM      OCI.POP_PCARD_SCAN PS
LEFT JOIN OCI.POP_DEVICE PD ON PD.DEVICE_ID = PS.DEVICE_ID
WHERE PS.PCARD_NAME IN ( :V_PCARD_LIST )
  AND PS.SCAN_DT BETWEEN TO_DATE(:V_DATE_F,'YYYYMMDD')
                     AND TO_DATE(:V_DATE_T,'YYYYMMDD') + 1
ORDER BY PS.SCAN_DT;
```

[확정: P_MSPD51000S_Q_V24 SCAN_DATA 분기 (L1383-1466) + P_MSPD52000S_Q_V39 SCAN_DATA 분기 (L2496-2579) 양쪽 대조 검증]

---

## `fn_po_size_cell_pcard`

**용도**: P-O Cross 화면에서 사이즈 셀(라인 × 스타일 × 사이즈 × IO_TYPE) 하나를 클릭했을 때 그 셀 안의 PCARD 들을 펼침. 사용자 표현 "이 사이즈 매칭 안 된 카드 어느 거?", "라인 03 OS 사이즈 8 의 Prod Only 카드".

**입력**: `:V_DATE`, `:V_COUNTRY`, `:V_FORM_ID`, `:V_LINE_CD`, `:V_CHECK_GROUP_CD` (예: 'OS'/'PP'/...), `:V_STYLE`, `:V_SIZE`, `:V_ITEM_CLASS`, `:V_IO_TYPE` ('P'/'P1'/'O'/'O1'), `:V_FIRST_ITEM`

**구조**: MAIN 의 DT CTE 와 동일하되, `WC_LIST.VIEW_GROUP_CD = :V_LINE_CD` 로 라인 단일 좁힘 + 최종 SELECT 에서 IO_TYPE 기준으로 PCARD_QTY 정함 + STYLE/SIZE/ITEM_CLASS 필터 추가.

**FN_GET_CHILD_ORG_LIST 사용** (DETAIL+ 분기 특성, 본 도메인 비대칭 섹션 참조).

```sql
WITH DT_GROUP AS (
  SELECT DISTINCT
         T_WC.ITEM_CLASS, T_GR.CHECK_GROUP_CD, T_WC.WC_CD,
         T_WC.CHECK_TIME_YN, T_WC.CHECK_START_DAY, T_WC.CHECK_START_HHMM,
         T_WC.CHECK_END_DAY, T_WC.CHECK_END_HHMM
    FROM MSBS_CHECKGROUP_WC T_WC
    JOIN MSBS_CHECKGROUP T_GR
      ON T_GR.COUNTRY_CD = T_WC.COUNTRY_CD AND T_GR.FORM_ID = T_WC.FORM_ID
     AND T_GR.CHECK_GROUP_CD = T_WC.CHECK_GROUP_CD
   WHERE T_GR.COUNTRY_CD = :V_COUNTRY AND T_GR.FORM_ID = :V_FORM_ID AND T_GR.USE_YN = 'Y'
),
W_ORG AS (
  SELECT A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE = B.ORG_TYPE AND A.SUB_ORG_CD = B.ORG_CD
   WHERE A.ORG_TYPE = 'COUNTRY' AND A.ORG_CD = :V_COUNTRY AND A.SUB_ORG_TYPE = 'GMES_PLANT'
),
WC_LIST AS (
  -- 라인 단일 좁힘 (VIEW_GROUP_CD = :V_LINE_CD)
  SELECT BS_WC.WC_CD, NVL(V_GR.VIEW_GROUP_CD, BS_WC.WC_CD) AS LINE_CD,
         NVL(V_NM.SUM_GROUP_MAME, BS_WC.WC_NAME) AS LINE_NAME,
         NVL(V_NM.SORT_SEQ, '0') AS WC_SEQ
    FROM      MSBS_WORK_CENTER BS_WC
    JOIN      MSBS_WC_GROUP BS_WCGRP ON BS_WC.PLANT_CD = BS_WCGRP.PLANT_CD AND BS_WC.WC_GROUP_CD = BS_WCGRP.WC_GROUP_CD
    JOIN      MSBS_SUM_GROUP_WC V_GR ON V_GR.COUNTRY_CD = :V_COUNTRY AND BS_WC.WC_CD = V_GR.WC_CD AND V_GR.FORM_ID = :V_FORM_ID
    JOIN      MSBS_SUM_GROUP_CD V_NM ON V_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND V_NM.SUM_GROUP_CD = V_GR.VIEW_GROUP_CD
                                    AND V_NM.FORM_ID = :V_FORM_ID AND V_NM.SUM_GROUP_TYPE = 'VIEW_GROUP' AND V_NM.USE_YN = 'Y'
    JOIN      W_ORG ON BS_WC.PLANT_CD = W_ORG.ORG_CD
   WHERE BS_WC.USE_YN = 'Y'
     AND V_GR.VIEW_GROUP_CD = :V_LINE_CD     -- ★ 단일 라인
),
DT AS (
  -- PRODUCTION leg
  SELECT '1' AS SEQ, DT_GROUP.CHECK_GROUP_CD,
         PO_T.ITEM_CLASS_TYPE, PO_T.FA_DATE, PO_T.FA_WC_CD,
         WC_LIST.LINE_CD, WC_LIST.LINE_NAME,
         PO_T.STYLE_CD, PO_T.SIZE_CD, PO_T.PROD_ORDER_TYPE,
         PO_T.PCARD_NAME, PO_T.BARCODE_KEY,
         PO_T.PROD_DT, PO_T.OUT_DT, PO_T.PROD_DATE, PO_T.OUT_DATE,
         PO_T.ITEM_CLASS, PO_T.OP_CD, PO_T.PROD_WC_CD, PO_T.OUT_WC_CD,
         CASE WHEN PO_T.PROD_DATE = :V_DATE THEN PO_T.PCARD_QTY ELSE 0 END                                    AS P_QTY,
         0                                                                                                    AS O_QTY,
         CASE WHEN PO_T.PROD_DATE = :V_DATE AND PO_T.OUT_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END    AS P1_QTY,
         0                                                                                                    AS O1_QTY,
         PO_T.DAY_SEQ, PO_T.PLAN_PROD_WC_CD, PO_T.ITEM_CD,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.PROD_WC_CD = DT_GROUP.WC_CD
    JOIN      WC_LIST  ON WC_LIST.WC_CD = DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD)
   WHERE PO_T.PROD_DATE      = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.PLANT_CD IN (SELECT ORG.ORG_CD FROM TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', :V_COUNTRY, 'GMES_PLANT')) ORG)
     AND PO_T.OP_CD          <> 'UPC'
     AND DT_GROUP.CHECK_GROUP_CD = :V_CHECK_GROUP_CD
     AND PO_T.RESULT_TYPE    = 'SCAN'
  UNION ALL
  -- MOVE/OUT leg (IPI/PHH Cross-plant EXISTS 룰)
  SELECT '1', DT_GROUP.CHECK_GROUP_CD,
         PO_T.ITEM_CLASS_TYPE, PO_T.FA_DATE, PO_T.FA_WC_CD,
         WC_LIST.LINE_CD, WC_LIST.LINE_NAME,
         PO_T.STYLE_CD, PO_T.SIZE_CD, PO_T.PROD_ORDER_TYPE,
         PO_T.PCARD_NAME, PO_T.BARCODE_KEY,
         PO_T.PROD_DT, PO_T.OUT_DT, PO_T.PROD_DATE, PO_T.OUT_DATE,
         PO_T.ITEM_CLASS, PO_T.OP_CD, PO_T.PROD_WC_CD, PO_T.OUT_WC_CD,
         0,
         PO_T.PCARD_QTY,
         0,
         CASE WHEN PO_T.PROD_DATE <= '20000101' THEN PO_T.PCARD_QTY ELSE 0 END,
         PO_T.DAY_SEQ, PO_T.PLAN_PROD_WC_CD, PO_T.ITEM_CD,
         ROW_NUMBER() OVER (PARTITION BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS_TYPE
                            ORDER BY PO_T.PCARD_NAME, PO_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT PO_T
    JOIN      DT_GROUP ON PO_T.ITEM_CLASS = DT_GROUP.ITEM_CLASS AND PO_T.OUT_WC_CD = DT_GROUP.WC_CD
    JOIN      WC_LIST  ON WC_LIST.WC_CD = DECODE(PO_T.PROD_ORDER_TYPE,'ZCP','ZCP01',PO_T.FA_WC_CD)
   WHERE PO_T.OUT_DATE       = :V_DATE
     AND PO_T.PROD_MOVE_TYPE = 'PROD'
     AND PO_T.END_ROUTING_YN = 'Y'
     AND PO_T.PLANT_CD IN (SELECT ORG.ORG_CD FROM TABLE(FN_GET_CHILD_ORG_LIST('COUNTRY', :V_COUNTRY, 'GMES_PLANT')) ORG)
     AND PO_T.OP_CD          <> 'UPC'
     AND DT_GROUP.CHECK_GROUP_CD = :V_CHECK_GROUP_CD
     AND PO_T.RESULT_TYPE    = 'SCAN'
     AND ( PO_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = PO_T.PCARD_NAME AND RES.ITEM_CD = PO_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> PO_T.PLANT_CD) )
)
SELECT 
  DT.LINE_CD, DT.LINE_NAME,
  DT.FA_DATE, DT.FA_WC_CD,
  DT.CHECK_GROUP_CD, DT.ITEM_CLASS_TYPE, DT.ITEM_CLASS,
  ICLS.ITEM_CLASS_NAME,
  DT.SIZE_CD, DT.STYLE_CD,
  FN_GET_STYLE_MODEL('', DT.STYLE_CD)               AS STYLE_NAME,
  DT.PROD_ORDER_TYPE,
  DT.BARCODE_KEY, DT.PCARD_NAME,
  TO_CHAR(DT.PROD_DT, 'YYYYMMDDHH24MISS')           AS PROD_SCAN_DT,
  TO_CHAR(DT.OUT_DT,  'YYYYMMDDHH24MISS')           AS OUT_SCAN_DT,
  DT.PROD_DATE, DT.OUT_DATE, DT.DAY_SEQ AS HH,
  DT.OP_CD AS PROD_OP_CD, DT.OP_CD AS OUT_OP_CD,
  NVL(DT.PROD_WC_CD, ' ') AS PROD_WC_CD,
  NVL(DT.OUT_WC_CD,  ' ') AS OUT_WC_CD,
  DT.PLAN_PROD_WC_CD, DT.ITEM_CD,
  -- IO_TYPE 별 PCARD_QTY 선택
  CASE WHEN :V_IO_TYPE = 'P'  THEN DT.P_QTY
       WHEN :V_IO_TYPE = 'P1' THEN DT.P1_QTY
       WHEN :V_IO_TYPE = 'O'  THEN DT.O_QTY
       WHEN :V_IO_TYPE = 'O1' THEN DT.O1_QTY
       ELSE 0 END                                  AS PCARD_QTY
FROM      DT
JOIN      MSBS_ITEM_CLASS ICLS ON DT.ITEM_CLASS = ICLS.ITEM_CLASS
WHERE ( (:V_IO_TYPE = 'O1' AND DT.O1_QTY > 0)
     OR (:V_IO_TYPE = 'P1' AND DT.P1_QTY > 0)
     OR (:V_IO_TYPE = 'P'  AND DT.P_QTY  > 0)
     OR (:V_IO_TYPE = 'O'  AND DT.O_QTY  > 0) )
  AND DT.STYLE_CD   = :V_STYLE
  AND DT.ITEM_CLASS = NVL(:V_ITEM_CLASS, DT.ITEM_CLASS)
  AND DT.SIZE_CD LIKE DECODE(:V_SIZE, '', '%%', :V_SIZE)
  AND ( (:V_FIRST_ITEM = 'Y' AND DT.FIRST_ITEM = 1)
     OR (:V_FIRST_ITEM = 'N' AND DT.FIRST_ITEM > 0) )
ORDER BY DT.PROD_DT NULLS LAST, DT.PCARD_NAME;
```

[확정: P_MSPD51000S_Q_V24 DETAIL_SIZE_DETAIL 분기 (L1092-1382) 본문 대조 검증]

---

## `fn_oi_size_cell_pcard`

**용도**: O-I Cross 화면에서 사이즈 셀(라인 × 스타일 × 사이즈 × IO_TYPE) 하나 클릭 시 PCARD 펼침. 사용자 표현 "라인 03 의 OUT_ONLY 카드", "라인 03 의 IN_ONLY 카드".

**입력**: `:V_DATE`, `:V_COUNTRY`, `:V_FORM_ID`, `:V_LINE_CD`, `:V_CHECK_GROUP_CD`, `:V_STYLE`, `:V_SIZE`, `:V_ITEM_CLASS`, `:V_IO_TYPE` ('OI'/'O'/'I'/'IN'), `:V_FIRST_ITEM`

**구조**: O-I MAIN 의 4 leg (INOUT_OK / ONLY_OUT / ONLY_IN / INCOMING) 와 같은 4 UNION ALL leg + 라인 단일 좁힘 + STYLE/SIZE 필터.

**FN_GET_CHILD_ORG_LIST 미사용** (SCR-004 의 특성, 본 도메인 비대칭 섹션 참조). W_ORG/ORG CTE 만 사용.

```sql
WITH ORG AS (
  SELECT A.SUB_ORG_CD AS ORG_CD
    FROM MSBS_ORGANIZATION_SUB A
    JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE = B.ORG_TYPE AND A.SUB_ORG_CD = B.ORG_CD
   WHERE A.ORG_TYPE = 'COUNTRY' AND A.ORG_CD = :V_COUNTRY AND A.SUB_ORG_TYPE = 'GMES_PLANT'
),
LG_LIST AS (
  SELECT BS_WC.WC_CD, BS_WC.WC_NAME,
         NVL(V_GR.VIEW_GROUP_CD, BS_WC.WC_CD) AS LINE_CD,
         NVL(V_NM.SUM_GROUP_MAME, BS_WC.WC_NAME) AS LINE_NAME,
         NVL(V_NM.SORT_SEQ, '0') AS WC_SEQ
    FROM      MSBS_WORK_CENTER BS_WC
    JOIN      MSBS_WC_GROUP BS_WCGRP ON BS_WC.PLANT_CD = BS_WCGRP.PLANT_CD AND BS_WC.WC_GROUP_CD = BS_WCGRP.WC_GROUP_CD
    JOIN      MSBS_SUM_GROUP_WC V_GR ON V_GR.COUNTRY_CD = :V_COUNTRY AND BS_WC.WC_CD = V_GR.WC_CD AND V_GR.FORM_ID = :V_FORM_ID
    JOIN      MSBS_SUM_GROUP_CD V_NM ON V_NM.COUNTRY_CD = V_GR.COUNTRY_CD AND V_NM.SUM_GROUP_CD = V_GR.VIEW_GROUP_CD
                                    AND V_NM.FORM_ID = :V_FORM_ID AND V_NM.SUM_GROUP_TYPE = 'VIEW_GROUP'
   WHERE BS_WC.USE_YN = 'Y'
),
DT_GROUP AS (
  SELECT DISTINCT CHK_WC.ITEM_CLASS, CHK_GRP.CHECK_GROUP_CD, CHK_WC.WC_CD
    FROM MSBS_CHECKGROUP CHK_GRP
    JOIN MSBS_CHECKGROUP_WC CHK_WC
      ON CHK_GRP.COUNTRY_CD = CHK_WC.COUNTRY_CD AND CHK_GRP.FORM_ID = CHK_WC.FORM_ID
     AND CHK_GRP.CHECK_GROUP_CD = CHK_WC.CHECK_GROUP_CD
   WHERE CHK_GRP.COUNTRY_CD = :V_COUNTRY
     AND CHK_GRP.FORM_ID = :V_FORM_ID
     AND CHK_GRP.USE_YN = 'Y'
     AND CHK_GRP.CHECK_GROUP_CD = :V_CHECK_GROUP_CD
),
DT AS (
  -- INOUT_OK leg (V_P_IO_TYPE = 'OI')
  SELECT OI_T.PLANT_CD, IN_T.PLANT_CD AS IN_PLANT_CD,
         OI_T.PCARD_NAME, OI_T.PCARD_QTY,
         OI_T.PCARD_QTY AS OUT_PCARD_QTY, OI_T.PCARD_QTY AS IN_PCARD_QTY, 0 AS IN_QTY,
         OI_T.FA_WC_CD, IN_T.PLAN_PROD_WC_CD,
         LG.LINE_CD, LG.LINE_NAME, LG.WC_NAME,
         OI_T.FA_DATE, OI_T.ITEM_CLASS, OI_T.ITEM_CD, OI_T.STYLE_CD, OI_T.SIZE_CD,
         OI_T.PROD_ORDER_TYPE,
         OI_T.OP_CD  AS OUT_OP_CD, OI_T.OUT_WC_CD, OI_T.OUT_DT, OI_T.OUT_DATE,
         IN_T.OP_CD  AS IN_OP_CD,  IN_T.IN_WC_CD,  IN_T.IN_WH_CD, IN_T.IN_DT, IN_T.IN_DATE,
         NVL(OI_T.BARCODE_KEY, OI_T.PCARD_ID) AS PCARD_ID,
         OI_T.ITEM_CLASS_TYPE, OI_T.ROUTING_SEQ, OI_T.DAY_SEQ, OI_T.PCARD_SEQ,
         OI_T.PLAN_PROD_WC_CD AS OUT_PLAN_WC_CD, IN_T.PLAN_PROD_WC_CD AS IN_PLAN_WC_CD,
         OI_T.BARCODE_KEY,
         ROW_NUMBER() OVER (PARTITION BY OI_T.PCARD_NAME, OI_T.ITEM_CLASS_TYPE
                            ORDER BY OI_T.PCARD_NAME, OI_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT OI_T
    JOIN      LG_LIST LG ON OI_T.FA_WC_CD = LG.WC_CD
    JOIN      ORG ON ORG.ORG_CD = OI_T.PLANT_CD
    JOIN      DT_GROUP ICT ON ICT.ITEM_CLASS = OI_T.ITEM_CLASS AND ICT.WC_CD = OI_T.OUT_WC_CD
    JOIN      MSPD_PCARD_RESULT IN_T
              ON IN_T.PCARD_NAME = OI_T.PCARD_NAME AND IN_T.ITEM_CD = OI_T.ITEM_CD
             AND IN_T.IN_DT > TO_DATE('20010101','YYYYMMDD')
             AND IN_T.PROD_MOVE_TYPE = 'MOVE' AND IN_T.RESULT_TYPE = 'SCAN'
   WHERE OI_T.OUT_DATE       = :V_DATE
     AND OI_T.PROD_MOVE_TYPE = 'PROD'
     AND OI_T.END_ROUTING_YN = 'Y'
     AND OI_T.RESULT_TYPE    = 'SCAN'
     AND LG.LINE_CD = :V_LINE_CD AND :V_IO_TYPE = 'OI'
     AND ( OI_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = OI_T.PCARD_NAME AND RES.ITEM_CD = OI_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> OI_T.PLANT_CD) )
     AND ( OI_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OI_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OI_T.BOMLEVEL <> 0) )
  UNION ALL
  -- ONLY_OUT leg (V_P_IO_TYPE = 'O') — 출고만, 입고 NOT EXISTS
  SELECT OUT_T.PLANT_CD, NULL,
         OUT_T.PCARD_NAME, OUT_T.PCARD_QTY,
         OUT_T.PCARD_QTY, 0, 0,
         OUT_T.FA_WC_CD, OUT_T.PLAN_PROD_WC_CD,
         LG.LINE_CD, LG.LINE_NAME, LG.WC_NAME,
         OUT_T.FA_DATE, OUT_T.ITEM_CLASS, OUT_T.ITEM_CD, OUT_T.STYLE_CD, OUT_T.SIZE_CD,
         OUT_T.PROD_ORDER_TYPE,
         OUT_T.OP_CD, OUT_T.OUT_WC_CD, OUT_T.OUT_DT, OUT_T.OUT_DATE,
         '', '', '', NULL, '',
         NVL(OUT_T.BARCODE_KEY, OUT_T.PCARD_ID),
         OUT_T.ITEM_CLASS_TYPE, OUT_T.ROUTING_SEQ, OUT_T.DAY_SEQ, OUT_T.PCARD_SEQ,
         OUT_T.PLAN_PROD_WC_CD,
         (SELECT PLAN_PROD_WC_CD FROM MSPD_PCARD_RESULT
           WHERE PCARD_NAME = OUT_T.PCARD_NAME AND ITEM_CD = OUT_T.ITEM_CD
             AND PROD_MOVE_TYPE = 'MOVE' AND END_ROUTING_YN = 'Y'),
         OUT_T.BARCODE_KEY,
         ROW_NUMBER() OVER (PARTITION BY OUT_T.PCARD_NAME, OUT_T.ITEM_CLASS_TYPE
                            ORDER BY OUT_T.PCARD_NAME, OUT_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT OUT_T
    JOIN      LG_LIST LG ON OUT_T.FA_WC_CD = LG.WC_CD
    JOIN      ORG ON ORG.ORG_CD = OUT_T.PLANT_CD
    JOIN      DT_GROUP ICT ON ICT.ITEM_CLASS = OUT_T.ITEM_CLASS AND ICT.WC_CD = OUT_T.OUT_WC_CD
   WHERE OUT_T.OUT_DATE       = :V_DATE
     AND OUT_T.PROD_MOVE_TYPE = 'PROD'
     AND OUT_T.END_ROUTING_YN = 'Y'
     AND OUT_T.RESULT_TYPE    = 'SCAN'
     AND LG.LINE_CD = :V_LINE_CD AND :V_IO_TYPE = 'O'
     AND ( OUT_T.OP_CD NOT IN ('IPI','PHH')
        OR EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT RES
                    WHERE RES.PCARD_NAME = OUT_T.PCARD_NAME AND RES.ITEM_CD = OUT_T.ITEM_CD
                      AND RES.PROD_MOVE_TYPE = 'MOVE' AND RES.PLANT_CD <> OUT_T.PLANT_CD) )
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
     AND NOT EXISTS (SELECT 1 FROM MSPD_PCARD_RESULT IN_T1
                      WHERE IN_T1.PCARD_NAME = OUT_T.PCARD_NAME
                        AND IN_T1.ITEM_CLASS = OUT_T.ITEM_CLASS
                        AND IN_T1.PROD_MOVE_TYPE = 'MOVE' AND IN_T1.END_ROUTING_YN = 'Y'
                        AND IN_T1.IN_DT > TO_DATE('20010101','YYYYMMDD')
                        AND IN_T1.RESULT_TYPE = 'SCAN')
  UNION ALL
  -- ONLY_IN leg (V_P_IO_TYPE = 'I') — 입고는 됐고 매칭 출고는 미발생 (OUT_T.OUT_DATE < '20010101')
  SELECT IN_T.PLANT_CD, IN_T.PLANT_CD AS IN_PLANT_CD,
         IN_T.PCARD_NAME, IN_T.PCARD_QTY,
         0 AS OUT_PCARD_QTY, IN_T.PCARD_QTY AS IN_PCARD_QTY, 0 AS IN_QTY,
         IN_T.FA_WC_CD, IN_T.PLAN_PROD_WC_CD,
         LG.LINE_CD, LG.LINE_NAME, LG.WC_NAME,
         IN_T.FA_DATE, IN_T.ITEM_CLASS, IN_T.ITEM_CD, IN_T.STYLE_CD, IN_T.SIZE_CD,
         IN_T.PROD_ORDER_TYPE,
         '' AS OUT_OP_CD, '' AS OUT_WC_CD, NULL AS OUT_DT, '' AS OUT_DATE,
         IN_T.OP_CD AS IN_OP_CD, IN_T.IN_WC_CD, IN_T.IN_WH_CD, IN_T.IN_DT, IN_T.IN_DATE,
         NVL(IN_T.BARCODE_KEY, IN_T.PCARD_ID) AS PCARD_ID,
         IN_T.ITEM_CLASS_TYPE, IN_T.ROUTING_SEQ, IN_T.DAY_SEQ, IN_T.PCARD_SEQ,
         (SELECT PLAN_PROD_WC_CD FROM MSPD_PCARD_RESULT
           WHERE PCARD_NAME = IN_T.PCARD_NAME AND ITEM_CD = IN_T.ITEM_CD
             AND PROD_MOVE_TYPE = 'PROD' AND RESULT_TYPE = 'SCAN' AND END_ROUTING_YN = 'Y') AS OUT_PLAN_WC_CD,
         IN_T.PLAN_PROD_WC_CD AS IN_PLAN_WC_CD,
         OUT_T.BARCODE_KEY,
         ROW_NUMBER() OVER (PARTITION BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE
                            ORDER BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS) AS FIRST_ITEM
    FROM      MSPD_PCARD_RESULT IN_T
    JOIN      MSPD_PCARD_RESULT OUT_T
              ON OUT_T.PCARD_NAME = IN_T.PCARD_NAME AND OUT_T.ITEM_CD = IN_T.ITEM_CD
             AND OUT_T.PROD_MOVE_TYPE = 'PROD' AND OUT_T.END_ROUTING_YN = 'Y'
             AND OUT_T.OUT_DATE < '20010101' AND OUT_T.RESULT_TYPE = 'SCAN'
    JOIN      LG_LIST LG ON IN_T.FA_WC_CD = LG.WC_CD
    JOIN      DT_GROUP ICT ON ICT.ITEM_CLASS = OUT_T.ITEM_CLASS AND ICT.WC_CD = OUT_T.PLAN_PROD_WC_CD
    JOIN      ORG ON ORG.ORG_CD = IN_T.PLANT_CD
   WHERE IN_T.IN_DATE        = :V_DATE
     AND IN_T.PROD_MOVE_TYPE  = 'MOVE'
     AND IN_T.END_ROUTING_YN  = 'Y'
     AND IN_T.RESULT_TYPE     = 'SCAN'
     AND LG.LINE_CD = :V_LINE_CD AND :V_IO_TYPE = 'I'
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
  UNION ALL
  -- INCOMING leg (V_P_IO_TYPE = 'IN') — 입고 발생 + 매칭 출고도 정상 있음
  SELECT IN_T.PLANT_CD, IN_T.PLANT_CD,
         IN_T.PCARD_NAME, IN_T.PCARD_QTY,
         0, 0, IN_T.PCARD_QTY AS IN_QTY,
         IN_T.FA_WC_CD, IN_T.PLAN_PROD_WC_CD,
         LG.LINE_CD, LG.LINE_NAME, LG.WC_NAME,
         IN_T.FA_DATE, IN_T.ITEM_CLASS, IN_T.ITEM_CD, IN_T.STYLE_CD, IN_T.SIZE_CD,
         IN_T.PROD_ORDER_TYPE,
         OUT_T.OP_CD, OUT_T.OUT_WC_CD, OUT_T.OUT_DT, OUT_T.OUT_DATE,
         IN_T.OP_CD, IN_T.IN_WC_CD, IN_T.IN_WH_CD, IN_T.IN_DT, IN_T.IN_DATE,
         NVL(IN_T.BARCODE_KEY, IN_T.PCARD_ID),
         IN_T.ITEM_CLASS_TYPE, IN_T.ROUTING_SEQ, IN_T.DAY_SEQ, IN_T.PCARD_SEQ,
         (SELECT PLAN_PROD_WC_CD FROM MSPD_PCARD_RESULT
           WHERE PCARD_NAME = IN_T.PCARD_NAME AND ITEM_CD = IN_T.ITEM_CD
             AND PROD_MOVE_TYPE = 'PROD' AND RESULT_TYPE = 'SCAN' AND END_ROUTING_YN = 'Y') AS OUT_PLAN_WC_CD,
         IN_T.PLAN_PROD_WC_CD,
         OUT_T.BARCODE_KEY,
         ROW_NUMBER() OVER (PARTITION BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS_TYPE
                            ORDER BY IN_T.PCARD_NAME, IN_T.ITEM_CLASS)
    FROM      MSPD_PCARD_RESULT IN_T
    JOIN      MSPD_PCARD_RESULT OUT_T
              ON OUT_T.PCARD_NAME = IN_T.PCARD_NAME AND OUT_T.ITEM_CD = IN_T.ITEM_CD
             AND OUT_T.PROD_MOVE_TYPE = 'PROD' AND OUT_T.END_ROUTING_YN = 'Y'
             AND OUT_T.RESULT_TYPE = 'SCAN'
    JOIN      LG_LIST LG ON IN_T.FA_WC_CD = LG.WC_CD
    JOIN      ORG ON ORG.ORG_CD = IN_T.PLANT_CD
    JOIN      DT_GROUP ICT ON ICT.ITEM_CLASS = OUT_T.ITEM_CLASS AND ICT.WC_CD = OUT_T.PLAN_PROD_WC_CD
   WHERE IN_T.IN_DATE        = :V_DATE
     AND IN_T.PROD_MOVE_TYPE  = 'MOVE'
     AND IN_T.RESULT_TYPE     = 'SCAN'
     AND LG.LINE_CD = :V_LINE_CD AND :V_IO_TYPE = 'IN'
     AND ( OUT_T.PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
        OR (OUT_T.PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND OUT_T.BOMLEVEL <> 0) )
)
SELECT 
  DT.LINE_CD, DT.LINE_NAME,
  DT.FA_DATE, DT.FA_WC_CD,
  DT.ITEM_CLASS, DT.ITEM_CLASS_TYPE,
  DT.SIZE_CD, DT.STYLE_CD,
  FN_GET_STYLE_MODEL('', DT.STYLE_CD)           AS STYLE_NAME,
  DT.PROD_ORDER_TYPE,
  DT.BARCODE_KEY, DT.PCARD_NAME,
  TO_CHAR(DT.OUT_DT,'YYYYMMDDHH24MISS')         AS OUT_SCAN_DT,
  TO_CHAR(DT.IN_DT, 'YYYYMMDDHH24MISS')         AS IN_SCAN_DT,
  DT.OUT_DATE, DT.IN_DATE,
  DT.OUT_OP_CD, DT.OUT_WC_CD, DT.IN_OP_CD, DT.IN_WC_CD, DT.IN_WH_CD,
  DT.PLAN_PROD_WC_CD, DT.IN_PLAN_WC_CD,
  -- IO_TYPE 별 PCARD_QTY
  CASE WHEN :V_IO_TYPE = 'OI' THEN DT.OUT_PCARD_QTY
       WHEN :V_IO_TYPE = 'O'  THEN DT.OUT_PCARD_QTY
       WHEN :V_IO_TYPE = 'I'  THEN DT.IN_PCARD_QTY
       WHEN :V_IO_TYPE = 'IN' THEN DT.IN_QTY
       ELSE 0 END                              AS PCARD_QTY
FROM      DT
WHERE DT.STYLE_CD   = :V_STYLE
  AND DT.ITEM_CLASS = NVL(:V_ITEM_CLASS, DT.ITEM_CLASS)
  AND DT.SIZE_CD LIKE DECODE(:V_SIZE, '', '%%', :V_SIZE)
  AND ( (:V_FIRST_ITEM = 'Y' AND DT.FIRST_ITEM = 1)
     OR (:V_FIRST_ITEM = 'N' AND DT.FIRST_ITEM > 0) )
ORDER BY DT.OUT_DT NULLS LAST, DT.PCARD_NAME;
```

[확정: P_MSPD52000S_Q_V39 DETAIL_SIZE_DETAIL 분기 (L1899-2495) 의 INOUT_OK (L1992-2112) + ONLY_OUT (L2113-2256) + ONLY_IN (L2257-2333) + INCOMING (L2334-2397) leg 4 종 모두 대조 검증]
