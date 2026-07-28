# Workforce (인사 발령 + 근태) — Analysis Workflow

워크포스 도메인 처리 절차. **인사(HR Action)** 와 **근태(Time & Labor)** 를 하나로 묶는다. 두 영역은 EMPID(같은 사람)로 연결되며, 공통코드/직무/부서 디코드(번역표)를 공유한다.

| 항목 | 값 |
|---|---|
| 영역 | 인사 발령(HR Action) · 근태(Time & Labor) |
| 메인 테이블 | 인사 `OCI.PW_HR_ACTION_T` / 근태 `OCI.PW_TL_DAILY_T` |
| 디코드/마스터 | `PW_ZZ_CODE_T`(공통코드) · `PW_HA_JOBCD_T`(직무) · `PW_HA_DEPT_T`(부서) · `semantic_models/ref/job_class_hierarchy.csv`(직무 계층·KPI·OH) |
| 1층 모델 | `semantic_models/PW_HR_ACTION_T.yml`, `PW_ZZ_CODE_T.yml`, `PW_HA_JOBCD_T.yml`, `PW_HA_DEPT_T.yml`, `PW_TL_DAILY_T.yml` |
| SQL 골격 | `functions/workforce.md` |

**공통 원칙은 `workflows/_common.md` 참조**(특히 §0 연결, §11 공통코드 디코드 규칙).

> **범위 제한**: 이 도메인은 위 5개 테이블 + CSV 안에서만 분석한다. 임의 테이블로 자유 분석하지 않는다(SKILL.md §4 원칙 동일). 근태 세부 규칙(출근율 분모/결근 정의/지각·조퇴)은 SKILL.md §4-1 과 `PW_TL_DAILY_T.yml` 의 [확정] 규칙을 그대로 따른다.

---

## 1. 이 도메인이 가진 분석 능력

### 1-A. 인사 발령 (PW_HR_ACTION_T)

| 분석 능력 | 무엇을 보나 | 함수 |
|---|---|---|
| A. 발령유형별 건수 | HIR/XFR/JOC/PLA 등 유형별 건수·인원 | `fn_action_by_type` |
| B. 입사 추이 | HIR(±REH) 월/일별 추이 | `fn_hire_trend` |
| C. 부서/직무/직급/PPH 인원 | 현재상태 기준 headcount | `fn_headcount_by_dim` |
| D. 현재상태 스냅샷 | 사원별 최신 발령 1행 | `fn_current_state` |
| E. 발령 상세(디코드) | 한 사원의 발령 이력을 이름으로 | `fn_action_decoded_detail` |
| F. 직무 계층/KPI 보강 | 패밀리/펑션·사무직vs생산직·OH 유형 (CSV) | `fn_jobcd_hierarchy` |

### 1-B. 근태 (PW_TL_DAILY_T)

SKILL.md §4-1 의 능력 전체(상태별 인원, **출근율·결근율**, **지각·조퇴**, 부서/직무/PPH/시프트별 분해, 사원 랭킹·누적). 근태는 이름 컬럼(JOB_POSITION_NM/JOBCD_NM/DEPT_FNM)을 이미 보유하므로 디코드 불필요.

### 1-C. 인사 × 근태 결합

| 분석 능력 | 무엇을 보나 | 함수 |
|---|---|---|
| G. 인사기준 근태 | 인사상 직무/부서/PPH 로 근태(출근율) 묶기, CSV 계층 보강 | `fn_hr_tl_bridge` |

---

## 2. 처리 절차

```
1) 영역 식별   → 인사(발령/입사/이동/직무/직급/headcount) vs 근태(출결/출근율/지각) vs 결합
2) 디코드 판단 → 인사면 코드형 컬럼 디코드 필요(_common.md §11). 근태는 디코드 불필요.
3) 기간/필터   → 인사 EFFDT, 근태 TL_DATE. 누락 시 되묻기.
4) SQL 조립   → functions/workforce.md 골격 + semantic_models/*.yml 컬럼
5) 검증       → §4 invariants
6) 답변       → 코드가 아닌 '이름'으로. 사실/추정 분리, SQL 포함.
```

---

## 3. 핵심 패턴과 함정

- **이력 vs 현재상태**: PW_HR_ACTION_T 는 발령 '이력'이다. "현재 부서/직급/인원"을 물으면 사원별 최신 발령(`ROW_NUMBER() OVER (PARTITION BY EMPID ORDER BY EFFDT DESC, EFFSEQ DESC)=1`)을 골라야 한다. 단순 COUNT 는 이벤트 수이지 인원이 아니다.
- **건수 vs 인원**: '발령 몇 건' = `COUNT(*)`, '몇 명' = `COUNT(DISTINCT EMPID)`. 혼동 금지.
- **코드는 반드시 이름으로**: 답변 표에 XFR/250/16 같은 원본 코드를 그대로 내지 않는다. `_common.md §11` 디코드 적용. 단 'PAY'/'ADL'(ACTION_TYPE)은 디코드 미확정 → 원본 노출하고 [미확정] 표기.
- **JOB_POSITION 은 'JOB_POSITION' 클래스**(47개)로 푼다. 'POSITION'(12개) 아님.
- **직무 마스터 중복**: PW_HA_JOBCD_T 는 `DISTINCT + EFF_STATUS='A'` 로 dedup(없으면 행 2배).
- **부서 매칭 한계**: 인사 부서코드 394종 중 86종만 부서 마스터에 매칭 → 부서명은 LEFT JOIN, 미매칭은 코드 노출 또는 '(구/미등록 부서)'.
- **공통코드 중복**: PW_ZZ_CODE_T 는 (CLASS, CODE_ID) 가 DATASET/EFFDT 로 중복될 수 있어 `GROUP BY ... MAX(CODE_NM)` 로 dedup.
- **근태 규칙 준수**: 근태는 `TL_DATE <= TRUNC(SYSDATE)`, 결근 = `WORK_STATUS='AB' OR CHAR10_02='016'`, 율 분모는 출근+결근(휴가 VC 제외). SKILL.md §4-1.
- **COMPANY 는 공장 아님**: 인사·근태 모두 COMPANY='JJ' 는 법인. 공장/조직 식별은 DEPT_FNM.

---

## 4. 검증 (invariants)

- 발령유형 합 = 전체 행수. [확정: 전체 19,517 = XFR 12,483 + JOC 4,500 + HIR 2,516 + PAY 15 + ADL 3]
- 현재상태 추출 시 사원 1명당 정확히 1행(rn=1) — `COUNT(*) = COUNT(DISTINCT EMPID)` 인지 확인.
- 디코드 후 행수가 디코드 전과 같아야 함(중복 마스터로 부풀지 않았는지). 늘었다면 dedup 누락.
- 인사↔근태 결합 시 조인 손실 점검: 인사 2,519 ∩ 근태 2,542 = 2,515 공유. 결합 결과 EMPID 수가 2,515 를 크게 벗어나면 조인 키 확인.
- 율 KPI 는 분모 정의(출근+결근, 휴가 제외)를 답변에 식으로 명시.

---

## 5. 답변 형식

SKILL.md §8 형식(요약·표·SQL·사용 테이블·검증·한계)을 따른다. 추가로:
- 표는 **코드가 아닌 이름**으로(예 직급=T/M, 사원유형=Production).
- 디코드 미확정 값('PAY'/'ADL', GRADE 코드 등)은 [미확정] 표기하고 단정하지 않음.
- 사용한 마스터/디코드 클래스 명시(예: "JOB_POSITION 클래스 + PW_HA_JOBCD_T 디코드, 부서는 PW_HA_DEPT_T LEFT JOIN").
- 연결 경로(로컬 SQLcl `changshinincaipoc` / fallback) 한 줄(_common.md §0-3).
