# In-Out Cross Check — Analysis Workflow

수불 관리 도메인 (SCR-003 P-O Cross + SCR-004 O-I Cross 통합) 처리 절차.

생산-출고-입고 흐름 전체의 정합성을 검증하는 도메인. 두 화면이지만 사용자 관점에서는 같은 자재 흐름의 두 단계.

| 항목 | 값 |
|---|---|
| 화면 | P-O Cross Check (SCR-003) + O-I Cross Check (SCR-004) |
| 프로시저 | `LMES.P_MSPD51000S_Q_V24` (P-O) + `LMES.P_MSPD52000S_Q_V39` (O-I) |
| 메인 테이블 | `OCI.MSPD_PCARD_RESULT` |
| 보조 테이블 | `MSBS_WORK_CENTER`, `MSBS_CHECKGROUP`, `MSBS_CHECKGROUP_WC`, `MSPD_PROD_GROUP`, `POP_PCARD_SCAN`, `POP_DEVICE` |
| metric 파일 | `metrics/po_cross_check.yml` + `metrics/oi_cross_check.yml` |
| 보조 1층 | `semantic_models/MSPD_PCARD_RESULT.yml`, `semantic_models/POP_PCARD_SCAN.yml`, `semantic_models/POP_DEVICE.yml` |

**공통 원칙은 `workflows/_common.md` 참조.**

---

## 1. 이 도메인이 가진 분석 능력

두 프로시저 모두 같은 6 분기 구조 (`V_P_WORK_TYPE`):

| 분기 | P-O (SCR-003) | O-I (SCR-004) |
|---|---|---|
| TEMPLATE | 템플릿 메타 | 템플릿 메타 |
| MAIN | Line 별 Prod/Out/매칭률 | Line 별 OK/Out Only/In Only/매칭률 |
| DETAIL | 라인별 PCARD 단위 상세 | 같은 패턴 |
| DETAIL_SIZE | 사이즈 분포 | 같은 패턴 |
| DETAIL_SIZE_DETAIL | 더 상세 | 같음 |
| SCAN_DATA | POP_PCARD_SCAN 이력 | POP_PCARD_SCAN 이력 |

분석 능력으로 정리:

| 분석 능력 | 무엇을 보나 |
|---|---|
| **A. P-O 단독** | 라인별 Prod/Out/Prod Only/Out Only/매칭률 |
| **B. O-I 단독** | 라인별 OK/Out Only/In Only/In/매칭률 |
| **C. 통합 흐름 (생산→출고→입고)** ★ | 같은 라인+일자에서 P-O 와 O-I metric 결합 |
| **D. 특이사항 PCARD 상세** | Out Only / In Only / Prod Only 의 PCARD 단위 |
| **E. 사이즈별 정합성** | SIZE_CD 그룹 + 정합률 |
| **F. 스캔 이력** (POP_PCARD_SCAN) | PCARD 별 스캔 시각·디바이스 추적 |

---

## 2. 처리 흐름

```
1) 질문 분해     → 기준일/Plant/OP/분해단위/특이사항 여부 추출
2) 분석 능력 매칭 → A~F 중 어느 것 (복수 가능)
3) 입력값 고정   → 미지정 항목 되묻기
4) SQL 작성     → 해당 분석의 SQL 패턴 (§3)
5) DB 조회
6) 답변 작성     → 특이사항 강조
```

### 2-1. 질문 분해 항목

| 항목 | 필수 | 디폴트 / 되묻기 |
|---|---|---|
| 기준일 | 필수 | 없으면 되묻기 |
| Plant (Country) | 필수 | 없으면 되묻기 |
| OP | 선택 | 없으면 IP/PH 5 개 전체 |
| 분해 단위 | 선택 | "라인별" 디폴트, "사이즈" → E, "PCARD" → D, "스캔 이력" → F |
| 특이사항 강조 여부 | 선택 | "특이사항" / "정합 안 된" 키워드 있으면 D |

### 2-2. 분석 능력 매칭 키워드

| 사용자 표현 | 분석 |
|---|---|
| "P-O", "P.O Cross", "생산-출고", "Prod Only" | **A. P-O** |
| "O-I", "O.I Cross", "출고-입고", "Cross-plant" | **B. O-I** |
| "수불", "전체 정합성", "생산-출고-입고", "흐름" | **C. 통합** |
| "특이사항", "Out Only", "In Only", "매칭 안 됨", "PCARD 상세" | **D. PCARD 상세** |
| "사이즈별 정합", "사이즈 매칭" | **E. 사이즈** |
| "스캔 이력", "디바이스", "누가 스캔", "POP" | **F. 스캔** |

---

## 3. SQL 패턴

### 3-A. P-O 단독 (라인별 Prod/Out/매칭률)

**산출**: 라인(WC_CD)별 PROD_QTY / OUT_QTY / PROD_ONLY_QTY / OUT_ONLY_QTY / 매칭률.

**사용 metric** (`metrics/po_cross_check.yml`):
- `prod_qty`, `out_qty`, `prod_only_qty`, `out_only_qty`, `po_match_rate`

**SQL 골격** (P-O 단순화): → [`functions/inout-cross-check.md#fn_po_cross_main`](../functions/inout-cross-check.md#fn_po_cross_main)

[확정: P_MSPD51000S_Q_V24 라인 87-273 검증]

---

### 3-B. O-I 단독 (라인별 OK/Out Only/In Only/In/매칭률)

**산출**: 라인별 OUT_IN_OK / OUT_ONLY / IN_ONLY / IN / 매칭률.

**사용 metric** (`metrics/oi_cross_check.yml`):
- `out_in_ok_qty`, `out_only_qty` (의미 다름!), `in_only_qty`, `in_qty`, `oi_match_rate`

**SQL 골격** (단순화 — 실제 프로시저는 더 복잡): → [`functions/inout-cross-check.md#fn_oi_cross_main`](../functions/inout-cross-check.md#fn_oi_cross_main)

[확정: P_MSPD52000S_Q_V39 라인 88-431 검증]

---

### 3-C. 통합 흐름 (P-O + O-I 결합) ★ 핵심 분석

**산출**: 같은 라인+일자에서 생산→출고→입고 전체 metric.

**전략**: A 와 B 의 결과를 라인 단위로 LEFT JOIN.

**SQL 골격**: → [`functions/inout-cross-check.md#fn_integrated_flow`](../functions/inout-cross-check.md#fn_integrated_flow)

**참고**:
- `PO_OUT_ONLY_QTY` 와 `OI_OUT_ONLY` 는 **이름 같지만 의미 다름**:
  - `PO_OUT_ONLY_QTY`: 생산 없는 출고
  - `OI_OUT_ONLY`: 입고 없는 출고
- 답변 시 컬럼명을 명확히 구분 (예: "출고만 있고 생산 없음" vs "출고만 있고 입고 없음")

---

### 3-D. 특이사항 PCARD 단위 상세

**산출**: 매칭 안 된 PCARD 의 상세 정보 (시간, 수량, Plant 등).

**SQL 골격** (Out Only PCARD 추출): → [`functions/inout-cross-check.md#fn_anomaly_pcard_out_only`](../functions/inout-cross-check.md#fn_anomaly_pcard_out_only)

비슷한 패턴으로:
- In Only: `OUT_DATE < '20010101'` 인 출고가 매칭 (실제로는 출고 미발생)
- Prod Only: `OUT_DATE <= '20000101'` (생산은 됐는데 출고 안 됨)

---

### 3-E. 사이즈별 정합성

**산출**: SIZE_CD 별 매칭 통계.

**SQL** — A/B 의 GROUP BY 에 SIZE_CD 추가: → [`functions/inout-cross-check.md#fn_size_match`](../functions/inout-cross-check.md#fn_size_match)

---

### 3-F. 스캔 이력 (POP_PCARD_SCAN)

**산출**: 특정 PCARD 의 스캔 시각·디바이스·결과.

**SQL 골격**: → [`functions/inout-cross-check.md#fn_pcard_scan_history`](../functions/inout-cross-check.md#fn_pcard_scan_history)

**참고**: LOG_MESSAGE 는 CLOB. 길면 `DBMS_LOB.SUBSTR(LOG_MESSAGE, 200, 1)` 사용.

---

## 4. 검증 (Invariants)

### 4-1. P-O 매칭률 공식

- `po_match_rate = 100 - (out_only_qty / out_qty) × 100`
- 100% = 모든 출고가 생산과 매칭
- **분모 0 (Out=0) 시 화면 NVL 디폴트 = 100.00** (`metrics/po_cross_check.yml#po_match_rate` 참조)

### 4-2. O-I 매칭률 공식

- `oi_match_rate = out_in_ok_qty / (out_in_ok_qty + out_only_qty + in_only_qty) × 100`
- 100% = 모든 출고/입고 1:1 매칭
- **분모 0 시 화면 NVL 디폴트 = 0.00** (★ P-O 와 다름. `metrics/oi_cross_check.yml#oi_match_rate` 참조)

### 4-3. 동음이의어 체크

- P-O 의 `out_only_qty` ≠ O-I 의 `out_only_qty`
- 답변에서 어느 쪽인지 컨텍스트로 명확히

### 4-4. Summary 산술 invariant (Cross-domain)

화면 PIVOT 에 PH/IP 만 보이고 나머지 8 종 CHECK_GROUP_CD (OS, PP, PU, II, CF, FS, UP, SL) 는 Summary 합에만 기여한다.

**P-O Summary 산식**:
```
Summary Prod = Σ (PH + IP + OS + PP + PU + II + CF + FS + UP + SL + IPJ) Prod
Summary Out  = Σ (PH + IP + OS + PP + PU + II + CF + FS + UP + SL + IPJ) Out
```

[확정: 2026-03-02 화면 L 03 검증 — PH Prod=1,727, 비표시 합=8,603, Summary Prod=10,330 ✓]

### 4-5. Cross-domain invariant (P-O ↔ O-I 정합)

같은 일자 같은 라인 같은 CHECK_GROUP 에 대해 P-O 와 O-I 가 다음 관계를 만족해야 한다.

```
P-O Out 합 = O-I (Out-In OK + Out Only) 합
```

라인별·공정별로 성립하며, Bottom Total / A1 Subtotal 단위에서도 성립한다.

[확정: 2026-03-02 ~ 03-06 5 일치 PH/IP 전체 + Bottom Total 검증 — 양변 완전 일치]

### 4-5-bis. P-O ↔ O-I 의 DT_GROUP / Summary 비대칭 ★

두 화면은 같은 MSPD_PCARD_RESULT 를 보지만 (1) CHECK_GROUP 셋이 다르고 (2) Summary 컬럼의 산식이 다르다. Cross-domain Summary 비교 시 반드시 고려.

| 항목 | SCR-003 (P-O) | SCR-004 (O-I) |
|---|---|---|
| DT_GROUP CHECK_GROUP 셋 | 10 종: **CF, FS, II, IP, OS, PH, PP, PU, SL, UP** | 11 종: **BC, CF, II, IP, IPF, OS, PH, PP, PU, SL, UP** |
| O-I 에만 있는 그룹 | — | **BC, IPF** |
| P-O 에만 있는 그룹 | **FS** | — |
| Summary 컬럼 산식 | 전 CHECK_GROUP 롤업 | **II / PP / IPF 제외 후 롤업** ★ |

[확정: P_MSPD51000S_Q_V24 vs P_MSPD52000S_Q_V39 reference DDL 대조 + 2026-03-02 ~ 03-06 5 일치 화면 캡쳐 검증]
[확정: P_MSPD52000S_Q_V39 라인 456 + 라인 504 — `LEFT OUTER JOIN SD ON LG_LIST.WC_CD = SD.FA_WC_CD AND SD.CHECK_GROUP_CD NOT IN ('II','PP','IPF')`]

**의미**:
1. **개별 라인의 PH/IP cell** — 양쪽 화면 모두 정상 (라인 단위 ROW_TYPE=1 의 첫 SELECT 는 모든 CHECK_GROUP 포함)
2. **Summary 컬럼 cell (Bottom Total + 라인별 Summary)** — O-I 에서만 II/PP/IPF 제외. 따라서:
   - O-I Bottom Total Sum (Out-In OK + Out Only + In Only) 은 PH/IP 가 아닌 다른 CHECK_GROUP 의 II/PP/IPF 분이 빠진 값.
   - 산출 SQL: `SUM(CASE WHEN ... AND CHECK_GROUP_CD NOT IN ('II','PP','IPF') THEN ... ELSE 0 END) AS SUM_*`
3. **Cross-domain invariant 4-5 의 Summary 비교 시 주의** — P-O Sum Out 에는 II/PP 포함, O-I Sum (OK+Out Only) 에는 II/PP/IPF 제외. 따라서:
   ```
   P-O Sum Out − O-I Sum (OK + Out Only)
     = (P-O 의 II + PP + IPF 분) + (O-I 의 비표시 CHECK_GROUP Out Only 누적)
   ```
   완전한 invariant 검증 시 양변에서 II/PP/IPF 를 동일하게 처리해야 함.

**자유 분석 답변 시 주의**:
- 사용자가 "O-I Summary 가 P-O Summary 보다 작은데 왜?" 라고 묻는 경우 II/PP/IPF 제외가 첫 번째 원인. 두 번째는 비표시 CHECK_GROUP Out Only 누적.

### 4-6. Summary 잔량 invariant — 비표시 CHECK_GROUP 의 Out Only 추정 ★

**P-O Summary Out 과 O-I Summary Out-In OK 의 차이는 비표시 CHECK_GROUP (OS/PP/PU/II/CF/FS/UP/SL) 의 Out Only 합과 같다.**

```
P-O Sum Out − O-I Sum (Out-In OK) = 비표시 CHECK_GROUP 의 Out Only 누적량
```

[확정: 2026-03-02 ~ 03-06 5 일치 검증 — 매일 36k~43k 켤레의 차이가 발생, 화면에서는 0 으로 보이지만 실제로는 OS/PP/UP 등에서 매칭 안 된 출고가 누적되고 있음]

| 일자 | P-O Sum Out | O-I Sum OK | 차이 (= 비표시 Out Only) |
|---|---|---|---|
| 2026-03-02 | 233,833 | 199,677 | 34,156 |
| 2026-03-03 | 237,179 | 194,251 | 42,928 |
| 2026-03-04 | 237,066 | 196,700 | 40,366 |
| 2026-03-05 | 235,502 | 195,880 | 39,622 |
| 2026-03-06 | 224,846 | 188,550 | 36,296 |

이 invariant 의 가치:
- 사용자가 화면만 보고 "정합성 100%" 라고 판단하기 쉽지만, 실제로는 매일 ~40k 켤레가 비표시 CHECK_GROUP 에서 미매칭 출고로 누적됨.
- 답변 시 "전체 정합성" 질문 들어오면 PH/IP 만 보지 말고 Summary Out 과 O-I Summary OK 차이도 확인.
- 이 차이가 **0 이 아니면** OS/PP/UP 등 비표시 공정의 자재 흐름 점검 필요 — **자재팀 알림 트리거**.

---

## 5. 함정 (가장 많음)

### 5-1. PROD_MOVE_TYPE 두 종류

**P-O Cross**: 생산도 출고도 모두 `PROD_MOVE_TYPE = 'PROD'`
**O-I Cross**: 출고는 `'PROD'`, 입고는 `'MOVE'` ← 다름

이걸 헷갈리면 입고 데이터를 출고로 잘못 셈.

### 5-2. out_only_qty 동음이의어

| 어느 도메인 | out_only_qty 의미 |
|---|---|
| P-O Cross (`po_cross_check.yml`) | 출고는 됐는데 **생산 기록 없음** |
| O-I Cross (`oi_cross_check.yml`) | 출고는 됐는데 **입고 기록 없음** |

답변 시 둘 다 사용하면 별칭으로 구분 (예: `PO_OUT_ONLY` vs `OI_OUT_ONLY`).

### 5-3. IPI/PHH 의 Cross-plant MOVE EXISTS

IPI 와 PHH 공정은 보통 다른 Plant 로 이동되는 게 정상. 출고로 인정하려면 다른 Plant 로의 MOVE 가 EXISTS 해야 함.

```sql
AND ( OP_CD NOT IN ('IPI','PHH')
   OR EXISTS (
        SELECT 1 FROM ... 
         WHERE PROD_MOVE_TYPE = 'MOVE' 
           AND PLANT_CD <> 원본.PLANT_CD
      ) )
```

이 조건 빠뜨리면 IPI/PHH 의 출고 수량이 부풀려짐.

### 5-4. PROD_ORDER_TYPE 'ZCP/ZSH/ZST' 처리

- `BOMLEVEL = 0` 인 ZCP/ZSH/ZST 는 제외 (자재 이동만 있고 실제 생산 아님)
- 추가 필터:
  ```sql
  AND ( PROD_ORDER_TYPE NOT IN ('ZCP','ZSH','ZST')
     OR (PROD_ORDER_TYPE IN ('ZCP','ZSH','ZST') AND BOMLEVEL <> 0) )
  ```

### 5-5. JJ Insole 표시 제외

- FA_PLANT_CD='3110' AND ITEM_CLASS_TYPE='SL' 인 것은 화면에 표시 안 함.
- O-I Cross 분석 시:
  ```sql
  AND ( (1 = DECODE(FA_PLANT_CD,'3210',1,0))
     OR (1 = DECODE(FA_PLANT_CD,'3110',1,0) AND ITEM_CLASS_TYPE <> 'SL') )
  ```

[확정: P_MSPD52000S_Q_V39 라인 232-235 검증]

### 5-6. CH Plan 함수 (FN_GET_CH_PLAN)

- 두 화면 모두 사용
- MSBS_SHIFT 테이블 참조 → OCI 에 없음 → 0/NULL 반환 가능
- 답변에 명시: "[참고] CH Plan 은 MSBS_SHIFT 테이블 부재로 NULL 일 수 있음"

### 5-7. CLOB LOG_MESSAGE 처리

스캔 이력 분석 시 (3-F):
- `LOG_MESSAGE` 는 CLOB
- `DBMS_LOB.SUBSTR(col, 200, 1)` 로 잘라서 조회

### 5-8. 단순화 (1) 의 적용 범위 — PROD leg 에 적용 금지 (★ 주요 함정)

`functions/inout-cross-check.md` 의 OCI 단순화 (1) (`OP_CD NOT IN ('UPC','IPI','PHH')`) 은 **OUT leg 전용**. PROD leg 는 원본 그대로 `OP_CD <> 'UPC'` 만 적용.

**근거**: 원본 프로시저 `P_MSPD51000S_Q_V24` 의 PROD leg WHERE 절은 `OP_CD <> 'UPC'` 만. IPI/PHH Cross-plant EXISTS 룰은 OUT leg 에만 존재 (출고를 다른 Plant 로 이동했을 때만 인정한다는 의미). 생산은 IPI/PHH 도 모두 정상 카운트.

**잘못 적용 시 영향** (2026-05-19 진단 — PROD leg 에 IPI/PHH 제외 잘못 추가):

| 일자 | Bottom Sum Prod 결과 | 캡쳐 | 차이 |
|---|---:|---:|---:|
| 2026-03-02 | 317,678 | 349,475 | -31,797 |
| 2026-03-03 | 330,966 | 366,435 | -35,469 |
| 2026-03-04 | 330,331 | 364,939 | -34,608 |
| 2026-03-05 | 319,350 | 347,601 | -28,251 |
| 2026-03-06 | 310,301 | 344,475 | -34,174 |

**올바르게 적용 시** (PROD leg `<> 'UPC'`, OUT leg `NOT IN ('UPC','IPI','PHH')`):

| 일자 | Bottom Sum Prod 결과 | 캡쳐 | 잔여 차이 |
|---|---:|---:|---:|
| 2026-03-02 | 347,430 | 349,475 | -2,045 |
| 2026-03-03 | 366,435 | 366,435 | **0** ✓ |
| 2026-03-04 | 356,486 | 364,939 | -8,453 |
| 2026-03-05 | 343,250 | 347,601 | -4,351 |
| 2026-03-06 | 343,867 | 344,475 | -608 |

→ 5 일 평균 ~90% 차이 해소. 잔여 -608 ~ -8,453 의 2 차 원인은 미규명.

[확정: 2026-05-19 진단 SQL — PROD leg `<> 'UPC'` 적용이 1 차 원인 해결]

**SQL 작성 시 체크리스트**:
1. `PROD_DATE = :V_DATE` 필터가 있는 leg (PRODUCTION) → `AND OP_CD <> 'UPC'`
2. `OUT_DATE = :V_DATE` 필터가 있는 leg (MOVE/OUT) → `AND OP_CD NOT IN ('UPC','IPI','PHH')`
3. PH cell, IP cell, Sum Out cell 은 잘못 적용해도 영향 없음. **Sum Prod cell 만 영향** (검증 시 첫 신호).

**답변 시 명시**:
- 단순화 SQL 작성 시 leg 별 OP_CD 필터 다름을 명시
- Sum Prod 가 화면보다 5-10% 작게 나오면 PROD leg 의 IPI/PHH 잘못 제외 의심

---

## 6. 답변 형식

기본 구조:

```
1. 한 줄 요약 — 라인별 매칭률 / 특이사항 N 건
2. 결과 표 — 라인별 P-O + O-I metric (통합 흐름이면)
3. (있을 때) 특이사항 강조
   - PCARD 단위로 Out Only / In Only / Mismatch
   - 시간, 라인, 수량, Plant 명시
4. 사용한 SQL (펼침)
5. 사용한 metric / 테이블
6. 검증
7. (있을 때) 한계
```

특이사항 표시 예시:
```
🔴 특이사항 (즉시 확인 필요)

[Out Only — 출고됐는데 입고 없음]
- PCARD AB123, 라인 LINE_A, 50켤레, 출고 14:30 (3시간 경과)
- ...

[In Only — 입고됐는데 출고 없음]
- PCARD CD456, 라인 LINE_B, 30켤레, 입고 16:00 (1시간 경과)
- ...
```

---

## 7. 자주 발생하는 모호성

| 사용자 표현 | 확인 |
|---|---|
| "정합성", "매칭률" | P-O? O-I? 통합? — 디폴트는 사용자 컨텍스트에 따라 |
| "Out Only" | P-O? O-I? — 컨텍스트로 판단, 모호하면 둘 다 보여주기 |
| "수불" | C 통합 흐름 디폴트 |
| "어떤 카드가 매칭 안 됐어" | D PCARD 단위 상세 |
| "왜 매칭 안 됐어" | 원인 분석은 [가설] 영역 — 데이터로 본 표면적 사실만 단정 |

---

## 8. 화면 캡쳐를 ground truth 로 사용할 때의 viewport 한계 (★ 측정 사실)

P-O / O-I Cross Check 화면 캡쳐가 보여주는 라인은 **부분적**이다. 검증·답변 작성 시 항상 인지.

**캡쳐 viewport 가 보여주는 영역** (2026-03-02 ~ 03-06 10 장 직접 확인):

| 표시 영역 | 라인 |
|---|---|
| 상단 visible | L 01, L 02, L 03, L 04, L 05, L 06, L 07, L 08, L 09, L 10, L 11, L 12, L 13, L 14, L 15, L 16 |
| 그 다음 | L 39, L 40, L 41 (모두 CH PLAN=0, 빈 라인) |
| A1 subtotal 행 (녹색 강조) | — |
| 하단 visible | L 17, L 18, L 19 |
| **Bottom Total 행** | 전체 라인 합 (스크롤 영역도 합산되어 있음) |

**미표시 영역 (스크롤)**: L 20 ~ L 38, L 42 ~ L 92, L A1 ~ L B4 등 — 즉 A1 그룹 외 거의 모든 라인.

**의미**:
1. **A1 invariant 케이스 (CP8/CO8) — 캡쳐 단독 검증 가능** — A1 group 라인 (L 01~L 16, L 39, L 40, L 41) 모두 visible.
2. **Bottom invariant 케이스 (CP9/CO9) — 캡쳐 단독 검증 불가** — 스크롤 영역 미표시. 단, **Bottom Total 셀 자체값**은 캡쳐에 표시되므로 SQL 결과와 직접 비교 가능 (CP7/CO5 통해 5 일치 SQL=캡쳐 정합 확인됨).
3. **PH/IP 활성 라인 목록 케이스 (CP4/CP5) — visible 라인만 확정 가능** — 스크롤 영역 라인이 활성/비활성인지 캡쳐에서 확인 불가.
4. **Out Only / In Only 컬럼 0 여부 (CO7) — visible 라인만 확정 가능** — 스크롤 영역 비검증.

**검증 워크플로우 답변 시**:
- 라인 단위 답변 (특정 라인 13/16 셀) → 캡쳐 viewport 에 있는 라인이면 캡쳐 단독으로 확정.
- 라인 목록 / 컬럼 패턴 답변 → **"visible 영역 기준"** 명시 + SQL 결과로 보완.
- A1 단위 답변 → 캡쳐 단독 가능.
- Bottom 단위 답변 → Bottom Total 셀값 단독으로 가능 (라인 합산 invariant 는 SQL 필요).

[확정: 2026-05-19 fresh 검증 — 10 장 캡쳐 모두 동일 viewport 패턴 확인]
