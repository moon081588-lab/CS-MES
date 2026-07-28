# Reports Pipeline — CKP 공식 리포트는 SQL 로 재현하지 말고 프로그램에 맡긴다

이 skill 은 **분석**(화면 재현·질문 답변)을 담당한다. 반면 현업에 나가는 **CKP Manual Report 공식 11 개 엑셀**은 별도 프로그램(CS-MES)이 만든다. 둘을 섞으면 숫자가 갈린다.

> **판단 기준**
> - "부족분이 얼마야", "라인별로 보여줘", "왜 늘었어" → **이 skill 로 SQL 분석**
> - "리포트 만들어줘", "11 개 뽑아줘", "일보 보내줘" → **아래 MCP 도구로 위임**

---

## 0. 먼저 — 도구가 있는지 확인한다 (없으면 만들 수 없다)

이 skill 은 **문서**다. 스스로 엑셀을 만들지 못한다. 공식 11 개는 사용자 PC 에 설치된
**로컬 MCP 서버 `ckp-reports`** 가 만든다. 그러니 요청을 받으면 **먼저 도구가 있는지 본다.**

- 사용 가능한 도구 목록에서 이름이 `…ckp_make_all` 로 끝나는 것을 찾는다(접두어는 환경마다 다르다).
- **있으면** → 2 장으로 간다.
- **없으면** → SQL 로 11 개를 흉내내려 하지 말 것. 그건 양식·색·사이즈열이 다른 가짜다.
  아래를 그대로 안내하고 멈춘다.

> **CKP 리포트 11 개는 이 PC 에 프로그램이 설치되어 있어야 만들어집니다.**
> 지금은 `ckp-reports` 도구가 보이지 않습니다. 아래 순서로 한 번만 설치하면 됩니다.
>
> 1. CS-MES 폴더를 **공백·한글이 없는 경로**에 풀어 둡니다. 예: `C:\CS-MES`
>    (OneDrive·Google Drive 안은 피하세요. 자바가 지갑 경로를 못 읽습니다 — ORA-17956)
> 2. OCI 지갑 zip 을 `C:\CS-MES\balance_outgoing_mailer\wallet` 에 풉니다.
> 3. `C:\CS-MES\install_windows.bat` 을 실행합니다.
>    (파이썬 가상환경·라이브러리·config.ini·Claude 등록까지 한 번에 처리합니다)
> 4. `config.ini` 의 `[db] password` 를 채웁니다.
> 5. **Claude Desktop 을 완전히 종료했다가**(트레이 아이콘까지) 다시 켭니다.
> 6. 다시 "CKP 레포트 11 개 만들어줘" 라고 하시면 됩니다.
>
> 설치가 이미 되어 있는데도 도구가 안 보이면, 5 번(완전 종료 후 재시작)을 아직 안 한 경우가
> 가장 많습니다. 그래도 안 되면 명령프롬프트에서
> `C:\CS-MES\balance_outgoing_mailer\.venv\Scripts\python.exe C:\CS-MES\balance_outgoing_mailer\setup_env.py --check`
> 를 실행해 결과를 알려 주세요.

**DB 분석만 필요한 경우**(부족분이 얼마인지, 라인별로 어떤지 등)는 `ckp-reports` 가 없어도
`_common.md` §0 의 SQL 경로로 답할 수 있다. 없다고 무조건 멈추지 말고, 사용자가 원한 것이
'엑셀 11 개'인지 '숫자·분석'인지 구분한다.

---

## 1. 사용할 도구

| MCP 서버 | 도구 | 하는 일 |
|---|---|---|
| `ckp-reports` | `ckp_make_all(date, wait=False)` | 공식 11 개 엑셀 생성 (백그라운드) |
| `ckp-reports` | `ckp_status(tail)` | 진행 상황·완료 여부·산출 파일 목록 |
| `ckp-reports` | `ckp_mail(date)` | 생성된 11 개를 ZIP 첨부로 발송 |
| `ckp-reports` | `ckp_make_and_mail(date)` | 생성 + 발송 (백그라운드) |
| `balance-outgoing` | `build_outgoing_report` / `make_demo_report` | BALANCE OUTGOING 단독 리포트 |

도구 이름의 접두어는 환경마다 다르다(`mcp__remote-devices__ckp-reports__…` 등). `_common.md` §0-1 과 같이 **접미사로 식별**한다.

## 2. 반드시 지킬 것 — 생성은 60 초 안에 안 끝난다

`ckp_make_all` 은 **약 100 초** 걸린다. MCP 호출 제한(60 초)을 넘기므로 **백그라운드로 돌고 즉시 반환**한다.

1. `ckp_make_all(date="YYYY-MM-DD")` 호출 → `▶ ... pid NNNNN` 을 받는다.
2. 잠시 뒤 `ckp_status()` 로 확인한다.
3. **완료 판정은 `ckp_status` 의 `✅ 종료됨` 과 로그의 `<<< DONE`** 으로 한다.
4. 호출이 타임아웃 에러를 반환해도 **실패가 아니다.** 프로세스는 계속 돈다. 다시 실행하지 말고 `ckp_status()` 를 볼 것.

## 2-1. 다 되면 어디에 있는지 알려준다

산출물은 채팅에 첨부되지 않는다. **사용자 PC 의 폴더**에 저장된다.
`ckp_status()` 가 알려주는 경로(보통 `<설치폴더>\report\CKP_official\`)와 파일 11 개 목록을
답변에 적어 준다. 메일로 보내려면 `ckp_mail(date)` 를 쓴다(수신자는 `config.ini [report] recipients`).

## 3. 결과 해석 — 0 행이 곧 버그는 아니다

생성기는 **넓은 창**(기준일 기준 작업일 D+10 ~ D-7)으로 한 번 조회하고, 리포트마다 **자기 창**으로 렌더한다. 그래서 이런 일이 정상적으로 생긴다.

- 스타일 행은 나오는데 수량·합계가 0 → 데이터가 그 리포트의 좁은 창 **밖**에 있다.
- 시트가 헤더만 → 그 창에 해당 `ITEM_CLASS_TYPE` 이 실제로 0 건.

**0 행을 보고하기 전 확인 순서**
1. 같은 코드로 데이터가 있는 다른 기준일(예: 6 월 초)을 넣어 재현되는지 본다. 재현되면 코드 문제, 아니면 데이터 문제.
2. 이 skill 로 `FA_DATE` 별 분포를 조회해 데이터가 그 창 안에 있는지 확인한다.

## 4. 리포트별 필터의 진실의 출처

공식 11 개의 `ITEM_CLASS_TYPE`·`DIV`·`END_ROUTING` 조합은 **`ckp_reports/balance_sql.py` 의 `REPORTS` 딕셔너리**가 유일한 기준이다. 같은 파일 상단 주석이나 이 문서가 아니라 그 표를 본다.

2026-07-27 현재 값 (원본 수기 시트와 대조 확정):

| No. | 리포트 | ITEM_CLASS_TYPE | DIV | END_ROUTING |
|---|---|---|---|---|
| 2 | Balance IP Production | II | Production | Y |
| 3 | Balance IP Prod. by size | II | Production | Y |
| 4 | Balance IP Outgoing by size | II, IP | Outgoing | Y |
| 7 | Balance CMP | CP | Production | Y |
| 8 | Balance Outgoing PH | PH, PP | Outgoing | Y |
| 9 | Balance PH before UV | PH, PP | Production | **N** |
| 10 | Balance PH after UV | PH, PP | Production | Y |
| 11 | Balance PH in Market by size | PH, PP | Production | Y |

`Production` 은 `PROD_DATE='19991231'` 로, `Outgoing` 은 `OUT_DATE='19991231'` 로 미완료를 판정한다. No.3 이 `II` 만 쓰고 No.4 가 `II+IP` 를 쓰는 것은 **의도된 차이**다.

## 5. 마감(CLOSING) 필터가 이 skill 과 다르다 — 알고 있을 것

| | 필터 |
|---|---|
| 이 skill (`functions/shortage-management.md`) | `CLOSING_YN='N'` 인 그룹만 |
| CS-MES 프로그램 (현재 운영값) | `NOT EXISTS(CLOSING_YN='Y')` — **loose** |

프로그램이 느슨한 쪽을 쓰는 것은 **의도된 임시 조치**다. OCI 쪽 `MSPD_PROD_GROUP` 동기화가 끝나지 않아 엄격 필터로는 0 행이 나오기 때문이다. 동기화 완료 후 프로그램의 `loose=False` 로 전환할 예정.

**따라서 이 skill 의 SQL 로 공식 리포트 숫자를 검산하면 값이 다르게 나오는 것이 정상이다.** 검산할 때는 어느 필터를 썼는지 답변에 명시한다.
