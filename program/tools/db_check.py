#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DB 접속 점검 — CKP.bat 의 3 번이 호출한다. 리포트를 만들지 않고 연결만 확인한다.

수시로 돌려도 되도록 가볍게(질의 3개) 만들었다. 리포트가 이상할 때
'DB 문제인가 코드 문제인가' 를 먼저 가르는 용도.

  python tools\\db_check.py

확인하는 것
  1) 어느 경로로 붙는가        드라이버 직결 / SQLcl
  2) 진짜 그 DB 가 맞는가      OCI 스키마 테이블 개수
  3) 데이터가 어디까지 들어와 있나   최신 스캔일
     ※ 우리가 보는 DB 는 원장의 **복사본**이라 최근 며칠이 비어 있는 것이 정상이다.
"""
import os, sys, csv, io, datetime, tempfile

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG  = os.path.join(ROOT, "ckp_reports")
sys.path.insert(0, PKG)

def line(c="="): print(c * 62)

SQL = (
    "SELECT (SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER='OCI') OCI_TABLES, "
    "TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI') KST_NOW, "
    "(SELECT MAX(SCAN_YMD) FROM OCI.POP_PCARD_SCAN) LAST_SCAN, "
    "(SELECT TO_CHAR(MAX(UPDATE_DT),'YYYY-MM-DD HH24:MI') FROM OCI.MSPD_PCARD_RESULT) LAST_SYNC "
    "FROM DUAL"
)

def main():
    line(); print(" DB 접속 점검"); line()
    try:
        from core import db
    except Exception as e:
        print(f" ❌ 코드를 불러오지 못했습니다: {e}")
        print("    CKP.bat 의 2 번(처음 설정)을 먼저 실행하세요."); return 1

    cfg = db.load_cfg()
    backend, why = db.choose_backend(cfg)
    print(f" 접속 경로 : {backend}")
    print(f"            {why}")
    wdir = db.wallet_dir(cfg)
    print(f" 지갑      : {wdir or '(없음)'}")
    if backend == "sqlcl":
        found = os.path.exists(db.SQLCL) or os.sep not in db.SQLCL
        print(f" SQLcl     : {db.SQLCL}" + ("" if os.path.exists(db.SQLCL) else "   ← PATH 에서 찾은 이름(실제 위치 미확인)"))
    if wdir and not os.path.isfile(os.path.join(wdir, "tnsnames.ora")):
        print("            ⚠ tnsnames.ora 가 없습니다.")

    # 자격증명을 따지기 전에 '길이 뚫려 있는가' 부터 본다.
    # 방화벽 문제를 계정 문제로 오해하면 현장에서 하루가 날아간다.
    dsn = cfg.get("db", "dsn", fallback="changshinincaipoc_medium").strip()
    host, port = db.dsn_endpoint(wdir, dsn)
    _pf  = (cfg.get("db", "preflight", fallback="") or "auto").strip().lower()
    _prx = cfg.get("db", "https_proxy", fallback="").strip()
    if _prx:
        print(f" 프록시    : {_prx}:{cfg.get('db','https_proxy_port',fallback='')}")
    if host and _pf != "off" and not _prx:
        ok, msg = db.preflight(host, port)
        print(f" 네트워크  : {'OK' if ok else 'X'}  {msg}")
        if ok is False:
            print()
            line("-")
            print(" ❌ DB 포트에 닿지 못했습니다. 여기서 멈춥니다.")
            print(f"    사내 방화벽/프록시에서 '{host} {port} 아웃바운드' 를 열어야 합니다.")
            print("    계정·지갑 문제가 아니므로 그쪽은 볼 필요 없습니다.")
            line("-")
            return 1
    print()

    conn = (cfg.get("db", "sqlcl_conn", fallback="") or "changshinincaipoc").strip()
    tmp = os.path.join(tempfile.gettempdir(), "ckp_dbcheck.csv")
    t0 = datetime.datetime.now()
    try:
        db.run_batch([(tmp, SQL)], conn)
    except Exception as e:
        print(" ❌ 접속 실패")
        line("-")
        print(f" {str(e)[:900]}")
        line("-")
        print(f" [원인] {db.classify(str(e), wdir, host if host else '', port if host else 0)}")
        print()
        print(" 참고 — SQLcl 을 못 찾는다는 메시지면, config.ini [db] 에")
        print("        user / password / wallet_password 를 채우면 SQLcl 없이 접속합니다.")
        print("        (CKP.bat 의 2 번을 다시 실행하면 물어봅니다)")
        return 1
    took = (datetime.datetime.now() - t0).total_seconds()

    row = next(csv.DictReader(io.StringIO(open(tmp, encoding="utf-8").read())), {})
    row = {(k or "").strip().upper(): v for k, v in row.items()}
    tables = row.get("OCI_TABLES", "?")
    last   = (row.get("LAST_SCAN") or "").strip()
    sync   = (row.get("LAST_SYNC") or "").strip()

    print(f" ✅ 접속 성공 ({took:.1f}초)")
    print(f" 현재 시각(한국) : {row.get('KST_NOW','?')}")
    print(f" OCI 테이블      : {tables}개", end="")
    try:
        print("  — 정상" if int(tables) >= 40 else "  ⚠ 너무 적습니다. 다른 DB 일 수 있습니다.")
    except ValueError:
        print()
    print()
    line("-"); print(" 데이터가 들어와 있는 범위"); line("-")
    print(f"   최신 스캔일   : {last or '?'}")
    print(f"   최종 반영시각 : {sync or '?'}")
    if last:
        try:
            d = datetime.datetime.strptime(last, "%Y%m%d").date()
            gap = (datetime.date.today() - d).days
            print(f"   오늘과의 차이 : {gap}일")
            print()
            print("   ※ 우리가 보는 DB 는 원장의 복사본입니다. 최근 며칠이 비어 있는 것은")
            print("      고장이 아니라 정상입니다. 리포트 기준일을 위 최신일 이전으로 잡으면")
            print("      데이터가 정상적으로 나옵니다.")
        except ValueError:
            pass
    print()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n중단했습니다.")
