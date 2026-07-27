# Internal OS&D (Bottom Internal OS&D Register) — Analysis Workflow

품질 관리 도메인의 **Internal 갈래 (SCR-007)** 처리 절차. 공장 **내부** 프레스/OP별 생산 불량.

| 항목 | 값 |
|---|---|
| 화면 | SCR-007 Bottom Internal OS&D Register |
| 메인 테이블 | `OCI.MSPQ_IN_OSND_BT` |
| metric 파일 | `metrics/internal_osnd.yml` |
| 1층 | `semantic_models/MSPQ_IN_OSND_BT.yml` |
| SQL 골격 | `functions/internal-osnd.md` (A~F 6개) |

> **진입 경로**: `workflows/quality-osnd.md` §0 분기 게이트에서 "내부/공정별 불량율/Phylon Press·CMP Press/Bottom Register" 판정 시 이 문서로 온다. **공통 원칙은 `workflows/_common.md`.**

> ⚠️ **External OS&D와 혼동 금지.** External(SCR-005/006, `MSPQ_EX_OSND`)=공장 간 후보충·회수율. Internal(여기)=공장 내부 불량율. 테이블·컬럼·KPI 전부 다름.

---

## 1. 이 갈래가 가진 분석 능력

| 분석 능력 | 무엇을 보나 | 함수 |
|---|---|---|
| **A. 공정(건물) 롤업** (기본) | IP / Phylon 별 등록·후보충·잔량·후보충률 | `fn_internal_by_process` |
| **B. OP 개별** | IPI / PHH(Phylon Press) / PHM(CMP Press) 분해 | `fn_internal_by_op` |
| **C. grade 분해** | CTM/UV/Trim/CMP 생산단계별 (보조축) | `fn_internal_by_grade` |
| **D. 화면 재현** | 특정 건물·일자 Grand Total(OS&D Qty/Repl/Bal) + 상세행 | `fn_internal_screen_reproduce` |
| **E. 내부 불량율** | 불량 ÷ 생산 × 100 (동일 스코프) | `fn_internal_defect_rate` |
| **F. 사유/스타일 Top N** | 원인 파고들기 | `fn_internal_top_reason_style` |

---

## 2. 처리 흐름

```
1) 질문 분해   → 기준일 / 건물(PB) or 공정 / OP / grade / 단위(낱개·켤레)
2) 능력 매칭   → A~F 중 무엇 (불량율이면 E, 화면 대조면 D, 기본 현황이면 A)
3) 입력값 고정 → 미지정 항목 되묻기 (기준일 필수)
4) SQL 작성    → 해당 함수 (functions/internal-osnd.md)
5) DB 조회
6) 검증        → §4 invariants
7) 답변        → 낱개 기본·켤레 병기, 계산식 명시
```

### 2-1. 질문 분해 항목

| 항목 | 필수 | 디폴트 / 되묻기 |
|---|---|---|
| 기준일 | 필수 | `OSND_DATE`. "어제"=SYSDATE-1, "전주 토요일" 등 요일 표현 해석 |
| 공정/건물 | 선택 | 없으면 전체(IP+Phylon). "Phylon"=PB_CD 'CKP-B'(PHH+PHM), "IP"=PB_CD 'CKP-A'(IPI) |
| OP | 선택 | 없으면 공정 롤업. 특정 프레스면 OP_CD |
| grade | 선택 | 없으면 전체. "CTM/UV/CMP만" 요청 시 OSND_TYPE 필터 |
| 단위 | 선택 | **낱개 기본, 켤레(÷2) 병기** |
| 불량율 여부 | 선택 | "불량율/달성 대비" 있으면 E(분모=생산실적) |

### 2-2. 능력 매칭 키워드

| 사용자 표현 | 능력 |
|---|---|
| "내부 불량", "공정별", "IP/Phylon 현황", "등록/후보충/잔량" | A |
| "프레스별", "Phylon Press", "CMP Press", "IPI/PHH/PHM" | B |
| "CTM만", "UV만", "생산단계별", "grade" | C |
| "화면 그대로", "Grand Total", "그 화면 개수", "Bottom Register" | D |
| "불량율", "생산 대비", "몇 %", "목표 대비" | E |
| "무슨 사유로", "어느 스타일", "Top", "원인" | F |

---

## 3. SQL 패턴 (요약 — 상세는 functions)

- **§3-A 공정 롤업**: `fn_internal_by_process`. PB_CD로 IP/Phylon 묶음. **불량율 헤드라인의 기본 스코프.**
- **§3-B OP 개별**: `fn_internal_by_op`. 롤업 안에서 프레스별.
- **§3-C grade 분해**: `fn_internal_by_grade`. 보조축. 헤드라인 대체 금지.
- **§3-D 화면 재현**: `fn_internal_screen_reproduce`. 화면 필터(Date/PB/Process/Line/Grade)를 바인드에 대응.
- **§3-E 불량율**: `fn_internal_defect_rate`. 분모=생산실적 도메인, 동일 공정 스코프·동일 단위.
- **§3-F Top N**: `fn_internal_top_reason_style`.

---

## 4. 검증 (Invariants)

- **롤업 정합**: `Phylon = PHH + PHM (+PHU)` = `PB_CD='CKP-B'`. IP = IPI = `PB_CD='CKP-A'`.
  - [확정: 2026-07-11] Phylon 낱개 = 3,801(PHH) + 610(PHM) = **4,411**. PHH만(3,801)은 CMP Press 누락.
- **Balance 공식**: `Bal = OSND_Qty - Repl`. 음수면 데이터 이상.
- **후보충률 범위**: `0 ≤ Repl/OSND ≤ 100`. Repl ≤ OSND 성립.
- **불량율 스코프**: 분자·분모 공정 스코프·단위 동일. 위반 시 무의미.
- **화면 대조**: OS&D Qty(=SUM OSND_BT_QTY)는 불변 → 정확히 일치해야. Repl/Bal은 라이브라 시점차 허용.

---

## 5. 함정

### 5-1. ★Phylon 롤업 누락 (이번 버그의 원인)
- "Phylon"을 `OP_CD='PHH'`만으로 잡으면 **CMP Press(PHM) 누락**. 반드시 `PB_CD='CKP-B'` 또는 `OP_CD IN ('PHH','PHM','PHU')`.

### 5-2. OSND_TYPE 오해
- `OSND_TYPE`은 `PQ_GRADE_TYPE`(생산단계 CTM/UV/Trim/CMP…)으로 디코드. **PQ_OSND_TYPE 아님·"검사단계" 아님.**
- 이걸 공정 축으로 쓰지 말 것. 공정 축은 PB_CD/OP_CD.

### 5-3. 불량율 분모 엇갈림
- 분자(불량)와 분모(생산) 스코프가 다르면(예: CTM 불량 ÷ PHH 전체 생산) 값이 무의미. 항상 동일 스코프.

### 5-4. 단위 혼동
- 화면=낱개(4,411). 켤레(÷2, 2,205.5)와 섞지 말 것. 불량율 계산 시 분자·분모 단위 통일.

### 5-5. Repl 시점차
- `REPL_QTY`는 후보충 진행에 따라 갱신. 화면 캡처 시점과 조회 시점이 다르면 Repl/Bal이 다를 수 있음(정상). 등록 수량(OSND_Qty)은 불변.

### 5-6. 이름 디코드 한계
- OP명/라인명/사유명/색상명/교대명 디코드 테이블이 OCI에 없음 → 코드로 표기하고 그 사실을 답변에 한 줄 명시.

---

## 6. 답변 형식

```
1. 한 줄 요약 (어느 공정/일자, 핵심 수치)
2. 결과 표 — 공정 롤업(IP/Phylon) 기본. 낱개 기본 + (켤레) 병기.
   - 불량율이면 분자/분모/율 + 계산식
3. 사용한 SQL (펼침)
4. 사용한 metric / 테이블 (internal_osnd.yml, MSPQ_IN_OSND_BT)
5. 검증 (§4)
6. 한계 (있을 때) — 이름 코드 표기, Repl 시점차, 분모 출처 등
```

추가 가공:
- "일보/리포트" → `data-analysis-report` 연계
- "그래프" → visualize (플롯 라벨은 영어)
- "메일" → Zapier
