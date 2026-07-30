# CS-MES / CKP Manual Report

창신 CKP 공장(공장코드 `3120`) 의 **공식 수기 리포트 11종**을 GMES 원장의 복제 DB
(OCI Autonomous) 에서 그대로 뽑아 엑셀로 만드는 프로그램입니다.
같은 일을 Claude 채팅으로 시킬 수 있는 skill 도 함께 들어 있습니다.

> ### 현장 PC 에 설치할 파일은 여기 하나입니다
> **[Releases → Latest](https://github.com/moon081588-lab/CS-MES/releases/latest)** 의
> `CKP-Report-field-v<날짜>.zip`  (파일 이름은 영문입니다 — GitHub 가 자산 이름의 한글을 지웁니다)
>
> 프로그램 + 오프라인 설치용 라이브러리 + Claude skill + 설치순서가 한 파일에 들어 있습니다.
> 메신저나 메일로 돌아다니는 zip 은 옛날 것일 수 있으니 쓰지 마세요.
> 이 저장소를 clone 하는 것은 **코드를 고칠 때**만입니다.

---

## 빠른 시작

```
CKP.bat
```

실행 파일은 이것 하나입니다. 누르면 메뉴가 뜹니다.

| 번호 | 하는 일 | 언제 |
|---|---|---|
| **1** | 리포트 11개 만들기 | 평소에는 이것만 |
| **2** | 처음 설정 / 설정 바꾸기 | 새 PC 에서 맨 처음 한 번 |
| **3** | DB 연결만 점검 | 뭔가 이상할 때 |
| **4** | Claude 에 이 폴더 연결 | skill 로 시키고 싶을 때만 |

새 PC 라면 **2 번 → 1 번** 순서입니다. 2 번이 라이브러리 설치, 지갑 인식,
DB 계정 입력, 방화벽 확인, 실제 접속 시험까지 한 번에 합니다.

자세한 절차: [program/사용법.txt](program/사용법.txt)
결과 위치: `report/CKP_official/기준<날짜>_요청<날짜>/`

### 필요한 것

| | |
|---|---|
| 파이썬 | 64비트 **3.11 ~ 3.14** (3.12 권장). 없거나 안 맞으면 2 번이 알려 줍니다 |
| 라이브러리 | `openpyxl`, `oracledb` — 2 번이 알아서 설치 |
| OCI 지갑 | 저장소 루트 `wallet/` 에 넣으면 됩니다. zip 째 넣어도 알아서 풉니다 |
| DB 계정 | 2 번에서 입력. **저장소·배포본 어디에도 비밀번호는 없습니다** |
| SQLcl | 선택. 계정을 넣으면 드라이버로 직접 붙어 SQLcl·Java 가 필요 없습니다 |

---

## 리포트 11종

`ITEM_CLASS_TYPE` · `DIV` 조합의 **유일한 기준은 `program/ckp_reports/core/sql.py` 의
`REPORTS` 딕셔너리**입니다. 문서나 주석이 아니라 그 표를 보세요.

| No | 리포트 | 품목 | 구분 |
|---|---|---|---|
| 1 | 1. DAILY REPORT SCAN | — | 스캔 집계 |
| 2 | 3-1. Balance IP Production | `II` | Production |
| 3 | 3-2. Balance IP Prod. by size | `II` | Production |
| 4 | 3-2. Balance IP Outgoing by size | `II`+`IP` | Outgoing |
| 5 | 3-3. Balance IP Outgoing Market | — | 별도 엔진 |
| 6 | 3-4. Balance External OS&D IPPH | — | OS&D |
| 7 | 3-1. Balance CMP | `CP` | Production |
| 8 | 3-1. Balance Outgoing PH | `PH`+`PP` | Outgoing |
| 9 | 3-1. Balance PH before UV | `PH`+`PP` | Production (공정 중) |
| 10 | 3-1. Balance PH after UV | `PH`+`PP` | Production (최종) |
| 11 | 3-2. Balance PH in Market PH by | `PH`+`PP` | Production |

GMES 화면 기준으로 2·3·4·7·8·9·10·11 은 모두 `P_MSPD90000S_Q`(Shortage Balance
Checking), 1 은 `P_MSPD29000S_Q`, 6 은 `P_MSPQ84000S_Q` 입니다.

---

## 폴더

```
CKP.bat        실행 진입점 (이것 하나)
README.md      이 파일
program/       프로그램 본체
  ckp_reports/   리포트 생성 코드
    core/          SQL 정의 · DB 접속 · 엑셀 렌더링
    reports/       리포트 11종 (r01 ~ r11)
    ckp_mcp.py     Claude 용 MCP 서버
  tools/         메뉴 · 설치 · 점검 · 연결 (ckp.py 가 창구)
  .venv/         이 프로그램이 쓰는 파이썬 환경 (커밋 안 함)
  CKP Manual Report (종합).xlsx   서식·항목의 원본 수기 리포트
  사용법.txt
skill/         Claude skill 원본 (v12.7)
docs/          리포트별 DB 다이어그램 (테이블 · 조인 · 필터, 2026-07-21)
report/        결과 엑셀 (커밋 안 함)
```

---

## Claude 로 시키기

`CKP.bat` → **4 번** → Claude 완전 종료 후 재시작 → `skill/` 을 `.skill` 로 묶어 업로드
→ 채팅창에 **"레포트 11개 작성해줘"**.

4 번은 `claude_desktop_config.json` 에 아래 서버를 **지금 이 폴더의 절대경로**로
등록합니다. 사람이 경로를 손으로 적지 않습니다. 쓰지 않게 된 서버가 남아 있으면 지웁니다.

| 서버 | 파일 |
|---|---|
| `ckp-reports` | `program/ckp_reports/ckp_mcp.py` |

Claude 를 쓰지 않아도 `CKP.bat` 1 번만으로 리포트는 똑같이 나옵니다.

---

## 스스로 복구하는 것들

경로·환경이 어긋나 조용히 실패하는 일이 반복돼서, 프로그램이 먼저 알아채고
맞추도록 했습니다.

| 상황 | 프로그램이 하는 일 |
|---|---|
| 폴더를 옮겨 MCP 등록이 깨짐 | `CKP.bat` 실행 때마다 서버 경로를 점검해 자동 수정 (0.5초) |
| 서버를 띄우는 파이썬에 `mcp` 가 없음 | 프로젝트 안의 기존 가상환경 라이브러리를 빌려 씀 (설치 안 함) |
| 지갑 `sqlnet.ora` 에 남의 PC 경로가 박혀 있음 | 그 PC 경로로 다시 씀 |
| 환경변수 `TNS_ADMIN` 이 없는 폴더를 가리킴 | 무시하고 자동 탐색 |
| DB 가 순간 끊김 (`ORA-03113` 등) | 5초 → 10초 간격으로 최대 3회 재시도 |
| 계정·지갑 오류 (`ORA-01017` 등) | 재시도 없이 즉시 중단하고 원인 한 줄로 표시 |
| 방화벽이 DB 포트를 막음 | 접속 전 TCP 확인으로 6초 안에 판별 |

단, **Claude 완전 종료 후 재시작**만은 사람이 해야 합니다. Claude 는 시작할 때만
설정을 읽습니다.

---

## 배포 경로 두 가지

| | 이 저장소 (clone) | 배포 zip (Releases) |
|---|---|---|
| 받는 곳 | `git clone` | [Releases → Latest](https://github.com/moon081588-lab/CS-MES/releases/latest) |
| 라이브러리 | 인터넷에서 받음 | `vendor/` 동봉 — **인터넷 불필요** |
| skill | `skill/` 폴더 (직접 압축) | 업로드용 zip 이 이미 들어 있음 |
| 용도 | 코드 수정 | **현장 PC 설치** |

`CKP.bat` 은 두 배치를 모두 인식합니다(`program/` 아래든, 저장소 루트든).
현장 PC 가 PyPI 에 못 나가면 저장소 방식은 거기서 멈추므로 **현장에는 zip** 을 쓰세요.

zip 은 저장소에 커밋하지 않고 Releases 에만 둡니다. 26MB 짜리를 커밋하면 고칠 때마다
git 히스토리에 영구히 쌓여 clone 이 느려지기 때문입니다. 그래서 **최신본이 어느 것인지는
Releases 페이지가 유일한 답**입니다 — 로컬 `dist/` 폴더에 남아 있는 zip 은 믿지 마세요.

새 배포본을 낼 때: Releases → Draft a new release → 태그 `v<날짜>` → zip 을 끌어다 놓기.

---

## 커밋하지 않는 것

지갑(`**/wallet/`), 비밀번호가 든 `config.ini`, 생성물(`report/`, `sql/`, `*.csv`).
`.gitignore` 를 보세요. DB 계정·지갑 비밀번호는 `CKP.bat` 2 번에서 입력받아
**그 PC 안에만** 저장됩니다.

---

## 숫자를 볼 때 알아야 할 것

- **우리가 보는 DB 는 원장의 복제본**입니다. 최근 며칠이 비어 있는 것은 고장이
  아닙니다. 실행할 때마다 `[health]` 줄로 데이터 최신일을 알려 줍니다.
- **마감(CLOSING) 필터는 자동 판정**입니다. 마감 마스터(`MSPD_PROD_GROUP`) 커버리지가
  90% 이상이면 정식(strict), 미만이면 임시(loose). 원장 동기화가 재개되면 설정을
  바꾸지 않아도 정식으로 넘어갑니다.
- **중복 제거는 `(PCARD_NAME, ITEM_CLASS, SIZE_CD)` 별 `ROUTING_SEQ` 최대 1행**
  입니다(2026-07 변경). 옛 `END_ROUTING_YN='Y'` 방식은 비최신 행에도 `Y` 가
  351,265 건 있어 유일키로 쓸 수 없었습니다(검증: CP 38,289 → 23,255).
  옛 방식으로 계산한 숫자와 다른 것이 정상입니다.
- **No.3 의 품목범위는 `II` 만**입니다(2026-07-28 확정). 원본 수기 리포트
  `3-2. Balance IP Prod. by size` 시트(기준 2026-04-20)의 Item Class 열이
  `II01~II93` 여덟 종뿐이고 `IP` 는 257행 중 0행이었습니다. 같은 워크북의 No.4 는
  반대로 `IP` 가 대부분이므로 **이 비대칭은 원본 그대로**입니다.
- **기준일은 그 PC 가 있는 지역의 오늘**입니다. 한국에서 돌리면 한국 날짜,
  현장에서 돌리면 현장 날짜. 어느 시계를 썼는지는 실행할 때마다 `[time]` 줄에 찍힙니다.
  지역과 무관하게 고정하려면 `config.ini` 의 `site_timezone` 에 `Asia/Seoul` 처럼 적으면 됩니다.
  PC 시계가 실제와 2시간 넘게 어긋나면 DB 시각과 대조해 경고합니다.
  DB 날짜 컬럼은 현장(WIB, UTC+7) 시계라, PC 가 더 앞선 시간대면 자정 직후 몇 시간은
  하루 어긋납니다 — 그 구간에서도 경고가 나옵니다.

---

## 문제가 생기면

`CKP.bat` → **3 번**. 방화벽 / 지갑 / 비밀번호 / 계정 중 무엇이 문제인지 한 줄로
짚어 줍니다. 자주 나오는 다섯 가지는 이렇습니다.

| 증상 | 원인 |
|---|---|
| 연결 시간 초과 | 사내 방화벽이 `adb.ap-chuncheon-1.oraclecloud.com:1522` 를 막음 |
| `ORA-01017` | DB 계정 또는 비밀번호가 틀림 |
| 지갑을 못 엶 | 지갑 비밀번호가 비었거나 틀림 |
| `ORA-12154` / `ORA-28759` | `wallet/` 에 지갑 파일 8개가 다 없음 |
| `ORA-17956` | 폴더 경로에 한글이나 공백 — `C:\CKP-Report` 로 옮길 것 |
