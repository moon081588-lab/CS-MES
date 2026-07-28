# Functions — Common (도메인 횡단 공용 함수/뷰)

여러 도메인 SQL 에서 공통으로 쓰는 PL/SQL 함수와 뷰. 도메인 전용 함수는 각 도메인 파일 참조 (`production-status.md`, `shortage-management.md`, `inout-cross-check.md`).

## 사용 원칙

각 항목마다 세 가지가 있다.

| 섹션 | 의미 |
|---|---|
| **호출 방식** | 함수가 OCI 에 적용됐을 때 SQL 안에서 `FN_XXX(...)` 형태로 직접 호출. |
| **인라인 풀이** | 함수가 OCI 에 없거나 함수 호출 비용을 피하고 싶을 때 — 같은 로직을 SQL 표현식으로 풀어 박는다. |
| **원본 DDL** | LMES 운영계 함수 본문. 인라인 풀이의 근거 + 운영팀 이관 요청 시 첨부. |

### OCI 적용 상태 (2026-05-15 확인)

| 함수/뷰 | OCI 적용 | 행동 |
|---|---|---|
| FN_GET_DATE_FORMAT | ✗ 미적용 | 인라인 풀이 사용 |
| FN_GET_TIME_FORMAT | ✗ 미적용 | 인라인 풀이 사용 |
| FN_GET_STYLE_MODEL | ✗ 미적용 | 인라인 풀이 사용 |
| FN_GET_CHILD_ORG_LIST | ✗ 미적용 | 인라인 풀이 사용 |
| VW_MSBS_CODE_MASTER | ✗ 미적용 | 인라인 풀이 사용 (원본 테이블 `MSBS_CODE_MASTER` 는 OCI 적용됨) |

OCI 에 deploy 되면 호출 방식으로 전환. 도메인 전용 함수의 적용 상태는 각 도메인 파일 참조.

---

## 목차

| 함수/뷰 | 종류 | 용도 |
|---|---|---|
| [`FN_GET_DATE_FORMAT`](#fn_get_date_format) | Scalar | YYYYMMDD → YYYY-MM-DD |
| [`FN_GET_TIME_FORMAT`](#fn_get_time_format) | Scalar | HHMISS → HH:MI:SS |
| [`FN_GET_STYLE_MODEL`](#fn_get_style_model) | Scalar | ITEM_CD → STYLE/MODEL 이름 |
| [`FN_GET_CHILD_ORG_LIST`](#fn_get_child_org_list) | Pipelined | 조직 트리 자식 펼치기 |
| [`VW_MSBS_CODE_MASTER`](#vw_msbs_code_master) | View | 코드 lookup (PLANT 별 + COMMON 통합) |

---

## `FN_GET_DATE_FORMAT`

**종류**: Scalar Function
**시그니처**: `FN_GET_DATE_FORMAT(arg_ymd VARCHAR2) RETURN VARCHAR2`
**입력**: `'YYYYMMDD'` 8 자리 (NULL/공백 OK)
**출력**: `'YYYY-MM-DD'`. 입력 NULL/공백이면 `''`.
**역할**: 분석 결과의 날짜 컬럼 (`PROD_DATE`, `OSND_DATE`, `IN_DATE` 등) 을 사람 가독 형식으로

### 호출 방식 (OCI 적용 시)

```sql
SELECT FN_GET_DATE_FORMAT(PROD_DATE) AS PROD_DATE_FMT
  FROM OCI.MSPD_PCARD_RESULT
 WHERE PROD_DATE = :V_DATE;
```

### 인라인 풀이 (현재 권장)

```sql
SELECT CASE WHEN TRIM(PROD_DATE) IS NULL THEN ''
            ELSE SUBSTR(PROD_DATE,1,4)||'-'||SUBSTR(PROD_DATE,5,2)||'-'||SUBSTR(PROD_DATE,7,2)
       END AS PROD_DATE_FMT
  FROM OCI.MSPD_PCARD_RESULT
 WHERE PROD_DATE = :V_DATE;
```

### 원본 DDL

<details>
<summary>LMES.FN_GET_DATE_FORMAT 원본</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_GET_DATE_FORMAT (ARG_YMD VARCHAR2)
   RETURN VARCHAR2
IS
BEGIN
   IF (TRIM (ARG_YMD) IS NULL)
   THEN
      RETURN '';
   END IF;

   RETURN    SUBSTR (ARG_YMD, 0, 4)
          || '-'
          || SUBSTR (ARG_YMD, 5, 2)
          || '-'
          || SUBSTR (ARG_YMD, 7, 2);
END ;
/
```

</details>

---

## `FN_GET_TIME_FORMAT`

**종류**: Scalar Function
**시그니처**: `FN_GET_TIME_FORMAT(arg_time VARCHAR2) RETURN VARCHAR2`
**입력**: `'HHMISS'` 6 자리 (NULL/공백 OK)
**출력**: `'HH:MI:SS'`. NULL/공백 시 `''`.
**역할**: `TO_CHAR(PROD_DT,'HH24MISS')` 결과 등 시각 문자열을 가독 형식으로

### 호출 방식 (OCI 적용 시)

```sql
SELECT FN_GET_TIME_FORMAT(TO_CHAR(PROD_DT,'HH24MISS')) AS PROD_TIME_FMT
  FROM OCI.MSPD_PCARD_RESULT;
```

### 인라인 풀이 (현재 권장)

원본 함수는 `SUBSTR(arg,1,2)||':'||SUBSTR(arg,3,2)||':'||SUBSTR(arg,-2)` 인데, `PROD_DT` 가 DATE 타입이면 `TO_CHAR` 한 번이 더 깔끔:

```sql
-- DATE 타입에서 바로 (가장 간단)
SELECT TO_CHAR(PROD_DT, 'HH24:MI:SS') AS PROD_TIME_FMT
  FROM OCI.MSPD_PCARD_RESULT;

-- 이미 'HHMISS' 6 자리 문자열인 경우
SELECT CASE WHEN TRIM(:T) IS NULL THEN ''
            ELSE SUBSTR(:T,1,2)||':'||SUBSTR(:T,3,2)||':'||SUBSTR(:T,5,2)
       END AS TIME_FMT
  FROM DUAL;
```

### 원본 DDL

<details>
<summary>LMES.FN_GET_TIME_FORMAT 원본</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_GET_TIME_FORMAT (ARG_TIME VARCHAR2)
   RETURN VARCHAR2
IS
BEGIN
   IF (TRIM (ARG_TIME) IS NULL)
   THEN
      RETURN '';
   END IF;

   RETURN    SUBSTR (ARG_TIME, 1, 2)
          || ':'
          || SUBSTR (ARG_TIME, 3, 2)
          || ':'
          || SUBSTR (ARG_TIME, -2);
END FN_GET_TIME_FORMAT;
/
```

</details>

---

## `FN_GET_STYLE_MODEL`

**종류**: Scalar Function
**시그니처**: `FN_GET_STYLE_MODEL(v_p_flag VARCHAR2, v_p_item_cd VARCHAR2) RETURN NVARCHAR2`
**입력**:
- `v_p_flag`: `'MODEL_CD'` (MODEL_CD 반환) | `'MODEL_NAME'` (MODEL_NAME 반환) | 그 외 (STYLE_NAME 반환)
- `v_p_item_cd`: `MSBS_ITEM.ITEM_CD`

**출력**: 해당 항목값 (NVARCHAR2). `ITEM_TYPE IN ('FP','SP','ASY')` 인 행 중 첫 행 기준.
**역할**: 분석 결과 표에 Style/Model 이름 붙이기

### 호출 방식 (OCI 적용 시)

```sql
SELECT R.ITEM_CD,
       FN_GET_STYLE_MODEL('STYLE',      R.ITEM_CD) AS STYLE_NAME,
       FN_GET_STYLE_MODEL('MODEL_CD',   R.ITEM_CD) AS MODEL_CD,
       FN_GET_STYLE_MODEL('MODEL_NAME', R.ITEM_CD) AS MODEL_NAME
  FROM OCI.MSPD_PCARD_RESULT R
 WHERE PROD_DATE = :V_DATE
 GROUP BY R.ITEM_CD;
```

### 인라인 풀이 (현재 권장)

`MSBS_ITEM` 을 한 번 JOIN 해서 세 컬럼을 한꺼번에 가져오는 게 함수 3 번 호출보다 훨씬 빠름.

```sql
SELECT R.ITEM_CD,
       I.STYLE_NAME,
       I.MODEL_CD,
       I.MODEL_NAME
  FROM OCI.MSPD_PCARD_RESULT R
  LEFT JOIN (
        SELECT ITEM_CD, STYLE_NAME, MODEL_CD, MODEL_NAME,
               ROW_NUMBER() OVER (PARTITION BY ITEM_CD ORDER BY ITEM_TYPE) AS RN
          FROM OCI.MSBS_ITEM
         WHERE ITEM_TYPE IN ('FP','SP','ASY')
       ) I
    ON I.ITEM_CD = R.ITEM_CD
   AND I.RN = 1
 WHERE R.PROD_DATE = :V_DATE
 GROUP BY R.ITEM_CD, I.STYLE_NAME, I.MODEL_CD, I.MODEL_NAME;
```

주의:
- 원본 함수는 `ROWNUM = 1` 로 임의 1 개 선택 — 인라인은 `ROW_NUMBER()` 로 안정적 선택.
- ITEM_CD 가 `MSBS_ITEM` 에 없을 때 원본 함수는 `NO_DATA_FOUND` 예외 (캐치 없음 → 호출 실패). LEFT JOIN 은 NULL 반환 — **인라인이 더 안전**.

### 원본 DDL

<details>
<summary>LMES.FN_GET_STYLE_MODEL 원본</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_GET_STYLE_MODEL
(
  V_P_FLAG IN VARCHAR2 -- STYLE, MODEL_CD, MODEL_NAME
  , V_P_ITEM_CD IN VARCHAR2
)
RETURN  NVARCHAR2
AS
   V_STR_RETURN_NAME NVARCHAR2(100);
BEGIN
    SELECT DECODE(V_P_FLAG, 'MODEL_CD', MODEL_CD, 'MODEL_NAME', MODEL_NAME, STYLE_NAME)
      INTO V_STR_RETURN_NAME
      FROM MSBS_ITEM
     WHERE (ITEM_CD = V_P_ITEM_CD )
       AND ITEM_TYPE IN ('FP','SP','ASY'  )
       AND ROWNUM   = 1;

    RETURN V_STR_RETURN_NAME;
END FN_GET_STYLE_MODEL;
/
```

</details>

---

## `FN_GET_CHILD_ORG_LIST`

**종류**: **Pipelined Function** (FROM 절에서 `TABLE(...)` 형태로 호출)
**시그니처**: `FN_GET_CHILD_ORG_LIST(v_p_org_type VARCHAR2, v_p_org_cd VARCHAR2, v_p_sub_org_type VARCHAR2) RETURN CHILD_ORG_TBL PIPELINED`
**입력**:
- `v_p_org_type`: 상위 조직 타입 (예: `'PLANT'`, `'LINE'`)
- `v_p_org_cd`: 상위 조직 코드
- `v_p_sub_org_type`: 자식 조직 타입 (NULL 이면 모든 자식 타입)

**출력**: `(ORG_TYPE, ORG_CD, ORG_NAME)` 행 집합
**역할**: 조직 트리에서 특정 상위 산하의 자식 list 펼치기

추가 의존: 함수 RETURN 타입이 `CHILD_ORG_TBL` (TYPE) — 의존 객체. `CHILD_ORG_ROW` (ROW 타입) 도.

### 호출 방식 (OCI 적용 시)

```sql
-- JJ Plant (3110) 산하 LINE 조직 펼치기
SELECT *
  FROM TABLE(FN_GET_CHILD_ORG_LIST('PLANT', '3110', 'LINE'));

-- 라인 list 를 다른 쿼리의 IN 조건으로
WITH LINES AS (
  SELECT ORG_CD AS LINE_CD
    FROM TABLE(FN_GET_CHILD_ORG_LIST('PLANT', '3110', 'LINE'))
)
SELECT R.*
  FROM OCI.MSPD_PCARD_RESULT R
 WHERE R.FA_WC_CD IN (SELECT LINE_CD FROM LINES);
```

### 인라인 풀이 (현재 권장)

함수 본문은 `MSBS_ORGANIZATION_SUB` + `MSBS_ORGANIZATION` JOIN 한 줄. 그대로 풀어 쓰면 됨.

```sql
-- 함수의 한 호출과 동일
SELECT A.SUB_ORG_TYPE AS ORG_TYPE,
       A.SUB_ORG_CD   AS ORG_CD,
       B.ORG_NAME
  FROM OCI.MSBS_ORGANIZATION_SUB A
  INNER JOIN OCI.MSBS_ORGANIZATION B
    ON A.SUB_ORG_TYPE = B.ORG_TYPE
   AND A.SUB_ORG_CD   = B.ORG_CD
 WHERE A.ORG_TYPE         = :V_ORG_TYPE        -- 예: 'PLANT'
   AND A.ORG_CD           = :V_ORG_CD          -- 예: '3110'
   AND A.SUB_ORG_TYPE     = :V_SUB_ORG_TYPE;   -- 예: 'LINE' (NULL 이면 조건 제거)

-- IN 절에 쓰는 경우
WITH LINES AS (
  SELECT A.SUB_ORG_CD AS LINE_CD
    FROM OCI.MSBS_ORGANIZATION_SUB A
   WHERE A.ORG_TYPE     = 'PLANT'
     AND A.ORG_CD       = '3110'
     AND A.SUB_ORG_TYPE = 'LINE'
)
SELECT R.*
  FROM OCI.MSPD_PCARD_RESULT R
 WHERE R.FA_WC_CD IN (SELECT LINE_CD FROM LINES);
```

주의:
- `MSBS_ORGANIZATION_SUB`, `MSBS_ORGANIZATION` 두 테이블이 OCI 에 있는지 확인 필요 (semantic_models 에 `MSBS_ORGANIZATION_SUB.yml` 은 있음 → OCI 에 적용된 것으로 추정).
- 함수가 NULL `sub_org_type` 받으면 `NVL` 로 조건 자체를 해제 — 인라인도 동적으로 처리하려면 `(A.SUB_ORG_TYPE = :T OR :T IS NULL)`.
- 호출 방식 (`TABLE(...)`) vs 인라인 (서브쿼리) 둘 다 옵티마이저 효율 비슷. 인라인이 통계 잘 활용함.

### 원본 DDL

<details>
<summary>LMES.FN_GET_CHILD_ORG_LIST 원본</summary>

```sql
CREATE OR REPLACE FUNCTION LMES.FN_GET_CHILD_ORG_LIST
(
    V_P_ORG_TYPE        IN VARCHAR2
   ,V_P_ORG_CD          IN VARCHAR2
   ,V_P_SUB_ORG_TYPE    IN VARCHAR2
)
RETURN CHILD_ORG_TBL PIPELINED
AS
   V_STR_ORG_CD     VARCHAR2(20);
BEGIN
    FOR CHILD_ORG IN (SELECT A.SUB_ORG_TYPE AS ORG_TYPE, A.SUB_ORG_CD AS ORG_CD, B.ORG_NAME
                        FROM MSBS_ORGANIZATION_SUB A
                       INNER JOIN MSBS_ORGANIZATION B ON A.SUB_ORG_TYPE     = B.ORG_TYPE
                                                     AND A.SUB_ORG_CD       = B.ORG_CD
                       WHERE A.ORG_TYPE         = V_P_ORG_TYPE
                         AND A.ORG_CD           = V_P_ORG_CD
                         AND A.SUB_ORG_TYPE     = NVL(V_P_SUB_ORG_TYPE, A.SUB_ORG_TYPE))
    LOOP
        PIPE ROW (CHILD_ORG_ROW(CHILD_ORG.ORG_TYPE, CHILD_ORG.ORG_CD, CHILD_ORG.ORG_NAME));
    END LOOP;

    RETURN;
END FN_GET_CHILD_ORG_LIST;
/
```

</details>

---

## `VW_MSBS_CODE_MASTER`

**종류**: View (PLANT 별 + COMMON 통합)
**스키마**: LMES (현재 OCI 에 미적용. 원본 테이블 `MSBS_CODE_MASTER` 는 OCI 에 적용됨)
**키 컬럼**: `(PLANT_CD, CODE_CLASS_CD, SUB_CODE)`
**주요 컬럼**:
- `CODE_NAME` — 코드의 표시 이름 (기본)
- `CODE_NAME2` — `SUB_CODE + ' - ' + CODE_NAME` 결합 형태
- `CODE_SHORT_NAME`, `CODE_INITIAL`, `COLOR_RGB`
- `EXTRA_COLUMN1~5`, `SORT_SEQ`, `USE_YN`

**역할**: 분석 결과의 코드값 (`OSND_TYPE`, `OP_CD`, `PROD_MOVE_TYPE` 등) 을 사람 가독 이름으로 변환. 뷰는 PLANT 별 코드 + COMMON 코드 (모든 Plant 공통) 를 한 결과로 합쳐 보여줌.

### 호출 방식 (OCI 적용 시)

```sql
SELECT EX.OSND_TYPE,
       CM.CODE_NAME AS TYPE_NAME,
       SUM(EX.OSND_QTY) AS QTY
  FROM OCI.MSPQ_EX_OSND EX
  LEFT JOIN OCI.VW_MSBS_CODE_MASTER CM
    ON CM.CODE_CLASS_CD = 'PQ_OSND_TYPE'
   AND CM.SUB_CODE      = EX.OSND_TYPE
   AND CM.USE_YN        = 'Y'
 WHERE EX.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND EX.CANCEL_YN = 'N'
 GROUP BY EX.OSND_TYPE, CM.CODE_NAME;
```

### 인라인 풀이 (현재 권장)

뷰 본문은 `MSBS_CODE_CLASS` + `MSBS_CODE_MASTER` 의 UNION ALL 두 갈래. lookup 용도라면 보통 한 갈래만으로 충분:

```sql
-- 가장 흔한 경우: 특정 CODE_CLASS_CD 의 코드 → 이름 변환
-- (PLANT_CD 미지정. COMMON 코드는 PLANT_CD='-' 인 행이 매칭)
SELECT EX.OSND_TYPE,
       CM.CODE_NAME AS TYPE_NAME,
       SUM(EX.OSND_QTY) AS QTY
  FROM OCI.MSPQ_EX_OSND EX
  LEFT JOIN OCI.MSBS_CODE_MASTER CM
    ON CM.CODE_CLASS_CD = 'PQ_OSND_TYPE'
   AND CM.SUB_CODE      = EX.OSND_TYPE
   AND CM.USE_YN        = 'Y'
 WHERE EX.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND EX.CANCEL_YN = 'N'
 GROUP BY EX.OSND_TYPE, CM.CODE_NAME;
```

PLANT 별 코드와 COMMON 코드를 둘 다 살펴야 하면 (= 진짜 뷰 본문 재현):

```sql
WITH CODE_LOOKUP AS (
  -- PLANT 별 코드
  SELECT CM.PLANT_CD, CM.CODE_CLASS_CD, CM.SUB_CODE,
         CM.CODE_NAME,
         CM.SUB_CODE || ' - ' || CM.CODE_NAME AS CODE_NAME2,
         CM.USE_YN
    FROM OCI.MSBS_CODE_CLASS CC
    INNER JOIN OCI.MSBS_CODE_MASTER CM
      ON CC.CODE_CLASS_CD = CM.CODE_CLASS_CD
   WHERE CC.CODE_MANAGE_TYPE = 'PLANT'
  UNION ALL
  -- COMMON 코드를 각 Plant 에 fan-out
  SELECT PL.PLANT_CD, CM.CODE_CLASS_CD, CM.SUB_CODE,
         CM.CODE_NAME,
         CM.SUB_CODE || ' - ' || CM.CODE_NAME AS CODE_NAME2,
         CM.USE_YN
    FROM OCI.MSBS_CODE_CLASS CC
    INNER JOIN OCI.MSBS_CODE_MASTER CM
      ON CC.CODE_CLASS_CD = CM.CODE_CLASS_CD
    CROSS JOIN OCI.MSBS_PLANT PL
   WHERE CC.CODE_MANAGE_TYPE = 'COMMON'
     AND CM.PLANT_CD = '-'
)
SELECT ...
  FROM CODE_LOOKUP CM
 WHERE CM.CODE_CLASS_CD = 'PQ_OSND_TYPE'
   AND CM.USE_YN = 'Y'
   ...
```

자주 쓰는 CODE_CLASS_CD:
- `PQ_OSND_TYPE` — OS&D 타입 (D=Damage / L=Lost / I=Issue / S=Shortage)
- `PQ_EX_ITEM_CLASS` — External Item Class
- 그 외 탐색: `SELECT DISTINCT CODE_CLASS_CD FROM OCI.MSBS_CODE_MASTER WHERE USE_YN='Y'`

주의:
- **뷰 컬럼명은 `CODE_NAME` 이다. `SUB_CODE_NAME` 이라는 컬럼은 없음** — `functions/quality-osnd.md` 의 `fn_osnd_by_type` 에 과거 오타 있었음 (현재 수정 완료).
- 대부분 lookup 은 한 갈래(PLANT 또는 COMMON)로 충분 — UNION ALL 풀이 본문은 PLANT 별 + COMMON 동시 조회가 진짜 필요할 때만.
- `MSBS_CODE_CLASS` 가 OCI 에 있는지 별도 확인 필요 (없으면 그냥 `MSBS_CODE_MASTER` 직접 lookup 으로 단순화 가능).

### 원본 DDL

<details>
<summary>LMES.VW_MSBS_CODE_MASTER 원본</summary>

```sql
CREATE OR REPLACE FORCE VIEW LMES.VW_MSBS_CODE_MASTER
(PLANT_CD, CODE_CLASS_CD, SUB_CODE, CODE_NAME, CODE_NAME2,
 CODE_SHORT_NAME, CODE_INITIAL, SYSTEM_YN, COLOR_RGB, EXTRA_COLUMN1,
 EXTRA_COLUMN2, EXTRA_COLUMN3, EXTRA_COLUMN4, EXTRA_COLUMN5, MEMO,
 SORT_SEQ, USE_YN, CREATION_OWNER)
AS
SELECT CM.PLANT_CD
      ,CM.CODE_CLASS_CD
      ,CM.SUB_CODE
      ,CM.CODE_NAME
      ,CM.SUB_CODE || ' - ' || CM.CODE_NAME     AS CODE_NAME2
      ,CM.CODE_SHORT_NAME
      ,CM.CODE_INITIAL
      ,CM.SYSTEM_YN
      ,CM.COLOR_RGB
      ,CM.EXTRA_COLUMN1
      ,CM.EXTRA_COLUMN2
      ,CM.EXTRA_COLUMN3
      ,CM.EXTRA_COLUMN4
      ,CM.EXTRA_COLUMN5
      ,CM.MEMO
      ,CM.SORT_SEQ
      ,CM.USE_YN
      ,CM.CREATION_OWNER
  FROM MSBS_CODE_CLASS CC
 INNER JOIN MSBS_CODE_MASTER CM ON CC.CODE_CLASS_CD = CM.CODE_CLASS_CD
 WHERE CC.CODE_MANAGE_TYPE = 'PLANT'
UNION ALL
SELECT PL.PLANT_CD
      ,CM.CODE_CLASS_CD
      ,CM.SUB_CODE
      ,CM.CODE_NAME
      ,CM.SUB_CODE || ' - ' || CM.CODE_NAME     AS CODE_NAME2
      ,CM.CODE_SHORT_NAME
      ,CM.CODE_INITIAL
      ,CM.SYSTEM_YN
      ,CM.COLOR_RGB
      ,CM.EXTRA_COLUMN1
      ,CM.EXTRA_COLUMN2
      ,CM.EXTRA_COLUMN3
      ,CM.EXTRA_COLUMN4
      ,CM.EXTRA_COLUMN5
      ,CM.MEMO
      ,CM.SORT_SEQ
      ,CM.USE_YN
      ,CM.CREATION_OWNER
  FROM MSBS_CODE_CLASS CC
 INNER JOIN MSBS_CODE_MASTER CM ON CC.CODE_CLASS_CD = CM.CODE_CLASS_CD
      ,MSBS_PLANT PL
 WHERE CC.CODE_MANAGE_TYPE = 'COMMON'
   AND CM.PLANT_CD = '-';
```

</details>
