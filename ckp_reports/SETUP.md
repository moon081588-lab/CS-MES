# CKP Manual Report 자동화 — 설정 및 사용 가이드

> 공식 11개 리포트를 **한 줄로 생성**하고, **메일로 발송**하는 프로그램의 설정법.
> (기존 `balance_outgoing_mailer/README.md` 는 예전 단일 리포트용 문서 — 이 문서가 현행 기준)

---

## 0. 이 프로그램이 하는 일

```
python make_all.py 2026-07-07      → 11개 리포트 엑셀 생성 (report/CKP_official/)
python mail_reports.py 2026-07-07  → 11개를 ZIP 첨부해 메일 발송
```

| 단계 | 무엇을 하나 | DB 접속 |
|---|---|---|
| 생성 | SQL 실행 → CSV → 엑셀 빌더 11종 | SQLcl 저장연결 |
| 발송 | `report/CKP_official/*.xlsx` → ZIP → Gmail SMTP | 불필요 |

---

## 1. 사전 준비 (1회)

### 1-1. Python + 라이브러리
```bash
python3 --version            # 3.9 이상
pip3 install openpyxl
```

### 1-2. SQLcl (Oracle) — **비밀번호 입력 불필요**
이 프로그램은 Oracle에 직접 붙지 않습니다. **이미 저장된 SQLcl 연결**을 그대로 씁니다.
Instant Client·월렛 비밀번호 **모두 불필요**합니다.

```bash
sql -version                                    # SQLcl 설치 확인
sql -S /nolog <<< $'connect -name changshinincaipoc\nselect 1 from dual;\nexit'
```
→ 결과가 나오면 준비 완료. (연결명이 다르면 `make_all.py ... --conn 이름` 으로 지정)

### 1-3. 메일 설정 — `balance_outgoing_mailer/config.ini`
```ini
[smtp]
host = smtp.gmail.com
port = 587
use_tls = true
user = moon081588@gmail.com
password = <Gmail 앱 비밀번호 16자리>     ; 일반 비번 아님. Google 계정 > 보안 > 앱 비밀번호
from = moon081588@gmail.com

[report]
plants = 3110,3120,3210
window_before = 3          ; No.5(Outgoing Market) 전용 버킷
window_after = 7
recipients = moon081588@gmail.com, idea.seahsteel@gmail.com
strict_outgoing = false    ; OCI 동기화 완료 후 true 로
```
> ⚠️ `config.ini` 는 비밀번호를 담고 있어 **.gitignore 로 커밋 제외**되어 있습니다. 절대 커밋하지 마세요.

### 1-4. 원본 워크북 경로 (No.2 존 양식 템플릿용)
`make_all.py` 의 `DEFAULT_SRC` 가 아래를 가리킵니다. 경로가 다르면 `--src` 로 지정하세요.
```
연구참여 (공유)/Google Drive Files/현업 Report Sample/CKP Manual Report (종합).xlsx
```

---

## 2. 사용법

```bash
cd "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/CS-MES/ckp_reports"

# ① 11개 리포트 생성
python3 make_all.py 2026-07-07

# ② 11개를 ZIP 첨부해 메일 발송
python3 mail_reports.py 2026-07-07
```

옵션:
```bash
python3 make_all.py 2026-07-07 --conn changshinincaipoc \
        --src "/path/to/CKP Manual Report (종합).xlsx"
```

**결과물**: `CS-MES/report/CKP_official/` 에 `NO) 리포트명.xlsx` 11개

---

## 3. 매일 자동 실행 (선택)

`~/Library/LaunchAgents/com.changshin.ckpreports.plist` (macOS, 매일 08:00):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.changshin.ckpreports</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd "$HOME/Library/CloudStorage/OneDrive-postech.ac.kr/CS-MES/ckp_reports" &amp;&amp; python3 make_all.py &amp;&amp; python3 mail_reports.py</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/ckp_reports.log</string>
  <key>StandardErrorPath</key><string>/tmp/ckp_reports.log</string>
</dict></plist>
```
```bash
launchctl load ~/Library/LaunchAgents/com.changshin.ckpreports.plist
```
(날짜 인자를 생략하면 오늘 날짜로 실행됩니다.)

---

## 4. 리포트 11종 · 데이터 소스

| No | 리포트 | 소스 | 빌더 |
|---|---|---|---|
| 1 | DAILY REPORT SCAN | `POP_PCARD_SCAN` op_cd='PHH' | `daily_scan.py` |
| 2 | Balance IP Production | 원본 존(zone) 양식 템플릿 복사 | `no2_zone.py` |
| 3 | IP Prod. by size | 부족분(II, Production) | `bysize_v2.py` |
| 4 | IP Outgoing by size | 부족분(II+IP, Outgoing) | `bysize_v2.py` |
| 5 | IP Outgoing Market | 미출고 + SCAN BEM/BEP | `balance_outgoing_mailer` |
| 6 | External OS&D IPPH | `MSPQ_EX_OSND` BALANCE | `osnd_pivot.py` |
| 7 | Balance CMP | 부족분(CP, Production) | `balance_bydate.py` |
| 8 | Outgoing PH | 부족분(PH+PP, Outgoing) | `balance_bydate.py` |
| 9 | PH before UV | 부족분(PH+PP, END_ROUTING='N') | `balance_bydate.py` |
| 10 | PH after UV | 부족분(PH+PP, END_ROUTING='Y') | `balance_bydate.py` |
| 11 | PH in Market by size | 부족분(PH+PP, Production) | `bysize_v2.py` |

모든 SQL은 `balance_sql.py` 한 곳에 있습니다.

### 양식 원칙
- **사이즈 컬럼**(1~18, OS&D는 1~17)과 **날짜 컬럼**(D+N…D-Day…D-7)은 **원본 고정 구조**로 항상 렌더됩니다.
  → 데이터가 0행이어도 열이 사라지지 않습니다.

### 아직 빈칸인 컬럼 (소스 미확정 — 확인되면 해당 빌더 한 곳만 채우면 됨)
- 전 리포트: `IP SPRAY (BEM)`, `PAD PRINTING (BEP)`, `SCAN DI CKP`
- No.1: `YIELD`, `TARGET`, `OS&D`, `TOTAL Kg`
- No.2: `STOCK CKP`, `STOCK SPRAY`, `BTM SET`, `Set Bal Stock`

---

## 5. 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| `SQL 오류: ORA-...` | SQLcl 연결명 확인 → `sql -S /nolog` 에서 `connect -name changshinincaipoc` 수동 테스트 |
| `결과 파싱 실패` | SQLcl 출력 형식 문제. `sql -version` 확인, `set sqlformat csv` 지원 버전인지 점검 |
| 메일 `535 BadCredentials` | `[smtp] password` 가 **Gmail 앱 비밀번호(16자리)** 인지, `user`/`from` 계정이 그 앱비번의 주인인지 확인 |
| 엑셀 저장 시 `Resource deadlock` | OneDrive가 파일을 클라우드 전용으로 잠금. Finder에서 해당 파일 "항상 이 기기에 유지" 하거나, 기존 파일을 옮긴 뒤 재실행 |
| 특정 리포트가 0행 | 정상일 수 있음(예: 그 기간 미생산 부족분 없음). 열/헤더는 그대로 나옵니다 |

---

## 6. 파일 구성

```
ckp_reports/
├─ make_all.py        ★ 11개 생성 오케스트레이터 (SQLcl 사용)
├─ mail_reports.py    ★ 11개 ZIP 첨부 메일 발송 (SMTP)
├─ balance_sql.py       모든 리포트의 SQL 생성기
├─ bysize_v2.py         by-size 빌더 (고정 사이즈, PH는 ME/WO 이중헤더)
├─ balance_bydate.py    by-date 빌더 (D-offset 고정 날짜열)
├─ osnd_pivot.py        No.6 OS&D 빌더
├─ daily_scan.py        No.1 스캔 빌더
├─ no2_zone.py          No.2 존 양식 템플릿 복사
└─ SETUP.md             (이 문서)

report/CKP_official/    생성 결과 11개
report/Past Reports/    구버전 보관
```

---

## 7. 보안 주의

- `config.ini`(Gmail 앱비번), `wallet/` 은 **절대 커밋 금지** (이미 `.gitignore` 처리됨).
- 비밀번호는 파일에만 두고 채팅·이슈에 붙여넣지 마세요.
