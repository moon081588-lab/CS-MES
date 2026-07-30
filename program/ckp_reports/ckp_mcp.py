#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — Claude Desktop용 로컬 MCP 서버
===================================================
Claude Desktop 에서 "레포트 11개 작성해줘" 한마디로 11개를 생성하게 한다.
서버가 Mac 위에서 run_all.py 를 그대로 실행하므로,
대용량 CSV가 Claude 컨텍스트를 지나가지 않는다(= 안정적). DB 조회는 make_all 이 내부에서
저장된 SQLcl 연결(changshinincaipoc)로 처리 → Claude 는 SQL 을 나르지 않는다.

필요: pip install mcp openpyxl  /  이 PC에 SQLcl(`sql`) + 'changshinincaipoc' 연결 저장.
claude_desktop_config.json 에 아래처럼 등록:
  "ckp-reports": { "command": ".../.venv/bin/python", "args": [".../ckp_reports/ckp_mcp.py"] }
"""
import os, sys, subprocess, datetime, threading, time, json

# ── MCP 프로토콜 보호 ────────────────────────────────────────────────────────
# 이 서버는 stdout 으로 JSON-RPC 를 주고받는다. 여기에 단 한 글자라도 다른 것이 섞이면
# 클라이언트는 "Server disconnected" 만 띄우고 이유는 알려주지 않는다.
#  (1) 윈도우는 텍스트 모드에서 \n 을 \r\n 으로 바꾼다 → 프레이밍이 깨진다. newline="" 로 막는다.
#  (2) 우리 코드의 모든 출력은 stderr 로 보낸다. stdout 은 MCP 전용으로 비워 둔다.
#      ※ sys.stdout 을 stderr 로 바꿔치기하면 안 된다 — MCP 가 응답을 그리로 보내 버려
#        클라이언트가 영원히 기다린다(2026-07-30 시험 중 확인).
try:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def log(*a):
    """서버 로그는 무조건 stderr 로. 실수로 print() 를 쓰지 않도록 이 함수만 쓴다."""
    print(*a, file=sys.stderr, flush=True)

HERE = os.path.dirname(os.path.abspath(__file__))
# 결과는 run_all.py 와 같은 곳을 봐야 한다 — 코드가 program\ 안에 있으면 결과는 그 한 단계 위.
_UP1   = os.path.abspath(os.path.join(HERE, ".."))
_TOP   = os.path.dirname(_UP1) if os.path.basename(_UP1).lower() == "program" else _UP1
OUTDIR = os.path.join(_TOP, "report", "CKP_official")

# --- DB keepalive(워밍업) 설정 -------------------------------------------------
# OCI Autonomous DB 는 유휴 상태에서 첫 접속 시 resume 지연이 커서, ckp_make_all 첫 호출이
# MCP 응답 제한시간(-32001)을 넘겨 타임아웃되곤 했다. 아래 백그라운드 스레드가 서버 기동 직후,
# 그리고 일정 주기로 가벼운 'SELECT 1 FROM DUAL' 을 실행해 DB 를 항상 웜 상태로 유지한다.
# → 사용자가 리포트를 부르는 시점엔 콜드 스타트 비용이 이미 지불돼 있어 첫 호출부터 통과한다.
# (make_all.py 안에 인라인 워밍업을 넣어도 같은 호출 안에서 콜드 비용을 치르므로 소용이 없다.)
def _sqlcl_path():
    """core/db.py 와 같은 방식으로 찾는다(가짜 sql.bat 을 걸러낸 결과).
    실패하면 워밍업만 포기하고 서버는 정상 기동한다."""
    try:
        sys.path.insert(0, HERE)
        from core import db as _db
        return _db.SQLCL
    except Exception:
        return os.environ.get("SQLCL", "sql")

SQLCL         = None            # 기동을 막지 않으려고 여기서 찾지 않는다. 워밍업 스레드가 처음 쓸 때 찾는다.
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

# --- 라이브러리 위치 보정 -------------------------------------------------------
# Claude 가 이 서버를 어떤 파이썬으로 띄울지는 claude_desktop_config.json 에 달려 있고,
# 그 파이썬에 mcp·openpyxl·oracledb 가 없을 수 있다(맥 Homebrew 파이썬은 전역 설치를 막는다).
# 그럴 때 새로 설치하지 않고, 이 프로젝트 안에 이미 있는 가상환경의 라이브러리를 빌려 쓴다.
def _borrow_site_packages():
    import glob
    root = os.path.dirname(HERE)                      # program 폴더
    # 파이썬 버전이 같은 것만 빌린다. 다른 버전의 site-packages 를 붙이면
    # 컴파일된 모듈이 안 맞아 더 이상한 오류가 난다.
    tag = "python%d.%d" % sys.version_info[:2]
    pats = [os.path.join(root, "*", ".venv", "lib", tag, "site-packages"),
            os.path.join(root, ".venv", "lib", tag, "site-packages"),
            os.path.join(os.path.dirname(root), "*", ".venv", "lib", tag, "site-packages"),
            os.path.join(root, "*", ".venv", "Lib", "site-packages")]   # 윈도우는 버전 폴더가 없다
    found = []
    for pat in pats:
        for d in sorted(glob.glob(pat)):
            if os.path.isdir(d) and d not in sys.path:
                sys.path.append(d); found.append(d)
    return found

_BORROWED = []
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    _BORROWED = _borrow_site_packages()
    from mcp.server.fastmcp import FastMCP        # 그래도 없으면 여기서 정직하게 실패한다

mcp = FastMCP("ckp-reports")


def _safe(fn):
    """도구 안에서 터진 예외가 연결을 흔들지 않게 한다.
    사용자에게는 한국어 한 줄로 무엇이 잘못됐는지 돌려준다."""
    import functools
    @functools.wraps(fn)
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            return (f"[오류] {type(e).__name__}: {str(e)[:400]}\n"
                    f"CKP.bat 의 3 번(DB 연결 점검)을 실행해 원인을 확인하세요.")
    return wrap

def _child_env():
    """자식(run_all.py)도 같은 라이브러리를 보게 한다. 위에서 빌려온 경로를 넘겨준다."""
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1"); env.setdefault("PYTHONIOENCODING", "utf-8")
    if _BORROWED:
        env["PYTHONPATH"] = os.pathsep.join(_BORROWED + [env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


def _run(script, date, *extra):
    args = [sys.executable, "-u", os.path.join(HERE, script)]
    if date: args.append(date)
    args += [x for x in extra if x]
    p = subprocess.run(args, capture_output=True, text=True, cwd=HERE,
                       env=_child_env(),
                       timeout=RUN_TIMEOUT)   # 무한대기 방지: 초과 시 subprocess.TimeoutExpired 발생(자식은 강제종료됨)
    out = p.stdout or ""
    if p.returncode != 0:
        out += "\n[오류]\n" + (p.stderr or "")[-1500:]
    # 종료코드를 같이 돌려준다. 예전에는 로그에 [오류] 만 붙이고 '성공' 으로 넘겨서,
    # run_all 이 중간에 죽어도 이전 실행에 남아 있던 파일 11개를 세어 [완료] 라고 답했다.
    # (2026-07-30 시뮬레이션: 엑셀로 열어 둔 3번 파일 하나 때문에 8개가 옛 데이터인 채 '완료')
    return out.strip(), p.returncode

# --- DB 워밍업(keepalive) ------------------------------------------------------
def _warm_ping():
    """DB 를 깨우는 최소 쿼리. 실패해도 서버 동작엔 영향 없음(stderr 로그만)."""
    script = (f"connect -name {WARM_CONN}\n"
              "set feedback off\nset pagesize 0\nset echo off\n"
              "SELECT 1 FROM DUAL;\nexit\n")
    global SQLCL
    if SQLCL is None:
        SQLCL = os.environ.get("SQLCL") or _sqlcl_path()
    try:
        p = subprocess.run([SQLCL, "-S", "/nolog"], input=script,
                           capture_output=True, text=True, env=dict(os.environ),
                           timeout=90)
        ok = ("ORA-" not in (p.stdout or "")) and p.returncode == 0
        log(f"[ckp warmup] {WARM_CONN} {'ok' if ok else 'warn'} (rc={p.returncode})")
    except Exception as e:
        log(f"[ckp warmup] skip: {e}")

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

def _list_reports(date, reqdate="", since=None):
    """since 를 주면 그 시각 이후에 실제로 쓰인 파일만 센다.
    폴더에 파일이 있다는 것과 '이번 실행이 만들었다' 는 것은 다르다. 이전 실행 결과가
    남아 있는 폴더에 다시 돌리면, 중간에 실패해도 파일 개수는 11개 그대로다."""
    try:
        names = sorted(f for f in os.listdir(_dated(date, reqdate)) if f.lower().endswith(".xlsx"))
    except FileNotFoundError:
        return []
    if since is None:
        return names
    d = _dated(date, reqdate)
    fresh = []
    for f in names:
        try:
            if os.path.getmtime(os.path.join(d, f)) >= since - 2:   # 2초는 파일시스템 시각 오차 여유
                fresh.append(f)
        except OSError:
            pass
    return fresh


def _cause(out):
    """로그를 보고 사람이 할 일을 한 줄로 짚어 준다. 실패 화면은 이 한 줄이 전부다."""
    low = (out or "").lower()
    if "permissionerror" in low or "operation not permitted" in low or "access is denied" in low \
       or "errno 13" in low or "[errno 1]" in low:
        return ("결과 폴더에 쓸 수 없습니다 — 엑셀에서 열어 둔 리포트 파일을 모두 닫고, "
                "결과 폴더가 읽기 전용인지(속성 → 읽기 전용) 확인한 뒤 다시 실행하세요.")
    if "no space left" in low or "errno 28" in low or "디스크" in (out or ""):
        return "디스크 공간이 부족합니다 — 여유 공간을 확보한 뒤 다시 실행하세요."
    if "sqlcl" in low and ("찾을 수 없" in (out or "") or "not found" in low):
        return "SQLcl 을 찾지 못했습니다 → CKP.bat 의 3 번으로 접속 경로를 확인하세요."
    if "ora-01017" in low:
        return "DB 계정 또는 비밀번호가 틀렸습니다 → CKP.bat 의 2 번에서 다시 입력하세요."
    if "지갑" in (out or "") or "ora-12154" in low or "ora-28759" in low:
        return "지갑을 읽지 못했습니다 → wallet 폴더에 파일 8개가 다 있는지 확인하세요."
    if "timed out" in low or "timeout" in low or "12170" in (out or ""):
        return "DB 로 나가지 못했습니다 → 사내 방화벽에서 1522 포트를 열어야 합니다."
    return "로그의 [오류] 부분을 보세요."

def _save_status(job):
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        pub = {k: v for k, v in job.items() if not k.startswith("_")}
        with open(_status_path(job["date"]), "w", encoding="utf-8") as f:
            json.dump(pub, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"[ckp job] 상태파일 저장 실패: {e}")

def _worker(date, only):
    job = _JOBS[date]
    rq = job.get("reqdate", "")
    try:
        job["output"], rc = _run("run_all.py", date, "--reqdate", rq, *only)
        # 이번 실행이 실제로 쓴 파일만 센다(옛 파일을 성과로 세지 않는다).
        job["files"] = _list_reports(date, rq, since=job["_t0"])
        if rc != 0:
            job["state"] = "error"
            job["error"] = _cause(job["output"])
        else:
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
    expected = len([x for x in reports.replace(",", " ").split()]) if reports.strip() else 11
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
        job = {"date": date, "reqdate": reqdate, "scope": scope, "expected": expected,
               "state": "running",
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

def _valid_date(v):
    """기준일 검증. 이 값이 그대로 폴더 이름이 되므로 형식을 어기면 여기서 끊는다.
    (2026-07-30 시험: '에러/../../' 가 그대로 통과해 엉뚱한 곳에 폴더를 만들었다.)"""
    v = (v or "").strip()
    if not v:
        return datetime.date.today().isoformat(), ""
    try:
        d = datetime.date.fromisoformat(v)
    except ValueError:
        return "", (f"[입력 오류] 기준일 '{v[:40]}' 은 날짜 형식이 아닙니다.\n"
                    "  YYYY-MM-DD 로 주세요. 예: 2026-07-25")
    today = datetime.date.today()
    if d.year < 2000 or d > today + datetime.timedelta(days=365):
        return "", f"[입력 오류] 기준일 {v} 은 범위를 벗어났습니다."
    return d.isoformat(), ""


def _valid_reports(v):
    """리포트 번호 검증. 1~11 만 허용."""
    v = (v or "").strip()
    if not v:
        return "", ""
    got, bad = [], []
    for x in v.replace(",", " ").split():
        x = x.strip().lower()
        x = x[2:] if x.startswith("no") else x
        (got if x in {str(i) for i in range(1, 12)} else bad).append(x)
    if bad:
        return "", (f"[입력 오류] 리포트 번호 {', '.join(bad[:5])} 은 없습니다.\n"
                    "  1~11 중에서 골라 주세요. 예: 3,4  또는 비워두면 전체 11개.")
    return ",".join(got), ""


@mcp.tool()
@_safe
def ckp_make_all(date: str = "", reports: str = "") -> str:
    """CKP Manual Report 리포트를 생성한다(기본 공식 11개 전체).
    실행이 끝날 때까지 기다렸다가 결과(생성 파일 목록·로그)를 바로 반환한다 — 보통 2분 내 완료라 한 번의 호출로 끝(폴링 불필요).
    드물게 대기 상한(SYNC_WAIT, 기본 210초)을 넘길 때만 '시작' 메시지를 반환하며, 그 경우에만 ckp_status(date) 로 완료를 확인한다.
    date: 'YYYY-MM-DD'(생략 시 오늘). reports: 특정 번호만 지정(예 '3,4' 또는 '3 4 11'), 생략 시 전체 11개.
      1 Daily Scan · 2 IP Production · 3 IP Prod by size · 4 IP Outgoing by size · 5 IP Outgoing Market ·
      6 External OS&D · 7 CMP · 8 Outgoing PH · 9 PH before UV · 10 PH after UV · 11 PH in Market by size.
    저장된 SQLcl 연결로 DB 조회(접속 1회 일괄) → report/CKP_official/기준<날짜>_요청<오늘>/ 에 xlsx 생성.
    양식(사이즈·날짜 D-offset 컬럼)은 원본 고정 구조라 데이터가 0행이어도 열이 유지된다."""
    d, why = _valid_date(date)
    if why:
        return why                      # 폴더 이름으로 그대로 쓰이므로 반드시 막는다
    reports, why = _valid_reports(reports)
    if why:
        return why
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
    rq = job.get("reqdate", "")
    out = job.get("output", "")
    exp = job.get("expected")
    if not exp:      # 구버전 상태파일에는 expected 가 없다 → scope('선택(3,4)') 에서 복원
        sc = job.get("scope") or ""
        exp = len([x for x in sc[sc.find("(") + 1:sc.find(")")].replace(",", " ").split()]) if "(" in sc else 11
        exp = exp or 11
    files = job.get("files")
    if files is None:
        files = _list_reports(d, rq)
    if state == "error":
        # 중간에 죽었으면 몇 개가 나왔든 실패다. 개수를 같이 보여 줘야 사람이 폴더를 믿지 않는다.
        return (f"[실패] {d} — {job.get('scope')} · 소요 {el}초 · "
                f"이번 실행이 만든 파일 {len(files)}/{exp}개\n"
                f"  {job.get('error') or _cause(out)}\n"
                f"  ※ 폴더에 남아 있는 파일은 이전 실행 결과일 수 있습니다. 그대로 쓰지 마세요.\n\n"
                f"== 생성 로그 ==\n{out[-2000:]}\n\n확인할 폴더: {_dated(d, rq)}")
    if not files:
        # 파일이 하나도 없으면 성공이 아니다. 여기서 '완료' 라고 답하면
        # 현장에서는 "만들어졌다는데 폴더가 비었다" 가 된다.
        return (f"[실패] {d} — {job.get('scope')} · 소요 {el}초 · **생성된 파일이 없습니다**\n"
                f"  {_cause(out)}\n\n== 생성 로그 ==\n{out[-2000:]}"
                f"\n\n확인할 폴더: {_dated(d, rq)}")
    if len(files) < exp:
        # 종료코드가 0이어도 개수가 모자라면 성공이 아니다.
        return (f"[실패] {d} — {job.get('scope')} · 소요 {el}초 · "
                f"{exp}개 중 {len(files)}개만 만들어졌습니다\n"
                f"  {_cause(out)}\n" + "\n".join(files)
                + f"\n\n== 생성 로그 ==\n{out[-2000:]}\n\n확인할 폴더: {_dated(d, rq)}")
    return (f"[완료] {d} — {job.get('scope')} · 소요 {el}초 · 파일 {len(files)}개\n"
            + "\n".join(files) + f"\n\n== 생성 로그 ==\n{out}"
            + f"\n\n저장 위치: {_dated(d, rq)}")

@mcp.tool()
@_safe
def ckp_ping() -> str:
    """연결 확인용. DB 도 파일도 건드리지 않고 즉시 답한다.
    현장에서 '브릿지가 살아 있는가' 만 1초 안에 확인하려고 만든 것."""
    import platform
    return ("[ckp-reports] 연결 정상\n"
            f"  프로그램 폴더 : {_TOP}\n"
            f"  결과 폴더     : {OUTDIR}\n"
            f"  파이썬        : {sys.version.split()[0]} ({sys.executable})\n"
            f"  OS            : {platform.platform()}\n"
            f"  지금          : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n"
            "  → 이 메시지가 보이면 Claude 와 프로그램이 붙어 있습니다. "
            "이제 ckp_make_all 로 리포트를 만들 수 있습니다.")


@mcp.tool()
@_safe
def ckp_status(date: str = "") -> str:
    """진행 중이거나 완료된 CKP 생성 잡의 상태를 조회한다.
    ckp_make_all 로 시작한 뒤, 완료 여부·소요시간·생성 파일 목록을 확인할 때 사용.
    date: 'YYYY-MM-DD' (생략 시 오늘)."""
    return _status_text(date or datetime.date.today().isoformat())

@mcp.tool()
@_safe
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
@_safe
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
@_safe
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
# async v2: ckp_make_all 즉시반환 + ckp_status 조회
