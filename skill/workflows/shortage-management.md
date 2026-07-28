# Shortage Management — Analysis Workflow

부족분 관리 도메인 (SCR-001, 화면 Shortage Balance Checking) 처리 절차.
대표 by-size 화면 = **BALANCE IP PH - PRODUCTION (AFTER SCAN UV) by size** → §3-E `fn_shortage_screen`.

| 항목 | 값 |
|---|---|
| 화면 | Shortage Balance Checking / BALANCE IP PH - PRODUCTION (AFTER SCAN UV) by size |
| 프로시저 | `LMES.P_MSPD90000S_Q_V14` |
| 메인 테이블 | `OCI.MSPD_PCARD_RESULT` |
| 보조 테이블 | `MSBS_ITEM_STYLE`, `MSBS_WORK_CENTER`, `MSPD_PROD_GROUP`, `MSBS_ITEM_CLASS`, `MSPD_BATCH_PLAN` |
| metric 파일 | `metrics/shortage_balance.yml` |
| 보조 1층 | `semantic_models/MSPD_PCARD_RESULT.yml`, `semantic_models/MSPD_PROD_GROUP.yml` |

**공통 원칙은 `workflows/_common.md` 참조.**

---

## 1. 이 도메인이 가진 분석 능력

프로시저 `V_P_DIV` 6 개 분기:

| 분기 | 의미 | 분석 능력 |
|---|---|---|
| `'P'` | Production Shortage | 생산 안 된 부족분 (PROD_DATE='19991231') |
| `'O'` | Outgoing Shortage | 출고 안 된 부족분 (OUT_DATE='19991231', END_ROUTING='Y') |
| `'B'` | Both | 위 둘 합산 |
| `DETAIL_P` | Production 상세 | 라인+스타일+사이즈별 |
| `DETAIL_O` | Outgoing 상세 | 같음 |
| (UNION) | FG → UP 변환 | ITEM_CLASS_TYPE='FG' 입력 시 'UP' 으로 변환 |

분석 능력으로 정리:

| 분석 능력 | 무엇을 보나 |
|---|---|
| **A. 부족분 잔량 (현재 시점)** | Production / Outgoing / Both / FG 별 전체 잔량 합계 |
| **B. 라인 × 스타일 × 사이즈별 분포** | 라인별 그룹 → 스타일 → 사이즈 (tidy 행) |
| **C. 일자별 추이** | FA_DATE 별 GROUP BY (예: 지난 7 일) |
| **D. 공정별 (OP_CD)** | IP/PH 공정 분리, 공정별 부족분 비교 |
| **E. 화면 그대로 재현 (by size PIVOT)** | BALANCE IP PH - PRODUCTION (AFTER SCAN UV) by size 그리드를 라인×모델×스타일×ItemClass×Color×FA_Date×Size 로 재현 (→ 리포트/엑셀) |

---

## 2. 처리 흐름

```
1) 질문 분해     → 기준일/Plant/OP/Item Class/분해단위 추출
2) 분석 능력 매칭 → A/B/C/D/E 중 어느 것
3) 입력값 고정   → 미지정 항목 되묻기
4) SQL 작성     → 해당 분석의 SQL 패턴 (§3)
5) DB 조회
6) 답변 작성 (필요 시 리포트/엑셀 가공 — §6)
```

### 2-1. 질문 분해 항목

| 항목 | 필수 | 디폴트 / 되묻기 |
|---|---|---|
| 기준일 (FA_DATE) | 필수 | "지난 7일" 같은 기간이면 BETWEEN. 단일 일자면 = |
| Plant | 필수 | 없으면 되묻기 (화면 재현 E 는 3120 CKP 고정 디폴트) |
| OP | 선택 | 없으면 IP/PH 5 개 전체. (E 는 OP 필터 안 씀 — END_ROUTING 으로 압축) |
| Item Class Type | 선택 | 없으면 전체. FG 입력 시 'UP' 변환 |
| FA W/C (라인) | 선택 (E) | 화면 재현 시 라인 CSV. 비우면 전체 라인 |
| 분해 단위 | 선택 | "라인별" → B, "일자별" → C, "공정별" → D, "화면 그대로/by size" → E |
| Production / Outgoing 구분 | 선택 | 없으면 Both (E 디폴트는 Production) |

**화면 재현(E) 3-파라미터**: 사용자가 `FA Date · FA W/C · Item Class Type` 만 주면 나머지(Plant 3120, Production, END_ROUTING='Y', 마감 제외, 색상 BOM)는 고정. 누락 시 이 3개를 되묻는다.

### 2-2. 분석 능력 매칭 키워드

| 사용자 표현 | 분석 |
|---|---|
| "현재 부족분", "남아있는", "잔량", "전체" | **A. 잔량** |
| "라인별 부족분", "스타일별", "사이즈별", "라인 × 스타일" | **B. 분포** |
| "일자별", "추이", "증감", "지난 7일" | **C. 추이** |
| "IP 부족분", "PH 부족분", "공정별" | **D. 공정별** |
| "화면 그대로", "화면 재현", "이 양식대로", "by size", "BALANCE IP PH", "AFTER SCAN UV", "Shortage 화면", "엑셀로 그대로", "FA W/C 별 사이즈" | **E. 화면 재현** |

---

## 3. SQL 패턴

### 3-A. 부족분 잔량 (현재 시점)

**산출**: Production / Outgoing 부족분 전체 합계.

**사용 metric**:
- `production_shortage_qty` (PROD_DATE='19991231')
- `outgoing_shortage_qty` (OUT_DATE='19991231', END_ROUTING_YN='Y')
- `total_shortage_qty` (둘 합)
- `fg_production_shortage_qty` (UP 만)

**SQL 골격**: → [`functions/shortage-management.md#fn_shortage_balance`](../functions/shortage-management.md#fn_shortage_balance)

**핵심 룰**:
- 미생산 판정: `PROD_DATE = '19991231'`
- 미출고 판정: `OUT_DATE = '19991231'`
- Plant 필터는 **`PLANT_CD`** (실적 ITPO_WC_PLANT_CD 가 아님 — 부족분은 계획 책임 공장 기준)
- `MSPD_PROD_GROUP.CLOSING_YN = 'N'` 필수 — 마감된 그룹 제외

[확정: P_MSPD90000S_Q_V14 라인 32-205 검증]

---

### 3-B. 라인 × 스타일 × 사이즈별 분포

**산출**: 라인(FA_WC_CD) → 스타일 → 사이즈별 부족분 수량 (tidy 행).

**SQL 골격** (Production 기준): → [`functions/shortage-management.md#fn_shortage_by_line_style_size`](../functions/shortage-management.md#fn_shortage_by_line_style_size)
(Outgoing 기준은 functions 파일의 주석 참조)

**참고**: 화면처럼 사이즈를 컬럼(15개) 으로 PIVOT 하려면 추가 처리 — 디폴트는 행 단위.
**⚠ 화면 by-size 그리드 그대로 재현은 §3-E 사용** (이 함수는 OP별·END_ROUTING 무관이라 카드 중복 집계됨).

**MCS Color 컬럼이 필요한 경우** (화면 재현 등): → [§X. MCS_COLOR 인라인 풀이](#x-mcs_color-인라인-풀이-oci-환경) 참조. OCI 환경에서는 `FN_MCS_COLOR` 미적용이므로 대체 경로 필수.

---

### 3-C. 일자별 추이

**산출**: FA_DATE 별 부족분 일자별 합계.

**SQL 골격**: → [`functions/shortage-management.md#fn_shortage_daily_trend`](../functions/shortage-management.md#fn_shortage_daily_trend)

**참고**:
- `DATE_RANGE` CTE 로 빈 일자도 포함 (LEFT JOIN)
- 사용자가 "지난 7일"이면 LEVEL <= 7
- 증감 분석은 LAG() 윈도우 함수 추가 가능

---

### 3-D. 공정별 (OP_CD) 부족분

**산출**: OP_CD 별 부족분 (IP/PH 공정 비교).

**SQL 골격**: → [`functions/shortage-management.md#fn_shortage_by_op`](../functions/shortage-management.md#fn_shortage_by_op)

---

### 3-E. 화면 그대로 재현 (BALANCE IP PH - PRODUCTION (AFTER SCAN UV) by size)

**산출**: 화면(SCR-001 의 by-size 뷰) 과 동일한 라인 × 모델 × 스타일 × ItemClass × MCS Color × FA Date × Size 부족분 그리드.

**바꾸는 값 3개**: `FA Date(기간)` · `FA W/C(라인 CSV, 비우면 전체)` · `Item Class Type(CSV, 비우면 전체)`.
Plant=3120(CKP), Div=Production 고정 (요청 시 Outgoing/Both 로 확장).

**SQL 골격**: → [`functions/shortage-management.md#fn_shortage_screen`](../functions/shortage-management.md#fn_shortage_screen)

**핵심 룰 (이게 화면 숫자 일치의 조건)**:
- **`END_ROUTING_YN='Y'`** = 화면명의 **"AFTER SCAN UV"**(마지막 공정/UV 스캔). 카드 1장=1행 압축. **OP_CD 로 합치지 말 것** — 빠뜨리면 약 4~5배 부풀어 화면 불일치(5,426 → ~26,556).
- `PROD_DATE='19991231'` (미생산) · `PLANT_CD='3120'` · `CLOSING_YN='N'`.
- MCS Color 는 §X (BOM 인라인 EXACT + STYLE fallback).

**답변/리포트화**: SIZE 동적 PIVOT + (LINE,STYLE) Total + MODEL G-Total + 전체 G-Total. → §6 의 리포트화 경로 참조 (엑셀/리포트/대시보드).

[확정: 2026-03-01~07 / 3120 / CP / FGA16,FGA19 → G-Total 5,426 (AIR MAX DAWN 108 / P-6000 5,318), CP06 BV1021-020 = 634 화면 일치]

---

## 4. 검증 (Invariants)

### 4-1. Both = Production + Outgoing

- `total_shortage_qty = production_shortage_qty + outgoing_shortage_qty`
- 같은 PCARD 가 양쪽에 잡힐 수도 있으니 정확히 합 같지 않을 수 있음 — 이 경우 description 에 명시.

### 4-2. FG 별도 카운트

- `fg_production_shortage_qty` 는 `ITEM_CLASS_TYPE = 'UP'` 만 카운트
- 다른 metric (Production Shortage, Outgoing Shortage) 는 `ITEM_CLASS_TYPE <> 'FG'` 로 FG 제외

### 4-3. Closing 검증

- `MSPD_PROD_GROUP.CLOSING_YN = 'N'` 인 그룹만 카운트
- 사용자가 "다 보여줘" 라고 해도 마감된 그룹은 제외 — 명시적 안내 필요.

### 4-4. 화면 재현(E) 검증

- 검증 케이스: `2026-03-01~07 / 3120 / CP / FGA16,FGA19` → G-Total **5,426** (AIR MAX DAWN 108 / P-6000 5,318) 나오면 정상.
- 안 맞으면 점검: ① `END_ROUTING_YN='Y'` 들어갔는지 ② OP_CD 필터를 잘못 넣지 않았는지 ③ `CLOSING_YN='N'` IN-서브쿼리 ④ 색상 BOM 키(ITEM_CD ↔ PARENT_ITEM_CD).

---

---

## X. MCS_COLOR 인라인 풀이 (OCI 환경)

### X-1. 배경

원본 `LMES.FN_MCS_COLOR(prod_group_no, item_class)` 는 `MSPD_BATCH_PLAN` + `MSPD_PROD_ORDER_BOM` 서브쿼리 의존. **OCI 에 `MSPD_PROD_ORDER_BOM` 부재** (ORA-00942) 이므로 `functions/shortage-management.md §FN_MCS_COLOR` 의 인라인 풀이 (`ITEM_PATH LIKE` 매칭) 도 그대로는 동작 안 함. 대안 인라인 경로 필요.

### X-2. 적용 시점

- SCR-001 화면 재현에서 MCS Color 컬럼이 필요한 모든 분석 능력 (§3-B 라인 × 스타일 × 사이즈, §3-E 화면 그대로 재현 등)
- 화면 캡처에 MCS Color 컬럼이 보이면 디폴트로 이 경로 사용
- 컬러 차원이 불필요한 경우 (§3-A 종합, §3-C 일자별 추이, §3-D 공정별) 는 적용 안 함 — 쿼리 비용만 늘어남

### X-3. 핵심 룰

PCARD ↔ BATCH_PLAN BOM 키 관계:
```
PCARD.(PROD_GROUP_NO, ITEM_CD) = BATCH_PLAN.(PROD_GROUP_NO, PARENT_ITEM_CD)
```
PCARD 의 `ITEM_CD` (예: `IM9013100CP01`) = STYLE_CD 하이픈 제거 + ITEM_CLASS = 공정 단위 부모 ITEM. BATCH_PLAN 의 `PARENT_ITEM_CD` 와 동일 값 체계 → 이 키로 join 하면 자식 부품의 `MCS_COLOR_CD` 추출 가능.

`MSPD_BATCH_PLAN.MCS_COLOR_CD` 의 값은 이미 `"BLACK(00A)"`, `"WHITE(10A)"`, `"CLEAR(91B)/20% TINT(C43)"` 텍스트 형식 (SCR-005 의 `MSBS_ITEM.MCS_COLOR_CD` 와 동일 포맷). **그대로 표시명 사용 가능** — `fn_color_lookup_cte` 박제 매핑 불필요.

→ SQL 골격은 [`functions/shortage-management.md#fn_mcs_color_inline_oci`](../functions/shortage-management.md#fn_mcs_color_inline_oci) 사용.

### X-4. 2 단 fallback 매칭 (필수)

1 단 정확 매칭 `(PROD_GROUP_NO, PARENT_ITEM_CD)` 만으로는 약 **68 %** 매칭 (예: 7 일치 127 키 중 87).

못 잡힌 키 패턴 — **PP01/PP02/PP03/PP06** (Packing 공정류). BOM 자식 부품이 없는 마지막 공정이라 BATCH_PLAN 에 부모-자식 관계 기록 안 됨.

2 단 STYLE 레벨 fallback (`SUBSTR(PARENT_ITEM_CD, 1, LENGTH-4)` = ITEM_CLASS 4 자리 제거 = STYLE) 추가하면 **100 %** 매칭. 같은 스타일 안에서 다른 ITEM_CLASS (CP02/CP03/II01 등) 는 동일 색상이라는 도메인 규칙 활용.

[확정: 2026-03-08~14 검증, EXACT 87 + STYLE_FALLBACK 40 = TOTAL 127, UNMATCHED 0]

### X-5. 함정

- **ITEM_CLASS 체계 불일치** — `PCARD_RESULT.ITEM_CLASS` 는 공정 분류 (CP01/CP02/PP91/II01 등), `BATCH_PLAN.ITEM_CLASS` 는 BOM 부품 분류 (OR/PZ/UL/IZ 등). 두 ITEM_CLASS 로 직접 join 시도 금지 — 0 매칭. PCARD 의 `ITEM_CD` ↔ BATCH_PLAN 의 `PARENT_ITEM_CD` 매칭이 정공법.
- **빈 코드 3 종 제외** — `MSPD_BATCH_PLAN.MCS_COLOR_CD` 에 `'NONE'`, `' '` (공백 1 자), NULL 이 의미 없는 값으로 섞여있음. WHERE 절에서 모두 제외.
- **FS 계열 ITEM_CLASS 는 NULL** — `SUBSTR(R.ITEM_CLASS, 1, 2) = 'FS'` 면 항상 NULL. 원본 `FN_MCS_COLOR` 의 마지막 조건과 동일 사양.
- **LISTAGG 4000 자 제한** — 그룹당 색이 매우 많을 때 ORA-01489 위험. 발생 시 `XMLAGG` 로 교체 (functions §FN_MCS_COLOR 주의사항과 동일).
- **STYLE 추출 시 끝 4 자 제거 가정** — ITEM_CLASS 가 4 자 (CP01, PP06, II01 등) 라는 도메인 규약. 5 자 이상 ITEM_CLASS 가 등장하면 패턴 재검토.

### X-6. 검증 (Invariants)

신규 기간 분석 시작 전 매칭률 확인 권장 — SQL 은 [`functions/shortage-management.md#fn_mcs_color_match_check`](../functions/shortage-management.md#fn_mcs_color_match_check) 사용.

기대치:
- EXACT_MATCH 비율 60~75% (Packing 비율에 따라 변동)
- STYLE_FALLBACK 으로 누락분 100% 보충
- UNMATCHED > 0 이면 신규 ITEM_CLASS 패턴 등장 의심 → §X-5 함정 재점검
- FS 계열은 매칭률 계산에서 제외 (정상 NULL)

---

## 5. 함정 (자주 틀리는 곳)

### 5-1. FA_DATE vs PROD_DATE 구분

- **FA_DATE**: "제조 예정일" (이날 만들기로 한 카드)
- **PROD_DATE**: "실제 생산일" (실제로 만들어진 날). 미생산이면 '19991231'

부족분의 핵심은 **FA_DATE 에 잡혔는데 PROD_DATE 가 '19991231'** 인 양 = 약속한 날에 못 만든 것.

### 5-2. Plant 컬럼 — 부족분은 PLANT_CD

생산 실적 분석 (SCR-002) 은 ITPO_WC_PLANT_CD 쓰지만, **부족분은 PLANT_CD** (계획 책임 공장).

[확정: P_MSPD90000S_Q_V14 라인 49 검증]

### 5-3. FG 처리

- 화면에서 ITEM_CLASS_TYPE='FG' 선택 시 SQL 안에서 'UP'으로 변환
- 다른 ITEM_CLASS_TYPE (IP/PH/BE/BU 등) 은 그대로

### 5-4. END_ROUTING_YN — 합계용 vs 화면(by size)용 구분 ★

- **부족분 "총량 합계"**(§3-A `fn_shortage_balance`, 공정별 작업 잔량 개념): Production 은 END_ROUTING **무관**(모든 공정).
- **화면 by-size 그리드 재현**(§3-E `fn_shortage_screen`): Production **도 `END_ROUTING_YN='Y'` 필수** — 화면명의 "AFTER SCAN UV"(마지막 공정/UV 스캔)에 해당. 카드 1장을 마지막 공정 1행으로 압축해 켤레 기준으로 셈. 빠뜨리면 약 4~5배 부풀어 화면과 불일치(검증: 5,426 → ~26,556).
- **Outgoing Shortage**: 항상 `END_ROUTING_YN='Y'` + `OUT_DATE='19991231'`.

[확정: 2026-03 화면 캡처 대조 — by size 그리드는 END_ROUTING='Y' 일 때만 일치]

### 5-5. CLOSING_YN 누락

- `MSPD_PROD_GROUP.CLOSING_YN = 'N'` 빠뜨리면 마감된 옛날 부족분까지 셈.
- 항상 EXISTS 또는 IN 서브쿼리.

---

## 6. 답변 형식 / 리포트화

기본 구조:

```
1. 한 줄 요약 — 현재 누적 부족분 N 켤레
2. 결과 표 — Production / Outgoing / Total 분리 (또는 화면 by-size 그리드)
3. 사용한 SQL (펼침)
4. 사용한 metric: shortage_balance.yml의 production_shortage_qty 등
5. 검증: Both = P + O ✓ / (E) 5,426 케이스 ✓
6. (있을 때) 한계
```

### 6-E. 화면 재현(E) 결과를 리포트로 만들기

`fn_shortage_screen` 의 tidy 결과(LINE…SIZE_CD, QTY)를 다음 순서로 가공:

1. **PIVOT**: SIZE_CD 를 컬럼으로 동적 전개(등장한 사이즈만). 행 합계 = Shortage.
2. **소계 행**: 맨 위 전체 `G-Total`, (LINE×STYLE) 마다 `Total`, 맨 아래 MODEL_NAME 별 `G-Total`.
3. **출력 형태 선택** (사용자 요청에 따라):
   - "엑셀로 / 다운로드" → **`xlsx` skill** 로 화면 레이아웃 그대로 .xlsx 생성.
   - "리포트 / 보고서 / Word" → **`data-analysis-report` skill** 연계 (사실/추정 분리 형식).
   - "메일로 / Gmail" → **`gmail-report-email` skill** 연계.
   - "대시보드 / 매번 갱신 / 라이브" → Cowork **live artifact**(create_artifact)로 — 컨트롤(Plant·ICT·FA W/C·Div·기간) + 동적 PIVOT + 엑셀 다운로드 버튼. (이미 제작된 `mes-production-status` 아티팩트가 이 형태)

추가 가공:
- "브리핑" → 표 + 핵심 수치 강조 (전일 대비 증감, Top 라인)
- "그래프" → 일자별 추이는 텍스트 막대 또는 visualize 도구

---

## 7. 자주 발생하는 모호성

| 사용자 표현 | 확인 |
|---|---|
| "부족분" | Production 만? Outgoing 만? Both? — 디폴트는 Both (단 화면 재현 E 는 Production) |
| "남아있는" | 현재 시점 잔량 (분석 능력 A) |
| "지난 7일" | 일자별 추이 (분석 능력 C) — 7 일 분 일자별 vs 7 일 누적? |
| "FG 부족분" | ITEM_CLASS_TYPE='UP' 으로 변환됨 안내 |
| "라인별" | FA_WC_CD 디폴트 |
| "화면 그대로 / by size" | **E. 화면 재현** — FA Date·FA W/C·Item Class Type 3개 확인 후 `fn_shortage_screen` |
