# CS-MES / CKP Manual Report

창신 CKP(공장코드 3120) 의 공식 리포트 11종을 GMES 원장 복제 DB(OCI Autonomous)에서
그대로 뽑아 엑셀로 만드는 프로그램과, 그것을 Claude 로 시키기 위한 skill.

## 실행

```
CKP.bat
```

이것 하나뿐이다. 누르면 메뉴가 뜬다.

| 번호 | 하는 일 |
|---|---|
| 1 | 리포트 11개 만들기 — 평소에는 이것만 |
| 2 | 처음 설정 / 설정 바꾸기 — 새 PC 에서 맨 처음 한 번 |
| 3 | DB 연결만 점검 — 뭔가 이상할 때 |
| 4 | Claude 에 이 폴더 연결 — skill 로 시키고 싶을 때만 |

자세한 절차는 [program/사용법.txt](program/사용법.txt).
결과는 `report/CKP_official/기준<날짜>_요청<날짜>/` 에 쌓인다.

## 폴더

```
CKP.bat      실행 진입점 (이것 하나)
program/     프로그램 본체
  ckp_reports/   리포트 생성 코드 (core = SQL·DB·렌더링, reports = 11종)
  tools/         설치·점검·연결 도우미
  mailer/        Balance Outgoing 메일 발송 (별도 기능)
  CKP Manual Report (종합).xlsx   서식 원본
  사용법.txt
skill/       Claude skill 원본 (업로드용 .skill 은 여기서 묶는다)
docs/        설계·조사 문서
report/      결과 (커밋 안 함)
```

## 두 가지 배포 경로

| | 이 저장소 | 배포 zip (`CKP-현장배포.zip`) |
|---|---|---|
| 라이브러리 | 인터넷으로 받음 | `vendor/` 동봉, 인터넷 불필요 |
| skill | `skill/` 폴더 | 업로드 가능한 `.skill` 한 개 |
| 용도 | 코드 관리 | 현장 PC 설치 |

`CKP.bat` 은 두 배치를 모두 인식한다.

## 커밋하지 않는 것

지갑(`**/wallet/`), 비밀번호가 든 `config.ini`, 생성물(`report/`, `sql/`, `*.csv`).
`.gitignore` 참고. DB 계정·지갑 비밀번호는 `CKP.bat` 2 번에서 입력받아 그 PC 에만 저장한다.

## 알아둘 것

- **DB 는 원장의 복제본**이다. 최근 며칠이 비어 있는 것은 고장이 아니다.
  실행할 때마다 `[health]` 줄로 데이터 최신일을 알려 준다.
- **마감(CLOSING) 필터는 자동 판정**이다. 마감 마스터 커버리지가 90% 미만이면 임시(loose).
- **중복 제거는 `ROUTING_SEQ` 최대 1행** 방식이다(2026-07 변경). 옛 `END_ROUTING_YN` 방식과
  숫자가 다른 것이 정상.
- **No.3 품목범위는 `II` 만**이다(2026-07-28, 원본 수기 리포트 대조 확정). No.4 는 `II+IP`.
  이 비대칭은 원본 그대로다.
