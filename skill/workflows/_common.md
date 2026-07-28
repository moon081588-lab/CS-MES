# Common Guide — 모든 workflow 가 참조하는 공통 원칙

이 문서는 5 개 도메인 workflow 모두에 공통 적용되는 데이터 위생·SQL 규칙·Plant 코드 등을 담는다.
각 workflow 는 자기 도메인 특유의 SQL 패턴/함정만 다루고, 공통 원칙은 여기를 참조한다.

---

## 0. DB 연결 (가장 먼저)

**어떤 SQL 도 실행하기 전에** DB 에 연결한다. 아래 절차는 **어느 PC·어느 실행 환경에서도** 통하도록 쓰였다. 특정 PC 의 연결 이름이나 도구 접두어를 가정하지 않는다.

> 원칙: **이름을 외우지 말고 목록을 읽어서 고른다. 고른 뒤에는 반드시 검증한다.**
> CS-MES 프로그램(`ckp_reports/make_all.py` 의 `resolve_conn()`)이 쓰는 규칙과 같은 규칙이다. 둘 중 하나를 고치면 다른 쪽도 같이 고칠 것.

### 0-1. 도구 찾기 — 접두어를 하드코딩하지 않는다

SQLcl MCP 도구의 전체 이름은 실행 환경마다 다르다.

| 환경 | 실제 도구 이름 |
|---|---|
| Cowork / 원격 브리지 | `mcp__remote-devices__sqlcl__connect` 등 |
| Claude Desktop 로컬 | `mcp__sqlcl__connect` 등 |

따라서 **이름 끝부분으로 식별**한다 — `…list-connections` / `…connect` / `…run-sql`. 사용 가능한 도구 목록에서 그 접미사를 가진 것을 찾아 쓴다. 접두어가 붙은 형태를 그대로 타이핑해 호출하지 말 것.

### 0-2. 연결 이름 정하기 — 목록을 읽고 고른다

1. `…list-connections` 로 저장된 연결 **목록을 먼저 읽는다**.
2. 아래 순서로 첫 번째 매칭을 고른다.

   | 순위 | 규칙 |
   |---|---|
   | 1 | 이름이 정확히 `changshinincaipoc` |
   | 2 | 이름에 `changshinincaipoc` 포함 |
   | 3 | 접속 문자열에 `changshinincaipoc` 포함 (이름이 달라도 됨) |
   | 4 | 이름이 `_medium` / `_high` / `_low` 로 끝남 |
   | 5 | 이름이 `csi` 로 시작 |

   `csi*` 를 **마지막에** 두는 이유: `csi_ok` / `csi` 처럼 **비밀번호가 저장되지 않은** 연결이 섞여 있어, 먼저 고르면 프롬프트를 기다리다 조용히 실패한다.

3. **항상 제외**: `lmes` / `lmes2` / `mylmes` / `lmes_v2` — 모두 `lmes_medium`(사용자 `mcp_user`)을 가리키는 **다른 레거시 DB** 다. MES(OCI) 테이블이 없어 ORA-00942 가 난다. 이름이나 접속 문자열에 `lmes` 가 있으면 후보에서 뺀다.

4. 목록을 못 읽으면 `changshinincaipoc` 로 시도하고, 실패하면 사용자에게 연결 생성을 요청한다.

### 0-3. 붙은 직후 검증 — 1회 필수

엉뚱한 DB 에 붙은 채로 20 개 쿼리를 돌리는 사고, 그리고 **며칠 묵은 복제본을 최신인 줄 알고 보고하는 사고**를 막는다. 접속 성공 직후 **반드시** 한 번 실행한다.

```sql
SELECT (SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER='OCI')            OCI_TABLES,
       DBTIMEZONE                                                     DB_TZ,
       TO_CHAR(SYSDATE,'YYYY-MM-DD HH24:MI')                          DB_SYSDATE,
       TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul',
               'YYYY-MM-DD HH24:MI')                                  KST_NOW,
       TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Jakarta',
               'YYYY-MM-DD HH24:MI')                                  WIB_NOW,
       (SELECT MAX(SCAN_YMD) FROM OCI.POP_PCARD_SCAN)                 LAST_SCAN,
       (SELECT TO_CHAR(MAX(UPDATE_DT),'YYYY-MM-DD HH24:MI')
          FROM OCI.MSPD_PCARD_RESULT)                                 LAST_SYNC
FROM DUAL
```

읽는 법:

| 항목 | 정상 | 이상하면 |
|---|---|---|
| `OCI_TABLES` | 40 개 이상 (2026-07 기준 43) | **0 이면 잘못된 DB** — 0-2 의 다음 후보로 |
| `DB_TZ` | `+00:00` (UTC) | 기준은 `KST_NOW`. `WIB_NOW` 와 날짜가 다르면 §4-1 의 00~02시 구간 |
| `LAST_SCAN` | 어제~오늘 | 며칠 전이면 **복제 지연**. 답변에 반드시 명시 |
| `LAST_SYNC` | 최근 | `LAST_SCAN` 과 함께 데이터 신선도 판단 |

**복제 지연을 발견하면 그대로 보고한다.** 예: "OCI 복제본의 마지막 스캔은 2026-07-24, 마지막 동기화는 07-25 07:00 입니다. 07-26 이후 데이터는 아직 없습니다." 지연을 모른 채 "최근 3일 실적"을 뽑으면 빈 결과를 실제 0 으로 오해한다.

### 0-3-1. 연결은 끊긴다 — 재접속 규칙

SQLcl MCP 연결은 **유휴 상태에서 끊긴다.** 앞 질문에서 붙었다고 다음 질문에서도 살아 있다고 가정하지 말 것.

- `Connection not established` 또는 `ORA-03113` / `ORA-03114` 가 보이면 → **0-2 로 돌아가 다시 접속**하고, 실패한 쿼리를 재실행한다.
- 재접속 후 0-3 검증을 **한 번 더** 한다. 다른 연결로 붙었을 수 있다.
- 한 번 실패했다고 사용자에게 "DB 를 못 씁니다"라고 보고하지 말 것. 재접속은 조용히 처리하고, 두 번 이상 실패할 때만 알린다.

### 0-4. 지갑(Wallet)·TNS_ADMIN — 현장 1순위 실패 원인

OCI Autonomous DB 는 지갑으로 붙는다. **지갑을 다른 PC 에서 복사해 오면 거의 항상 깨진다.**

- 원인: `sqlnet.ora` 의 `WALLET_LOCATION ... DIRECTORY` 에 **복사해 준 PC 의 절대경로**가 박혀 있다. 원본 zip 상태는 `DIRECTORY="?/network/admin"` 이고 파일이 약 114 bytes 다. 그보다 크면 누군가 경로를 박아둔 것이다.
- 조치: `DIRECTORY` 를 **이 PC 의 실제 지갑 폴더**로 고친다. CS-MES 를 쓰고 있다면 자동이다 —
  `CKP.bat` 의 2 번(처음 설정)이 매 실행마다 교정한다.
- **경로에 공백·한글·괄호를 쓰지 말 것.** SQLcl 은 자바라서 `연구참여 (2026-여름학기)` 같은 경로를 만나면 `ORA-17956` 을 낸다. OneDrive·Google Drive 동기화 폴더도 피한다(온라인 전용 파일·잠금 문제).
- 권장 위치 — 프로그램 폴더의 `wallet\` (예: `C:\CKP-Report\wallet`). 한글·공백 없는 ASCII 경로여야 한다.

**Windows 절차**
1. 지갑 zip 을 `C:\oracle\wallet\changshinincaipoc` 에 푼다.
2. `setx TNS_ADMIN "C:\oracle\wallet\changshinincaipoc"`
3. `sqlnet.ora` 의 `DIRECTORY` 를 같은 경로로 고친다.
4. **Claude Desktop 을 완전 종료(트레이 아이콘까지) 후 재시작.** 실행 중인 프로세스는 옛 환경변수를 계속 들고 있다.

MCP 서버에 `env.TNS_ADMIN` 을 지정해 뒀다면, 폴더를 옮긴 뒤에는 손으로 고치지 말고
`CKP.bat` 의 4 번을 쓴다(지금 폴더 위치 기준으로 재작성 + 백업).

### 0-5. 증상별 조치표

| 증상 | 원인 | 조치 |
|---|---|---|
| `ORA-12154` 식별자 해석 불가 | TNS 별칭 오타 / `tnsnames.ora` 를 못 찾음 | `TNS_ADMIN` 확인, 별칭을 `tnsnames.ora` 에서 직접 확인 |
| `ORA-12263` TNS admin 디렉터리 접근 불가 | `TNS_ADMIN` 이 없는 경로를 가리킴 (폴더 이동 후 흔함) | 경로 교정 후 **Desktop 재시작** |
| `ORA-17956` wallet location 파싱 불가 | 지갑 경로에 **공백·괄호·한글** | 지갑을 ASCII 경로로 옮긴다 (0-4) |
| `ORA-28759` 파일 열기 실패 | `sqlnet.ora` 의 `DIRECTORY` 가 남의 PC 경로 | `DIRECTORY` 교정 (0-4) |
| `ORA-29024` 인증서 검증 실패 | 지갑 파일 일부 누락/손상 | 지갑 zip 을 다시 풀어 8개 파일을 모두 채운다 |
| `ORA-01017` 아이디/비번 불일치 | 비번 미저장 연결(`csi_ok`/`csi`)을 골랐다 | 0-2 의 다음 후보로 (csi* 는 마지막) |
| `ORA-00942` 테이블/뷰 없음 | `lmes` 계열 DB 에 붙었다 | 연결을 바꾼다. 0-3 검증을 건너뛰지 말 것 |
| `ORA-03113` 통신 채널 끊김 | 대형 쿼리 타임아웃 | 기간·Plant 로 범위를 좁혀 재시도 |
| 도구 자체가 없음 | MCP 미등록/미인증 | 사용자에게 SQLcl 연결 생성 또는 커넥터 인증 요청 |

### 0-6. fallback — `changshinin_db2` 커넥터

SQLcl 계열 도구가 아예 없거나 위 후보가 전부 실패하면, plugin 에 포함된 **`changshinin_db2`** 커넥터(OCI ADB Data Access MCP, `EXECUTE_SQL`)로 같은 DB 를 조회한다. 도구 이름은 여기서도 접미사(`…EXECUTE_SQL`)로 찾는다. SQL 본문은 SQLcl 경로와 **완전히 동일**하게 쓴다. 이 경로로 붙어도 0-3 검증은 똑같이 수행한다.

### 0-7. 어느 경로로 붙었는지 답변에 명시

조회 후 답변의 "사용한 metric/테이블" 부근에 **연결 경로와 실제 고른 연결 이름**을 한 줄로 적는다.
예: `연결: 로컬 SQLcl / changshinincaipoc (OCI 테이블 1,2xx 개 확인)`

---

## 1. 데이터 위생 (Data Hygiene)

### 1-1. PROD_MOVE_TYPE — 이벤트 종류

MSPD_PCARD_RESULT 의 모든 행은 `PROD_MOVE_TYPE` 으로 구분.

| 값 | 의미 | 사용 |
|---|---|---|
| `'PROD'` | 생산/출고 이벤트 | 생산·출고·부족분·P-O Cross 분석 |
| `'MOVE'` | 입고 이벤트 | 입고·O-I Cross 분석 |

**규칙**:
- 생산 실적 → 항상 `PROD_MOVE_TYPE = 'PROD'`
- 입고 실적 → 항상 `PROD_MOVE_TYPE = 'MOVE'`
- 둘 다 필요 (예: O-I Cross) → 별도 서브쿼리로 처리

### 1-2. 19991231 sentinel — 미발생 표기

날짜 컬럼이 `'19991231'` 이면 **"이벤트 아직 발생 안 함"** 의미. 실제 1999 년이 아님.

| 컬럼 | 19991231 의미 | [확정 출처] |
|---|---|---|
| `PROD_DATE = '19991231'` | 미생산 | P_MSPD90000S_Q_V14 라인 57 |
| `OUT_DATE  = '19991231'` | 미출고 | P_MSPD90000S_Q_V14 라인 154 |
| `IN_DATE   = '19991231'` | 미입고 | 같은 패턴 |
| `INPUT_DATE = '19991231'` | 미투입 | 같은 패턴 |

**규칙**:
- 실적 집계는 항상 sentinel 제외: `WHERE PROD_DATE NOT IN ('19991231','20981231')`
  - 또는 `WHERE PROD_DT > TO_DATE('20010101', 'YYYYMMDD')` (DATE 타입 비교)
- 부족분 분석은 정반대 — sentinel 인 행만 카운트 (예: `WHERE PROD_DATE = '19991231'` = 미생산 잔량)

### 1-3. PROD_DATE vs PROD_DT — 같은 이벤트의 두 표현

| 컬럼 | 타입 | 용도 |
|---|---|---|
| `PROD_DATE` | VARCHAR2(8) `'YYYYMMDD'` | 일자별 GROUP BY, 날짜 비교 |
| `PROD_DT` | DATE (시분초 포함) | 시간대 분석, sentinel 비교 |

같은 이벤트면 `PROD_DATE = TO_CHAR(PROD_DT, 'YYYYMMDD')` 가 성립 (PROD_DT 가 NULL/sentinel 일 때 제외).

**시간대 분석은 PROD_DT, 일자 집계는 PROD_DATE.**

### 1-4. END_ROUTING_YN = 'Y' — 라인 마지막 공정

PCARD 가 라인 마지막 공정에서 발생한 행만 마킹.

**규칙**:
- 출고/입고/Cross Check 분석에서는 거의 항상 `END_ROUTING_YN = 'Y'` 필터.
- Production Status 의 일부 분석은 모든 공정 (`END_ROUTING_YN` 무관) — 도메인 workflow 참조.

### 1-5. RESULT_TYPE = 'SCAN' — 스캔 데이터만

대부분의 분석은 스캔된 데이터만 봐야 함. 디폴트값이지만 명시적으로 필터.

[확정: P_MSPD51000S_Q_V24, P_MSPD52000S_Q_V39 모두 사용]

### 1-6. BARCODE_KEY — 카드 중복 카운트 함정

MSPD_PCARD_RESULT 의 한 카드(BARCODE_KEY)는 라우팅에 따라 여러 OP row 로 분산.
각 row 는 그 단계의 (OP_CD, ITEM_CLASS_TYPE) 페어 가짐. PCARD_QTY 는 모든 row 에서 동일.

| 상황 | SUM(PCARD_QTY) 결과 |
|---|---|
| (OP, ITEM_CLASS_TYPE) 페어 단일 필터 | 정상 — 페어 안 중복 없음 |
| OP 묶음 (IN 절, 페어 미고정) | 묶음 안 카드별 row 수만큼 부풀림 |
| OP 필터 없음 | 카드의 모든 라우팅 row 카운트 — 더 부풀림 |

**규칙**:
- 화면 재현 분석: 페어 단일 호출이므로 함정 해당 없음.
- 자유 분석 (OP 묶음/미좁힘):
  - "OP별 분해" 요청 → `GROUP BY OP_CD` 추가 (각 OP 안에서 카드 중복 없음)
  - "카드 단위 총량" 요청 → `metrics/production_status.yml` 의 `distinct_card_qty` 사용
- 자세한 옵션 분기는 `workflows/production-status.md` §3-B 부록 참조.

[확정: 2026-03-02 / FGA03 실측 검증]

---

## 2. Plant 코드 약어 변환

사용자가 공장 약어로 말하면 `PLANT_CD` 로 변환.

| 약어 | PLANT_CD | 비고 |
|---|---|---|
| JJ | `3110` | |
| CKP | `3120` | |
| RJ | `3210` | |
| JJS | `3220` | |

### Plant 컬럼 두 개 — 메트릭에 따라 다르게 사용

가장 흔한 함정. **계획과 실적이 다른 Plant 컬럼을 쓴다.**

| 메트릭/분석 | Plant 필터 컬럼 | 의미 |
|---|---|---|
| 계획 (`plan_qty`, `production_shortage_qty` 등) | `PLANT_CD` | 계획 책임 공장 |
| 실적 (`production_qty`, `outgoing_qty` 등) | `ITPO_WC_PLANT_CD` | 실제 작업 발생 공장 (외주 포함) |

**[확정: P_MSPD29000S_Q_V06, P_MSPD90000S_Q_V14 검증]**

이걸 헷갈리면 답이 조용히 틀린다. 사용자가 "JJ 공장" 이라고 하면 메트릭에 따라 다른 컬럼으로 필터하는 SQL 을 만든다.

---

## 3. OP_CD 분류

Level 1(그룹) → Level 2(실제 OP_CD) 구조. 아래 표가 진실의 출처 (공정코드.xlsx 기준).

| Level 1 코드 | Level 1 명 | Level 2 OP_CD | Level 2 명 |
|---|---|---|---|
| FG | FINISHED GOODS | FGA | ASSEMBLING |
| FS | FINISHED SOLE | FSS | STOCKFITTING |
| UP | UPPER | UPS | STOCKFITTING |
| UP | UPPER | UPC | UPPER CUTTING |
| UL | LAMINATION | UPL | LAMINATION |
| UE | UPPER EMBELLISHMENT | UPA | UPPER LASER ETCHING |
| UE | UPPER EMBELLISHMENT | UPD | UPPER PAD PRINTING |
| UE | UPPER EMBELLISHMENT | UPE | EMBROIDERY |
| UE | UPPER EMBELLISHMENT | UPF | HF WELDING |
| UE | UPPER EMBELLISHMENT | UPH | COMPRESSION MOLDING |
| UE | UPPER EMBELLISHMENT | UPN | NO-SEW |
| UE | UPPER EMBELLISHMENT | UPP | UPPER SCREEN PAINTING |
| UE | UPPER EMBELLISHMENT | UPW | WIRE |
| UE | UPPER EMBELLISHMENT | UPY | UPPER SPRAY |
| SL | SOCKLINER | SLM | SOCKLINER MAKING |
| OS | OUTSOLE | OSP | OUTSOLE PRESS |
| OS | OUTSOLE | OSR | OUTSOLE ROLLING |
| OS | OUTSOLE | OST | OUTSOLE TRIMMING |
| IP | IP/IU | IPF | IP PREFOAM INJECTION |
| IP | IP/IU | **IPI** | **IP INJECTION** |
| IP | IP/IU | **IPU** | **IP UV** |
| IZ | PELLET | IPZ | IP/IU PELLETIZING |
| PH | PHYLON | **PHH** | **PHYLON PRESS** |
| PH | PHYLON | **PHM** | **CMP PRESS** |
| PH | PHYLON | **PHU** | **PHYLON UV** |
| PH | PHYLON | PHC | BOTTOM CUTTING |
| PH | PHYLON | BUA | BUPPING AFTER |
| PH | PHYLON | BUB | BUPPING BEFORE |
| PZ | PELLET | PHZ | PHYLON PELLETIZING |
| PU | PU | PUR | PU POURING |
| PU | PU | PUF | PU FORMULATION |
| CF | COLD FUSION | CFU | COLD FUSION UV |
| CF | COLD FUSION | DMP | DMP PRESS |
| CF | COLD FUSION | CLS | COLD SHOT |
| EV | EVA | EVR | EVA ROLLING |
| BE | BOTTOM EMBELLISHMENT | BEA | AIRBAG PAINTING |
| BE | BOTTOM EMBELLISHMENT | BEH | HOT KNIFE |
| BE | BOTTOM EMBELLISHMENT | BEI | INJECTION SPRAY |
| BE | BOTTOM EMBELLISHMENT | BEL | BOTTOM LASER ETCHING |
| BE | BOTTOM EMBELLISHMENT | BEM | MIDSOLE PAINTING |
| BE | BOTTOM EMBELLISHMENT | BEO | OUTSOLE PAINTING |
| BE | BOTTOM EMBELLISHMENT | BEP | BOTTOM PAD PRINTING |
| BE | BOTTOM EMBELLISHMENT | BES | BOTTOM LASER SIPING |

**규칙**:
- "IP 공정" → `OP_CD IN ('IPI','IPU')`
- "PH 공정" → `OP_CD IN ('PHH','PHM','PHU')`
- "IP+PH 공정" → `OP_CD IN ('IPI','IPU','PHH','PHM','PHU')`
- Level 1 코드(2글자)로 질문이 오면 → 위 표에서 해당 Level 2 OP_CD 목록으로 변환
- 참고용 공정(BE/OS/UP 등) 언급 시 5개 도메인 metric 적용 가능 여부 확인 필요

---

## 4. 시간 처리

### 4-1. "어제/오늘" 의 기준 — 한국시간(KST)이 표준, 단 데이터는 현장시간

**기준 타임존은 한국시간 `Asia/Seoul`(KST, UTC+9)** 이다 — 조직 표준. 어느 PC 에서 조회하든 같은 날짜가 나오게 하는 것이 목적이므로, **접속한 PC 의 로컬 날짜를 쓰지 않는다.**

같은 순간에 세 시각이 존재한다 (2026-07-28 실측):

| 기준 | 값 | 정체 |
|---|---|---|
| `SYSDATE` / `SYSTIMESTAMP` | `2026-07-28 00:19` | **DB 서버 = UTC** (`DBTIMEZONE = +00:00`) |
| `CURRENT_DATE` | `2026-07-28 09:19` | 세션 타임존 — 접속 PC 를 따라가므로 신뢰 불가 |
| 한국 (KST) | `2026-07-28 09:19` | **기준 타임존** |
| 현장 CKP(Cikampek) | `2026-07-28 07:19` | WIB = UTC+7. **DB 날짜 컬럼이 쓰는 시계** |

**규칙**

1. 달력 기준 "오늘/어제"는 **KST** 로 계산한다. `SYSDATE`(UTC) 도 `CURRENT_DATE`(접속 PC) 도 쓰지 않는다.

   ```sql
   -- 기준일 (YYYYMMDD 문자열)
   TO_CHAR(TRUNC(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul'), 'YYYYMMDD')      -- 오늘
   TO_CHAR(TRUNC(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul') - 1, 'YYYYMMDD')  -- 어제
   ```

2. ⚠️ **알고 쓸 것 — 데이터는 현장(WIB) 시계로 기록된다.** `FA_DATE`·`SCAN_YMD`·`CREATE_DT` 는 전부 공장 벽시계 기준이다. KST 와 WIB 는 **2시간** 차이라, **KST 00:00~01:59 구간에서만** 두 날짜가 어긋난다(그때 현장은 아직 전일 22~23시). 그 시간대의 조회 결과는 하루 밀린 것으로 보일 수 있으니, 해당 구간이면 답변에 그 사실을 적는다. 그 외 22시간은 두 날짜가 같다.

   ```sql
   -- 지금이 그 구간인지 확인
   SELECT TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI') KST_NOW,
          TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Jakarta','YYYY-MM-DD HH24:MI') WIB_NOW FROM DUAL
   ```

3. **하지만 실무 디폴트는 여전히 "실데이터 최신일"이다.** OCI 는 복제본이라 며칠 밀려 있을 수 있다(§0-3 에서 확인). 달력상 오늘로 조회하면 빈 결과가 나오고, 그걸 실제 0 으로 오해하기 쉽다.

   ```sql
   SELECT MAX(SCAN_YMD) FROM OCI.POP_PCARD_SCAN;      -- 실적 최신일
   SELECT MAX(FA_DATE)  FROM OCI.MSPD_PCARD_RESULT;   -- ⚠️ 미래 계획일 포함
   ```

   ⚠️ `MSPD_PCARD_RESULT.FA_DATE` 에는 **미래 계획일**이 들어 있어 `MAX(FA_DATE)` 가 실적 최신일보다 앞선다. 신선도 판단은 `POP_PCARD_SCAN.MAX(SCAN_YMD)` 나 `MAX(UPDATE_DT)` 로 한다.

4. **답변에 어느 기준을 썼는지 적는다.** 예: "KST 2026-07-28 기준 조회. 단 OCI 복제본의 최신 실적일은 07-24 라 07-25 이후 데이터는 아직 없습니다."

**시프트 경계와의 관계**: 야간 시프트(3 교대)의 스캔은 `RESULT_DATE` 가 전일자로 기록될 수 있다(`semantic_models/POP_PCARD_SCAN.yml` 참조). 일자별 수치가 이상하면 이 규칙과 위 2번(KST 00~02시)을 모두 의심한다.

### 4-2. 날짜 형식 변환

날짜 컬럼은 `VARCHAR 'YYYYMMDD'`. 비교/연산 시 변환.

```sql
-- 날짜 범위
WHERE PROD_DATE BETWEEN '20260420' AND '20260427'

-- TO_DATE 비교 (간격 계산 등)
WHERE TO_DATE(PROD_DATE,'YYYYMMDD') BETWEEN
        SYSDATE - 7 AND SYSDATE
```

### 4-3. 시프트 결정 함수

`FN_GET_BT_SHIFT(plant_substr, prod_date, time_str)` 가 'S1'/'S2'/'S3' 반환.

```sql
FN_GET_BT_SHIFT(
  SUBSTR(PROD_WH_CD, 3, 2),    -- 'IP' 또는 'BT' 추출
  PROD_DATE,
  TO_CHAR(PROD_DT, 'HH24MISS')
)
```

[확정: P_MSPD29000S_Q_V06 라인 391-393]

---

## 5. SQL 작성 공통 규칙

### 5-1. 탐색 vs 본 쿼리

| 단계 | 규칙 |
|---|---|
| 탐색 (DISTINCT, 컬럼 확인) | `FETCH FIRST 100 ROWS ONLY` 강제 |
| 본 쿼리 (집계) | 필터 좁힌 후 실행 |

### 5-2. 대규모 테이블 (700 만 행+) 주의

- `COUNT(DISTINCT x)` 대신 `APPROX_COUNT_DISTINCT(x)`
- `FULL OUTER JOIN` 금지 (UNION ALL 로 분리)
- 카티션 곱 (조인 조건 없는 `FROM A, B`) 절대 금지

### 5-3. WHERE 좁히기 순서

1. `PLANT_CD` (가장 좁힘)
2. `FA_DATE` / `PROD_DATE` (인덱스 활용)
3. `OP_CD` (그다음)
4. 기타 필터

### 5-4. CLOB 컬럼 처리

`TEXT`, `LOG_MESSAGE`, `LONG_MEMO` 등은 잘라서:
```sql
DBMS_LOB.SUBSTR(col, 200, 1) AS col_short
```

### 5-5. 에러 대응

| 에러 | 대응 |
|---|---|
| `ORA-03113`, `ORA-17008` | `connect changshinincaipoc` 재실행 후 재시도 (§0 참조) |
| MCP 240 초 타임아웃 | 쿼리 단순화 (범위 축소, FETCH FIRST 추가) |
| `ORA-00904` (컬럼 없음) | `ALL_TAB_COLUMNS` 로 실제 컬럼명 확인 |
| `ORA-00942` (테이블 없음) | `OCI.` 스키마 접두사 확인 |

---

## 6. 사실 vs 추정 분리 (최우선 원칙)

| 무엇 | 어떻게 표현 |
|---|---|
| 조회 결과로 확인된 사실 | 단정문 ("~로 조회되었습니다") |
| yaml 의 [확정] 사항 | 단정문 가능 |
| yaml 의 [추측] 사항 | 답변에서 "[추측]" 표시 유지 |
| 원인/해석/경향 | 반드시 "[가설]" 또는 "추정" 으로 명시 |
| Claude 의 추론 (자유 분석 등) | "[추정]" 또는 "이렇게 해석했습니다" 명시 |

**원칙**: "자신 없는 해석을 단정문으로 쓰는 것" 은 "모른다고 밝히고 확인하는 것" 보다 나쁘다.

---

## 7. 답변 투명성

### 항상 포함

- 실행한 SQL (사용자가 검증할 수 있도록)
- 사용한 metric / 테이블 / 컬럼
- 사용한 yaml 파일 명시 (예: "metrics/shortage_balance.yml의 production_shortage_qty 사용")

### 조건부 포함

- invariant 자동 체크 결과 (검증 모드 / "확인" 키워드)
- 한계 / [확인필요] 항목 (있을 때만, 답변 끝에 짧게)

---

## 8. 자주 묻는 표현 — 디폴트 처리

| 모호한 표현 | 디폴트 (확신 없으면 되묻기) |
|---|---|
| "수량" | PCARD_QTY (켤레 수). 다른 의미면 사용자 확인. |
| "오늘/어제" | MAX(FA_DATE) 기준 |
| "라인" | FA_WC_CD 컬럼. 단 PROD_ORDER_TYPE='ZCP' 면 'ZCP01' 매핑 |
| "전체" | Plant/OP/Item Class 미지정 → 사용자 확인 후 적용 |
| "최근" | 7 일 디폴트 (사용자 명시 없을 시) |

---

## 9. 1층 + 2층 yaml 활용 패턴

자유 분석이나 metric 에 없는 컬럼이 필요할 때:

1. **2층 metric 먼저** — 비슷한 metric 있으면 차용 + 약간 변형.
2. **1층 dimension 확인** — metric 에 없는 GROUP BY 키는 1층 dimension 에서 가져옴.
3. **1층 measure** — metric 정의 안 된 raw 측정값은 1층 measure 사용 (대부분 PCARD_QTY 합).
4. **컬럼 자체가 yaml 에 없으면** — `ALL_TAB_COLUMNS` 조회 후 description 보강 제안.

[확정] 마커 있는 정보는 신뢰, [추측] 마커는 답변에 그대로 표시.

---

## 10. 색상 코드 lookup

스타일의 색상명을 표시해야 할 때 (예: SCR-005 External OS&D Balance by Size 의 Color 컬럼, 자유 분석에서 "색상별 그룹") 따르는 규칙.

### 10-1. 어디서 가져오나

**원칙: `MSPQ_EX_OSND.COLOR_CD` (5자리, 예: `1010A`) 의 끝 3자리가 색상 키.**

| 컬럼 | OCI 에서 채워짐? | 사용 |
|---|---|---|
| `MSPQ_EX_OSND.COLOR_CD` | **Y** (5자리, 끝 3자리가 색상 키) | **OS&D 분석 디폴트** |
| `MSBS_ITEM_STYLE.COLOR_CD` | N (26,172 행 전부 NULL) | 사용 불가 |
| `MSBS_ITEM.COLOR_CD` / `.COLOR_NAME` | N (619,700 행 전부 NULL) | 사용 불가 |
| `MSBS_ITEM.MCS_COLOR_CD` | **Y** (`BLACK(00A)/WHITE(10A)` 형식 텍스트) | **신규 색상 코드 매핑 추출용** |
| `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` | DB link 부재 | 사용 불가 |

**OS&D 가 아닌 분석에서 STYLE 의 색상이 필요한 경우** — `MSBS_ITEM` 의 FG 행은 색상 비어있으므로, 같은 STYLE_CD 의 ITEM 행 중 `MCS_COLOR_CD` 채워진 걸 사용. 단일 색상이 아닐 수 있다는 점 주의 ([추정: 복합색이 흔함]).

### 10-2. 코드 → 색상명 매핑 (자주 등장)

검증된 15개. OS&D 분석에서 거의 90% 이상 커버.

| 코드 | 색상명 |
|---|---|
| 00A | BLACK |
| 10A | WHITE |
| 01V | WOLF GREY |
| 11K | SAIL |
| 12J | SUMMIT WHITE |
| 06F | ANTHRACITE |
| 0BB | PHOTON DUST |
| 22Z | BAROQUE BROWN |
| 14A | OFF WHITE |
| 2CQ | VELVET BROWN |
| 29E | CREAM II |
| 3QG | CUCUMBER CALM |
| 84V | TURF ORANGE |
| 73B | CASHMERE |
| 06H | FLINT GREY |

**출처**: `OCI.MSBS_ITEM.MCS_COLOR_CD` 텍스트 파싱 (`색상명(3자리코드)` 형식).
[검증: 2026-03-03 JJ Plant PH 공정 데이터 — 등장 코드 15개 전부 매핑 성공]

### 10-3. CTE 박제 (재사용 패턴)

```sql
WITH COLOR_MAP AS (
  SELECT '00A' AS K, 'BLACK' AS N FROM DUAL UNION ALL
  SELECT '10A', 'WHITE'           FROM DUAL UNION ALL
  SELECT '01V', 'WOLF GREY'       FROM DUAL UNION ALL
  SELECT '11K', 'SAIL'            FROM DUAL UNION ALL
  SELECT '12J', 'SUMMIT WHITE'    FROM DUAL UNION ALL
  SELECT '06F', 'ANTHRACITE'      FROM DUAL UNION ALL
  SELECT '0BB', 'PHOTON DUST'     FROM DUAL UNION ALL
  SELECT '22Z', 'BAROQUE BROWN'   FROM DUAL UNION ALL
  SELECT '14A', 'OFF WHITE'       FROM DUAL UNION ALL
  SELECT '2CQ', 'VELVET BROWN'    FROM DUAL UNION ALL
  SELECT '29E', 'CREAM II'        FROM DUAL UNION ALL
  SELECT '3QG', 'CUCUMBER CALM'   FROM DUAL UNION ALL
  SELECT '84V', 'TURF ORANGE'     FROM DUAL UNION ALL
  SELECT '73B', 'CASHMERE'        FROM DUAL UNION ALL
  SELECT '06H', 'FLINT GREY'      FROM DUAL
)
-- ... 본 쿼리 ...
LEFT JOIN COLOR_MAP CM ON CM.K = SUBSTR(OS.COLOR_CD, -3)
-- CM.N 이 색상명
```

### 10-4. 신규 코드 등장 시 — 동적 추출

OS&D 데이터에 위 15개 외 코드가 나오면 (예: `C90`, `04Z`) `MSBS_ITEM.MCS_COLOR_CD` 에서 그 자리에서 매핑 가져오기.

```sql
-- 등장 코드 → 색상명 동적 lookup
-- 사용 시 :V_NEW_COLOR_KEYS 위치에 콤마 구분 코드 목록 ('C90','04Z',...) 넣기
WITH SPLIT AS (
  SELECT TRIM(REGEXP_SUBSTR(MCS_COLOR_CD, '[^/]+', 1, LEVEL)) AS PART
  FROM (
    SELECT DISTINCT MCS_COLOR_CD 
    FROM OCI.MSBS_ITEM
    WHERE MCS_COLOR_CD LIKE '%(%' AND MCS_COLOR_CD <> 'NONE'
  )
  CONNECT BY REGEXP_SUBSTR(MCS_COLOR_CD, '[^/]+', 1, LEVEL) IS NOT NULL
        AND PRIOR MCS_COLOR_CD = MCS_COLOR_CD
        AND PRIOR SYS_GUID() IS NOT NULL
),
PARSED AS (
  SELECT 
    TRIM(SUBSTR(PART, INSTR(PART,'(')+1, 
                INSTR(PART,')') - INSTR(PART,'(') - 1))     AS COLOR_KEY,
    TRIM(SUBSTR(PART, 1, INSTR(PART,'(')-1))                AS COLOR_NAME
  FROM SPLIT
  WHERE PART LIKE '%(%' AND PART LIKE '%)%'
),
RANKED AS (
  SELECT COLOR_KEY, COLOR_NAME, COUNT(*) cnt,
         ROW_NUMBER() OVER (PARTITION BY COLOR_KEY ORDER BY COUNT(*) DESC) rn
  FROM PARSED
  WHERE LENGTH(COLOR_KEY)=3 AND LENGTH(COLOR_NAME)>0
  GROUP BY COLOR_KEY, COLOR_NAME
)
SELECT COLOR_KEY, COLOR_NAME, cnt AS RELIABILITY
FROM RANKED 
WHERE rn = 1
  AND COLOR_KEY IN ( :V_NEW_COLOR_KEYS )
ORDER BY cnt DESC;
```

**규칙**:
- 분석 시작 시 `SELECT DISTINCT SUBSTR(COLOR_CD,-3) FROM MSPQ_EX_OSND WHERE ...` 으로 등장 코드 먼저 확인
- 위 15개 박제에 다 있으면 그대로 CTE 사용
- 모르는 코드가 있으면 §10-4 쿼리로 추출 후 CTE 에 추가
- 추출 결과의 `RELIABILITY` 가 낮으면 (예: 3 미만) 답변에 [추정] 표시

### 10-5. 한계

- 색상 매핑이 **정식 마스터가 아니라 `MCS_COLOR_CD` 텍스트 파싱 결과** [추정]. 회사 코드 마스터 문서와 100% 일치하는지 미확인.
- 같은 코드에 여러 이름 매핑되는 경우 — 빈도 1위 채택.
- 복합색 (`BLACK(00A)/WHITE(10A)`) 의 경우 OS&D 데이터에서는 단일 코드 (`1010A` 끝 3자리 = `10A` = WHITE) 로 들어옴 — STYLE 의 주색만 반영하는 듯 [추정].
- `EPPP_MAT_MCS_COLOR_INFO@JJEDIF` DB link 가 복구되거나 OCI 에 정식 마스터가 동기화되면 그쪽이 진실의 출처. 이 섹션은 우회 경로.
