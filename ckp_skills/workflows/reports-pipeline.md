# Reports Pipeline — CKP 공식 리포트는 SQL 로 재현하지 말고 프로그램에 맡긴다

이 skill 은 **분석**(화면 재현·질문 답변)을 담당한다. 반면 현업에 나가는 **CKP Manual Report 공식 11 개 엑셀**은 별도 프로그램(CS-MES)이 만든다. 둘을 섞으면 숫자가 갈린다.

> **판단 기준**
> - "부족분이 얼마야", "라인별로 보여줘", "왜 늘었어" → **이 skill 로 SQL 분석**
> - "리포트 만들어줘", "11 개 뽑아줘", "일보 보내줘" → **아래 MCP 도구로 위임**

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
