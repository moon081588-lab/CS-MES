# Production Status — Analysis Workflow

생산 실적 도메인 (SCR-002, 화면 Production Status OP) 처리 절차.

| 항목 | 값 |
|---|---|
| 화면 | Production Status (OP) |
| 프로시저 | `LMES.P_MSPD29000S_Q_V06` |
| 메인 테이블 | `OCI.MSPD_PCARD_RESULT` |
| metric 파일 | `metrics/production_status.yml` |
| 보조 1층 | `semantic_models/MSPD_PCARD_RESULT.yml` |

**공통 원칙은 `workflows/_common.md` 참조.**

---

## 1. 이 도메인이 가진 분석 능력

프로시저 4 개 분기 (`V_P_WORK_TYPE`) 가 화면의 4 가지 영역 = 4 가지 분석 능력:

| 분석 능력 | 화면 영역 | 분기 |
|---|---|---|
| **A. Process 트리** | Process > Total | MAIN |
| **B. 라인별 시간/시프트** | Prod. Status of Time | DETAIL |
| **C. 스타일별 사이즈 PIVOT** | Prod. Status of Size | DETAIL |
| **D. 시프트 시간대 메타** | (조회조건) | SHIFT |

각 분석 능력의 SQL 패턴은 §3 참조.

---

## 2. 처리 흐름

```
1) 질문 분해     → 기준일/Plant/OP/분해단위 추출
2) 분석 능력 매칭 → A/B/C/D 중 어느 것
3) 입력값 고정   → 미지정 항목 되묻기
4) SQL 작성     → 해당 분석의 SQL 패턴 (§3)
5) DB 조회      → SQLcl
6) invariant 검증 (§4)
7) 답변 작성     → 사실/추정 분리
```

### 2-1. 질문 분해 항목

| 항목 | 필수 | 디폴트 / 되묻기 |
|---|---|---|
| 기준일 | 필수 | 없으면 되묻기, "어제"는 MAX(FA_DATE) |
| Plant | 필수 | 없으면 되묻기 (JJ/CKP/RJ/JJS) |
| OP | 선택 | 없으면 IP/PH 5 개 전체 |
| Item Class Type | 선택 | 없으면 전체 (FG 입력 시 'UP' 변환) |
| 분해 단위 | 선택 | "라인별" → B, "스타일별" → C, "Item Class별" → A |
| 메트릭 | 선택 | "%" → achievement_rate, "시프트" → shift1/2/3, "시간대" → HH 분해 |

### 2-2. 분석 능력 매칭 키워드

| 사용자 표현 | 분석 |
|---|---|
| "Item Class 별", "트리", "PRODUCT/OUTGOING 구분", "Process Total" | **A. Process 트리** |
| "라인별", "시프트별", "%", "Plan 대비", "06~05", "시간대별", "가동률" | **B. 라인 시간** |
| "스타일별 사이즈", "사이즈 PIVOT", "스타일별 분포" | **C. 스타일 사이즈** |
| "시프트 시간대 (몇시~몇시)" | **D. 시프트 메타** |

---

## 3. SQL 패턴

### 3-A. Process 트리 (`MAIN_tree`)

**산출**: ITPO_TYPE × ITEM_CLASS × OP_CD 별 PRODUCT/OUTGOING 합계.

**사용 metric**: `production_qty`, `outgoing_qty`

**SQL 골격**: → [`functions/production-status.md#fn_main_tree`](../functions/production-status.md#fn_main_tree)

**핵심 룰**:
- 실적: `PROD_DATE` 기준
- 출고: `OUT_DATE` 기준
- 둘 다 `ITPO_WC_PLANT_CD` 로 Plant 필터 (실제 작업 발생)
- ITEM_CLASS_TYPE 필터 **박지 말 것** (트리가 일부만 보임)

[확정: P_MSPD29000S_Q_V06 라인 130-205 검증]

---

### 3-B. 라인별 시간/시프트 (`DETAIL_line_hourly`)

**산출**: 화면 그리드와 동일한 구조 — W/C Group × Line × Plan / Sum / Shift1/2/3 / HH_06~05 / %.

**사용 metric**: `plan_qty`, `sum_qty`, `shift1/2/3_qty`, `achievement_rate`

**핵심 구조 — 3 CTE + 마스터 LEFT JOIN**:
1. `WC_LIST` — COUNTRY 단위 라인 마스터 (왼쪽 outer 기준, 그날 활동 0인 라인도 표시)
2. `PLAN_DT` — 계획 LEG (PLANT_CD + PLAN_PROD_DATE 기준)
3. `PROD_DT` — 실적 LEG (ITPO_WC_PLANT_CD + PROD_DATE 기준, sentinel 제외)
4. WC_LIST LEFT JOIN PLAN_DT LEFT JOIN PROD_DT

**[전제] PLANT → COUNTRY 변환**: → [`functions/production-status.md#fn_country_from_plant`](../functions/production-status.md#fn_country_from_plant) (MSBS_ORGANIZATION_SUB 한 줄 조회)

**SQL 골격**: → [`functions/production-status.md#fn_detail_line_hourly`](../functions/production-status.md#fn_detail_line_hourly)

**핵심 룰** (가장 함정 많음):
- **Plant 컬럼 두 개**:
  - Plan : `PLANT_CD` (계획 책임 공장)
  - 실적 : `ITPO_WC_PLANT_CD` (실제 작업 발생 공장, 외주 포함)
- **COUNTRY 변환 필수**: WC_LIST 는 PLANT 필터 없이 COUNTRY 단위. 카드(PLAN_DT/PROD_DT) leg 만 PLANT 필터.
- **화면 컬럼 출처**:
  - 'W/C Group' = `MSBS_SUM_GROUP_WC.SUB_TOTAL_CD` (마스터 WC_GROUP_CD 와 다를 수 있음)
  - 'Line'      = `MSBS_SUM_GROUP_WC.VIEW_GROUP_CD`
  - FORM_ID = 'MSPD22000S' 고정 (다른 화면 매핑 섞이면 안 됨)
- **OP 단일 동등**: DETAIL CV_1 은 OP 한 개만. 화면도 좌측 Process 트리에서 1개 클릭 → DETAIL 호출.
- **ITEM_CLASS_TYPE 강제 동등**: DETAIL 에서만. MAIN(§3-A) 에서는 박지 말 것.
- **실적 sentinel 제외**: `PROD_DT > TO_DATE('20010101','YYYYMMDD')`.
- **PROD_RT raw_level_form**: 라인별 ROUND 후 * 100. 그룹 소계/총계는 final_form 별도 계산 (§3-B-2).

[확정: P_MSPD29000S_Q_V06 라인 291/313/343-446 + WC_LIST CTE 검증]

---

### 3-B 부록. 자유 분석 — OP 묶음 처리

**언제 등장**:
화면 재현이 아닌 자유 분석. 사용자 표현 예시:
- "어제 라인 03 PH 공정 생산량" → PH 공정 = (PHH, PHM, PHU) 묶음
- "어제 라인 03 IP·PH 합쳐서" → 5개 묶음
- "어제 라인 03 카드 몇 장 다뤘어" → OP 묶음 + 카드 단위 카운트
- `_common.md` §3 의 IP/PH 공정 약어 사용 시

**왜 함정**:
같은 카드(BARCODE_KEY) 가 라우팅 따라 여러 OP row 로 분산. PCARD_QTY 는 모든 row 동일.
묶은 OP 안에 카드별 row 가 N 개 있으면 SUM 시 부풀림 발생.
부풀림 배수는 묶음 안에 카드별 row 수만큼 — 고정값 아님 (데이터에 따라 다름).

[확정: PROD_DATE / FA_WC_CD / OP IN 절 묶음 실측 검증]

**처리 옵션** (사용자 의도에 따라 선택):

| 옵션 | 의미 | SQL |
|---|---|---|
| A. OP별로 따로 행 | "OP 별로 분해해서" | `OP_CD IN (...) GROUP BY OP_CD, FA_WC_CD` |
| B. 카드 단위 합 | "이 라인이 다룬 카드 켤레 총량" | DISTINCT BARCODE_KEY 서브쿼리 → `distinct_card_qty` metric |
| C. row 단순 합 | "공정 통과 횟수" — 드물 | `OP_CD IN (...) SUM(PCARD_QTY)` 그대로 |

**디폴트 결정 규칙**:
- "각각", "별로", "분해" → **A**
- "합쳐서", "묶어서", "총량" → **B** (카드 중복 제거)
- C 는 사용자가 명시적으로 "공정 통과 횟수" 같이 말할 때만

**옵션 A SQL 골격** (분해): → [`functions/production-status.md#fn_op_group_breakdown`](../functions/production-status.md#fn_op_group_breakdown)

**옵션 B SQL 골격** (카드 중복 제거): → [`functions/production-status.md#fn_op_group_distinct_card`](../functions/production-status.md#fn_op_group_distinct_card)

**답변 시**: 어느 옵션 썼는지 명시 + 사용자 의도 확인 한 줄
(예: "PH 공정 묶음을 카드 중복 제거해서 합산했습니다 (옵션 B).
각 공정별로 따로 보고 싶으면 OP별로 분해해 드릴까요?")

---

### 3-B 부록 2. 모델 단위 분해 (STYLE_CD + MODEL_NAME)

**언제 등장**: "모델별 달성률", "실적 저조한 모델", "STYLE_CD·MODEL_NAME으로 뽑아줘" 등.

**처리**: §3-B 의 PLAN_DT / PROD_DT 2-leg 구조를 그대로 쓰되,
GROUP BY 키를 `FA_WC_CD` → `STYLE_CD` 로 교체 (또는 둘 다).
MODEL_NAME 은 `OCI.MSBS_ITEM_STYLE` LEFT JOIN 으로 표시 (STYLE_CD 단일키).
'모델' 식별 단위 = STYLE_CD + MODEL_NAME 함께 GROUP BY.

**⚠ 필수**: OP_CD + ITEM_CLASS_TYPE 단일 동등 유지 (DETAIL 분기 규칙 그대로).
미고정 시 한 카드가 여러 OP row 로 분산돼 SUM 부풀림 — §3-B 부록의 BARCODE_KEY
함정과 동일 원리.
- OP 미고정: 부풀림 발생 (2026-03-13 CKP 실측 약 2.15배)
- OP 단일 고정: 부풀림 없음 (row합 = 카드중복제거합)

[확정: 2026-03-13 CKP 실측 검증 — 전체 OP 248,910 vs 카드중복제거 115,632 / IPI·II 단일 43,207=43,207]

**SQL 골격**: `metrics/production_status.yml` 의 `model_achievement_rate` /
`achievement_rate` description 의 [모델 단위 SQL 골격] 참조.

**미생산 모델 (계획 있고 실적 0)**: FULL OUTER JOIN 으로 plan_only 노출.
단 "한 달간 계획만 잡히고 실적 0" 같은 누적 미생산 질문은 부족분 관리 도메인
(Shortage Management, `fn_shortage_by_line_style_size`) 가 더 정확 — 그쪽으로 라우팅 고려.

**답변 시**: OP·ITEM_CLASS_TYPE 를 무엇으로 고정했는지 명시.
OP 미지정으로 들어오면 §5-6 의 ICT 후보 조회처럼 OP/ICT 를 먼저 되묻기.

---

### 3-B-2. W/C Group 단위 소계 (화면 그리드 회색 헤더 행)

3-B 결과에서 `SUB_TOTAL_CD` 단위로 한 번 더 묶음 — **PROD_RT 는 final_form 사용**:

**SQL 골격**: → [`functions/production-status.md#fn_wc_group_subtotal`](../functions/production-status.md#fn_wc_group_subtotal)

[확정: PROD_RT 그룹 단위는 final_form 사용]

---

### 3-C. 스타일별 사이즈 PIVOT (`DETAIL_style_size_pivot`)

**산출**: 라인 × 스타일 × 시프트별로 사이즈 분포.

**사용 metric**: `production_qty` (sum_qty 도 가능)

**SQL 골격** (사이즈 동적 PIVOT): → [`functions/production-status.md#fn_detail_style_size_pivot`](../functions/production-status.md#fn_detail_style_size_pivot)

**Size 컬럼 하드코딩 40개** 및 PIVOT 전환 방법은 위 functions 파일 참조.

---

### 3-D. 시프트 시간대 메타 (`SHIFT_mapping`)

**산출**: Plant·요일별 Shift 시작/종료 시각.

**SQL** (실데이터 집계 아님, 메타데이터): → [`functions/production-status.md#fn_shift_mapping`](../functions/production-status.md#fn_shift_mapping)

[확정: P_MSPD29000S_Q_V06 라인 89-117 검증]

---

## 4. 검증 (Invariants)

분석 후 답변 전에 자동 체크.

### 4-1. 시프트 합

- `SHIFT1 + SHIFT2 + SHIFT3 = SUM_QTY`
- 안 맞으면 → 시프트 함수 호출에서 매칭 안 된 데이터 있음. 답변에 명시.

### 4-2. 시간대 합

- `HH_06 + HH_07 + ... + HH_05 = SUM_QTY` (24 개 합)
- 안 맞으면 → 위와 동일.

### 4-3. PROD_RT 공식

- `PROD_RT = SUM_QTY / PLAN_QTY × 100` (PLAN=0 이면 0)
- 답변에 % 표시 시 위 공식 적용 결과인지 확인.

---

## 5. 함정 (자주 틀리는 곳)

### 5-1. Plant 컬럼 두 개

**가장 흔한 함정**. 위 §3-B 강조.

| 메트릭 | Plant 필터 |
|---|---|
| `plan_qty` | `PLANT_CD` |
| `sum_qty`, `shift*_qty`, `production_qty`, `outgoing_qty` | `ITPO_WC_PLANT_CD` |

### 5-2. 실적 sentinel

`PROD_DATE = '19991231'` 인 행은 PROD_DT 가 NULL/sentinel. 실적 집계에서 자동 제외:
```sql
AND PROD_DT > TO_DATE('20010101','YYYYMMDD')
```
이 조건 빠뜨리면 미생산 카드까지 셈.

### 5-3. 야간 시프트 (S3) 자정 넘김

S3 가 자정을 넘어가지만 PROD_DATE 는 시프트 시작일 기준. 즉 03/26 23:00 ~ 03/27 06:00 작업은 PROD_DATE='20260326'.

답변에서 시프트 시간대 표시 시 "S3 (예: 22:00~06:00, 다음날 새벽 포함)" 같이 명시.

### 5-4. FN_GET_BT_SHIFT Plant 인자

`SUBSTR(PROD_WH_CD, 3, 2)` 로 'IP' 또는 'BT' 추출. 'IP' 외 값 ('BT' 등) 들어오면 시프트 매핑 다를 수 있음.

### 5-5. ITEM_CLASS_TYPE='FG' 입력 시

프로시저는 'FG' 입력 받으면 SQL 안에서 'UP'으로 변환. 사용자가 "FG 보여줘" 하면 ITEM_CLASS_TYPE='UP' 으로 필터.

[확정: P_MSPD29000S_Q_V06 라인 82]

---

### 5-6. ITEM_CLASS_TYPE — MAIN/DETAIL 비대칭

| 분기 | ITEM_CLASS_TYPE 필터 | 비고 |
|---|---|---|
| MAIN (Process 트리, §3-A) | **미적용** | 프로시저 본문 주석처리. WHERE 절에 박지 말 것. |
| DETAIL (라인별/사이즈, §3-B/§3-C) | **강제 동등** (`= :V_ICT`) | 박아야 화면 일치. |

**왜 비대칭인가**:
화면 좌측 'Process' 트리(MAIN)는 ITEM_CLASS_TYPE 별로 다 펼쳐 보여주는 게 정상.
즉 같은 OP=BUA 안에 ITEM_CLASS_TYPE=CP 묶음 한 번, II 묶음 한 번 따로 보임.
따라서 MAIN SQL 에 ITEM_CLASS_TYPE 박으면 화면 트리가 일부만 보임 (잘못됨).

반대로 DETAIL(우측 그리드, 하단 사이즈)은 좌측에서 클릭한 노드 1개에 대한 결과만 보여줌.
즉 (OP, ITEM_CLASS_TYPE) 페어 단일. 박지 않으면 다른 페어 row 가 섞여서 라인별 합계가 부풀려짐.

**사용자가 OP 만 말하고 ITEM_CLASS_TYPE 안 말했을 때**:
DETAIL 분석 시 ITEM_CLASS_TYPE 필수. 사용자에게 되묻기.
예: "BUA 공정은 ITEM_CLASS_TYPE 가 CP / II 두 종류 가능합니다. 어느 쪽 보시겠어요?
     - CP: 일반 신발 부착 / II: 인서트 부착"

DISTINCT 조회로 그날 해당 OP 의 ITEM_CLASS_TYPE 후보 보여주고 선택받는 방식 권장:
→ [`functions/production-status.md#fn_item_class_type_candidates`](../functions/production-status.md#fn_item_class_type_candidates)

[확정: P_MSPD29000S_Q_V06 본문 검증 + 화면 좌측 Process 트리 구조 분석]

---

## 6. 답변 형식

기본 구조:

```
1. 한 줄 요약
2. 결과 표 (라인별 / 시프트별 / 사이즈별 등)
3. 사용한 SQL (펼침)
4. 사용한 metric: production_status.yml의 sum_qty, plan_qty, achievement_rate
5. 검증: SHIFT1+2+3=SUM_QTY ✓ (또는 ✗ 시 사유)
6. (있을 때) 한계
```

추가 가공 요청 시:
- "일보" → 표 + 미달 라인 강조 (achievement_rate < 90% → ⚠️)
- "리포트" → `data-analysis-report` skill 연계
- "그래프" → 텍스트 막대 또는 visualize 도구

---

## 7. 자주 발생하는 모호성

| 사용자 표현 | 확인 |
|---|---|
| "어제 가동률" | Plant 단위? 라인 단위? OP 단위? — 디폴트는 라인별, OP 전체 |
| "% 어떻게 나왔어" | PROD_RT 공식 명시 |
| "FG 생산" | ITEM_CLASS_TYPE='UP' 으로 변환됨 안내 |
| "더 자세히" | 분석 능력 다음 단계로 (A→B→C) |
