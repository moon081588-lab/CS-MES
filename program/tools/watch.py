#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CKP 리포트 — 폴더 큐 러너 (Claude 가 어디서 돌든 동작하게 만드는 다리).

■ 왜 이 파일이 필요한가
  ckp-reports 를 MCP 로 등록하면 Claude 데스크톱 '대화' 에서는 도구가 보인다.
  그러나 Cowork 작업이 클라우드에서 실행되면 그 세션은 이 PC 의 MCP 프로세스를
  볼 수 없다. 등록이 잘못된 게 아니라, 세션이 다른 컴퓨터에 있어서다.
  그때 Claude 쪽에는 아무 단서도 안 남는다 — 도구가 그냥 '없는' 것으로 보인다.
  (이 문제로 한 달을 날렸다. 2026-08-03 확인.)

■ 그래서 어떻게 푸는가
  MCP 대신 **연결된 폴더** 를 통로로 쓴다. 폴더는 클라우드 세션이든 로컬
  세션이든 휴대폰이든 항상 읽고 쓸 수 있다.

      Claude  →  _ckp_queue/requests/<id>.json   (무엇을 뽑을지)
      이 파일 →  run_all.py 실행
      이 파일 →  _ckp_queue/status/<id>.json     (진행·결과·오류)
      Claude  ←  report/CKP_official/기준…/*.xlsx

  이 창은 켜 두기만 하면 된다. 사람이 할 일은 그게 전부다.

■ 다른 PC 로 그대로 가져가도 되게 만든 것들
  · 경로는 전부 __file__ 기준. 절대경로를 파일에 적지 않는다.
  · 결과·상태 파일은 임시파일에 쓰고 os.replace 로 바꿔치기(원자적).
    Claude 가 반쯤 쓰인 json 을 읽는 일이 없다.
  · 같은 폴더에서 두 번 켜면 두 번째는 스스로 물러난다(중복 실행 방지).
  · 예외는 전부 잡아 status 에 남긴다. 워처가 죽어서 조용해지는 상황을 없앤다.
  · heartbeat.json 을 매 초 갱신한다. Claude 는 이 파일만 보면
    '워처가 꺼져 있음' 과 '아직 도는 중' 을 구별할 수 있다.
  · 콘솔 인코딩·한글 폴더명·읽기전용 폴더를 모두 사전에 확인하고 사람 말로 알린다.

사용:
  python watch.py            # 큐를 지켜본다(보통 이것만)
  python watch.py --once     # 큐에 있는 것만 처리하고 끝낸다
  python watch.py --self-test  # DB 없이 배관만 점검한다
"""
import os, sys, json, time, uuid, shutil, datetime, traceback, subprocess

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))                 # …/program/tools
PROGRAM = os.path.dirname(HERE)                                    # …/program
ROOT = os.path.dirname(PROGRAM) if os.path.basename(PROGRAM).lower() == "program" else PROGRAM
RUN_ALL = os.path.join(PROGRAM, "ckp_reports", "run_all.py")
if not os.path.exists(RUN_ALL):                                    # git 체크아웃 배치
    RUN_ALL = os.path.join(ROOT, "ckp_reports", "run_all.py")

QUEUE = os.path.join(ROOT, "_ckp_queue")
REQ = os.path.join(QUEUE, "requests")
STA = os.path.join(QUEUE, "status")
LOG = os.path.join(QUEUE, "logs")
DONE = os.path.join(QUEUE, "processed")
HEARTBEAT = os.path.join(QUEUE, "heartbeat.json")
LOCK = os.path.join(QUEUE, "watcher.lock")

POLL_SEC = 2.0
LOCK_STALE_SEC = 30.0          # 이보다 오래 갱신이 없으면 죽은 워처로 본다


# ---------------------------------------------------------------- 유틸

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def say(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def write_json(path, obj):
    """반쯤 쓰인 파일을 남기지 않는다. Claude 가 동시에 읽어도 안전하다."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def ensure_dirs():
    for d in (QUEUE, REQ, STA, LOG, DONE):
        os.makedirs(d, exist_ok=True)


def writable(d):
    try:
        p = os.path.join(d, ".w")
        with open(p, "w") as f:
            f.write("x")
        os.remove(p)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 중복 실행 방지

def lock_alive():
    try:
        age = time.time() - os.path.getmtime(LOCK)
    except OSError:
        return False
    return age < LOCK_STALE_SEC


def take_lock():
    write_json(LOCK, {"pid": os.getpid(), "host": _hostname(), "since": now_iso()})


def _hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "?"


# ---------------------------------------------------------------- 하트비트

def beat(state="idle", current=None):
    write_json(HEARTBEAT, {
        "state": state,                 # idle | running
        "current": current,
        "at": now_iso(),
        "pid": os.getpid(),
        "host": _hostname(),
        "root": ROOT,
        "python": sys.version.split()[0],
        "poll_sec": POLL_SEC,
    })


# ---------------------------------------------------------------- 실행

def outdir_for(date, reqdate):
    return os.path.join(ROOT, "report", "CKP_official", f"기준{date}_요청{reqdate}")


def run_one(req_path):
    rid = os.path.splitext(os.path.basename(req_path))[0]
    req = read_json(req_path) or {}
    date = str(req.get("date") or "").strip()
    only = str(req.get("only") or "").strip()
    mode = str(req.get("mode") or "").strip()          # "" | "plan" | "build"
    reqdate = str(req.get("reqdate") or "").strip() or datetime.date.today().isoformat()
    stat_path = os.path.join(STA, rid + ".json")
    log_path = os.path.join(LOG, rid + ".log")

    st = {"id": rid, "state": "running", "date": date, "only": only, "mode": mode or "full",
          "reqdate": reqdate, "started": now_iso(), "log": os.path.relpath(log_path, ROOT)}
    write_json(stat_path, st)
    beat("running", rid)
    say(f"▶ {rid}  기준일={date or '(오늘)'} 대상={only or '전체 11개'} 모드={mode or 'full'}")

    cmd = [sys.executable, RUN_ALL]
    if date:
        cmd.append(date)
    if only:
        cmd += ["--only", only]
    if reqdate:
        cmd += ["--reqdate", reqdate]
    if mode == "plan":
        cmd.append("--plan")
    elif mode == "build":
        cmd.append("--build")

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    t0 = time.time()
    tail = []
    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"$ {' '.join(cmd)}\n\n")
            lf.flush()
            p = subprocess.Popen(cmd, cwd=os.path.dirname(RUN_ALL), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                lf.write(line)
                lf.flush()
                line = line.rstrip()
                if line:
                    tail.append(line)
                    del tail[:-40]
                    print("   " + line, flush=True)
                    # 오래 걸리는 동안에도 살아 있음을 알린다
                    if time.time() - t0 > 5:
                        beat("running", rid)
            rc = p.wait()
    except Exception:
        rc = -1
        tail.append(traceback.format_exc())

    od = outdir_for(date or datetime.date.today().isoformat(), reqdate)
    # 이번 실행이 실제로 쓴 파일만 센다. 폴더에 남아 있던 옛 파일을 세면
    # 실패했는데도 '11개 완료' 로 보인다 — 그 착각이 제일 위험하다.
    files, stale = [], []
    if os.path.isdir(od):
        for f in sorted(os.listdir(od)):
            if not f.lower().endswith(".xlsx"):
                continue
            (files if os.path.getmtime(os.path.join(od, f)) >= t0 - 1 else stale).append(f)
        files.sort(key=lambda s: (int(s.split(")")[0]) if s.split(")")[0].isdigit() else 999, s))

    st.update({
        "state": "done" if rc == 0 else "error",
        "returncode": rc,
        "csv_asof": _csv_asof(),
        "finished": now_iso(),
        "seconds": round(time.time() - t0, 1),
        "outdir": os.path.relpath(od, ROOT) if os.path.isdir(od) else "",
        "outdir_abs": od if os.path.isdir(od) else "",
        "files": files,
        "file_count": len(files),
        "stale_files": stale,          # 이번에 다시 쓰이지 않은 옛 파일
        "tail": tail[-25:],
    })
    if rc != 0:
        st["hint"] = _hint("\n".join(tail))
    write_json(stat_path, st)

    try:
        shutil.move(req_path, os.path.join(DONE, os.path.basename(req_path)))
    except Exception:
        try:
            os.remove(req_path)
        except Exception:
            pass

    say(("✔ 완료 " if rc == 0 else "✖ 실패 ") + f"{rid}  ({st['seconds']}초, 파일 {len(files)}개)")
    beat("idle", None)
    return rc


def _csv_asof():
    """원천 CSV 를 언제 뽑았는지. build 모드로 옛 CSV 를 재활용하면
    날짜만 바뀐 채 옛 데이터로 엑셀이 나온다 — 그걸 눈에 보이게 남긴다."""
    d = os.path.join(os.path.dirname(RUN_ALL), "sql")
    try:
        ts = max(os.path.getmtime(os.path.join(d, f))
                 for f in os.listdir(d) if f.lower().endswith(".csv"))
        return datetime.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except Exception:
        return ""


def _hint(text):
    """실패 로그를 사람 말로 한 줄 바꿔 준다. 현장에서 실제로 나온 것만 넣는다."""
    t = text.lower()
    if "ora-12170" in t or "timed out" in t or "timeout" in t:
        return "DB 로 나가지 못했습니다 → 방화벽에서 adb...oraclecloud.com 1522 아웃바운드를 열어야 합니다."
    if "ora-17956" in t or "wallet" in t and "not found" in t:
        return "지갑을 못 읽었습니다 → 폴더를 OneDrive/구글드라이브 밖(예: C:\\CKP-Report)으로 옮기세요."
    if "ora-01017" in t:
        return "계정/비밀번호가 틀립니다 → config.ini 의 [db] user/password 를 확인하세요."
    if "sqlcl" in t and ("not found" in t or "없" in text):
        return "SQLcl 을 못 찾았습니다 → config.ini 에 DB 계정을 채우면 SQLcl 없이 돕니다."
    if "permission" in t or "읽기 전용" in text or "열려 있" in text:
        return "결과 파일이 엑셀에서 열려 있습니다 → 전부 닫고 다시 요청하세요."
    if "csv 없음" in text:
        return "원천 CSV 가 없습니다 → mode 를 비우고(전체 실행) 다시 요청하세요."
    return "logs 폴더의 로그 전문을 확인하세요."


# ---------------------------------------------------------------- 점검

def preflight():
    ok = True
    print("=" * 64)
    print(" CKP 폴더 큐 러너")
    print("=" * 64)
    print(f" 프로젝트 폴더 : {ROOT}")
    print(f" 실행 파일     : {RUN_ALL}")
    print(f" 파이썬        : {sys.version.split()[0]}  ({sys.executable})")
    if not os.path.exists(RUN_ALL):
        print(" ❌ run_all.py 를 찾지 못했습니다. 이 파일을 program\\tools\\ 안에 두세요.")
        ok = False
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print(" ❌ openpyxl 이 없습니다 → CKP.bat 의 2 번(처음 설정)을 한 번 실행하세요.")
        ok = False
    ensure_dirs()
    if not writable(QUEUE):
        print(f" ❌ 큐 폴더에 쓸 수 없습니다: {QUEUE}")
        ok = False
    rep = os.path.join(ROOT, "report")
    os.makedirs(rep, exist_ok=True)
    if not writable(rep):
        print(f" ❌ 결과 폴더에 쓸 수 없습니다: {rep}")
        ok = False
    low = ROOT.lower()
    if "onedrive" in low or "dropbox" in low or "google drive" in low:
        print(" ⚠ 클라우드 동기화 폴더 안입니다. 지갑을 못 읽는 일이 있습니다(ORA-17956).")
        print("   문제가 나면 C:\\CKP-Report 같은 곳으로 옮기세요.")
    print("-" * 64)
    return ok


def self_test():
    """DB 없이 배관만 본다 — 요청을 넣고 상태가 나오는지."""
    ensure_dirs()
    rid = "selftest-" + uuid.uuid4().hex[:6]
    write_json(os.path.join(REQ, rid + ".json"), {"date": "", "only": "7", "mode": "build"})
    say("자체 점검 요청을 넣었습니다 → " + rid)
    return rid


# ---------------------------------------------------------------- 메인

def main():
    args = sys.argv[1:]
    once = "--once" in args
    if "--self-test" in args:
        preflight()
        self_test()
        once = True

    if not preflight():
        print("\n 위 문제를 먼저 해결한 뒤 다시 실행하세요.")
        try:
            input("\n엔터를 누르면 닫습니다...")
        except Exception:
            pass
        return 1

    if lock_alive() and not once:
        cur = read_json(LOCK) or {}
        print(f" 이미 다른 창에서 돌고 있습니다 (pid {cur.get('pid')}, {cur.get('since')}).")
        print(" 이 창은 닫아도 됩니다.")
        try:
            input("\n엔터를 누르면 닫습니다...")
        except Exception:
            pass
        return 0

    take_lock()
    beat("idle", None)
    print(" 준비됐습니다. 이 창을 켜 둔 채로 Claude 에게 리포트를 요청하세요.")
    print(f" 큐 폴더 : {os.path.relpath(QUEUE, ROOT)}")
    print(" 끄려면 이 창을 닫거나 Ctrl+C 를 누르세요.")
    print("-" * 64)

    last_beat = 0.0
    try:
        while True:
            pend = sorted(f for f in os.listdir(REQ) if f.lower().endswith(".json"))
            for f in pend:
                run_one(os.path.join(REQ, f))
                take_lock()
            if once:
                break
            now = time.time()
            if now - last_beat >= 1.0:
                beat("idle", None)
                take_lock()
                last_beat = now
            time.sleep(POLL_SEC)
    except KeyboardInterrupt:
        print("\n 종료합니다.")
    finally:
        try:
            os.remove(LOCK)
        except Exception:
            pass
        beat("stopped", None)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
