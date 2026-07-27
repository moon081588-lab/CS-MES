#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — Claude Desktop용 로컬 MCP 서버
===================================================
Claude Desktop이 "CKP 리포트 만들어줘 / 메일 보내줘" 한마디로 11개를 생성·발송하게 한다.
서버가 이 PC 위에서 make_all.py / mail_reports.py 를 그대로 실행하므로,
대용량 CSV가 Claude 컨텍스트를 지나가지 않는다(= 안정적). DB 조회는 make_all 이 내부에서
저장된 SQLcl 연결로 처리 → Claude 는 SQL 을 나르지 않는다.
연결 이름은 고정이 아니다: --conn > env CKP_CONN > config.ini [db] sqlcl_conn > 자동 탐색.

※ 11개 생성은 70~90초가 걸려 MCP 호출 제한(60초)을 넘긴다. 그래서 ckp_make_all 은
  **백그라운드로 띄우고 즉시 반환**한다. 진행 상황은 ckp_status() 로 확인한다.
  한 번의 호출로 끝까지 기다리려면 ckp_make_all(wait=True) — 단 타임아웃될 수 있다.

필요: pip install mcp openpyxl  /  이 PC 에 SQLcl(`sql`) 설치 + OCI ADB 연결 1개 저장.

claude_desktop_config.json 등록 예 (경로는 실제 설치 위치로 바꿀 것):

  macOS / Linux
    "ckp-reports": {
      "command": "/path/to/CS-MES/balance_outgoing_mailer/.venv/bin/python",
      "args":    ["/path/to/CS-MES/ckp_reports/ckp_mcp.py"]
    }

  Windows  ※ .venv\\Scripts\\python.exe 이고, JSON 이라 역슬래시는 두 번 씁니다
    "ckp-reports": {
      "command": "C:\\\\CS-MES\\\\balance_outgoing_mailer\\\\.venv\\\\Scripts\\\\python.exe",
      "args":    ["C:\\\\CS-MES\\\\ckp_reports\\\\ckp_mcp.py"],
      "env":     { "TNS_ADMIN": "C:\\\\CS-MES\\\\balance_outgoing_mailer\\\\wallet" }
    }
  설정 파일 위치 — Windows: %APPDATA%\\Claude\\claude_desktop_config.json
                   macOS  : ~/Library/Application Support/Claude/claude_desktop_config.json
  수정 후 Claude Desktop 을 완전히 종료(트레이 아이콘까지)했다가 재시작해야 반영됩니다.

  ※ 폴더를 옮겼다면 위 경로를 손으로 고치지 말고:
        python balance_outgoing_mailer/setup_env.py --fix-claude
     이 스크립트가 자기 위치를 기준으로 config 를 다시 써 준다. 그다음 Desktop 재시작.
"""
import os, sys, json, time, signal, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))
LOG   = os.path.join(HERE, "last_run.log")
STATE = os.path.join(HERE, "last_run.json")

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("ckp-reports")


# ---------------------------------------------------------------- 공통 실행
def _run(script, date):
    """동기 실행. 짧게 끝나는 작업(메일 등)에만 쓴다."""
    args = [sys.executable, os.path.join(HERE, script)]
    if date: args.append(date)
    p = subprocess.run(args, capture_output=True, text=True, cwd=HERE)
    out = p.stdout or ""
    if p.returncode != 0:
        out += "\n[오류]\n" + (p.stderr or "")[-1500:]
    return out.strip()


def _start(scripts, date, label):
    """scripts 를 순서대로 백그라운드 실행하고 즉시 반환. 로그는 LOG 에 누적."""
    prev = _read_state()
    if prev and _alive(prev.get("pid")):
        return (f"⚠️ 이미 실행 중입니다 — {prev.get('label')} ({prev.get('date')}, "
                f"{int(time.time() - prev.get('started', time.time()))}초 경과)\n"
                f"   ckp_status() 로 진행 상황을 확인하세요.")
    runner = (
        "import subprocess,sys,json,os\n"
        "scripts=json.loads(sys.argv[1]); here=sys.argv[2]; date=sys.argv[3]\n"
        "for s in scripts:\n"
        "    a=[sys.executable, os.path.join(here,s)] + ([date] if date else [])\n"
        "    print('>>> '+s, flush=True)\n"
        "    r=subprocess.run(a, cwd=here)\n"
        "    if r.returncode!=0:\n"
        "        print('[오류] %s 종료코드 %d' % (s, r.returncode), flush=True); break\n"
        "print('<<< DONE', flush=True)\n"
    )
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(f"=== {label} | {date} | {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    logf = open(LOG, "a", encoding="utf-8")
    kw = {}
    if os.name == "posix":
        kw["start_new_session"] = True                      # 부모(MCP 서버)와 수명 분리
    else:
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    p = subprocess.Popen([sys.executable, "-u", "-c", runner,
                          json.dumps(scripts), HERE, date or ""],
                         stdout=logf, stderr=subprocess.STDOUT, cwd=HERE, **kw)
    _write_state({"pid": p.pid, "date": date, "label": label,
                  "started": time.time(), "scripts": scripts})
    return (f"▶ {label} 시작 (기준일 {date}, pid {p.pid})\n"
            f"   11개 생성은 보통 70~90초 걸립니다. ckp_status() 로 확인하세요.\n"
            f"   저장 위치: {OUTDIR}")


def _read_state():
    try:
        with open(STATE, encoding="utf-8") as f: return json.load(f)
    except Exception:
        return None


def _write_state(d):
    try:
        with open(STATE, "w", encoding="utf-8") as f: json.dump(d, f)
    except Exception:
        pass


def _alive(pid):
    if not pid: return False
    try:
        os.kill(int(pid), 0); return True
    except Exception:
        return False


# ---------------------------------------------------------------- 툴
@mcp.tool()
def ckp_make_all(date: str = "", wait: bool = False) -> str:
    """CKP Manual Report 공식 11개 리포트를 생성한다.
    date: 'YYYY-MM-DD' (생략 시 오늘). 저장된 SQLcl 연결로 DB 조회 → report/CKP_official/ 에 'NO) 리포트명.xlsx' 11개.
    기본은 백그라운드 실행 후 즉시 반환한다(생성에 70~90초 걸려 MCP 60초 제한을 넘기 때문).
    진행 상황은 ckp_status() 로 확인할 것. wait=True 면 끝까지 기다리지만 타임아웃될 수 있다.
    양식(사이즈·날짜 D-offset 컬럼)은 원본 고정 구조라 데이터가 0행이어도 열이 유지된다."""
    d = date or datetime.date.today().isoformat()
    if wait:
        return f"[CKP 11개 생성] {d}\n{_run('make_all.py', d)}\n\n저장 위치: {OUTDIR}"
    return _start(["make_all.py"], d, "CKP 11개 생성")


@mcp.tool()
def ckp_status(tail: int = 25) -> str:
    """직전(또는 진행 중)인 CKP 작업의 상태를 돌려준다.
    실행 여부·경과 시간·로그 끝부분·산출 파일 목록(생성 시각)을 함께 보여준다."""
    st = _read_state()
    lines = []
    if not st:
        lines.append("실행 기록이 없습니다. ckp_make_all() 로 시작하세요.")
    else:
        el = int(time.time() - st.get("started", time.time()))
        running = _alive(st.get("pid"))
        lines.append(f"작업     : {st.get('label')} (기준일 {st.get('date')})")
        lines.append(f"상태     : {'⏳ 실행 중' if running else '✅ 종료됨'} — {el}초 경과, pid {st.get('pid')}")
    try:
        log = open(LOG, encoding="utf-8").read().splitlines()
        done = any("<<< DONE" in l for l in log)
        err  = [l for l in log if "[오류]" in l or "Traceback" in l]
        if not st or not _alive((st or {}).get("pid")):
            lines.append(f"완료표시 : {'있음' if done else '없음(중단되었을 수 있음)'}")
        if err: lines.append(f"오류     : {len(err)}건 — 아래 로그 확인")
        lines.append(f"--- 로그 마지막 {tail}줄 ---")
        lines += log[-tail:]
    except FileNotFoundError:
        lines.append("(로그 파일 없음)")
    try:
        fs = sorted(f for f in os.listdir(OUTDIR) if f.endswith(".xlsx"))
        lines.append(f"--- 산출 파일 {len(fs)}개 @ {OUTDIR} ---")
        for f in fs:
            m = os.path.getmtime(os.path.join(OUTDIR, f))
            lines.append(f"  {datetime.datetime.fromtimestamp(m):%H:%M:%S}  {f}")
    except Exception as e:
        lines.append(f"(산출 폴더 확인 실패: {e})")
    return "\n".join(lines)


@mcp.tool()
def ckp_mail(date: str = "") -> str:
    """생성된 11개 리포트를 ZIP으로 묶어 메일 첨부 발송한다(config.ini [smtp]/[report] 수신자).
    ckp_make_all 로 먼저 생성하고 ckp_status() 가 '종료됨' 인지 확인한 뒤 호출."""
    d = date or datetime.date.today().isoformat()
    return f"[CKP 메일 발송] {d}\n{_run('mail_reports.py', d)}"


@mcp.tool()
def ckp_make_and_mail(date: str = "") -> str:
    """CKP 11개 생성 후 곧바로 메일 첨부 발송까지. 백그라운드로 돌고 즉시 반환하므로
    ckp_status() 로 진행을 확인할 것."""
    d = date or datetime.date.today().isoformat()
    return _start(["make_all.py", "mail_reports.py"], d, "CKP 11개 생성 + 메일 발송")


if __name__ == "__main__":
    mcp.run()
