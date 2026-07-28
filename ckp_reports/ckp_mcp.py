#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — Claude Desktop용 로컬 MCP 서버
===================================================
Claude Desktop이 "CKP 리포트 만들어줘 / 메일 보내줘" 한마디로 11개를 생성·발송하게 한다.
서버가 Mac 위에서 run_all.py 를 그대로 실행하므로,
대용량 CSV가 Claude 컨텍스트를 지나가지 않는다(= 안정적). DB 조회는 make_all 이 내부에서
저장된 SQLcl 연결(changshinincaipoc)로 처리 → Claude 는 SQL 을 나르지 않는다.

필요: pip install mcp openpyxl  /  이 PC에 SQLcl(`sql`) + 'changshinincaipoc' 연결 저장.
claude_desktop_config.json 에 아래처럼 등록:
  "ckp-reports": { "command": ".../.venv/bin/python", "args": [".../ckp_reports/ckp_mcp.py"] }
"""
import os, sys, subprocess, datetime, threading, time, json

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))

# --- DB keepalive(워밍업) 설정 -------------------------------------------------
# OCI Autonomous DB 는 유휴 상태에서 첫 접속 시 resume 지연이 커서, ckp_make_all 첫 호출이
# MCP 응답 제한시간(-32001)을 넘겨 타임아웃되곤 했다. 아래 백그라운드 스레드가 서버 기동 직후,
# 그리고 일정 주기로 가벼운 'SELECT 1 FROM DUAL' 을 실행해 DB 를 항상 웜 상태로 유지한다.
# → 사용자가 리포트를 부르는 시점엔 콜드 스타트 비용이 이미 지불돼 있어 첫 호출부터 통과한다.
# (make_all.py 안에 인라인 워밍업을 넣어도 같은 호출 안에서 콜드 비용을 치르므로 소용이 없다.)
SQLCL         = os.environ.get("SQLCL", "sql")                        # SQLcl 실행파일
WARM_CONN     = os.environ.get("CKP_WARM_CONN", "changshinincaipoc")  # 저장된 연결명
WARM_INTERVAL = int(os.environ.get("CKP_WARM_INTERVAL", "240"))       # 핑 주기(초)
WARM_ENABLE   = os.environ.get("CKP_WARM_ENABLE", "1") != "0"         # '0' 이면 비활성

# --- 실행 안정화(timeout / 스태일 자동초기화) 설정 -----------------------------
# 원인: run_all.py 실행에 시간제한이 없어 DB/SQLcl 가 멈추면 잡이 영원히 'running' 으로 남고,
#       같은 날짜 재실행이 '[이미 진행 중]' 으로 막혔다(수동 해제 불가 → Claude 재시작만이 유일).
# 대책: (1) run_all.py 에 timeout 을 걸어 초과 시 강제중단→오류로 종료,
#       (2) running 잡이 STALE_AFTER 초를 넘으면 죽은 것으로 보고 재실행 허용,
#       (3) ckp_reset 도구로 걸린 잡을 즉시 해제.
RUN_TIMEOUT   = int(os.environ.get("CKP_RUN_TIMEOUT", "900"))                    # run_all.py 1회 최대 실행시간(초)
STALE_AFTER   = int(os.environ.get("CKP_STALE_AFTER", str(RUN_TIMEOUT + 180)))   # 진행중 잡을 죽은걸로 간주하는 경과시간(초)
SYNC_WAIT     = int(os.environ.get("CKP_SYNC_WAIT", "210"))                      # ckp_make_all 동기 대기 상한(초). 이 안에 끝나면 결과를 바로 반환(240초 클라 타임아웃 회피)

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("ckp-reports")

def _run(script, date, *extra):
    args = [sys.executable, "-u", os.path.join(HERE, script)]
    if date: args.append(date)
    args += [x for x in extra if x]
    p = subprocess.run(args, capture_output=True, text=True, cwd=HERE,
                       timeout=RUN_TIMEOUT)   # 무한대기 방지: 초과 시 subprocess.TimeoutExpired 발생(자식은 강제종료됨)
    out = p.stdout or ""
    if p.returncode != 0:
        out += "\n[오류]\n" + (p.stderr or "")[-1500:]
    return out.strip()

# --- DB 워밍업(keepalive) ------------------------------------------------------
def _warm_ping():
    """DB 를 깨우는 최소 쿼리. 실패해도 서버 동작엔 영향 없음(stderr 로그만)."""
    script = (f"connect -name {WARM_CONN}\n"
              "set feedback off\nset pagesize 0\nset echo off\n"
              "SELECT 1 FROM DUAL;\nexit\n")
    try:
        p = subprocess.run([SQLCL, "-S", "/nolog"], input=script,
                           capture_output=True, text=True, env=dict(os.environ),
                           timeout=180)
        ok = ("ORA-" not in (p.stdout or "")) and p.returncode == 0
        print(f"[ckp warmup] {WARM_CONN} {'ok' if ok else 'warn'} (rc={p.returncode})",
              file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[ckp warmup] skip: {e}", file=sys.stderr, flush=True)

def _keepalive_loop():
    while True:
        _warm_ping()
        time.sleep(max(30, WARM_INTERVAL))

def _start_keepalive():
    """서버 기동 시 즉시 1회 + 주기적으로 DB 를 깨우는 백그라운드 데몬 스레드."""
    if not WARM_ENABLE:
        return
    threading.Thread(target=_keepalive_loop, name="ckp-warmup", daemon=True).start()

# --- 비동기 생성 잡 관리 ------------------------------------------------------
# Claude Desktop 의 MCP 요청 타임아웃(=240초)보다 11개 생성(~4.5분)이 더 걸려 매번 취소되던 문제를
# 근본 회피한다. 생성은 백그라운드 스레드에서 돌리고 도구는 '즉시' 시작 메시지를 반환 → 클라이언트가
# 타임아웃 걸 대상이 없다. 진행상태는 메모리(_JOBS) + 상태파일(_ckp_status_<date>.json)에 기록하고,
# ckp_status 로 완료 여부·파일 목록을 조회한다. (make_all 자체 소요는 안 줄지만, 타임아웃엔 안 걸린다.)
_JOBS = {}
_JOBS_LOCK = threading.Lock()

def _dated(date, reqdate=""):
    # 기준날짜_요청날짜 하위폴더 → CKP_official/기준YYYY-MM-DD_요청YYYY-MM-DD/. reqdate 없으면 기준날짜만(구버전 호환).
    sub = f"기준{date}_요청{reqdate}" if reqdate else date
    return os.path.join(OUTDIR, sub)

def _status_path(date):
    return os.path.join(OUTDIR, f"_ckp_status_{date}.json")   # 상태 json 은 상위(CKP_official)에 유지 → 날짜 몰라도 조회 가능

def _list_reports(date, reqdate=""):
    try:
        return sorted(f for f in os.listdir(_dated(date, reqdate)) if f.lower().endswith(".xlsx"))
    except FileNotFoundError:
        return []

def _save_status(job):
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        pub = {k: v for k, v in job.items() if not k.startswith("_")}
        with open(_status_path(job["date"]), "w", encoding="utf-8") as f:
            json.dump(pub, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ckp job] 상태파일 저장 실패: {e}", file=sys.stderr, flush=True)

def _worker(date, only):
    job = _JOBS[date]
    rq = job.get("reqdate", "")
    try:
        job["output"] = _run("run_all.py", date, "--reqdate", rq, *only)
        job["files"] = _list_reports(date, rq)
        job["state"] = "done"
    except subprocess.TimeoutExpired as e:
        job["state"] = "error"
        job["error"] = (f"시간초과: run_all.py 가 {RUN_TIMEOUT}초 안에 끝나지 않아 중단했습니다. "
                        f"SQLcl 저장연결(changshinincaipoc)·지갑·DB 상태를 확인한 뒤 다시 실행하세요.")
        job["output"] = e.stdout if isinstance(e.stdout, str) else ""
    except Exception as e:
        job["state"] = "error"; job["error"] = repr(e)
    finally:
        job["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        job["elapsed_sec"] = round(time.time() - job["_t0"], 1)
        _save_status(job)

def _start_job(date, reports):
    only = ("--only", reports) if reports.strip() else ()
    scope = f"선택({reports.strip()})" if reports.strip() else "11개 전체"
    reqdate = datetime.date.today().isoformat()   # 요청(실행) 날짜 — 잡 생성 시점에 고정
    with _JOBS_LOCK:
        cur = _JOBS.get(date)
        if cur and cur["state"] == "running":
            age = time.time() - cur.get("_t0", 0)
            if age < STALE_AFTER:
                return (f"[이미 진행 중] {date} — {cur['scope']} · 경과 {round(age)}초. "
                        f"ckp_status(date='{date}') 로 확인하세요. "
                        f"(멈춘 것 같으면 ckp_reset(date='{date}') 로 초기화)")
            # STALE_AFTER 초과 → 이전 잡은 죽은 것으로 간주하고 새로 시작(아래로 진행)
        job = {"date": date, "reqdate": reqdate, "scope": scope, "state": "running",
               "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "finished_at": None, "elapsed_sec": 0, "output": "", "files": [],
               "error": "", "_t0": time.time()}
        _JOBS[date] = job
        _save_status(job)
    threading.Thread(target=_worker, args=(date, only),
                     name=f"ckp-gen-{date}", daemon=True).start()
    eta = "약 4~5분(11개 전체)" if not reports.strip() else "약 1~3분(선택 생성)"
    return (f"[CKP 생성 시작] {date} — {scope}. 백그라운드에서 생성 중입니다({eta}).\n"
            f"완료되면 아래 폴더에 파일이 생깁니다. 지금 대화는 끝내셔도 되고, 확인이 필요할 때만 '상태 확인'이라고 하세요.\n"
            f"저장 위치: {_dated(date, reqdate)}")

# 리포트 번호 안내(선택 생성용):
#   1 Daily Scan · 2 IP Production · 3 IP Prod by size · 4 IP Outgoing by size ·
#   5 IP Outgoing Market · 6 External OS&D · 7 Balance CMP · 8 Outgoing PH ·
#   9 PH before UV · 10 PH after UV · 11 PH in Market by size

@mcp.tool()
def ckp_make_all(date: str = "", reports: str = "") -> str:
    """CKP Manual Report 리포트를 생성한다(기본 공식 11개 전체).
    실행이 끝날 때까지 기다렸다가 결과(생성 파일 목록·로그)를 바로 반환한다 — 보통 2분 내 완료라 한 번의 호출로 끝(폴링 불필요).
    드물게 대기 상한(SYNC_WAIT, 기본 210초)을 넘길 때만 '시작' 메시지를 반환하며, 그 경우에만 ckp_status(date) 로 완료를 확인한다.
    date: 'YYYY-MM-DD'(생략 시 오늘). reports: 특정 번호만 지정(예 '3,4' 또는 '3 4 11'), 생략 시 전체 11개.
      1 Daily Scan · 2 IP Production · 3 IP Prod by size · 4 IP Outgoing by size · 5 IP Outgoing Market ·
      6 External OS&D · 7 CMP · 8 Outgoing PH · 9 PH before UV · 10 PH after UV · 11 PH in Market by size.
    저장된 SQLcl 연결로 DB 조회(접속 1회 일괄) → report/CKP_official/기준<날짜>_요청<오늘>/ 에 xlsx 생성.
    양식(사이즈·날짜 D-offset 컬럼)은 원본 고정 구조라 데이터가 0행이어도 열이 유지된다."""
    d = date or datetime.date.today().isoformat()
    start_msg = _start_job(d, reports)
    if "[이미 진행 중]" in start_msg:
        return start_msg
    # 동기 대기: 전체/선택 모두 끝날 때까지 기다렸다가 결과를 바로 반환(ps1 처럼 한 번에 끝).
    # SYNC_WAIT 안에 못 끝내면 그때만 '시작' 메시지로 폴백해 클라이언트 타임아웃(240초)을 피한다.
    t0 = time.time()
    while time.time() - t0 < SYNC_WAIT:
        with _JOBS_LOCK:
            job = _JOBS.get(d)
        if job and job.get("state") in ("done", "error"):
            return _status_text(d)
        time.sleep(2)
    return start_msg + "\n(예상보다 오래 걸립니다 — '상태 확인'으로 완료를 확인하세요.)"

def _status_text(d):
    with _JOBS_LOCK:
        job = _JOBS.get(d)
    if job is None and os.path.exists(_status_path(d)):   # 서버 재시작 등으로 메모리 유실 시 파일에서 복구
        try:
            with open(_status_path(d), encoding="utf-8") as f: job = json.load(f)
        except Exception: job = None
    if job is None:
        return f"[상태 없음] {d} — 진행 중이거나 완료된 생성 기록이 없습니다. ckp_make_all 로 시작하세요."
    state = job.get("state")
    el = job.get("elapsed_sec") or (round(time.time() - job["_t0"], 1) if "_t0" in job else 0)
    if state == "running":
        return f"[진행 중] {d} — {job.get('scope')} · 생성 중 · 경과 {el}초. 잠시 후 다시 확인하세요."
    if state == "error":
        return f"[오류] {d} — {job.get('scope')} · 경과 {el}초\n{job.get('error')}\n{(job.get('output') or '')[-800:]}"
    rq = job.get("reqdate", "")
    files = job.get("files") or _list_reports(d, rq)
    return (f"[완료] {d} — {job.get('scope')} · 소요 {el}초 · 파일 {len(files)}개\n"
            + "\n".join(files) + f"\n\n== 생성 로그 ==\n{job.get('output', '')}"
            + f"\n\n저장 위치: {_dated(d, rq)}")

@mcp.tool()
def ckp_status(date: str = "") -> str:
    """진행 중이거나 완료된 CKP 생성 잡의 상태를 조회한다.
    ckp_make_all 로 시작한 뒤, 완료 여부·소요시간·생성 파일 목록을 확인할 때 사용.
    date: 'YYYY-MM-DD' (생략 시 오늘)."""
    return _status_text(date or datetime.date.today().isoformat())

@mcp.tool()
def list_report_dir(date: str = "") -> str:
    """생성 결과 폴더의 리포트 파일 목록(개수·크기·시각)을 조회한다. 탐색기 안 열고 채팅에서 바로 확인용.
    date: 'YYYY-MM-DD' (생략 시 오늘). 해당 기준일의 '기준<date>_요청*' 폴더들을 훑는다."""
    import glob
    d = date or datetime.date.today().isoformat()
    dirs = sorted(glob.glob(os.path.join(OUTDIR, f"기준{d}_요청*")))
    if os.path.isdir(os.path.join(OUTDIR, d)): dirs.append(os.path.join(OUTDIR, d))   # 구버전 폴더
    if not dirs:
        return f"[없음] {d} — 생성 폴더가 아직 없습니다. ckp_make_all(date='{d}') 로 시작하세요."
    lines = []
    for dr in dirs:
        try: files = sorted(f for f in os.listdir(dr) if f.lower().endswith(".xlsx"))
        except FileNotFoundError: continue
        lines.append(f"[폴더] {os.path.basename(dr)} — {len(files)}개")
        for f in files:
            p = os.path.join(dr, f); sz = os.path.getsize(p)
            mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")
            lines.append(f"   {f}  ({sz:,}B · {mt})")
    return "\n".join(lines)

@mcp.tool()
def tail_ckp_log(date: str = "", lines: int = 40) -> str:
    """마지막 생성 실행 로그(run_all 출력)의 끝부분을 본다 — 오류 원인 빠른 확인용.
    date: 'YYYY-MM-DD' (생략 시 오늘). lines: 보여줄 줄 수(기본 40)."""
    d = date or datetime.date.today().isoformat()
    with _JOBS_LOCK:
        job = _JOBS.get(d)
    if job is None and os.path.exists(_status_path(d)):
        try:
            with open(_status_path(d), encoding="utf-8") as f: job = json.load(f)
        except Exception: job = None
    if job is None:
        return f"[로그 없음] {d} — 실행 기록이 없습니다."
    out = (job.get("output") or "").strip()
    n = max(1, int(lines))
    tail = "\n".join(out.splitlines()[-n:]) if out else "(출력 없음)"
    head = f"[{d}] 상태={job.get('state')} · 경과={job.get('elapsed_sec')}초"
    err = (job.get("error") or "").strip()
    return head + (f"\n== 오류 ==\n{err}" if err else "") + f"\n== 로그(끝 {n}줄) ==\n{tail}"

@mcp.tool()
def ckp_reset(date: str = "") -> str:
    """멈춰 있는(진행 중으로 걸린) CKP 생성 작업을 강제로 해제한다.
    '[이미 진행 중]' 때문에 재실행이 막힐 때 사용. date 생략 시 오늘.
    (리포트 생성 로직은 건드리지 않고 상태 플래그만 초기화 → 이후 ckp_make_all 로 바로 재실행 가능.)"""
    d = date or datetime.date.today().isoformat()
    with _JOBS_LOCK:
        job = _JOBS.get(d)
        if job and job.get("state") == "running":
            job["state"] = "error"
            job["error"] = "사용자가 강제 초기화(ckp_reset)했습니다."
            job["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            job["elapsed_sec"] = round(time.time() - job.get("_t0", time.time()), 1)
            _save_status(job)
            return (f"[초기화됨] {d} — 진행 중이던 작업을 해제했습니다. "
                    f"이제 다시 '리포트 만들어줘'로 실행하시면 됩니다.")
    return f"[초기화 불필요] {d} — 진행 중인 작업이 없습니다. 바로 실행하시면 됩니다."

if __name__ == "__main__":
    _start_keepalive()   # DB 워밍업(keepalive) 백그라운드 시작 → 첫 호출 콜드 스타트 타임아웃 방지
    mcp.run()
# async v2: ckp_make_all 즉시반환 + ckp_status 조회 (메일 발송 기능 제거됨)
