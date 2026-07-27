# ckp_skills — CKP MES 분석 스킬 원본 (v12.2)

이 폴더는 Claude 스킬 `CKP-skills-v12` 의 **버전관리용 원본**이다.
실제로 동작하는 것은 사용자 계정에 설치된 사본이고, 이 폴더는 그 사본의 소스다.

## 왜 코드와 같은 저장소에 두는가

스킬(분석)과 프로그램(리포트 생성)이 **같은 도메인 정의를 각자 들고 있어서** 계속 어긋났다.
2026-07-27 대조에서 확인된 것:

- 스킬이 MCP 도구 접두어(`mcp__sqlcl__*`)와 연결 이름을 하드코딩 → Cowork 환경에서 안 통함
- 스킬에 지갑/TNS_ADMIN 절차가 통째로 없음 (ORA-17956·12263 대응 불가)
- 스킬이 `ckp-reports` MCP(공식 11개 리포트)의 존재를 모름
- `balance_sql.py` 상단 주석이 같은 파일의 `REPORTS` 표와 불일치

한 저장소에 두면 한쪽만 고치고 잊는 일을 줄일 수 있다.

## 고칠 때 같이 봐야 하는 짝

| 스킬 | 프로그램 |
|---|---|
| `workflows/_common.md` §0 (연결 절차) | `ckp_reports/make_all.py` `resolve_conn()` |
| `workflows/_common.md` §0-4 (지갑) | `balance_outgoing_mailer/setup_env.py` |
| `workflows/reports-pipeline.md` §4 (리포트별 필터) | `ckp_reports/balance_sql.py` `REPORTS` |
| `functions/shortage-management.md` (마감필터) | `ckp_reports/balance_sql.py` `_closing_pred()` |

## 패키징

    cd ckp_skills && zip -r -X ../CKP-skills-v12.2.skill . -x '.*'

만든 `.skill` 파일을 Claude 에 전달해 설치한다. 설치 후에는 `SKILL.md` 의
변경 이력 첫 줄로 어느 버전이 깔려 있는지 확인할 수 있다.
