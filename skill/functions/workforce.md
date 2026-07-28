# Functions — Workforce (인사 발령 + 근태)

워크포스 도메인 SQL 골격 모음. 인사(HR Action)와 근태(Time & Labor)를 한 도메인으로 묶고, 공통코드/직무/부서 디코드(번역표)를 공유한다.

| 영역 | 메인 테이블 | 디코드/마스터 |
|---|---|---|
| 인사 발령 | `OCI.PW_HR_ACTION_T` | `PW_ZZ_CODE_T`(공통코드) · `PW_HA_JOBCD_T`(직무) · `PW_HA_DEPT_T`(부서) · `ref/job_class_hierarchy.csv`(직무 계층/KPI) |
| 사원 마스터 | `OCI.PW_HR_EMPLOYEES` | 자체 `_NM` 컬럼(DEPT_FNM/JOBCD_NM/JOB_POSITION_NM/GRADE_NM 등 이미 디코드됨) — 현재 재직 로스터 1행/사원 |
| 근태 | `OCI.PW_TL_DAILY_T` | 자체 컬럼(JOB_POSITION_NM/JOBCD_NM/DEPT_FNM 이미 디코드됨) |

> ⚠️ **뷰(_V)는 우리 OCI 에 없다.** 정의서의 `PW_HR_EMPLOYEES_V`/`PW_TL_DAILY_V` 는 DB 객체로 존재하지 않으므로(전수 확인), 쿼리는 반드시 **베이스 테이블**(`PW_HR_EMPLOYEES`, `PW_TL_DAILY_T`)로 한다. 컬럼 정의(의미)는 뷰 정의서 그대로 유효하고 베이스에도 `_NM` 컬럼이 있어 결과는 동일하다. 상대방이 준 SQL 에 `..._V` 가 보이면 베이스 테이블로 바꿔 실행할 것.
> ⚠️ **사원 마스터 PII 주의.** `PW_HR_EMPLOYEES` 에는 NID(주민번호)/PASSPORT/ADDRESS/PHONE/EMAIL 등 순수 식별자와 성별·종교·장애·임신 등 민감 속성이 있다. `SELECT *` 금지, 명시 컬럼만. 식별자는 출력 금지(참조 전용), 민감 속성은 그룹 집계만. 상세는 `semantic_models/PW_HR_EMPLOYEES.yml` 의 3단계 규칙.

`workflows/workforce.md` 가 절차·함정·검증을 다루고, 이 파일은 **SQL 골격**만 모은다. 공통 원칙·디코드 규칙은 `workflows/_common.md`(특히 §0 연결, §11 디코드).

> ⚠️ **근태(PW_TL_DAILY_T)는 이미 이름 컬럼을 보유**(JOB_POSITION_NM/JOBCD_NM/DEPT_FNM)하므로 디코드 조인이 필요 없다. 디코드는 주로 **인사(PW_HR_ACTION_T)** 의 코드형 컬럼에 적용한다.

**바인드 변수 규약**:

| 변수 | 의미 | 비고 |
|---|---|---|
| `:V_EFF_F`, `:V_EFF_T` | EFFDT 범위 (DATE) | 인사 발령 기간 |
| `:V_TL_F`, `:V_TL_T` | TL_DATE 범위 (DATE) | 근태 기간 |
| `:V_ACTION_TYPE` | 발령유형 (HIR/XFR/JOC/PLA...) | NULL 가능 |
| `:V_DEPT` | 부서코드 | NULL 가능 |
| `:V_EMPID` | 사번 | NULL 가능 |

**공통 룰**:
- 인사 grain = (EMPID, EFFDT, EFFSEQ) = 발령 1건. '인원수'는 `COUNT(DISTINCT EMPID)`, '발령건수'는 `COUNT(*)`.
- ACTION_TYPE 의 'PAY'/'ADL' 은 디코드 미확정 → 라벨 보류(원본 코드 노출).
- 디코드는 `PW_ZZ_CODE_T` 에서 `SERVICE_ID='JJ'` + `CODE_CLASS_ID` 지정. 중복행은 `MAX(CODE_NM)` 집계로 dedup.
- 직무 디코드 `PW_HA_JOBCD_T` 는 `EFF_STATUS='A'` + `DISTINCT` 로 중복 제거.
- 부서 디코드 `PW_HA_DEPT_T` 는 **LEFT JOIN**(인사 부서코드 일부만 매칭).
- 미래/예정 제외 등 근태 규칙은 `semantic_models/PW_TL_DAILY_T.yml` 와 SKILL.md §4-1 준수(`TL_DATE <= TRUNC(SYSDATE)`, 결근 = `WORK_STATUS='AB' OR CHAR10_02='016'`).

---

## 목차

| 함수 | 용도 | workflow 매핑 |
|---|---|---|
| [`cte_code_decode`](#cte_code_decode) | 공통코드 디코드 CTE (박제 + 라이브) | §디코드 |
| [`fn_decode_action_type`](#fn_decode_action_type) | ACTION_TYPE 한 컬럼 디코드 | §디코드 |
| [`fn_action_by_type`](#fn_action_by_type) | 발령유형별 건수 | §A |
| [`fn_hire_trend`](#fn_hire_trend) | 입사(HIR) 추이 (월/일별) | §B |
| [`fn_headcount_by_dim`](#fn_headcount_by_dim) | 부서/직무/직급/PPH 별 인원 | §C |
| [`fn_current_state`](#fn_current_state) | 사원별 현재상태(최신 발령) 스냅샷 | §D |
| [`fn_action_decoded_detail`](#fn_action_decoded_detail) | 발령 상세 + 전체 디코드(코드→이름) | §E |
| [`fn_jobcd_hierarchy`](#fn_jobcd_hierarchy) | 직무 계층/KPI 보강(CSV) 조인 | §F |
| [`fn_hr_tl_bridge`](#fn_hr_tl_bridge) | 인사↔근태 결합 (직무/PPH 보강 후 출근율) | §G |
| [`fn_current_dept_name`](#fn_current_dept_name) | 사원의 현재 부서명 조회(사원 마스터 기준, LEFT JOIN 교정) | §H |

---

## cte_code_decode

공통코드 디코드의 두 가지 방식. 답변 표를 코드가 아닌 이름으로 내기 위한 핵심 재료다.

### (1) 라이브 조인 — PW_ZZ_CODE_T (중복 dedup 포함)

```sql
-- 클래스별 dedup 된 디코드 뷰. 필요한 클래스만 골라 LEFT JOIN.
WITH CODE AS (
  SELECT CODE_CLASS_ID, CODE_ID, MAX(CODE_NM) AS CODE_NM
  FROM   OCI.PW_ZZ_CODE_T
  WHERE  SERVICE_ID = 'JJ'
    AND  CODE_CLASS_ID IN ('JOB_TITLE','JOB_POSITION','EMP_TYPE','HIRE_TYPE','PERS_TYPE',
                           'HIRE_ACTN_MODE','MUTS_ACTN_TYPE','ABS_CLASS','PROBATION_POSITION')
  GROUP  BY CODE_CLASS_ID, CODE_ID          -- DATASET/EFFDT 중복 제거
)
SELECT ... 
FROM   OCI.PW_HR_ACTION_T H
LEFT JOIN CODE JT  ON JT.CODE_CLASS_ID='JOB_TITLE'    AND JT.CODE_ID = H.JOB_TITLE
LEFT JOIN CODE JP  ON JP.CODE_CLASS_ID='JOB_POSITION' AND JP.CODE_ID = H.JOB_POSITION
LEFT JOIN CODE ET  ON ET.CODE_CLASS_ID='EMP_TYPE'     AND ET.CODE_ID = H.EMP_TYPE
LEFT JOIN CODE HT  ON HT.CODE_CLASS_ID='HIRE_TYPE'    AND HT.CODE_ID = H.HIRE_TYPE
-- JT.CODE_NM = 직책명, JP.CODE_NM = 직급명, ET.CODE_NM = 사원유형명 ...
```

### (2) 박제 CTE — DB 재조회 없이 (검증된 값, 2026-06-23)

소규모 코드라 하드코딩으로 박아두면 조회 1회로 끝난다. [확정: DB 검증]

```sql
WITH ACTION_MAP AS (   -- ACTION_TYPE (4개 클래스 합집합)
  SELECT 'HIR' C, 'New Hire' N FROM DUAL UNION ALL
  SELECT 'REH','Rehire'            FROM DUAL UNION ALL
  SELECT 'TRN','Transfers-in btw company' FROM DUAL UNION ALL
  SELECT 'JOC','Personnel Changes' FROM DUAL UNION ALL
  SELECT 'XFR','Transfer'          FROM DUAL UNION ALL
  SELECT 'PLA','Leave of Absence'  FROM DUAL UNION ALL
  SELECT 'POS','Probation Position Divition' FROM DUAL
  -- 미확정: 'PAY','ADL' 은 라벨 없음(원본 코드 노출)
),
EMPTYPE_MAP AS (
  SELECT '10' C,'Executives' N FROM DUAL UNION ALL
  SELECT '14','Office worker'  FROM DUAL UNION ALL
  SELECT '16','Production'     FROM DUAL UNION ALL
  SELECT '17','Special service' FROM DUAL
),
HIRETYPE_MAP AS (
  SELECT '14' C,'Permanent' N FROM DUAL UNION ALL
  SELECT '15','Contract'      FROM DUAL UNION ALL
  SELECT '18','Entrustment'   FROM DUAL UNION ALL
  SELECT '24','Temporary'     FROM DUAL UNION ALL
  SELECT '25','Dispatched'    FROM DUAL
),
POS_MAP AS (        -- JOB_POSITION (주요값 발췌; 전체는 라이브 조인 권장)
  SELECT '250' C,'T/M' N FROM DUAL UNION ALL
  SELECT '248','T/L'   FROM DUAL UNION ALL
  SELECT '246','G/L'   FROM DUAL UNION ALL
  SELECT '230','Staff' FROM DUAL UNION ALL
  SELECT '200','Assistant Manager' FROM DUAL UNION ALL
  SELECT '190','Manager' FROM DUAL UNION ALL
  SELECT '160','Director' FROM DUAL
)
-- ... LEFT JOIN ACTION_MAP A ON A.C = H.ACTION_TYPE  →  NVL(A.N, H.ACTION_TYPE)
```

> 직책(JOB_TITLE 32개)·직급(JOB_POSITION 47개)처럼 코드가 많으면 박제보다 **라이브 조인(1)** 이 안전하다. 박제는 ACTION_TYPE/EMP_TYPE/HIRE_TYPE 같이 적은 클래스에 쓴다.

---

## fn_decode_action_type

ACTION_TYPE 한 컬럼만 이름으로.

```sql
SELECT H.ACTION_TYPE,
       NVL(C.CODE_NM, H.ACTION_TYPE) AS ACTION_TYPE_NM,
       COUNT(*) AS CNT
FROM   OCI.PW_HR_ACTION_T H
LEFT JOIN (
  SELECT CODE_ID, MAX(CODE_NM) CODE_NM
  FROM   OCI.PW_ZZ_CODE_T
  WHERE  SERVICE_ID='JJ'
    AND  CODE_CLASS_ID IN ('HIRE_ACTN_MODE','MUTS_ACTN_TYPE','ABS_CLASS','PROBATION_POSITION')
  GROUP  BY CODE_ID
) C ON C.CODE_ID = H.ACTION_TYPE
GROUP BY H.ACTION_TYPE, NVL(C.CODE_NM, H.ACTION_TYPE)
ORDER BY CNT DESC;
-- 결과 예: Transfer 12483 / Personnel Changes 4500 / New Hire 2516 / PAY 15 / ADL 3
```

---

## fn_action_by_type

기간 내 발령유형별 건수 + 인원수.

```sql
SELECT NVL(C.CODE_NM, H.ACTION_TYPE) AS ACTION_TYPE_NM,
       COUNT(*)                AS ACTION_CNT,
       COUNT(DISTINCT H.EMPID) AS EMP_CNT
FROM   OCI.PW_HR_ACTION_T H
LEFT JOIN (
  SELECT CODE_ID, MAX(CODE_NM) CODE_NM FROM OCI.PW_ZZ_CODE_T
  WHERE SERVICE_ID='JJ'
    AND CODE_CLASS_ID IN ('HIRE_ACTN_MODE','MUTS_ACTN_TYPE','ABS_CLASS','PROBATION_POSITION')
  GROUP BY CODE_ID
) C ON C.CODE_ID = H.ACTION_TYPE
WHERE H.EFFDT BETWEEN :V_EFF_F AND :V_EFF_T
GROUP BY NVL(C.CODE_NM, H.ACTION_TYPE)
ORDER BY ACTION_CNT DESC;
```

---

## fn_hire_trend

입사(HIR) 추이 — 월별/일별.

```sql
SELECT TO_CHAR(EFFDT,'YYYY-MM')      AS YM,
       COUNT(*)                      AS HIRE_CNT,
       COUNT(DISTINCT EMPID)         AS HIRE_EMP
FROM   OCI.PW_HR_ACTION_T
WHERE  ACTION_TYPE IN ('HIR')        -- 재입사 포함 시 ('HIR','REH')
  AND  EFFDT BETWEEN :V_EFF_F AND :V_EFF_T
GROUP  BY TO_CHAR(EFFDT,'YYYY-MM')
ORDER  BY YM;
```

---

## fn_headcount_by_dim

부서/직무/직급/PPH 별 인원(현재상태 기준 권장 → fn_current_state 와 결합). 단순 발령행 기준이면 아래.

```sql
WITH CUR AS (   -- 사원별 최신 발령 1행
  SELECT H.*,
         ROW_NUMBER() OVER (PARTITION BY EMPID ORDER BY EFFDT DESC, EFFSEQ DESC) rn
  FROM   OCI.PW_HR_ACTION_T H
  WHERE  EFFDT <= :V_EFF_T
)
SELECT NVL(D.DEPT_FNM, C.DEPT)        AS DEPT_NM,
       NVL(JP.CODE_NM, C.JOB_POSITION) AS POSITION_NM,
       C.PPH_FLAG,
       COUNT(*) AS HEADCOUNT
FROM   CUR C
LEFT JOIN OCI.PW_HA_DEPT_T D ON D.DEPT = C.DEPT
LEFT JOIN ( SELECT CODE_ID, MAX(CODE_NM) CODE_NM FROM OCI.PW_ZZ_CODE_T
            WHERE SERVICE_ID='JJ' AND CODE_CLASS_ID='JOB_POSITION' GROUP BY CODE_ID
          ) JP ON JP.CODE_ID = C.JOB_POSITION
WHERE  C.rn = 1
  AND  C.EMP_STATUS = 'A'
GROUP  BY NVL(D.DEPT_FNM, C.DEPT), NVL(JP.CODE_NM, C.JOB_POSITION), C.PPH_FLAG
ORDER  BY HEADCOUNT DESC;
```

---

## fn_current_state

사원별 현재 상태 = 최신 발령행. 이력 테이블에서 '현재 인원/배치'를 뽑는 표준 패턴.

```sql
SELECT *
FROM (
  SELECT H.*,
         ROW_NUMBER() OVER (PARTITION BY EMPID ORDER BY EFFDT DESC, EFFSEQ DESC) rn
  FROM   OCI.PW_HR_ACTION_T H
  WHERE  EFFDT <= TRUNC(SYSDATE)
)
WHERE rn = 1 AND EMP_STATUS = 'A';
```

---

## fn_action_decoded_detail

발령 상세를 전체 디코드(코드→이름)해 사람이 읽게.

```sql
WITH CODE AS (
  SELECT CODE_CLASS_ID, CODE_ID, MAX(CODE_NM) CODE_NM
  FROM   OCI.PW_ZZ_CODE_T
  WHERE  SERVICE_ID='JJ'
    AND  CODE_CLASS_ID IN ('JOB_TITLE','JOB_POSITION','EMP_TYPE','HIRE_TYPE','PERS_TYPE',
                           'HIRE_ACTN_MODE','MUTS_ACTN_TYPE','ABS_CLASS','PROBATION_POSITION')
  GROUP  BY CODE_CLASS_ID, CODE_ID
),
JOBM AS (
  SELECT DISTINCT JOBCD, JOBCD_NM FROM OCI.PW_HA_JOBCD_T WHERE EFF_STATUS='A'
)
SELECT H.EMPID, H.EFFDT,
       NVL(AC.CODE_NM, H.ACTION_TYPE)  AS ACTION_TYPE_NM,
       NVL(D.DEPT_FNM, H.DEPT)         AS DEPT_NM,
       NVL(JT.CODE_NM, H.JOB_TITLE)    AS JOB_TITLE_NM,
       NVL(JP.CODE_NM, H.JOB_POSITION) AS JOB_POSITION_NM,
       NVL(JM.JOBCD_NM, H.JOBCD)       AS JOBCD_NM,
       NVL(ET.CODE_NM, H.EMP_TYPE)     AS EMP_TYPE_NM,
       NVL(HT.CODE_NM, H.HIRE_TYPE)    AS HIRE_TYPE_NM,
       H.PPH_FLAG
FROM   OCI.PW_HR_ACTION_T H
LEFT JOIN CODE AC ON AC.CODE_CLASS_ID IN ('HIRE_ACTN_MODE','MUTS_ACTN_TYPE','ABS_CLASS','PROBATION_POSITION') AND AC.CODE_ID=H.ACTION_TYPE
LEFT JOIN CODE JT ON JT.CODE_CLASS_ID='JOB_TITLE'    AND JT.CODE_ID=H.JOB_TITLE
LEFT JOIN CODE JP ON JP.CODE_CLASS_ID='JOB_POSITION' AND JP.CODE_ID=H.JOB_POSITION
LEFT JOIN CODE ET ON ET.CODE_CLASS_ID='EMP_TYPE'     AND ET.CODE_ID=H.EMP_TYPE
LEFT JOIN CODE HT ON HT.CODE_CLASS_ID='HIRE_TYPE'    AND HT.CODE_ID=H.HIRE_TYPE
LEFT JOIN JOBM JM ON JM.JOBCD = H.JOBCD
LEFT JOIN OCI.PW_HA_DEPT_T D ON D.DEPT = H.DEPT
WHERE  H.EMPID = :V_EMPID
ORDER  BY H.EFFDT, H.EFFSEQ;
-- ⚠️ AC 조인은 4개 클래스에 같은 CODE_ID 가 겹치면 행이 늘 수 있다. 안전하게는 fn_decode_action_type 처럼 ACTION 전용 서브쿼리(GROUP BY CODE_ID)로 분리.
```

---

## fn_jobcd_hierarchy

직무 코드에 엑셀 계층/KPI 보강(CSV) 조인. CSV(`ref/job_class_hierarchy.csv`)를 외부 테이블/스테이징으로 적재했다고 가정하고 `JOB_HIER` 로 칭한다. (적재 전이면 CSV 를 사람이 참조하거나 별도 로드)

```sql
-- JOB_HIER(JOBCD, JOBCD_NM, JOBCLS, JOBCD_LVL, PPH_FLAG,
--          J_FAMILY_CD, J_FAMILY_NM, J_FUNCTION_CD, J_FUNCTION_NM, J_JOB_NAME, EMP_CLS_KPI, OH_TYPE)
SELECT JH.J_FAMILY_NM,
       JH.J_FUNCTION_NM,
       JH.J_JOB_NAME,
       JH.EMP_CLS_KPI,                 -- Office Worker / Production Worker
       JH.OH_TYPE,                     -- SOH / SG&A / OH Indirect / -
       COUNT(DISTINCT C.EMPID) AS HEADCOUNT
FROM (
  SELECT EMPID, JOBCD,
         ROW_NUMBER() OVER (PARTITION BY EMPID ORDER BY EFFDT DESC, EFFSEQ DESC) rn
  FROM OCI.PW_HR_ACTION_T WHERE EFFDT <= TRUNC(SYSDATE)
) C
LEFT JOIN JOB_HIER JH ON JH.JOBCD = C.JOBCD
WHERE C.rn = 1
GROUP BY JH.J_FAMILY_NM, JH.J_FUNCTION_NM, JH.J_JOB_NAME, JH.EMP_CLS_KPI, JH.OH_TYPE
ORDER BY HEADCOUNT DESC;
-- CSV 미적재 환경: PW_HA_JOBCD_T 로 직무명까지는 즉시 디코드 가능(JOBCD→JOBCD_NM). 패밀리/KPI/OH 보강만 CSV 필요.
```

---

## fn_hr_tl_bridge

인사↔근태 결합 — 인사에서 직무/PPH/부서를 가져와 근태(출근율)와 합친다. [확정: EMPID 2,515명 공유]

```sql
WITH CUR AS (   -- 사원 현재 직무/PPH (인사)
  SELECT EMPID, JOBCD, PPH_FLAG, JOB_POSITION,
         ROW_NUMBER() OVER (PARTITION BY EMPID ORDER BY EFFDT DESC, EFFSEQ DESC) rn
  FROM   OCI.PW_HR_ACTION_T WHERE EFFDT <= TRUNC(SYSDATE)
),
TL AS (         -- 근태 집계 (출근/근무대상)
  SELECT EMPID,
         COUNT(CASE WHEN WORK_STATUS='AT' AND (CHAR10_02<>'016' OR CHAR10_02 IS NULL) THEN 1 END) present_cnt,
         COUNT(CASE WHEN WORK_STATUS IN ('AT','AB') OR CHAR10_02='016' THEN 1 END)               target_cnt
  FROM   OCI.PW_TL_DAILY_T
  WHERE  TL_DATE BETWEEN :V_TL_F AND :V_TL_T
    AND  TL_DATE <= TRUNC(SYSDATE)
  GROUP  BY EMPID
)
SELECT C.PPH_FLAG,
       SUM(TL.present_cnt) present_cnt,
       SUM(TL.target_cnt) target_cnt,
       ROUND(SUM(TL.present_cnt)/NULLIF(SUM(TL.target_cnt),0)*100, 1) AS attendance_rate_pct
FROM   CUR C
JOIN   TL ON TL.EMPID = C.EMPID
WHERE  C.rn = 1
GROUP  BY C.PPH_FLAG
ORDER  BY target_cnt DESC;
-- 주의: 근태 자체에도 PPH_FLAG/JOBCD_NM/DEPT_FNM 이 이미 있으므로, 단순 'PPH별 출근율'은 PW_TL_DAILY_T 단독으로도 가능.
--       인사 결합은 '인사상 직무/부서 기준'으로 근태를 보고 싶을 때(예: 직무 패밀리별 출근율 + CSV 보강) 의미가 있다.
```

> 출근율 분모/결근 정의는 SKILL.md §4-1 및 `semantic_models/PW_TL_DAILY_T.yml` 의 [확정] 규칙을 그대로 따른다(근무대상 = 출근 AT + 결근(AB OR CHAR10_02='016'), 휴가 VC 분모 제외, `TL_DATE <= TRUNC(SYSDATE)`).


## fn_current_dept_name

사원의 **현재 부서명**을 뽑는다. 상대방이 준 "가장 최근에 부서명을 가져오는 SQL"을 우리 OCI 환경에 맞게 교정한 표준 레시피.

**교정 포인트 2가지**:
1. `PW_HR_EMPLOYEES_V`(뷰, DB 없음) → 베이스 `OCI.PW_HR_EMPLOYEES` 로 교체.
2. 원본은 `LEFT JOIN` 해놓고 `WHERE` 절에 우측 테이블 조건(`D.EFFDT = (...)`, `B.ACTION_ID = (...)`)을 걸어 **사실상 INNER JOIN** 이 됐다 → 부서 마스터/발령에 미매칭인 사원이 통째로 사라진다(부서 마스터는 91부서만 커버). **우측 조건을 ON 절로 이동**해 LEFT JOIN 을 지킨다.

```sql
-- (A) 가장 단순: 사원 마스터가 DEPT_NM/DEPT_FNM 을 이미 보유 → 조인 불필요.
SELECT E.EMPID, E.NAME, E.DEPT, E.DEPT_NM, E.DEPT_FNM
FROM   OCI.PW_HR_EMPLOYEES E
WHERE  E.SERVICE_ID = 'JJ'
  AND  E.HR_STATUS  = 'A'
  AND  E.EMPID      = :V_EMPID;   -- 전체 대상이면 이 줄 제거
```

```sql
-- (B) 부서 마스터 버전명을 쓰거나 최신 발령 부서를 함께 보고 싶을 때 (LEFT JOIN 교정판).
--     우측 조건을 ON 절로 넣어, 미매칭 사원도 결과에서 사라지지 않게 한다.
SELECT E.EMPID, E.NAME,
       E.DEPT                       AS EMP_DEPT,
       NVL(D.DEPT_NM, E.DEPT_NM)     AS DEPT_NM,     -- 마스터 미매칭이면 사원 마스터 내 이름으로 폴백
       B.DEPT                        AS LAST_ACTION_DEPT
FROM   OCI.PW_HR_EMPLOYEES E
LEFT JOIN OCI.PW_HA_DEPT_T D
       ON  D.SERVICE_ID = E.SERVICE_ID
       AND D.DEPT       = E.DEPT
       AND D.EFFDT      = (SELECT MAX(E2.EFFDT) FROM OCI.PW_HA_DEPT_T E2
                            WHERE E2.SERVICE_ID = D.SERVICE_ID AND E2.DEPT = D.DEPT)
LEFT JOIN OCI.PW_HR_ACTION_T B
       ON  B.SERVICE_ID = E.SERVICE_ID
       AND B.EMPID      = E.EMPID
       AND B.ACTION_ID  = (SELECT MAX(C.ACTION_ID) FROM OCI.PW_HR_ACTION_T C
                            WHERE C.SERVICE_ID = B.SERVICE_ID AND C.EMPID = B.EMPID)
WHERE  E.SERVICE_ID = 'JJ'
  AND  E.HR_STATUS  = 'A'
  AND  E.EMPID      = :V_EMPID;    -- 전체 대상이면 이 줄 제거
```

> [확정: DB 검증] 우리 OCI 의 `PW_HA_DEPT_T` 는 (SERVICE_ID, DEPT)당 **1행**(EFFDT 버전 중복 없음, 91부서)이라 위 `D.EFFDT = MAX(...)` 서브쿼리는 사실상 no-op 다. 원본 시스템처럼 부서 이력이 여러 EFFDT 로 쌓인 환경을 위해 남겨둔 방어 코드이며, 그대로 둬도 무해하다.
>
> **현재 부서의 출처**: (A)/(B) 모두 사원 마스터 `E.DEPT` 가 현재 부서다(발령 이력 `B.DEPT` 가 아님). 발령 최신행은 참고/대사용으로만 노출. 사원 마스터가 이미 '현재 상태'이므로 발령 테이블의 `ROW_NUMBER` 최신행 선택(§D `fn_current_state`)이 필요 없다.
