# CKP Manual Report — Claude Desktop 실행 가이드

> **기획 의도**: 이 프로그램은 **Claude Desktop에서 한마디로 구동**하는 것이 목적.
> "CKP 리포트 만들어서 메일 보내줘" → 11개 생성 + 메일 발송.

---

## 왜 Claude Desktop인가 (구조)

- Claude Desktop의 도구는 **당신 Mac 위에서** 실행됩니다. → SQLcl(`sql`)·파일·SMTP가 전부 로컬이라 그대로 동작.
- `ckp-reports` MCP 서버가 Mac에서 `make_all.py`를 통째로 실행합니다.
  → **대용량 CSV가 Claude 대화 컨텍스트를 지나가지 않음** (Cowork 샌드박스에서 불안정했던 이유가 바로 이 데이터 이동이었음).
- DB 조회는 `make_all.py`가 내부에서 **저장된 SQLcl 연결 `changshinincaipoc`(ADMIN, 비번 저장됨)** 로 처리 → 비밀번호·Instant Client·월렛비번 전부 불필요.

```
Claude Desktop  ──(MCP 호출)──▶  ckp-reports 서버 (Mac)
                                     │  make_all.py  ──▶ SQLcl(changshinincaipoc) ──▶ Oracle
                                     │              ──▶ 엑셀 빌더 11종 ──▶ report/CKP_official/
                                     └  mail_reports.py ──▶ Gmail SMTP (ZIP 첨부)
```

---

## 1회 설정

### (1) 라이브러리
```bash
# 리포트 생성기용 venv (이미 있으면 재사용)
cd "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/CS-MES/balance_outgoing_mailer"
python3 -m venv .venv && ./.venv/bin/pip install -U mcp openpyxl
```

### (2) 사전 확인
```bash
sql -version                                                   # SQLcl 있음?
sql -S /nolog <<< $'connect -name changshinincaipoc\nselect 1 from dual;\nexit'   # 연결 됨?
```
- `sql` 이 PATH에 없으면, ckp_mcp가 쓰도록 `SQLCL` 환경변수에 전체 경로 지정(아래 config의 env).
- 메일: `balance_outgoing_mailer/config.ini` 의 `[smtp] password` = Gmail **앱 비밀번호**(16자리), `[report] recipients` 확인.

### (3) claude_desktop_config.json 에 서버 등록
`~/Library/Application Support/Claude/claude_desktop_config.json` 의 `mcpServers` 에 추가:

```json
"ckp-reports": {
  "command": "/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/CS-MES/balance_outgoing_mailer/.venv/bin/python",
  "args": ["/Users/nicklee/Library/CloudStorage/OneDrive-postech.ac.kr/CS-MES/ckp_reports/ckp_mcp.py"],
  "env": { "SQLCL": "sql" }
}
```
> `sql` 이 PATH에 없으면 `"SQLCL": "/Applications/SQLcl/bin/sql"` 처럼 전체 경로로.

### (4) Claude Desktop 재시작
설정 저장 후 Claude Desktop을 완전히 종료했다가 다시 켜면 `ckp-reports` 도구 3개가 뜹니다.

---

## 사용 (Claude Desktop에서 한마디)

| 하고 싶은 것 | 이렇게 말하면 | Claude가 호출하는 도구 |
|---|---|---|
| 오늘자 11개 생성 | "CKP 리포트 만들어줘" | `ckp_make_all` |
| 생성 + 메일 발송 | "CKP 리포트 만들어서 메일 보내줘" | `ckp_make_and_mail` |
| 이미 만든 것 메일만 | "방금 CKP 리포트 메일로 보내줘" | `ckp_mail` |
| 특정 날짜 | "2026-07-07자 CKP 리포트 만들어줘" | `ckp_make_all("2026-07-07")` |

결과물: `CS-MES/report/CKP_official/` 에 `NO) 리포트명.xlsx` 11개. 메일은 ZIP 첨부로 수신자에게 발송.

---

## 매일 자동 (선택)
Claude Desktop 없이도 스케줄로 돌리려면(launchd, 매일 08:00) — `SETUP.md §3` 참고.
`make_all.py && mail_reports.py` 를 그대로 등록하면 됩니다.

---

## 문제 해결
| 증상 | 조치 |
|---|---|
| 도구가 안 뜸 | config.json 경로/JSON 문법 확인 → Claude Desktop 완전 재시작 |
| `SQL 오류/파싱 실패` | `sql -S /nolog` 에서 `connect -name changshinincaipoc` 수동 테스트. `SQLCL` 경로 확인 |
| 메일 `535` | `[smtp] password` 가 Gmail 앱비번(16자리)인지, `user`/`from` 이 그 앱비번 주인 계정인지 |
| 엑셀 저장 `Resource deadlock` | OneDrive 클라우드 전용 잠금. Finder에서 report 폴더 "이 기기에 항상 유지" |

> 참고: 지금 쓰는 Cowork(웹) 세션은 리눅스 샌드박스라 SQLcl·SMTP가 없어 우회로(sqlcl MCP·Zapier)를 썼습니다.
> **Claude Desktop = Mac 로컬 실행**이라 위 방식이 원안대로 안정적으로 동작합니다.
