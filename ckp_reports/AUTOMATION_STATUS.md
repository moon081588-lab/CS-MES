# CKP Manual Report — Claude 자동생성 구현 현황

> 기준일 2026-07-03 · 원본 파일 `CKP Manual Report (종합).xlsx` (16시트) 대비
> 판정: ✅ 완료(검증) · 🔶 엔진 가능·소스/검증 필요 · 🔴 소스 미확인

## 요약

- **완료 7시트** — 부족분(Balance) 계열. GMES 프로시저 `P_MSPD90000S_Q_V14` 로직을 재현했고,
  스킬 검증 케이스(2026-03-01~07 / 3120 / CP / FGA16,FGA19 → **G-Total 5,426**)와 **정확히 일치** 확인.
- 산출 파일: `report/BALANCE_OUTGOING_20260703.xlsx`, `report/CKP_Balance_bysize_20260703.xlsx`,
  `report/CKP_Balance_bydate_20260703.xlsx`
- 생성 코드(커밋됨): `ckp_reports/balance_bysize.py`, `ckp_reports/balance_bydate.py`,
  `balance_outgoing_mailer/` (Outgoing Market)

## 시트별 현황

| # | 원본 시트 | 도메인 | 상태 | 데이터 소스 / 비고 |
|---|---|---|---|---|
| 9 | 3-3. Balance IP Outgoing Market | 부족분(Outgoing) | ✅ | MSPD_PCARD_RESULT(OUT_DATE) + 색상 BATCH_PLAN + SCAN POP_PCARD_SCAN(BEM/BEP) |
| 7 | 3-2. Balance IP Prod by size | 부족분(Production) | ✅ | shortage-screen 엔진(END_ROUTING='Y'), 사이즈 PIVOT |
| 8 | 3-2. Balance IP Outgoing by size | 부족분(Outgoing) | ✅ | 동일 엔진, DIV=Outgoing |
| 15 | 3-2. Balance PH in Market by size | 부족분(PH) | ✅ | 동일 엔진, ICT=PH/PP/CP |
| 6 | 3-1. Balance IP Production | 부족분(Production) | ✅ | by-date 집계 |
| 12 | 3-1. Balance Outgoing PH | 부족분(Outgoing) | ✅ | by-date 집계, ICT=PH/PP |
| 11 | 3-1. Balance CMP | 부족분(CP) | ✅ | 엔진 완료(이 기간 미생산 잔량 0) |
| 13 | 3-1. Balance PH before UV | 부족분(스테이지) | 🔶 | 엔진 재사용 가능. "before UV" = END_ROUTING='N'/특정 공정 매핑 확인 필요 |
| 14 | 3-1. Balance PH after UV | 부족분(스테이지) | 🔶 | 동일(after UV = END_ROUTING='Y') |
| 1 | 1.Hasil Prod. IP | 생산 실적 | 🔶 | TARGET PLAN·PRODUKSI HASIL·GAP 산출 가능(⚠OP 중복 집계 시 최대 2.15배 부풀림 → 카드 중복제거 필요). INTERNAL OS&D·BTM SET·BALANCE·STOCK CKP·STOCK SPRAY 소스 미확인 |
| 2 | 1.Hasil Prod. PH | 생산 실적 | 🔶 | 동일 |
| 3 | 1.Prod. Report IP | 생산 실적 | 🔶 | 대형(MP Plan·APS Plan·COMPOUND IN·UV Packing) — 다중 소스 매핑 필요 |
| 4 | 1. DAILY REPORT SCAN | 스캔 | 🔶 | POP_PCARD_SCAN 기반 가능, 컬럼(TARGET/NORMAL/OS&D/Kg) 매핑 필요 |
| 10 | 3-4. Balance External OS&D IPPH | 품질 | 🔶 | quality-osnd 워크플로우 OCI 재현 CTE 존재, 검증 필요 |
| 5 | 3.Add. Request Material | 자재 | 🔴 | Additional Request Order 소스 테이블 미확인 |
| 16 | 5.Summary Stock PH | 재고 | 🔴 | PREFORM/BUB/BUA STOCK 소스 미확인 |

## 전 리포트 공통 미확인 컬럼 (현업/DB 회신 대기)

- **IP SPRAY (BEM) · PAD PRINTING (BEP)** — 스프레이/패드 공정 색상. 조인키 확인 요청 중.
- **SCAN DI CKP** — CKP 출고 스캔. MSPD_PCARD_RESULT 내 식별 조건 확인 요청 중.
- **STOCK CKP · STOCK SPRAY · BTM SET · BALANCE** — 재고/반제품 소스 미확인.

> 원칙: 검증 안 된 지표는 **빈칸**으로 두고 추측 숫자를 넣지 않는다(현업 전달용 정확성 우선).
