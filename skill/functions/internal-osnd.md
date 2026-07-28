# Functions — Internal OS&D (Bottom Internal OS&D Register)

내부 불량(Internal OS&D) 도메인 SQL 골격 모음. **SCR-007** 전용.

| 화면 | 프로시저 | 메인 테이블 |
|---|---|---|
| **SCR-007** Bottom Internal OS&D Register | Bottom Internal OS&D Register (MSPQ_IN_OSND_BT 메인) | `OCI.MSPQ_IN_OSND_BT` |

`workflows/internal-osnd.md` 가 절차·함정·검증을, 이 파일은 **SQL 골격**만 담는다.
1층 컬럼 정의는 `semantic_models/MSPQ_IN_OSND_BT.yml`, metric은 `metrics/internal_osnd.yml`.

> ⚠️ **External OS&D(SCR-005/006, `MSPQ_EX_OSND`)와 별개 테이블·별개 화면.** 여기 함수는 전부 `MSPQ_IN_OSND_BT`.

**바인드 변수 규약**:

| 변수 | 의미 | 비고 |
|---|---|---|
| `:V_DATE_F`, `:V_DATE_T` | OSND_DATE 범위 (YYYYMMDD VARCHAR8) | 단일일이면 F=T |
| `:V_PLANT_CD` | Plant (단일) | CKP=3120 |
| `:V_PB_CD` | Plant Building — 공정 롤업 기준 | 'CKP-A'=IP / 'CKP-B'=Phylon / NULL=전체 |
| `:V_OP_CD` | OP 코드 (콤마 다중 가능) | IPI/PHH/PHM… / NULL=전체 |
| `:V_OSND_TYPE` | grade 코드 (콤마 다중) | 9/10/13/15… / NULL=전체 |
| `:V_STYLE` | 스타일 LIKE | NULL 가능 |

**공통 룰 [확정: DB 검증 2026-07-11]**:
- **CANCEL 필터 없음** — 이 테이블엔 취소 컬럼이 없다(External과 다름). 날짜/스코프 필터만.
- **dedup 불필요** — 베이스가 OSND_ID당 1행. 화면 procedure의 `ROW_NUMBER … WHERE RN=1` + `@JJEDIF` 색상 조인은 OCI에서 생략(색상 '이름'용일 뿐 수량 무관).
- **미래 sentinel 없음** — OSND_DATE는 실제 등록일. 그래도 실적 집계는 `OSND_DATE <= TO_CHAR(SYSDATE,'YYYYMMDD')` 권장.
- **수량 = 낱개 기본**. 켤레는 `/2`(근사, L/R 짝 보장 없음) 병기.
- **공정(건물) 롤업**: `PB_CD` — 'CKP-A'→IP, 'CKP-B'→Phylon(PHH+PHM+PHU). ★Phylon을 PHH만으로 잡지 말 것.
- **OSND_TYPE 디코드**: `MSBS_CODE_MASTER`, `CODE_CLASS_CD='PQ_GRADE_TYPE'`, `PLANT_CD` 스코프. (PQ_OSND_TYPE 아님)
- **이름 디코드 가용성(OCI)**: STYLE(`MSBS_ITEM_STYLE`)·ITEM_CLASS(`MSBS_ITEM_CLASS`)·GRADE(`MSBS_CODE_MASTER`)는 조인 가능. OP명(`MSBS_OPERATION`)·라인명(`MSBS_WC_SUB`)·사유명(`MSPQ_OP_DEFECT`)·색상명/교대명(`@JJEDIF`)은 **OCI 부재 → 코드로 표기**.

---

## 목차

| 함수 | 분석 능력 | workflow 매핑 |
|---|---|---|
| [`fn_internal_by_process`](#fn_internal_by_process) | **A. 공정(건물) 롤업 — IP / Phylon** (기본) | §3-A |
| [`fn_internal_by_op`](#fn_internal_by_op) | B. OP 개별 (IPI/PHH/PHM) | §3-B |
| [`fn_internal_by_grade`](#fn_internal_by_grade) | C. grade(생산단계) 분해 (CTM/UV/CMP…) | §3-C |
| [`fn_internal_screen_reproduce`](#fn_internal_screen_reproduce) | **D. 화면 Grand Total 재현** (PB/일자) | §3-D |
| [`fn_internal_defect_rate`](#fn_internal_defect_rate) | **E. 내부 불량율** (불량 ÷ 생산, 동일 스코프) | §3-E |
| [`fn_internal_top_reason_style`](#fn_internal_top_reason_style) | F. 사유/스타일 Top N | §3-F |

---

## fn_internal_by_process

**A. 공정(건물) 롤업 — 내부 불량율 기본 출력 단위.** PB_CD로 IP/Phylon을 묶어 등록/후보충/잔량(낱개+켤레).

```sql
SELECT CASE MTB.PB_CD WHEN 'CKP-A' THEN 'IP'
                      WHEN 'CKP-B' THEN 'Phylon'
                      ELSE NVL(MTB.PB_CD,'(기타)') END          AS PROCESS,
       COUNT(*)                                                 AS OSND_CNT,
       SUM(NVL(MTB.OSND_BT_QTY,0))                              AS OSND_QTY_EA,
       ROUND(SUM(NVL(MTB.OSND_BT_QTY,0))/2, 1)                  AS OSND_QTY_PRS,
       SUM(NVL(MTB.REPL_QTY,0))                                 AS REPL_EA,
       SUM(NVL(MTB.OSND_BT_QTY,0)) - SUM(NVL(MTB.REPL_QTY,0))   AS BALANCE_EA,
       ROUND( CASE WHEN SUM(NVL(MTB.OSND_BT_QTY,0))=0 THEN 0
                   ELSE SUM(NVL(MTB.REPL_QTY,0))/SUM(NVL(MTB.OSND_BT_QTY,0))*100 END, 2) AS REPLEN_RATE_PCT
  FROM OCI.MSPQ_IN_OSND_BT MTB
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD IS NULL OR MTB.PB_CD = :V_PB_CD)
 GROUP BY MTB.PB_CD
 ORDER BY PROCESS;
```

> ★ "Phylon"은 여기서 자동으로 PHH+PHM(+PHU)을 합친 값이 된다(PB_CD='CKP-B'). 이게 이전 버그(PHH만
> 세던 문제)의 정답. [확정: 2026-07-11 CKP-B OSND_QTY_EA=4,411].

---

## fn_internal_by_op

**B. OP 개별 분해.** 공정 롤업 안에서 프레스별로 더 쪼갤 때 (IPI/PHH=Phylon Press/PHM=CMP Press).

```sql
SELECT CASE MTB.PB_CD WHEN 'CKP-A' THEN 'IP' WHEN 'CKP-B' THEN 'Phylon'
                      ELSE NVL(MTB.PB_CD,'(기타)') END          AS PROCESS,
       MTB.OP_CD                                                AS OP_CD,
       CASE MTB.OP_CD WHEN 'IPI' THEN 'IP Injection'
                      WHEN 'PHH' THEN 'Phylon Press (CTM)'
                      WHEN 'PHM' THEN 'CMP Press'
                      WHEN 'PHU' THEN 'Phylon UV'
                      ELSE MTB.OP_CD END                        AS OP_DESC,
       COUNT(*)                                                 AS OSND_CNT,
       SUM(NVL(MTB.OSND_BT_QTY,0))                              AS OSND_QTY_EA,
       ROUND(SUM(NVL(MTB.OSND_BT_QTY,0))/2, 1)                  AS OSND_QTY_PRS,
       SUM(NVL(MTB.REPL_QTY,0))                                 AS REPL_EA,
       SUM(NVL(MTB.OSND_BT_QTY,0)) - SUM(NVL(MTB.REPL_QTY,0))   AS BALANCE_EA
  FROM OCI.MSPQ_IN_OSND_BT MTB
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD IS NULL OR MTB.PB_CD = :V_PB_CD)
   AND (:V_OP_CD IS NULL OR MTB.OP_CD IN (SELECT REGEXP_SUBSTR(:V_OP_CD,'[^,]+',1,LEVEL) FROM dual
                                          CONNECT BY REGEXP_SUBSTR(:V_OP_CD,'[^,]+',1,LEVEL) IS NOT NULL))
 GROUP BY MTB.PB_CD, MTB.OP_CD
 ORDER BY PROCESS, OP_CD;
```

> [확정: 2026-07-11] IPI 2,826(1,413켤레) / PHH 3,801(1,900.5) / PHM 610(305). Phylon=PHH+PHM=4,411.

---

## fn_internal_by_grade

**C. grade(생산 하위단계) 분해.** OSND_TYPE을 PQ_GRADE_TYPE으로 디코드해 CTM/UV/Trim/CMP 등 단계별로.
※ 이건 **보조 분해축**이다. 공정 불량율 헤드라인을 이걸로 대체하지 말 것(분모 스코프 어긋남 위험).

```sql
SELECT CASE MTB.PB_CD WHEN 'CKP-A' THEN 'IP' WHEN 'CKP-B' THEN 'Phylon'
                      ELSE NVL(MTB.PB_CD,'(기타)') END          AS PROCESS,
       MTB.OP_CD                                                AS OP_CD,
       MTB.OSND_TYPE                                            AS GRADE_CD,
       NVL(G.CODE_NAME, MTB.OSND_TYPE)                          AS GRADE_NM,
       SUM(NVL(MTB.OSND_BT_QTY,0))                              AS OSND_QTY_EA,
       ROUND(SUM(NVL(MTB.OSND_BT_QTY,0))/2, 1)                  AS OSND_QTY_PRS
  FROM OCI.MSPQ_IN_OSND_BT MTB
  LEFT JOIN OCI.MSBS_CODE_MASTER G
         ON G.CODE_CLASS_CD='PQ_GRADE_TYPE'
        AND G.PLANT_CD = MTB.PLANT_CD
        AND G.SUB_CODE = MTB.OSND_TYPE
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD IS NULL OR MTB.PB_CD = :V_PB_CD)
   AND (:V_OP_CD IS NULL OR MTB.OP_CD = :V_OP_CD)
 GROUP BY MTB.PB_CD, MTB.OP_CD, MTB.OSND_TYPE, G.CODE_NAME
 ORDER BY PROCESS, OP_CD, OSND_QTY_EA DESC;
```

> [확정: 2026-07-11 PHH] 13=Production-CTM 2,436 · 10=Production-UV 1,355 · 9=Production-Trim 10. PHM 15=Production-CMP 610.

---

## fn_internal_screen_reproduce

**D. "Bottom Internal OS&D Register" 화면 Grand Total 재현.** 특정 건물(PB)·일자의 OS&D Qty / Repl / Bal.
화면 필터: Date=OSND_DATE, Plant Building=PB_CD, Process=OP_CD, Line=SUB_WC_CD, Grade=OSND_TYPE.

```sql
SELECT SUM(NVL(MTB.OSND_BT_QTY,0))                              AS OSND_QTY_EA,     -- 화면 OS&D Qty
       SUM(NVL(MTB.REPL_QTY,0))                                 AS REPL_EA,         -- 화면 Repl (라이브)
       SUM(NVL(MTB.OSND_BT_QTY,0)) - SUM(NVL(MTB.REPL_QTY,0))   AS BALANCE_EA,      -- 화면 Bal
       ROUND(SUM(NVL(MTB.OSND_BT_QTY,0))/2, 1)                  AS OSND_QTY_PRS
  FROM OCI.MSPQ_IN_OSND_BT MTB
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD    IS NULL OR MTB.PB_CD    = :V_PB_CD)
   AND (:V_OP_CD    IS NULL OR MTB.OP_CD    = :V_OP_CD)
   AND (:V_OSND_TYPE IS NULL OR MTB.OSND_TYPE = :V_OSND_TYPE)
   AND (:V_STYLE    IS NULL OR MTB.STYLE_CD LIKE :V_STYLE || '%');
```

**상세 행(화면 그리드)이 필요하면** GROUP BY 없이 행 단위로. STYLE/ITEM_CLASS/GRADE는 이름 디코드,
OP/라인/사유/색상/교대는 코드로:

```sql
SELECT MTB.SHIFT_CD, TO_CHAR(MTB.OSND_DT,'HH24') AS HOUR,
       MTB.ITEM_CLASS, NVL(IC.ITEM_CLASS_NAME, MTB.ITEM_CLASS) AS ITEM_CLASS_NM,
       NVL(ST.STYLE_NAME, MTB.STYLE_CD) AS STYLE_NM, MTB.STYLE_CD,
       MTB.MOLD_ID, MTB.MCS_CD, MTB.COLOR_CD,
       MTB.OSND_TYPE, NVL(G.CODE_NAME, MTB.OSND_TYPE) AS GRADE_NM,
       MTB.REASON_CD, MTB.SIZE_CD, MTB.LR_CD,
       NVL(MTB.OSND_BT_QTY,0) AS OSND_QTY, NVL(MTB.REPL_QTY,0) AS REPL,
       NVL(MTB.OSND_BT_QTY,0)-NVL(MTB.REPL_QTY,0) AS BAL
  FROM OCI.MSPQ_IN_OSND_BT MTB
  LEFT JOIN OCI.MSBS_ITEM_CLASS IC ON IC.ITEM_CLASS = MTB.ITEM_CLASS
  LEFT JOIN OCI.MSBS_ITEM_STYLE ST ON ST.STYLE_CD   = MTB.STYLE_CD
  LEFT JOIN OCI.MSBS_CODE_MASTER G
         ON G.CODE_CLASS_CD='PQ_GRADE_TYPE' AND G.PLANT_CD=MTB.PLANT_CD AND G.SUB_CODE=MTB.OSND_TYPE
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD IS NULL OR MTB.PB_CD = :V_PB_CD)
 ORDER BY MTB.SHIFT_CD, MTB.OP_CD, MTB.SUB_WC_CD, MTB.STYLE_CD,
          MTB.OSND_TYPE, MTB.REASON_CD,
          TO_NUMBER(REPLACE(MTB.SIZE_CD,'T','.5')), MTB.LR_CD;
```

> [재현 확정: 2026-07-11, PB_CD='CKP-B'] OSND_QTY_EA = **4,411** = 화면 Grand Total 일치.
> Repl(현재 1,690)·Bal은 라이브 컬럼이라 캡처 시점차 가능.

---

## fn_internal_defect_rate

**E. 내부 불량율 = 내부 불량 ÷ 생산 × 100.** ★분자·분모 **동일 공정 스코프·동일 단위** 필수★

이 테이블엔 생산량이 없다. 분모(생산)는 **생산 실적 도메인**(`functions/production-status.md` /
`OCI.MSPD_PCARD_RESULT`)에서 **같은 OSND_DATE·같은 공정(PB/OP) 스코프**로 가져와 조인한다.

```sql
WITH osnd AS (   -- 분자: 내부 불량 (낱개), 공정 롤업
  SELECT CASE PB_CD WHEN 'CKP-A' THEN 'IP' WHEN 'CKP-B' THEN 'Phylon' ELSE PB_CD END AS PROCESS,
         SUM(NVL(OSND_BT_QTY,0)) AS OSND_QTY_EA
    FROM OCI.MSPQ_IN_OSND_BT
   WHERE PLANT_CD = :V_PLANT_CD
     AND OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   GROUP BY CASE PB_CD WHEN 'CKP-A' THEN 'IP' WHEN 'CKP-B' THEN 'Phylon' ELSE PB_CD END
),
prod AS (        -- 분모: 생산량 (같은 단위·같은 공정 스코프)
  -- ⚠️ 아래는 자리표시. production-status 도메인의 검증된 생산 집계로 교체하되,
  --    반드시 PROCESS(IP/Phylon) 스코프와 단위(낱개 or 켤레)를 osnd CTE와 일치시킬 것.
  --    (예) IP=IPI 공정 생산, Phylon=PHH+PHM(+PHU) 공정 생산 합.
  SELECT :V_PROC AS PROCESS, :V_PROD_QTY AS PROD_QTY_EA FROM dual
)
SELECT o.PROCESS,
       o.OSND_QTY_EA,
       p.PROD_QTY_EA,
       ROUND(CASE WHEN NVL(p.PROD_QTY_EA,0)=0 THEN 0
                  ELSE o.OSND_QTY_EA / p.PROD_QTY_EA * 100 END, 2) AS DEFECT_RATE_PCT
  FROM osnd o
  LEFT JOIN prod p ON p.PROCESS = o.PROCESS
 ORDER BY o.PROCESS;
```

> ★★ 이전 버그 재발 방지 ★★
> - Phylon 불량율 = (PHH+PHM 불량) ÷ (PHH+PHM 생산). **PHH 분자 ÷ PHH 전체 분모** 같은 엇갈린
>   스코프 금지(무의미). grade(CTM만 등)로 쪼갤 땐 분모도 같은 grade 스코프로만.
> - 분자·분모 단위 통일(둘 다 낱개 or 둘 다 켤레).
> - 답변에 **계산식·분모 출처·스코프를 명시**한다.

---

## fn_internal_top_reason_style

**F. 주요 발생 사유 / 스타일 Top N.** 원인 파고들기용.

```sql
SELECT MTB.OP_CD,
       MTB.REASON_CD,          -- 사유명 테이블 OCI 부재 → 코드
       NVL(ST.STYLE_NAME, MTB.STYLE_CD) AS STYLE_NM,
       SUM(NVL(MTB.OSND_BT_QTY,0)) AS OSND_QTY_EA
  FROM OCI.MSPQ_IN_OSND_BT MTB
  LEFT JOIN OCI.MSBS_ITEM_STYLE ST ON ST.STYLE_CD = MTB.STYLE_CD
 WHERE MTB.PLANT_CD = :V_PLANT_CD
   AND MTB.OSND_DATE BETWEEN :V_DATE_F AND :V_DATE_T
   AND (:V_PB_CD IS NULL OR MTB.PB_CD = :V_PB_CD)
   AND (:V_OP_CD IS NULL OR MTB.OP_CD = :V_OP_CD)
 GROUP BY MTB.OP_CD, MTB.REASON_CD, NVL(ST.STYLE_NAME, MTB.STYLE_CD)
 ORDER BY OSND_QTY_EA DESC
 FETCH FIRST 20 ROWS ONLY;
```
