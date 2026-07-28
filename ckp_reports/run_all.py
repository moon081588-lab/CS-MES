#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CKP Manual Report — 통합 러너 (하나).
reports/ 레지스트리를 순회하며 (1) 선택된 리포트의 SQL을 모아 접속 1회 배치로 실행하고
(2) 각 리포트를 빌드한다. 실제 SQL·엑셀·DB 로직은 core/ 와 reports/ 에 위임 — 이 파일은 얇다.

사용:
  python run_all.py 2026-07-13                 # 전체 11개
  python run_all.py 2026-07-13 --only "3,4,8"  # 일부만
  python run_all.py 2026-07-13 --plan          # SQL만 sql/no*.sql 로 저장(DB 미접속)
  python run_all.py 2026-07-13 --build         # 기존 sql/no*.csv 로 엑셀만 생성
  옵션: --conn <SQLcl 연결명>  --src <종합.xlsx 경로>
"""
import os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import db, health, market_engine as ME
from core.context import Ctx
import reports

OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
SQLDIR = os.path.join(HERE, "sql")
DEFAULT_SRC = os.environ.get("CKP_SRC", "")
_SRC_CANDIDATES = [
    os.path.join(HERE, "..", "CKP Manual Report (종합).xlsx"),
    os.path.join(HERE, "..", "report", "CKP Manual Report (종합).xlsx"),
]


def _find_src():
    for c in _SRC_CANDIDATES:
        if os.path.exists(c):
            return c
    # 파일명이 깨져 전달되는 일이 실제로 있었다(압축 해제 시 한글 손상).
    # 이름이 정확하지 않아도 같은 자리에 있으면 찾아 쓴다.
    import glob
    for d in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "report")):
        for c in sorted(glob.glob(os.path.join(d, "CKP Manual Report*.xlsx"))):
            if not os.path.basename(c).startswith("~$"):
                return c
    return ""


def _parse_ids(only):
    req = set()
    for x in only.replace(",", " ").split():
        x = x.strip().lower()
        if x.startswith("no"):
            x = x[2:]
        if x:
            req.add(x)
    return req


def run(date, only="", conn="changshinincaipoc", mode="sqlcl", src="", reqdate=""):
    _cfgp = os.path.join(HERE, "config.ini")
    date = date or health.site_today(cfg_path=_cfgp).isoformat()   # 실행 PC 가 아니라 한국시간 기준
    reqdate = reqdate or health.site_today(cfg_path=_cfgp).isoformat()
    outdir = os.path.join(OUTDIR, f"기준{date}_요청{reqdate}")   # 기준날짜_요청날짜 하위폴더 → CKP_official/기준YYYY-MM-DD_요청YYYY-MM-DD/
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(SQLDIR, exist_ok=True)

    # --- 리포트 선택: 기본 전체(1~11). --only "3,4" 지정 시 그것만 ---
    if only.strip():
        req = _parse_ids(only)
        want = [i for i in reports.ALL_IDS if i in req]
        bad = [i for i in sorted(req) if i not in reports.ALL_IDS]
        if bad:
            print(f"[경고] 알 수 없는 리포트 번호 무시: {','.join(bad)}")
        if not want:
            sys.exit(f"[오류] 유효한 리포트 번호가 없습니다. 가능: {','.join(reports.ALL_IDS)}")
    else:
        want = reports.ALL_IDS[:]
    selected = reports.select(want)

    # 설정·지갑·템플릿 보완 (원본 make_all 과 동일)
    cfg = ME.load_config(os.path.join(HERE, "config.ini"))
    if not db.TNS_ADMIN:
        db.TNS_ADMIN = cfg.get("db", "wallet_dir", fallback="").strip() or None
    if not src:
        src = DEFAULT_SRC or cfg.get("report", "src_workbook", fallback="").strip() or _find_src()

    # 공장 코드를 코드에 박아두면 다른 공장·법인 PC 에서 에러 없이 0행이 나온다.
    from core import sql as _BS
    _BS.PLANT = (cfg.get("report", "plant", fallback="") or "").strip() or _BS.PLANT

    ctx = Ctx(date, outdir, SQLDIR, src, cfg)

    # 선택된 리포트의 SQL 수집(접속 1회 배치 실행 대상)
    fetch_items = []
    for r in selected:
        for name, sql in r.plan(ctx):
            fetch_items.append((ctx.csv(name), sql))

    print(f"=== CKP [{mode}] {date} 대상 {len(want)}개({','.join(want)}) 공장 {_BS.PLANT} "
          f"부족분창 {ctx.d_from}~{ctx.d_to} → {outdir}")

    health_msgs = []
    if mode == "sqlcl":
        try:
            base = datetime.date.fromisoformat(date)
        except ValueError:
            base = health.site_today(cfg=cfg)
        loose, health_msgs = health.check(db, cfg, conn, ctx.d_from, ctx.d_to, _BS.PLANT, SQLDIR, base)
        for m in health_msgs: print(m)
        if not loose:                      # 정식 마감필터로 전환된 경우 SQL 을 다시 만든다
            fetch_items = []
            for r in selected:
                for name, sql in r.plan(ctx):
                    fetch_items.append((ctx.csv(name), sql))

    if mode == "plan":                               # SQL 만 저장(DB 미접속)
        for path, sql in fetch_items:
            with open(path[:-4] + ".sql", "w", encoding="utf-8") as f:
                f.write(sql + "\n")
        print(f"SQL 저장 완료 → {SQLDIR}/no*.sql ({len(fetch_items)}개, sqlcl 로 실행해 no*.csv 를 만든 뒤 --build)")
        return

    if mode == "build":                              # 기존 CSV 사용(DB 미접속)
        miss = [p for p, _ in fetch_items if not os.path.exists(p)]
        if miss:
            raise RuntimeError("CSV 없음: " + ", ".join(os.path.basename(x) for x in miss)
                               + "\n  → --plan 으로 SQL 뽑고 sqlcl 로 실행해 CSV 를 먼저 만들어 주세요.")
    else:                                            # sqlcl: 접속 1회로 모든 쿼리 일괄 실행
        db.run_batch(fetch_items, conn)

    for r in selected:
        r.build(ctx)
        print(f"  No.{r.ID} 완료")
    print(f"완료: {len(selected)}개 → {outdir}")
    for m in health_msgs: print(m)       # 로그 끝만 보는 경우를 위해 한 번 더


def main():
    a = list(sys.argv[1:]); src = DEFAULT_SRC; conn = "changshinincaipoc"; mode = "sqlcl"; only = ""
    if "--src" in a:   i = a.index("--src");   src = a[i + 1];  del a[i:i + 2]
    if "--conn" in a:  i = a.index("--conn");  conn = a[i + 1]; del a[i:i + 2]
    if "--only" in a:  i = a.index("--only");  only = a[i + 1]; del a[i:i + 2]
    if "--plan" in a:  mode = "plan";  a.remove("--plan")
    if "--build" in a: mode = "build"; a.remove("--build")
    reqdate = None
    if "--reqdate" in a: i = a.index("--reqdate"); reqdate = a[i + 1]; del a[i:i + 2]
    date = a[0] if a else ""          # 비우면 run() 이 config 기준(한국시간)으로 정한다
    run(date, only=only, conn=conn, mode=mode, src=src, reqdate=reqdate)


if __name__ == "__main__":
    main()
