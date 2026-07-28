---
name: CKP-skills-v12
description: CSI GMES MES 데이터베이스(OCI 스키마)의 5개 핵심 화면 — 생산 실적, 부족분 관리, 수불 관리(P-O/O-I Cross Check), 품질 관리(OS&D Balance + Return Rate) — 와 근태(Time & Labor, CKP)를 분석하는 skill. 트리거 키워드 — "Production Status", "생산 실적", "가동률", "라인별 % 컬럼", "Shortage Balance", "부족분", "남아있는 수량", "P-O Cross Check", "O-I Cross Check", "수불 관리", "출고-입고 정합성", "Out Only", "In Only", "External OS&D", "후보충", "OS&D 발생", "Damage/Lost/Issue/Shortage", "Return Rate", "회수율", "Replenishment Rate", "C.GRADE RETURN", "CKP 리포트", "레포트", "11개 리포트", "리포트 만들어줘", "뽑아줘", "작성해줘", 그리고 근태 — "근태", "출결", "출근율", "결근", "지각", "조퇴", "휴가", "교대/시프트", "사무직/NON_SHIFT", "Direct/Indirect/Overhead", "부서/직무별 근태". 분석은 이 4개 workflow + 워크포스(PW_TL_DAILY_T·PW_HR_ACTION_T·PW_HR_EMPLOYEES) 범위 안에서만 하고, 임의 테이블 자유 분석은 하지 않는다. 매칭 안 되는 질문은 가장 가까운 도메인으로 유도한다. semantic layer YAML(2층)이 진실의 출처. v12.7 변경점 — 공식 11개 엑셀 리포트 생성을 ckp-reports MCP 에 위임(workflows/reports-pipeline.md 신설), DB 연결을 환경 비의존화(도구는 접미사로 식별·연결은 목록에서 매칭·접속 직후 검증 1회·지갑/TNS_ADMIN 절차), 기준 타임존은 한국시간(KST).
---

# MES Metric Analysis Skill (v12.7)

> **답변은 항상 한국어로 한다** (실행 환경이 영어로 기울어도 유지). 그림 속 라벨만 영어. 상세 §8.

> **변경 이력**
> - **v12.7 (현재)** — ① `workflows/reports-pipeline.md` 신설 — 공식 11개 엑셀은 SQL 로 흉내내지 말고 `ckp-reports` MCP(`ckp_make_all`/`ckp_status`)에 위임한다. 리포트별 필터의 진실의 출처는 `program/ckp_reports/core/sql.py` 의 `REPORTS`. **No.3 품목범위는 `II` 만**(2026-07-28 원본 수기 리포트 대조 확정, No.4 는 `II+IP` — 비대칭은 원본 그대로). 중복 제거는 `ROUTING_SEQ` 최대 1행(옛 `END_ROUTING_YN` 방식과 값이 다른 것이 정상). 마감 필터는 프로그램이 커버리지를 재서 자동 판정. ② `workflows/_common.md` §0 개편 — 도구는 **접미사로 식별**, 연결은 **목록을 읽어 매칭**(이름 하드코딩 제거), 접속 직후 OCI 검증 1회, 지갑/TNS_ADMIN 절차와 ORA 증상별 조치표 신설, 기준 타임존 **KST** 통일. ③ 메일 발송 기능 폐지에 따라 관련 라우팅 제거.
> - **v11** — 워크포스 도메인을 **근태 + 인사**로 확장. ① 사원 마스터 `PW_HR_EMPLOYEES` 신규(현재 재직 로스터 1행/사원, `_NM` 디코드 보유, **PII 3단계 취급규칙**). ② 인사 발령 `PW_HR_ACTION_T` 확정 보강 — `ESTAB`(17=KLARI/그외 CIKAMPEK)·`GRADE`(급여등급)·`COMPANY`(JJ/RJ). ③ 근태 `PW_TL_DAILY_T` 컬럼 보강 — 파견(`SUPP_*`)·잔업(`OT_*`)·생산계층(`LINE/UNIT/CELL`). ④ 부서 마스터 `OLD_DEPT`(구부서 매핑). ⑤ `functions/workforce.md#fn_current_dept_name`(현재 부서명 레시피) 추가. ⑥ **뷰(_V)→베이스 테이블 규칙**(정의서는 _V 기준이나 DB엔 베이스만 존재). ⑦ §4 분석 범위를 워크포스(근태+인사)의 정의된 PW 세트로 확장. ⑧ 구버전 6-플래그 legacy 섹션 정리, 메일 발송 Zapier화.
> - **v11.1 (추가)** — 품질(OS&D) 도메인에 **Internal OS&D(SCR-007, `MSPQ_IN_OSND_BT`)** 갈래 신규. `quality-osnd.md` §0 에 Internal/External 분기 게이트. 공정(건물) 롤업 **Phylon=PHH+PHM+PHU (PB_CD='CKP-B')**·IP=IPI(PB_CD='CKP-A'), `OSND_TYPE`→`PQ_GRADE_TYPE`(CTM/UV/Trim/CMP…) 디코드 [확정: DB]. 현장 불일치 교정 — Phylon 에서 CMP Press(PHM) 누락되던 문제.
> - **v9** — 근태 주력 테이블을 구버전 `PW_TL_DAILY`(6-플래그 예외로그)에서 신버전 `PW_TL_DAILY_T`(풀 로스터·실제 스캔시각·부서/직무/PPH)로 교체 → 출근율·지각·조퇴 등 율(rate) KPI 산출 가능.

## 1. 이 skill 이 처리하는 것

CSI GMES 의 OCI 스키마 데이터를 자연어 질문으로 분석한다. 5 개 핵심 화면 도메인을 처리:

| 도메인 | 화면 | 프로시저 |
|---|---|---|
| **생산 실적** | Production Status (OP) | P_MSPD29000S_Q_V06 |
| **부족분 관리** | Shortage Balance Checking | P_MSPD90000S_Q_V14 |
| **수불 관리** | P-O Cross Check + O-I Cross Check | P_MSPD51000S_Q_V24 + P_MSPD52000S_Q_V39 |
| **품질 관리 (External)** | External OS&D Balance by Size + External OS&D Return Rate (New) | P_MSPQ38100S_Q + SP_GMES00142_Q_JJ_V5 |
| **품질 관리 (Internal)** | Bottom Internal OS&D Register (SCR-007) — 공정별 내부 불량 | `MSPQ_IN_OSND_BT` (내부 불량 등록) |

이 skill 의 동작 방식은 **2-layer semantic layer 우선**이다. 사전 정의된 YAML 파일을 진실의 출처로 두고, 자연어 질문을 그 안의 metric/dimension 으로 매핑해 SQL 을 조립한다.

- **1층** (`semantic_models/`): raw 컬럼 정의 (entities, dimensions, measures)
- **2층** (`metrics/`): 비즈니스 룰이 박힌 metric (프로시저로 검증된 [확정] 정의)

## 2. 처리 흐름

질문이 들어오면 다음 순서로 진행한다.

```
1) 질문 분석     → 어느 도메인인지 식별
2) 도메인 매칭   → 4개 workflow 중 매칭 → 해당 workflow 1개 read
                 → 매칭 안 됨 → §4 (무조건 가까운 도메인 유도 / 영 안 되면 범위 밖 안내)
3) 입력값 고정   → 날짜/Plant/OP 등 변환, 누락 시 되묻기
4) SQL 조립     → workflow 의 패턴 + metrics/yaml + semantic_models/yaml
5) DB 조회      → 로컬 SQLcl `changshinincaipoc` 우선, 실패 시 changshinin_db2 커넥터 fallback (_common.md §0)
6) 검증         → workflow 의 invariants 체크
7) 답변 작성     → 사실/추정 분리, SQL 포함
```

## 3. 도메인 라우팅

질문 키워드로 workflow 매칭. 첫 번째로 매칭되는 도메인 1개의 workflow read.

| 사용자 표현 | 도메인 | workflow 파일 |
|---|---|---|
| "Production Status", "생산 실적", "가동률", "달성률", "Plan 대비", "라인별 시프트", "%", "06~05", "스타일별 사이즈", "PIVOT" | 생산 실적 | `workflows/production-status.md` |
| "Shortage", "부족분", "남아있는", "미생산", "미출고", "잔량" | 부족분 관리 | `workflows/shortage-management.md` |
| "P-O Cross", "O-I Cross", "수불", "출고-입고", "정합성", "Prod Only", "Out Only", "In Only", "매칭률", "특이사항" | 수불 관리 | `workflows/inout-cross-check.md` |
| **[External]** "OS&D", "External OS&D", "후보충", "Return Rate", "회수율", "후보충 비율", "C.GRADE RETURN", "Replenishment Rate", "공장 간", "Supply/Demand" · **[Internal]** "내부 불량율", "공정별 불량", "Phylon Press", "CMP Press", "Bottom Internal OS&D", "IP/Phylon 불량 개수" | 품질 관리 | `workflows/quality-osnd.md` → **§0 게이트에서 Internal/External 분기** (Internal 은 `workflows/internal-osnd.md`) |

**복수 도메인 질문** (예: "어제 가동률과 부족분 같이"):
- 각 도메인 workflow 를 모두 read
- 각자 SQL 실행 후 결과를 라인/일자 단위로 결합

## 4. 도메인 매칭이 안 될 때 (자유 분석 금지 · 워크포스는 예외)

4 개 workflow(5 개 화면) 중 어디에도 매칭되지 않는 질문은 **임의 테이블로 즉흥 SQL 을 짜서 자유 분석하지 않는다.** 무조건 4 개 workflow 로 유도하고, 영 안 되면 범위 밖이라고 안내한다.
**단, 워크포스(근태 + 인사) 질문은 사전 승인된 예외**다. 다만 "아무 테이블이나"가 아니라 **아래 정의된 PW 테이블 세트 안에서만** 분석한다(§4-1):
- 근태: `OCI.PW_TL_DAILY_T` (주력)
- 인사: `OCI.PW_HR_ACTION_T`(발령 이력) · `OCI.PW_HR_EMPLOYEES`(사원 마스터, ⚠️PII 3단계 규칙)
- 디코드/마스터: `OCI.PW_ZZ_CODE_T`(공통코드) · `OCI.PW_HA_JOBCD_T`(직무) · `OCI.PW_HA_DEPT_T`(부서)

절차·SQL 골격은 `workflows/workforce.md` · `functions/workforce.md`, 컬럼 진실의 출처는 각 `semantic_models/PW_*.yml`. 이 세트 밖의 임의 테이블로는 확장하지 않는다(가드레일 유지).

### 4-1. 워크포스(근태 + 인사) 질문 — 분석 허용

근태/출결·인사 질문은 4 개 workflow 로 유도하지 말고 아래 방식으로 직접 처리한다. **근태의 코어 테이블은 `OCI.PW_TL_DAILY_T`** 이고, 사원 속성(부서/직무/직급/근속)·발령 이력이 필요하면 **§4 에 정의된 PW 세트(인사 발령·사원 마스터·디코드 마스터) 안에서 EMPID 로 조인**해 확장한다. 세트 밖 임의 테이블로는 확장하지 않는다.

> **근태 주력 테이블(중요)**: 주력 근태 테이블은 구버전 `PW_TL_DAILY`(결격 사유만 적재하던 6-플래그 예외로그)가 아니라 **`PW_TL_DAILY_T`**(풀 로스터 + 실제 스캔시각 + 부서/직무/PPH)다. **모집단(분모)이 테이블 안에 존재**하므로 출근율·지각·조퇴 같은 율(rate) KPI 산출이 가능하다. 구버전 6-플래그(`PW_TL_DAILY`)를 콕 집어 요청한 경우에만 `semantic_models/PW_TL_DAILY.yml` 참조.

- **트리거 표현**: 근태, 출결, 출근율, 결근, 지각, 조퇴(조기퇴근), 휴가, 교대/시프트, 사무직/NON_SHIFT, Direct/Indirect/Overhead, "누가 많이 빠졌나", "부서별 출근/결근", "사원별 지각", attendance / leave / absence / late 등.
- **진실의 출처**: `semantic_models/PW_TL_DAILY_T.yml` (raw 컬럼 정의). 이 YAML 의 dimension/measure 로 매핑해 SQL 조립.
- **테이블 구조** [확정: DB 검증 — 985,986행 = distinct(EMPID|TL_DATE), 사원 2,542명]:
  - 한 행 = (`EMPID`, `TL_DATE`) — 사원 1 명의 하루. (물리 PK 는 `SERVICE_ID`+`TL_DAILY_ID`)
  - **풀 로스터**: 결격 사유가 있는 사원-일뿐 아니라 정상 출근분까지 모두 적재. 과거 실적 ~ 미래 예정분 포함.
  - 대상: **CKP 근무자**(`DEPT_FNM` 이 전부 `CIKAMPEK ...`), 2026-01-01 ~ 현재(+미래 예정).
  - `COMPANY` 는 전부 `'JJ'` — **법인 코드이며 공장 코드 아님**. plant 필터로 쓰지 말 것. 공장/부서 식별은 `DEPT_FNM`.
- **근태 상태 — `WORK_STATUS` 단일 코드** (구버전 6-플래그 대체):

  | 코드 | 의미 | 근거 |
  |---|---|---|
  | `AT` | 출근(Attendance) | [확정: 사용자] |
  | `VC` | 휴가(Vacation) | [확정: 사용자] |
  | `HO` | 휴일(Holiday) | [확정: 사용자] |
  | `NN` | 생략(분석 미사용) | [확정: 사용자] |
  | 공백 | 미래 예정분 등 — 미확정 | — |

  - **⚠️ 결근(Absent)은 WORK_STATUS 단일 코드만으로 잡지 않는다.** [확정: 사용자] **결근 = `WORK_STATUS='AB' OR CHAR10_02='016'`**. `'AB'` 행(소수)뿐 아니라 결근 사유코드 `CHAR10_02='016'` 행을 OR 로 함께 포함한다. `'AB'` 만으로 세면 과소집계되므로 반드시 OR 조건을 함께 쓴다.
  - **집계 규칙(숫자 보호)**: 실적·율 집계의 모집단은 **출근(AT) + 결근(AB OR CHAR10_02='016')** 만 사용. `VC`(휴가)는 분모 제외·별도 관리. `HO`(휴일)·`NN`(생략)·공백은 **실적 집계에서 제외**하고, 항상 `TL_DATE <= TRUNC(SYSDATE)` 와 함께 쓴다.
  - **실제 출근 집계는 `WORK_STATUS='AT'`** 로 필터(단 `CHAR10_02='016'` 인 행은 결근으로 빠짐). AT 행만 실제 스캔시각(`BGN_TIME`/`END_TIME`) 보유.
- **시각 컬럼** [확정: 사용자 회신]:
  - `SCHED_BGN_TIME`/`SCHED_END_TIME` = 시스템이 만든 **예정** 출퇴근.
  - `BGN_TIME`/`END_TIME` = 작업자가 **실제 스캔**한 출퇴근. → 지각/조퇴 계산의 핵심.
  - `APP_BGN_TIME`/`APP_END_TIME` = SCHED 와 동일(승인). **무시 가능.**
  - 모두 `TIMESTAMP(6)`. 지각/조퇴 분(分)은 `(CAST(BGN_TIME AS DATE) - CAST(SCHED_BGN_TIME AS DATE))*24*60`.
- **부서/직무/노무구분** [확정: DB 검증]:
  - `DEPT_FNM`(부서 전체명, 예 'CIKAMPEK IP - INJECTION GROUP C') — 부서별 집계 표시명.
  - `JOB_POSITION_NM`(직급명: T/M·T/L·Staff·G/L·Manager 등), `JOBCD_NM`(직무명: 'IP Injection Associate' 등).
  - `PPH_FLAG` [확정: 사용자] `D`=Direct / `I`=Indirect / `O`=Overhead.
  - `SCHED_ID='NON_SHIFT'` [확정: 사용자] = **사무직**(교대 없이 근무). 그 외 `*SHIFT*` = 교대 근무.
- **미래/sentinel 제외**: `TL_DATE` 에 3031-09-04 같은 미래 sentinel + 예정분이 섞여 있으므로, **실적 집계는 `TL_DATE <= TRUNC(SYSDATE)`** 로 막는다.
- **분석 가능**:
  - 상태별 인원 — 일자·부서·직무별 출근(AT)/휴가(VC)/휴일(HO)/결근 인원
  - **율 KPI** — [확정: 사용자] **분모에서 휴가(VC)는 제외**하고 따로 관리. 휴일(HO)·생략(NN)·미래분(공백)도 제외 → 근무대상 = 출근(AT) + 결근(AB OR CHAR10_02='016').
    - 출근율 = 출근 / 근무대상,  결근율 = 결근 / 근무대상  (결근 = `WORK_STATUS='AB' OR CHAR10_02='016'`)
    - **답변 시 계산식을 사용자에게 함께 명시**한다(분모 정의와 결근 정의가 율 수치를 좌우하므로).
  - **지각·조퇴** — AT 행에서 `BGN_TIME > SCHED_BGN_TIME`(지각), `END_TIME < SCHED_END_TIME`(조퇴), 평균 지각분
    - [확정: DB 검증] `OFFSET_MINUTE`는 `SCHED_BGN_TIME`에 **이미 반영**됨 → 지각식에 OFFSET 재적용 금지(이중 보정).
    - [확정] 야간조는 `TL_DATE`=근무 시작일로 귀속되고 시각이 풀 TIMESTAMP라 자정 넘김 보정 불필요.
    - [확정: 사용자] 지각 유예시간(grace) 없음 — 1분만 늦어도 지각. `BGN_TIME > SCHED_BGN_TIME` 이면 무조건 지각.
  - 부서/직무/PPH(Direct·Indirect·Overhead)/시프트(사무직 vs 교대)별 분해
  - 일자/월별 추세, 부서·사원 랭킹(Top N), 사원별 기간 누적(잦은 지각·결근자 식별)
- **주의**: `NN`(생략)·공백은 실적 집계에서 제외(위 집계 규칙). `HO`=휴일은 분모에서 빼되 별도 집계 가능. 결근은 반드시 `WORK_STATUS='AB' OR CHAR10_02='016'` 로 잡고, 율 KPI 의 분모 정의(휴가 VC 제외 = 출근+결근)는 답변에 식으로 명시.
- **SQL 패턴**: `WORK_STATUS` 필터 + `TL_DATE` / `DEPT_FNM` / `JOBCD_NM` / `PPH_FLAG` / `EMPID` 기준 `GROUP BY`. 기간은 `TL_DATE`(DATE) 를 DATE 리터럴 범위로.
- **답변**: §8 형식(요약·표·SQL·사용 테이블·한계) 그대로. 사실/추정 분리 유지.

### 4-2. 가장 가까운 도메인으로 유도

- 질문 의도를 4 개 workflow 의 분석 능력에 비춰보고, 근접한 도메인이 있으면 그 도메인으로 처리한다.
  - 예: "Style별 매칭률" → 수불 관리(P-O/O-I Cross Check), "공정별 부족분" → 부족분 관리.
- 단, **해당 workflow 의 metric / SQL 패턴 범위 안에서만** 푼다. workflow 가 정의하지 않은 테이블·컬럼으로 SQL 을 새로 만들지 않는다.
- 어떤 도메인으로 해석했는지 답변에 한 줄 명시하고, 의도가 다르면 정정해 달라고 안내.

### 4-3. 어느 도메인에도 안 맞으면 — 범위 밖 안내 (분석 안 함)

위 처리 가능 범위(4 개 workflow + 근태)로도 풀리지 않으면(예: PCARD 발행 추이, POP 스캔 건수, 리드타임 등 화면 밖 자유 질문) **추측으로 임의 테이블을 조회하지 않는다.** 자유 분석 fallback 도 하지 않는다. 대신:

- 처리 가능한 도메인과 각 분석 능력을 짧게 제시하고, 그 범위 안에서 다시 질문해 달라고 요청한다.

처리 가능한 범위(이 안에서만 분석):

| 도메인 | 할 수 있는 분석 |
|---|---|
| 생산 실적 | Production Status — 라인별/시프트/사이즈/달성률 |
| 부족분 관리 | Shortage Balance — 미생산/미출고 잔량 |
| 수불 관리 | P-O / O-I Cross Check — 출고-입고 정합성, 매칭률 |
| 품질 관리 | External OS&D Balance + Return Rate |
| 근태 (T&L) | PW_TL_DAILY_T — 상태별(출근 AT/휴가 VC/휴일 HO/결근 등) 인원·구성비·추세, **출근율·지각·조퇴 등 율 KPI**, 부서/직무/PPH(Direct·Indirect·Overhead)/시프트(사무직 vs 교대)별 분해, 사원 랭킹·누적 (CKP, 풀 로스터·실제 스캔시각 보유. 결근 = `AB OR CHAR10_02='016'`) |
| 인사 (HR) | PW_HR_ACTION_T(발령 이력: 입사/이동/인사변동 추이, 코드→이름 디코드) + PW_HR_EMPLOYEES(사원 마스터: 현재 재직 로스터·부서/직무/직급/근속, `_NM` 디코드 보유). 절차·SQL 은 `workflows/`·`functions/workforce.md`. ⚠️사원 마스터 PII 3단계 규칙·`_V`→베이스 준수 |

### 4-4. 항상 적용

- 데이터 위생 (`workflows/_common.md`)
- Plant 약어 변환
- 사실/추정 분리

## 5. 자료 사용 원칙

### 5-1. 진실의 출처

| 자료 | 우선순위 | 언제 |
|---|---|---|
| `metrics/*.yml` (2층) | 최우선 | 프로시저 검증된 metric — 화면 결과 재현 시 |
| `semantic_models/*.yml` (1층) | 2위 | raw 컬럼 정보 필요 시 (workflow 컬럼 검증) |
| `workflows/*.md` | 절차 | SQL 패턴, 함정, 검증 |
| 사용자의 막연한 기억, 일반 지식 | 최후 | 위 셋과 충돌하면 yaml 우선 |

### 5-2. yaml 마커 준수

yaml 의 description 에 다음 마커가 있다. 답변에 그대로 반영.

- **[확정: ...]** — 프로시저/사용자 회신/공식 문서로 검증된 사실. 단정문으로 사용.
- **[추측: ...]** — 정의서·샘플만 보고 추정. 답변에서 "[추측]" 표시 유지.
- **[정의서: ...]** — 컬럼 정의서 원문 인용.

특히 `[확정: P_XXX 라인 N 검증]` 표기가 있으면 그 메트릭의 비즈니스 룰은 100% 신뢰 가능.

### 5-3. 어디까지 read 하는가

질문 처리 단계마다 read 할 파일이 다르다. **전체를 매번 read 하지 않는다.**

| 처리 단계 | 먼저 read |
|---|---|
| 도메인 식별 | (이 SKILL.md 의 §3 표) |
| 도메인 매칭 됨 | 해당 `workflows/XXX.md` 1개 |
| SQL 골격이 필요할 때 | 해당 `functions/XXX.md` (workflow 가 포인터로 가리킴) |
| metric 정의 확인 | 해당 `metrics/XXX.yml` |
| raw 컬럼 확인 (workflow 컬럼 검증) | 관련 `semantic_models/XXX.yml` |
| 공통 원칙 (모든 흐름) | `workflows/_common.md` |

**workflow 와 functions 의 분담**:
- `workflows/XXX.md` — 처리 절차, 분석 능력 매칭, 함정, 검증, 답변 형식
- `functions/XXX.md` — 재사용 가능한 SQL 골격 모음. workflow 에서 `functions/XXX.md#fn_name` 으로 포인팅

## 6. 항상 적용하는 공통 원칙

상세는 **`workflows/_common.md`** 참조. 여기서는 핵심만:

- **DB 연결 (가장 먼저, 2단)**: 첫 조회 전 **① 로컬 SQLcl MCP `changshinincaipoc`** (대소문자 구분, ADMIN @ `changshinincaipoc_medium`, OCI 스키마)에 접속한다. SQLcl 이 없거나 연결이 전부 실패하면 **② `changshinin_db2` 커넥터(EXECUTE_SQL)** 로 같은 OCI ADB 에 fallback. 옛 `lmes_medium` 계열(lmes/lmes2/mylmes/lmes_v2)은 **다른 레거시 DB** — 쓰지 말 것. 상세·절차는 `_common.md` §0.
- **데이터 위생**: PROD_MOVE_TYPE='PROD'(실적)/'MOVE'(입고), 19991231 sentinel 제외, PROD_DATE vs PROD_DT 구분, END_ROUTING_YN='Y' (라인 마지막), RESULT_TYPE='SCAN'.
- **Plant 약어**: JJ=3110, CKP=3120, RJ=3210, JJS=3220.
- **OP 분류**: IPI/IPU=IP 공정, PHH/PHM/PHU=PH(Phylon) 공정. [내부 OS&D 확정: DB] **PHH=Phylon Press(SUB_WC CTM01~30), PHM=CMP Press(CP01~06), PHU=Phylon UV**. 내부 OS&D 건물(PB_CD) 롤업: **CKP-A→IP, CKP-B→Phylon(=PHH+PHM+PHU)**. ⚠️내부 불량율에서 Phylon 을 PHH 만으로 잡으면 CMP Press 누락(수량 과소).
- **Plant 컬럼 두 개**: 계획은 `PLANT_CD`, 실적은 `ITPO_WC_PLANT_CD`. (생산 실적 도메인에서 가장 흔한 함정)
- **사실/추정 분리**: 조회 결과는 단정문, 원인/해석/경향은 [가설]/[추정] 명시.
- **답변 투명성**: 실행 SQL 포함, 사용한 metric/테이블 명시, 검증 결과 짧게.

## 7. 모호성 처리

답을 만들기 전 되묻는다.

| 모호한 표현 | 확인할 것 |
|---|---|
| "가동률", "달성률" | achievement_rate(SCR-002) vs po_match_rate(SCR-003) vs oi_match_rate(SCR-004) — 어느 화면? |
| "어제/오늘" + 데이터 없을 때 | 실제 달력 유지할지 최신일로 바꿀지 |
| OP 미지정 | IP/PH 5 개 전체로 가는지 특정 OP 인지 |
| "더 자세히" / "breakdown" | workflow 내 다음 분해 단계 |
| Plant 미지정 | 단일 Plant 인지 전체인지 |
| "출고만 있는 수량" (Out Only) | P-O 의 Out Only(생산 없음) vs O-I 의 Out Only(입고 없음) — 의미 다름 |

## 8. 답변 형식

**답변 언어 — 항상 한국어 (필수).**
모든 답변 산문(요약·설명·표 헤더·해석·되묻기)은 **반드시 한국어**로 쓴다. 사용자가 영어로 질문하거나
실행 환경(Cowork 등)이 영어로 기울어도 한국어를 유지한다. SQL·컬럼명·연결 이름·코드·에러 코드 등
고유 식별자는 원문 그대로 둔다.
- **예외 — 그림 속 텍스트**: matplotlib 등 **플롯 안의 제목/축/범례 라벨은 영어**로 둔다 (한글 폰트 깨짐 방지).
  그래프를 설명하는 본문은 한국어.

기본 답변 구조:

```
1. 한 줄 요약 (질문에 대한 직접적 답)
2. 결과 표 (필요 시)
3. 사용한 SQL (펼침)
4. 사용한 metric / 테이블
5. 검증 결과 (invariant 체크)
6. 한계 / 추가 확인 필요 사항 (있을 때만)
```

추가 가공 요청 (일보, 리포트, 그래프 등) 있을 시 결과를 그 형태로 가공.

## 9. 연계 skill

| 사용자 추가 요청 | 연계 skill |
|---|---|
| "리포트", "보고서", "Word", "docx" | `data-analysis-report` |

## 10. 이 skill 범위 밖 (명시적 거절 대상)

- **MES 외부 시스템 데이터** — ERP, 물류 등 OCI 스키마에 없는 데이터.
- **개별 PCARD 의 의미 해석** — 코드 그대로 보여주되, 사람이 가진 도메인 지식이 필요한 비즈니스 의미는 단정 안 함.

> **참고: SCR-006 (External OS&D Return Rate)** — `LMES.V_PQ_EX_OSND_V3` 뷰는 OCI 부재이지만 `functions/quality-osnd.md` §V-2 의 OCI 재현 CTE(`OSND_V3_REPLICA`) 로 처리 가능. 워크플로 §3-H ~ §3-M 참조.

## 11. 참고 파일

| 파일 | 용도 | 읽는 시점 |
|---|---|---|
| `workflows/_common.md` | 데이터 위생, Plant 약어, SQL 규칙 | 모든 처리 시 |
| `workflows/production-status.md` | 생산 실적 처리 절차/함정 | 생산 실적 도메인 |
| `workflows/shortage-management.md` | 부족분 처리 절차/함정 | 부족분 도메인 |
| `workflows/inout-cross-check.md` | 수불 처리 절차/함정 (P-O+O-I) | 수불 도메인 |
| `workflows/quality-osnd.md` | OS&D 처리 절차/함정 (§0 Internal/External 게이트) | 품질 도메인 (External) |
| `workflows/internal-osnd.md` | **내부 OS&D(SCR-007)** 처리 절차/함정 | 품질 도메인 (Internal) |
| `workflows/reports-pipeline.md` | **공식 11개 엑셀 리포트 생성**(ckp-reports MCP 위임) | "리포트/레포트 만들어줘" 요청 시 |
| `functions/production-status.md` | 생산 실적 SQL 골격 (fn_main_tree, fn_detail_line_hourly 등 9 개) | workflow 가 포인터로 가리킬 때 |
| `functions/shortage-management.md` | 부족분 SQL 골격 (4 개) | 같음 |
| `functions/inout-cross-check.md` | 수불 SQL 골격 (6 개) | 같음 |
| `functions/quality-osnd.md` | External OS&D SQL 골격 (SCR-005/006) | 같음 |
| `functions/internal-osnd.md` | **내부 OS&D SQL 골격 (A~F 6 개, DB 검증)** | 내부 불량 질문 시 |
| `metrics/*.yml` | 각 도메인의 metric 정의 (내부 OS&D = `internal_osnd.yml`) | metric 사용 시 |
| `semantic_models/*.yml` | 테이블의 raw 컬럼 정의 (화면 메인/보조) | 컬럼 검증 시 |
| `semantic_models/MSPQ_IN_OSND_BT.yml` | **내부 OS&D 메인** 테이블 raw 컬럼 (PB 롤업·`PQ_GRADE_TYPE` 디코드) | 내부 불량 질문 시 |
| `semantic_models/PW_TL_DAILY_T.yml` | **근태 주력** 테이블 raw 컬럼 정의 (CKP 풀 로스터) | 근태 질문 시 (§4-1) |
| `semantic_models/PW_TL_DAILY.yml` | (LEGACY) 구버전 6-플래그 예외로그 (신버전 PW_TL_DAILY_T 로 대체됨) | 구버전 6-플래그를 명시 요청 시만 |
| `semantic_models/PW_HR_EMPLOYEES.yml` | **사원 마스터**(현재 재직 로스터, 1행/사원, `_NM` 디코드 보유) — ⚠️PII 다수, 3단계 취급규칙·`_V`→베이스 주의 | 사원 속성 조인·현재 부서/직무/직급, 현재 부서명(functions/workforce.md#fn_current_dept_name) |

**읽는 원칙**: 필요한 섹션만. 도메인 매칭되면 해당 workflow 1 개를 먼저 read, SQL 골격이 필요해진 시점에 functions 의 해당 함수 부분만 read. metric 정의 필요하면 그때 yaml 1 개 read.
