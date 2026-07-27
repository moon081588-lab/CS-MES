# Quality (External OS&D) — Analysis Workflow

품질 관리 도메인 (**SCR-005 External OS&D Balance + SCR-006 External OS&D Return Rate**) 처리 절차.

| 항목 | 값 |
|---|---|
| 화면 | SCR-005 External OS&D Balance by Size / SCR-006 External OS&D Return Rate (New) |
| 프로시저 | SCR-005: `LMES.P_MSPQ38100S_Q` / SCR-006: `LMES.SP_GMES00142_Q_JJ_V5` |
| 메인 테이블 | SCR-005: `OCI.MSPQ_EX_OSND` / SCR-006: `LMES.V_PQ_EX_OSND_V3` (OCI 부재 — 재현 CTE 사용) |
| 보조 테이블 | `MSBS_CODE_MASTER`, `MSBS_PLANT`, `MSPQ_INSPECT_POINT`, `MSBS_ITEM_CLASS`, `MSBS_CALENDAR`, `MSPQ_RPT_IP`, `MSPQ_MATERIAL_MOVE`, `MSPD_PCARD_RESULT` |
| metric 파일 | `metrics/external_osnd_balance.yml` |
| 보조 1층 | `semantic_models/MSPQ_EX_OSND.yml` |
| SQL 골격 | `functions/quality-osnd.md` (SCR-005 함수 10 + SCR-006 함수 6 + §V 뷰 재현 부록) |

**공통 원칙은 `workflows/_common.md` 참조.**

---

## 0. Internal / External 분기 게이트 (가장 먼저)

"OS&D" 질문은 두 화면으로 갈린다. **이 workflow 를 읽기 시작하면 먼저 아래로 분기**한다.

| 신호 | 갈래 | 처리 |
|---|---|---|
| "내부", "공정별 불량율", "Phylon Press / CMP Press", "Bottom (Internal) OS&D Register", "IP/Phylon 불량 개수", `MSPQ_IN_OSND_BT`, PB_CD(CKP-A/CKP-B), 화면의 OS&D Qty/Repl/Bal | **Internal (SCR-007)** | → **`workflows/internal-osnd.md` 로 이동** (이 문서 §1~ 는 읽지 않음) |
| "후보충", "회수율/Return Rate", "공장 간", "Supply/Demand", "출고/입고 스캔", "Balance by Size", `MSPQ_EX_OSND` | **External (SCR-005/006)** | ↓ 이 문서 §1~ 계속 |

> ⚠️ 둘은 이름만 "OS&D"지 테이블·컬럼·KPI 가 완전히 다르다. Internal 질문을 External 로직(`MSPQ_EX_OSND`)으로 풀면 틀린다(반대도 마찬가지). 애매하면 "공장 **내부** 불량율(Internal)인지, 공장 **간** 후보충/회수율(External)인지" 한 번 되묻는다.

---

## 1. 이 도메인이 가진 분석 능력

### 1-1. SCR-005 (External OS&D Balance) — `P_MSPQ38100S_Q`

4 개 STATUS 분기 (UNION ALL):

| Status | 의미 | 판정 조건 |
|---|---|---|
| REQUEST | OS&D 발생 (전체) | CANCEL_YN='N' |
| OUTGOING | 공급 Plant 출고 완료 | CANCEL_YN='N' AND O_SCN_DT IS NOT NULL |
| INCOMING | 수요 Plant 입고 완료 | CANCEL_YN='N' AND I_SCN_DT IS NOT NULL |
| BALANCE | 잔량 (출고/입고 미완료) | (별도 계산) |

추가 능력:
- OSND_TYPE 분류 (D/L/I/S 타입별)
- MSBS_CODE_MASTER lookup (CODE_CLASS_CD='PQ_OSND_TYPE') 으로 코드 → 이름 변환
- 공장 간 보충 흐름 (SUPPLY_PLANT_CD → DEMAND_PLANT_CD)

분석 능력으로 정리:

| 분석 능력 | 무엇을 보나 |
|---|---|
| **A. OS&D 종합 (4 Status)** | Request / Outgoing / Incoming / Balance 한 화면 |
| **B. 타입별 분석 (D/L/I/S)** | OSND_TYPE GROUP BY |
| **C. 일자별 발생 추이** | OSND_DATE GROUP BY |
| **D. 후보충 잔량 상세** | Balance > 0, 출고 미완 vs 입고 미완 분리 |
| **E. 공장 간 보충 흐름** | SUPPLY_PLANT_CD → DEMAND_PLANT_CD |
| **F. SCR-005 화면 그대로** | 4 STATUS × 사이즈 PIVOT (Line × CMP × Model × Style × Type × Supply Plant) |

### 1-2. SCR-006 (External OS&D Return Rate) — `SP_GMES00142_Q_JJ_V5`

뷰 `V_PQ_EX_OSND_V3` 기반. **OCI 에 뷰가 없으므로** `functions/quality-osnd.md` §V 의 재현 CTE (`OSND_V3_REPLICA`) 사용.

핵심 지표:
- `DEFECT_QTY` = `OSND_EX_QTY / 2` (L/R 켤레 환산, OSND_TYPE 별 분리)
- `REPLEN_QTY` = `DECODE(I_SCN_DT, NULL, 0, OSND_EX_QTY) / 2` (입고 완료된 것만)
- `Return Rate (%)` = `REPLEN_QTY / DEFECT_QTY * 100` (소수점 둘째 자리)
- 필터: `OSND_TYPE IN ('D','S')` (2025.09.22 이후), `IN_DATE` 기준 (OSND_DATE 아님)

분석 능력으로 정리:

| 분석 능력 | 무엇을 보나 |
|---|---|
| **H. 일자별 Return Rate (경량)** | IN_DATE 별 REPLEN/DEFECT 비율 (메인 그리드, CV_2) — DEFECT 분기만 |
| **H'. 화면 하단표 풀 재현** | Incoming Qty / OS&D Qty / Replen / Replen Rate / OS&D Rate — 4분기 UNION |
| **I. Target 기준선** | PQ_INSPECT_TYPE = 'EX' 의 EXTRA_COLUMN1 (CV_4) |
| **J. 달력 일자 컬럼** | MSBS_CALENDAR (Plant=3110 고정, CV_1) |
| **K. 차트 break 설정** | PQ_REPORT = 'BREAK_EX' (CV_3) |
| **L/M. 콤보박스** | Plant / Process 드롭다운 |

**화면 ↔ metric/컬럼 매핑** (SCR-006 하단 6행 표):

| 화면 표기 | 차트 라벨 | metric | 프로시저 CV_2 출력 컬럼 |
|---|---|---|---|
| Incoming Quantity (Prs) | — | `osnd_in_qty` | `PROD_QTY` (= `SUM(IN_QTY)`) |
| OS&D Quantity (Prs) | **C.GRADE RETURN** 막대 | `osnd_defect_qty` | `DEFECT_QTY` |
| Replenishment (Prs) | **REPLENISHMENT** 막대 | `osnd_replen_qty` | `REPLEN_QTY` |
| Replenishment Rate (%) | **%** 자주색 라인 | `osnd_return_rate` | `PER` |
| OS&D Rate (%) | — | `osnd_rate_pct` | (프로시저 없음 — 클라이언트 표현식 [추측]) |

> "C.GRADE RETURN" 은 OS&D Quantity (= DEFECT_QTY) 의 화면 별칭이며 별도 컬럼이 아니다.
> 프로시저 출처 [확정: SP_GMES00142_Q_JJ_V5 CV_2 라인 87-110].

---

## 2. 처리 흐름

```
1) 질문 분해     → 기준일/Plant/OSND 타입/분해단위 추출
2) 분석 능력 매칭 → A~E 중 어느 것
3) 입력값 고정   → 미지정 항목 되묻기
4) SQL 작성     → 해당 분석의 SQL 패턴 (§3)
5) DB 조회
6) 답변 작성
```

### 2-1. 질문 분해 항목

| 항목 | 필수 | 디폴트 / 되묻기 |
|---|---|---|
| **화면 선택** | 필수 | "Return Rate" / "회수율" / "후보충 비율" 키워드 → SCR-006 / 그 외 → SCR-005 |
| 기준일 | 필수 | SCR-005 → `OSND_DATE`, SCR-006 → `IN_DATE`. "어제"는 SYSDATE-1 |
| Plant | 선택 | 없으면 전체. 있으면 SUPPLY/DEMAND 어느 쪽인지 |
| OSND 타입 | 선택 | SCR-005 → 전체 (D/L/I/S). SCR-006 → `'D','S'` 고정 (변경 시 명시) |
| 분해 단위 | 선택 | "타입별" → B, "일자별" → C/H, "잔량" → D |

### 2-2. 분석 능력 매칭 키워드

| 사용자 표현 | 분석 | 화면 |
|---|---|---|
| "OS&D 현황", "발생", "후보충", "Balance" | **A. 종합** | SCR-005 |
| "Damage", "Lost", "Issue", "Shortage", "타입별", "분류" | **B. 타입별** | SCR-005 |
| "일자별", "추이", "발생량" | **C. 추이** | SCR-005 |
| "후보충 안 끝난", "잔량 상세", "처리 안 된", "미완료" | **D. 잔량 상세** | SCR-005 |
| "공장 간", "Supply", "Demand", "어느 공장에서 어느 공장으로" | **E. 공장 흐름** | SCR-005 |
| "화면 그대로", "사이즈별", "Line × Style × Type" | **F. 화면 재현** | SCR-005 |
| "Return Rate", "회수율", "후보충 비율", "REPLEN/DEFECT" | **H. Return Rate (경량)** | SCR-006 |
| "화면 그대로", "하단표", "Incoming + Replenishment + Rate 같이", "C.GRADE RETURN", "OS&D Rate (%)" | **H'. 화면 풀 재현** | SCR-006 |

---

## 3. SQL 패턴

### 3-A. OS&D 종합 (4 Status)

**산출**: REQUEST / OUTGOING / INCOMING / BALANCE 한 번에.

**사용 metric**:
- `osnd_request_qty`, `osnd_outgoing_qty`, `osnd_incoming_qty`, `osnd_balance_qty`

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_summary`](../functions/quality-osnd.md#fn_osnd_summary)

**핵심 룰**:
- `CANCEL_YN = 'N'` 필수 — 취소된 OS&D 제외
- 출고 판정: `O_SCN_DT IS NOT NULL` ([확정: 라인 379])
- 입고 판정: `I_SCN_DT IS NOT NULL` ([확정: 라인 295])
- BALANCE = REQUEST - INCOMING (INCOMING 만 봄, OUTGOING 따로)

[확정: P_MSPQ38100S_Q 라인 133-379 검증]

---

### 3-B. 타입별 분석 (D/L/I/S)

**산출**: OSND_TYPE 별 metric (D=Damage, L=Lost, I=Issue, S=Shortage).

**사용 metric**:
- `osnd_damage_qty`, `osnd_lost_qty`, `osnd_issue_qty`, `osnd_shortage_qty`

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_by_type`](../functions/quality-osnd.md#fn_osnd_by_type)

**참고**:
- OSND_TYPE 코드 의미는 `MSBS_CODE_MASTER.CODE_CLASS_CD='PQ_OSND_TYPE'` 에서 lookup
- D=Damage, L=Lost, I=Issue, S=Shortage [확정: 사용자 지침 + 프로시저 라인 99]

---

### 3-C. 일자별 발생 추이

**산출**: OSND_DATE 별 발생량.

**사용 metric**: `osnd_request_qty`, `osnd_event_count`

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_daily_trend`](../functions/quality-osnd.md#fn_osnd_daily_trend)

---

### 3-D. 후보충 잔량 상세

**산출**: 처리 안 된 OS&D (Balance > 0). 출고 미완 vs 입고 미완 구분.

**사용 metric**: `osnd_balance_qty`

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_balance_detail`](../functions/quality-osnd.md#fn_osnd_balance_detail)

**참고**: "출고는 됐고 입고는 미완" 인 게 진짜 in-transit (배송 중). "출고도 미완" 은 아직 보내지도 않은 것.

---

### 3-E. 공장 간 보충 흐름

**산출**: SUPPLY_PLANT_CD → DEMAND_PLANT_CD 흐름별 수량.

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_plant_flow`](../functions/quality-osnd.md#fn_osnd_plant_flow)

---

### 3-F. SCR-005 화면 재현 (4 STATUS × 사이즈 PIVOT)

**산출**: 화면 그대로 — Line × OSND_DATE × CMP × Model × Style × Type × Supply Plant × STATUS × 43개 사이즈 컬럼.

**사용 metric**: `osnd_request_qty_screen`, `osnd_outgoing_qty_screen`, `osnd_incoming_qty_screen`, `osnd_balance_qty_screen`

**SQL 골격**: → [`functions/quality-osnd.md#fn_osnd_screen_pivot`](../functions/quality-osnd.md#fn_osnd_screen_pivot)

부분 재현용 함수:
- REQUEST 만 → [`#fn_osnd_request_by_size`](../functions/quality-osnd.md#fn_osnd_request_by_size)
- OUTGOING 만 → [`#fn_osnd_outgoing_by_size`](../functions/quality-osnd.md#fn_osnd_outgoing_by_size)
- INCOMING 만 → [`#fn_osnd_incoming_by_size`](../functions/quality-osnd.md#fn_osnd_incoming_by_size)
- STYLE 콤보 → [`#fn_osnd_style_list`](../functions/quality-osnd.md#fn_osnd_style_list)

**핵심 룰**:
- `CFM_DT IS NOT NULL` 필수 ([확정: 라인 104, 208, 294, 378])
- 사이즈별 컬럼 = `OSND_EX_QTY / 2` (L/R 켤레 환산)
- LINE = `IP.SUB_WC_CD`, CMP = `SUBSTR(SUPPLY_OP_CD, 1, 2)`

---

### 3-H. SCR-006 일자별 Return Rate (경량)

**산출**: IN_DATE 별 DEFECT/REPLEN 수량 + Return Rate %. (Incoming Qty, OS&D Rate 제외)

**사용 metric**: `osnd_return_rate`, `osnd_replen_qty`, `osnd_defect_qty`

**SQL 골격**: → [`functions/quality-osnd.md#fn_return_rate_daily`](../functions/quality-osnd.md#fn_return_rate_daily) (변형 A: LMES 원본 / 변형 B: OCI DEFECT 분기 단독)

**언제 사용**: Return Rate % 만 필요한 경우 (경량 — 4분기 UNION 안 함).

**핵심 룰**:
- `V_PQ_EX_OSND_V3` 는 OCI 에 없음 → `functions/quality-osnd.md` §V 의 재현 CTE 사용
- `OSND_TYPE IN ('D', 'S')` ([확정: 라인 115, 2025.09.22 it.fikri])
- 날짜 기준은 `IN_DATE` (입고일) — `OSND_DATE` 와 다름
- Return Rate = `REPLEN_QTY / DEFECT_QTY * 100` (소수점 둘째 자리)

[확정: SP_GMES00142_Q_JJ_V5 라인 85-127 + V_PQ_EX_OSND_V3 정의 검증]

---

### 3-H'. SCR-006 화면 하단표 풀 재현

**산출**: 화면 하단 6행 표 전체 — Incoming Qty / OS&D Qty / Replen Qty / Replen Rate % / OS&D Rate %.

**사용 metric**: `osnd_in_qty`, `osnd_defect_qty`, `osnd_replen_qty`, `osnd_return_rate`, `osnd_rate_pct`

**SQL 골격**: → [`functions/quality-osnd.md#fn_return_rate_daily_full`](../functions/quality-osnd.md#fn_return_rate_daily_full) (변형 A: LMES 원본 / 변형 B: OCI 4분기 UNION)

**언제 사용**:
- 사용자가 화면 그대로 보고 싶다고 한 경우 ("하단표", "Incoming + Replenishment + Rate 같이", "OS&D Rate")
- 차트 막대 (C.GRADE RETURN / REPLENISHMENT) 와 % 라인을 모두 산출할 때
- Replenishment Rate 외에 OS&D Rate (%) 도 필요한 경우

**핵심 룰**:
- §3-H 의 모든 룰 + 추가:
- 4분기 UNION 필수 — Incoming Qty (PROD_QTY) 는 분기 2~4 (`MSPQ_MATERIAL_MOVE`, `MSPD_PCARD_RESULT`) 에서만 채워짐
- OSND_TYPE 필터 — Oracle 에서 빈 문자열 `''` = NULL 이므로 `OSND_TYPE IS NULL` 한 조건으로 분기 2~4 모두 잡힘. 프로시저 원본 (SP_GMES00142_Q_JJ_V5 라인 115) 과 동일.
- OS&D Rate (%) = `DEFECT_QTY / PROD_QTY × 100` ([추측: 클라이언트 표현식] — 프로시저 CV_2 는 PER 만 산출, OS&D Rate 컬럼은 클라이언트 그리드 표현식으로 추정)
- 의존 사용자 정의 함수 `FN_GET_STYLE_INFO`, `FN_GET_PCARD_PLANT` 부재 시 §V-5 대체 방안 적용

**프로시저 컬럼 별칭 (CV_2 원본 — SP_GMES00142_Q_JJ_V5 라인 87-110)**:

| 출력 컬럼 | 산식 | 화면 위치 |
|---|---|---|
| `PROD_QTY` | `SUM(IN_QTY)` | Incoming Quantity (Prs) |
| `DEFECT_QTY` | `SUM(DEFECT_QTY)` | OS&D Quantity (Prs) / 차트 C.GRADE RETURN 막대 |
| `REPLEN_QTY` | `SUM(REPLEN_QTY)` | Replenishment (Prs) / 차트 REPLENISHMENT 막대 |
| `PER` | `ROUND(DECODE(SUM(DEFECT_QTY),0,0, SUM(REPLEN_QTY)/SUM(DEFECT_QTY)*100), 2)` | Replenishment Rate (%) / 차트 % 라인 |
| `YMD` | `'02 Mar - 06 Mar'` 형식 (IN_DATE ~ MAX(REPLEN_DATE)) | 차트 X축 라벨 |
| `OSND_RATE_PCT` | 함수에서 추가 (프로시저에 없음) | OS&D Rate (%) [추측] |

**차트 막대 라벨 매핑**:
- 왼쪽 막대 "C.GRADE RETURN" = OS&D Quantity (DEFECT_QTY)
- 오른쪽 막대 "REPLENISHMENT" = Replenishment (REPLEN_QTY)
- 자주색 라인 "%" = Replenishment Rate (Return Rate %)

[확정: SP_GMES00142_Q_JJ_V5 라인 85-127 + V_PQ_EX_OSND_V3 정의 라인 4-117 검증]
[추측: OS&D Rate (%) 산식 — 실제 화면 결과와 한 번 대조 필요]

---

### 3-I. SCR-006 Target 기준선

**산출**: 차트의 Target % (단일 값).

**SQL 골격**: → [`functions/quality-osnd.md#fn_return_rate_target`](../functions/quality-osnd.md#fn_return_rate_target)

`MSBS_CODE_MASTER.CODE_CLASS_CD='PQ_INSPECT_TYPE'`, `SUB_CODE='EX'` 의 `EXTRA_COLUMN1`.

---

### 3-J. SCR-006 달력 일자 컬럼

**산출**: 그리드의 일자별 컬럼 헤더용.

**SQL 골격**: → [`functions/quality-osnd.md#fn_return_rate_calendar`](../functions/quality-osnd.md#fn_return_rate_calendar)

**주의**: 프로시저는 `PLANT_CD='3110'` (JJ) 하드코딩. 다른 plant 분석 시 변경.

---

### 3-K. SCR-006 차트 break 설정

**산출**: `AutoScaleBreaks_MaxCount` 단일 값.

**SQL 골격**: → [`functions/quality-osnd.md#fn_return_rate_break_max`](../functions/quality-osnd.md#fn_return_rate_break_max)

---

### 3-L. SCR-006 콤보박스 — Plant

**SQL 골격**: → [`functions/quality-osnd.md#fn_combo_plant`](../functions/quality-osnd.md#fn_combo_plant)

---

### 3-M. SCR-006 콤보박스 — Process

**SQL 골격**: → [`functions/quality-osnd.md#fn_combo_process`](../functions/quality-osnd.md#fn_combo_process)

`PQ_EX_OSND_SUPPLY_OP_CD` 코드 마스터에서 공급 plant 별 매핑.

---

## 4. 검증 (Invariants)

### 4-1. Balance 공식 (SCR-005)

- `BALANCE = REQUEST - INCOMING` (입고 안 된 것 = 처리 미완료)
- OUTGOING 도 BALANCE 와 별개로 봐야 함 (출고는 됐지만 입고 안 됨 = in-transit)

### 4-2. CANCEL_YN

- 모든 metric 에 `CANCEL_YN = 'N'` 필수 — 취소 분석 시 외에는 항상.

### 4-3. 시간 순서

- OSND 발생 → 출고 → 입고 (O_SCN_DT < I_SCN_DT)
- 데이터에서 출고가 입고보다 먼저인 게 정상 (CKP 출고 → JJ 입고 시간차).

### 4-4. Return Rate 범위 (SCR-006)

- `0 ≤ Return Rate (%) ≤ 100` — DEFECT 가 0 이면 0 (DECODE 로 zero-division 보호)
- `REPLEN_QTY ≤ DEFECT_QTY` 항상 성립 (입고 완료된 양 ≤ 발생량)
- 위반 시 데이터 이상 또는 분기 누락 의심

### 4-4'. 화면 풀 재현 검증 (§3-H')

- `0 ≤ OS&D Rate (%) ≤ 100` — PROD_QTY (= IN_QTY 합) 가 0 이면 0
- `DEFECT_QTY ≤ PROD_QTY` 보통 성립 (입고된 양 중 OS&D — 일반적으로 1% 미만)
  - 예외: OS&D 의 IN_DATE 와 일반 입고의 IN_DATE 가 정확히 같지 않을 수 있어 일자별 비교 시 어긋날 수 있음
- PROD_QTY = 0 인 일자 = 그 날 입고가 없는데 OS&D 만 있는 비정상 — 데이터 분기 누락 의심
- `OS&D Rate (%)` 산식은 `[추측: 클라이언트 표현식]` — 프로시저에 명시 정의 없음, 화면 실값과 한 번 대조 필요

### 4-5. SCR-006 재현 CTE 검증

OCI 재현 결과는 `functions/quality-osnd.md` §V-3 의 비교 SQL 로 LMES 원본과 대조 가능. 다음이 일치해야 함:
- 같은 기간·plant 의 row count
- DEFECT_QTY 합계 (분기 1 만 영향)
- REPLEN_QTY 합계 (분기 1 만 영향)
- IN_QTY 합계 (분기 2~4 합산)

---

## 5. 함정

### 5-1. SUPPLY vs DEMAND Plant

- `SUPPLY_PLANT_CD` = 보충품을 보내는 공장 (예: CKP)
- `DEMAND_PLANT_CD` = 보충품을 받는 공장 (예: JJ)

사용자가 "JJ Plant 의 OS&D" 라고 하면 어느 쪽인지 확인 (디폴트는 보통 DEMAND = 받는 쪽).

### 5-2. OSND_TYPE 코드 lookup

- 코드만 보지 말고 MSBS_CODE_MASTER 로 이름 변환
- D=Damage, L=Lost, I=Issue, S=Shortage

### 5-3. CANCEL_YN 누락

- 빠뜨리면 취소된 OS&D 까지 셈 → 수량 부풀려짐.

### 5-4. O_SCN_DT, I_SCN_DT 의미

- 둘 다 NULL = 발생만 됐고 보충 행위 시작 안 함
- O 만 있음 = 출고 됐고 배송 중
- O, I 둘 다 있음 = 보충 완료

### 5-5. SCR-006 (External OS&D Return Rate) 처리

- `V_PQ_EX_OSND_V3` 뷰는 **OCI 에 없음** → `functions/quality-osnd.md` 의 **§V 재현 SQL** 사용
- 환경에 따라 두 변형 중 선택:
  - **변형 A**: LMES 직접 접근 가능 → 원본 뷰 `LMES.V_PQ_EX_OSND_V3` 호출
  - **변형 B** (디폴트): OCI 만 가능 → 재현 CTE `OSND_V3_REPLICA` 인라인 사용
- 재현 SQL 의존 OCI 테이블 존재 여부는 사전 확인 (`functions/quality-osnd.md` §V-4 의 체크리스트):
  - `MSPQ_EX_OSND`, `MSPQ_RPT_IP`, `MSBS_CODE_MASTER`, `MSPQ_MATERIAL_MOVE`, `MSPD_PCARD_RESULT`, `MSBS_PLANT`
- 의존 사용자 정의 함수 (`FN_GET_STYLE_INFO`, `FN_GET_PCARD_PLANT`, `FN_GET_DEFECT_REASON`) 부재 시 §V-5 의 대체 방안 적용
- Return Rate 계산만 필요하면 DEFECT 분기 1 만 사용 (경량). PROD_QTY/IN_QTY 통합 필요 시 4 분기 전체 UNION

### 5-6. SCR-006 의 OSND_TYPE 필터 변경 이력

- ~2022/11/18: `OSND_TYPE = 'D' OR NULL` (Damage 만)
- 2025/09/22 ~ : `OSND_TYPE IN ('D', 'S') OR NULL` (Damage + Shortage)
- 사용자가 과거 분석을 요청하면 어느 시점인지 확인 필요

---

## 6. 답변 형식

기본 구조:

```
1. 한 줄 요약 (어느 화면 / 어느 분석 능력 사용했는지)
2. 결과 표
   - SCR-005: 종합 (Request/Outgoing/Incoming/Balance) / 타입별 / 일자별 / 잔량 상세 / 공장 흐름 / 사이즈 PIVOT
   - SCR-006: 일자별 Return Rate (DEFECT/REPLEN/PER) / Target 비교
3. 사용한 SQL (펼침)
   - SCR-006 변형 B 사용 시 재현 CTE 출처 (functions §V-2) 명시
4. 사용한 metric / 화면:
   - SCR-005 → `external_osnd_balance.yml` (osnd_request_qty 등)
   - SCR-006 → 같은 파일의 `osnd_return_rate`, `osnd_defect_qty`, `osnd_replen_qty`
5. 검증 (§4 invariants)
6. (있을 때) 한계 — 의존 테이블/함수 부재로 인한 컬럼 누락 등
```

추가 가공:
- "후보충 현황" → D 잔량 상세 + 시간 경과 강조 (오래된 미완료 우선)
- "그래프" → 일자별 추이/Return Rate 는 텍스트 막대 또는 visualize 도구
- "리포트" → `data-analysis-report` skill 연계

---

## 7. 자주 발생하는 모호성

| 사용자 표현 | 확인 |
|---|---|
| "OS&D" | External OS&D 디폴트 (이 도메인) |
| "Plant" | SUPPLY 인지 DEMAND 인지 — 디폴트는 양쪽 둘 다 OR |
| "어제" | SCR-005 → `OSND_DATE` / SCR-006 → `IN_DATE` 디폴트 |
| "처리 안 된" | I_SCN_DT IS NULL (Balance) |
| "후보충 안 끝난" | 같음 (D 잔량 상세) |
| "Return Rate", "회수율" | SCR-006 — `functions/quality-osnd.md` §V 재현 CTE 사용 (변형 B 디폴트). Return Rate 만 필요하면 §3-H (경량), 화면 하단표 6행 모두 필요하면 §3-H' (풀 재현) |
| "Incoming Qty", "OS&D Rate", "화면 그대로", "C.GRADE RETURN" | §3-H' (풀 재현) — 4분기 UNION 필수 |
| "Damage 만" / "Damage + Shortage" | SCR-006 의 `OSND_TYPE` 필터 — 디폴트는 `'D','S'` (2025.09.22 이후) |
| "Plant 3110 아닌" | SCR-006 의 `fn_return_rate_calendar` 는 PLANT_CD 하드코딩 → 변경 필요 명시 |
