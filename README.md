# CS-MES

창신 MES 레포트 자동생성기 구축

밑창(底部)의 **미드솔(IP·PH) + 아웃솔(OS) 출고 부족분(BALANCE OUTGOING)** 을 라이브 DB에서 조회하여
원본과 같은 구조의 Excel로 만들고, **매일 아침 8시에 사내 메일로 자동 발송**하는 독립 실행 프로그램입니다.

> **Claude·특정 계정과 무관**합니다. 순수 Python이므로 어느 PC/서버든 올려서 OS 스케줄러로 돌리면 됩니다.

---

## 레포 구조

```
CS-MES/
├─ README.md                         ← (이 문서)
└─ balance_outgoing_mailer/
   ├─ balance_outgoing_mailer.py     본체 (조회 → Excel → 메일 발송)
   ├─ config.ini.example             설정 템플릿 (복사해서 config.ini 로 사용)
   ├─ .gitignore
   └─ SAMPLE_BALANCE_OUTGOING_*.xlsx 샘플 결과물
```

> 실제 `config.ini`(비밀번호 포함)는 `.gitignore` 로 커밋 제외됩니다.

---

## ⚠️ 데이터 한계 — 현재 Oracle DB에 없는 항목

원본 BALANCE OUTGOING 리포트에는 있으나, **현재 우리가 보유한 Oracle DB(OCI)에는 아래 정보 자체가 들어있지 않습니다.**
그래서 이 컬럼들은 리포트에 **자리만 만들고 빈칸**으로 출력됩니다. 추후 해당 데이터 소스가 확보되면
코드의 `color_specs()` / `scan_di_ckp()` **한 곳만** 채우면 자동 반영되도록 설계해 두었습니다.

| 빈칸(데이터 없음) | 비고 |
|---|---|
| **COLOR** | 제품 컬러웨이. 색상 마스터(`MSBS_ITEM`/`MSBS_ITEM_STYLE`)가 공란 |
| **IP SPRAY (BEM)** | 미드솔 스프레이 색상 스펙 — 소스 미발견 |
| **PAD PRINTING (BEP)** | 패드 프린팅 색상 스펙 — 소스 미발견 |
| **SCAN DI CKP** | DI 체크포인트 스캔 — 현재 스캔 데이터에 DI 식별자 없음 |

> 정상 출력 항목: PLANT(동 A·B·C…), ITEM CLASS, LINE, MODEL, STYLE, GEN, 일자버킷(D+3~D-7, 색상강조), TOTAL, GRAND TOTAL, SCAN BEM/BEP.

---

## 1. 설치 (대상 PC/서버에서 1회)

```bash
# Python 3.9+ 필요
pip install oracledb openpyxl
```

- `oracledb` 는 **Thin 모드**라 Oracle Client(Instant Client) 설치 없이 동작합니다.

---

## 2. 설정 (`config.ini`)

```bash
cd balance_outgoing_mailer
cp config.ini.example config.ini   # 복사 후 값 채우기
```

### DB 접속 — 두 방법 중 택1
- **① OCI 월렛 (Autonomous DB)**: 월렛 zip을 풀어서 그 폴더 경로를 `wallet_dir` 에 지정, `dsn` 은 TNS 별칭(예: `changshinincaipoc_medium`).
- **② 사내망 직접접속**: `dsn = host:port/service_name` (easy connect) 형태로 적고 `wallet_dir` 은 비워둠.

### SMTP — 사내 메일 서버
- `host`/`port`/`from` 필수. 인증이 필요하면 `user`/`password` 입력, 아니면 비워둠.

### 리포트
- `plants` 포함 공장(예: `3110,3120,3210`), `recipients` 받는사람(쉼표로 여러 명), `window_before/after` 일자버킷 범위(D+3~D-7).

---

## 3. 수동 점검 (스케줄 걸기 전에 꼭)

```bash
python balance_outgoing_mailer.py --test-db    # DB 접속만 확인
python balance_outgoing_mailer.py --dry-run    # Excel만 생성(메일 발송 X) → 파일 열어 확인
python balance_outgoing_mailer.py              # 실제: 조회 → Excel → 메일 발송
```

---

## 4. 매일 아침 8시 자동 실행 설정

### Windows (작업 스케줄러)
```cmd
schtasks /create /tn "BalanceOutgoing" /tr "python C:\경로\balance_outgoing_mailer\balance_outgoing_mailer.py" /sc daily /st 08:00
```
또는 `작업 스케줄러` GUI → 기본 작업 만들기 → 매일 08:00 → 프로그램 시작(python + 스크립트 경로, 시작 위치 = 스크립트 폴더).

### Linux / macOS (cron)
```bash
crontab -e
# 매일 08:00
0 8 * * * cd /경로/balance_outgoing_mailer && /usr/bin/python3 balance_outgoing_mailer.py >> cron.log 2>&1
```

---

## 5. 집계 규칙 (원본 BALANCE OUTGOING 로직)

미출고 부족분 판정 = 다음 조건의 패스카드 실적:
- `OUT_DATE = '19991231'` (미출고)  · `PROD_MOVE_TYPE = 'PROD'`  · `END_ROUTING_YN = 'Y'`
- 시트별 반제품 등급: **IP**(II·IP) / **PH**(PH·PP·CP) / **OS**(OS)
- **마감 그룹 제외**: `MSPD_PROD_GROUP.CLOSING_YN='Y'` 인 그룹만 제외

> ⚠️ **아웃솔 관련 중요**: 공장 3110의 아웃솔 생산그룹은 그룹 마스터(`MSPD_PROD_GROUP`)에
> 등재돼 있지 않습니다. 그래서 원본처럼 `CLOSING_YN='N'` 을 *요구*하면 3110 아웃솔이 거의 다 누락됩니다.
> 이 프로그램은 **"명시적으로 마감된(CLOSING_YN='Y') 그룹만 제외"** 규칙을 써서 두 공장 모두 빠짐없이 집계합니다.

---

## 6. 산출물 형식

- 시트 3개: `IP{MMDD}` / `PH{MMDD}` / `OS{MMDD}` (예: IP0624)
- 컬럼: PLANT · ITEM CLASS · LINE · MODEL · STYLE · [D+3 … D-7 일자버킷] · TOTAL, 하단 GRAND TOTAL
- 행은 잔량(TOTAL) 큰 순 정렬

---

## 7. 주의사항

- **네트워크 필요**: 창신 DB(OCI 클라우드)와 사내 SMTP에 접근 가능해야 합니다. 완전 오프라인 PC에서는 동작하지 않습니다(사내망에서 DB·메일서버 접근 가능하면 OK).
- 비밀번호가 `config.ini` 에 평문으로 들어가므로 **파일 접근 권한**을 제한하세요(chmod 600 / NTFS 권한).
- 실행 결과·오류는 `balance_outgoing.log` 에 기록됩니다.
