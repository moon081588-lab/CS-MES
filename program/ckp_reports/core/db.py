#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DB 실행 계층 — **두 가지 경로를 자동 선택**한다.

  1) oracledb 드라이버 직결   config.ini [db] 에 user/password 가 있으면 이쪽.
                              SQLcl·Java 가 필요 없다. (권장 — 무설치 배포용)
  2) SQLcl 서브프로세스        계정이 비어 있으면 이쪽. SQLcl 저장 연결의
                              비밀번호를 쓰므로 config 에 비밀번호를 안 적어도 된다.

어느 쪽이든 바깥에서 쓰는 함수(run_batch / sqlcl_csv / run_builder)와
CSV 출력 형식은 같다. 리포트 빌더는 무엇으로 조회했는지 몰라도 된다.

접속을 1회로 묶는 이유(원본 주석 유지): 리포트마다 SQLcl(JVM)·지갑 콜드 접속을
반복하던 구조가 타임아웃 원인이었다. 드라이버 경로도 같은 이유로 접속 1회를 유지한다.
"""
import os, sys, csv, time, datetime, subprocess, configparser

CORE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../ckp_reports/core
PKG_DIR  = os.path.dirname(CORE_DIR)                           # .../ckp_reports
ROOT_DIR = os.path.dirname(PKG_DIR)                            # 코드가 놓인 폴더

# 사용자가 보는 최상위 폴더. 코드는 program\ 안에 몰아넣고 지갑·결과만 위로 꺼내
# 두었기 때문에, 그 경우 한 단계 위가 '사람이 여는 폴더' 다.
USER_ROOT = os.path.dirname(ROOT_DIR) if os.path.basename(ROOT_DIR).lower() == "program" else ROOT_DIR

def _find_sqlcl():
    """SQLcl 실행파일 탐색. env SQLCL > PATH > 흔한 설치 위치 순.
    macOS 는 로그인 셸 PATH 에 없는 경우가 잦아(Homebrew·수동 압축해제) 직접 뒤진다."""
    import shutil, glob as _g
    v = os.environ.get("SQLCL")
    if v: return v
    for n in (("sql.exe", "sql.cmd", "sql.bat", "sql") if os.name == "nt" else ("sql",)):
        p = shutil.which(n)
        if p: return p
    cands = [os.path.join(ROOT_DIR, "sqlcl", "bin", "sql"),
             "/opt/homebrew/bin/sql", "/usr/local/bin/sql",
             os.path.expanduser("~/sqlcl/bin/sql"), "/opt/sqlcl/bin/sql",
             r"C:\sqlcl\bin\sql.exe", r"C:\Program Files\sqlcl\bin\sql.exe"]
    cands += sorted(_g.glob("/opt/homebrew/Cellar/sqlcl/*/bin/sql"))
    cands += sorted(_g.glob(os.path.expanduser("~/Applications/sqlcl*/bin/sql")))
    for c in cands:
        if os.path.exists(c): return c
    return "sql"


SQLCL = _find_sqlcl()


def _valid_wallet(d):
    """지갑 폴더로 쓸 수 있는지. tnsnames.ora 가 실제로 있어야 인정한다."""
    return bool(d) and os.path.isfile(os.path.join(d, "tnsnames.ora"))


# 환경변수 TNS_ADMIN 은 **실제로 존재할 때만** 쓴다.
# 셸이나 예전 설치에서 남은 경로가 박혀 있으면(폴더 이동·OneDrive 이관 등) 그게 자동탐색을
# 이겨서 접속이 조용히 실패한다. 2026-07-28 현장에서 정확히 이 일이 일어났다 —
# TNS_ADMIN 이 사라진 OneDrive 경로를 가리키고 있었다.
_ENV_TNS = os.environ.get("TNS_ADMIN") or ""
if _ENV_TNS and not _valid_wallet(_ENV_TNS):
    print(f"[db] 환경변수 TNS_ADMIN 이 가리키는 곳에 지갑이 없어 무시합니다: {_ENV_TNS}")
    _ENV_TNS = ""
TNS_ADMIN = _ENV_TNS or None
JAVA_HOME = os.environ.get("JAVA_HOME") or None


# ----------------------------------------------------------------- 공통
def load_cfg():
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    cp.read(os.path.join(PKG_DIR, "config.ini"), encoding="utf-8")
    return cp


def wallet_dir(cfg=None):
    """지갑 폴더. config 가 비면 번들 안의 wallet/ 을 자동으로 찾는다."""
    cfg = cfg or load_cfg()
    d = cfg.get("db", "wallet_dir", fallback="").strip()
    if _valid_wallet(d):
        return os.path.abspath(d)
    for c in (os.path.join(USER_ROOT, "wallet"),                            # 배포본 배치
              os.path.join(ROOT_DIR, "wallet"),
              os.path.join(ROOT_DIR, "mailer", "wallet"),                    # 저장소 배치
              os.path.join(ROOT_DIR, "balance_outgoing_mailer", "wallet"),   # 옛 폴더명
              os.path.join(PKG_DIR, "wallet")):
        got = find_wallet(c)          # zip 째·하위폴더째 넣어도 찾아낸다
        if got:
            return got
    return TNS_ADMIN or ""


def _unpack_wallet_zip(folder):
    """wallet\\ 에 zip 을 그대로 넣어두는 일이 잦다. 있으면 그 자리에 풀어 준다."""
    import glob as _g, zipfile
    if not os.path.isdir(folder):
        return
    for z in sorted(_g.glob(os.path.join(folder, "*.zip"))):
        try:
            with zipfile.ZipFile(z) as zf:
                if any(n.endswith("tnsnames.ora") for n in zf.namelist()):
                    zf.extractall(folder)
                    print(f"[db] 지갑 zip 을 풀었습니다: {os.path.basename(z)}")
                    # 이름을 바꿔 둔다. 안 그러면 실행할 때마다 다시 풀고 같은 줄을 또 찍는다.
                    try: os.rename(z, z + ".unpacked")
                    except OSError: pass
        except Exception:
            pass


def find_wallet(start):
    """start 아래를 훑어 tnsnames.ora 가 있는 폴더를 찾는다.
    담당자가 지갑을 하위 폴더째 넣거나(Wallet_XXX\\) zip 째 넣어도 동작하게 한다."""
    if not start or not os.path.isdir(start):
        return ""
    _unpack_wallet_zip(start)
    if _valid_wallet(start):
        return os.path.abspath(start)
    for root, dirs, files in os.walk(start):
        dirs[:] = [d for d in dirs if not d.startswith(("__", "."))]
        if "tnsnames.ora" in files:
            return os.path.abspath(root)
        if root.count(os.sep) - start.count(os.sep) >= 3:
            dirs[:] = []
    return ""


def dsn_endpoint(wdir, dsn=""):
    """tnsnames.ora 에서 (host, port) 를 뽑는다. 방화벽 점검용."""
    import re
    p = os.path.join(wdir or "", "tnsnames.ora")
    if not os.path.isfile(p):
        return ("", 0)
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        return ("", 0)
    block = txt
    if dsn:
        m = re.search(re.escape(dsn) + r"\s*=\s*(.+)", txt, re.I)
        if m:
            block = m.group(1)
    h = re.search(r"host\s*=\s*([^\s)]+)", block, re.I)
    q = re.search(r"port\s*=\s*(\d+)", block, re.I)
    return (h.group(1) if h else "", int(q.group(1)) if q else 0)


def preflight(host, port, timeout=6.0):
    """DB 포트가 이 PC 에서 열려 있는지 먼저 본다.
    방화벽/프록시 문제를 '계정이 틀렸다' 로 오해하지 않게 하려는 것."""
    import socket
    if not (host and port):
        return (None, "접속 주소를 tnsnames.ora 에서 찾지 못했습니다")
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return (True, f"{host}:{port} 열림")
    except socket.gaierror as e:
        return (False, f"주소를 못 찾습니다({host}) — DNS/인터넷 연결 문제: {e}")
    except Exception as e:
        return (False, f"{host}:{port} 로 연결되지 않습니다 — 사내 방화벽에서 이 포트를 열어야 합니다: {e}")


def save_cfg(updates, section="db"):
    """config.ini 를 주석을 지키면서 갱신한다(키=값 줄만 갈아끼움)."""
    import re
    path = os.path.join(PKG_DIR, "config.ini")
    if not os.path.exists(path):
        ex = path + ".example"
        if os.path.exists(ex):
            import shutil; shutil.copy(ex, path)
    lines = open(path, encoding="utf-8").read().splitlines(True) if os.path.exists(path) else []
    cur, left = "", dict(updates)
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st.startswith("[") and st.endswith("]"):
            cur = st[1:-1].lower(); continue
        if cur != section.lower() or st.startswith((";", "#")) or "=" not in ln:
            continue
        k = ln.split("=", 1)[0].strip()
        if k in left:
            v = str(left.pop(k))
            tail = ""
            m = re.search(r"\s;.*$", ln.rstrip("\n"))
            # 값에 ';' 가 들어 있으면(비밀번호에 흔하다) 뒤의 설명 주석을 지운다.
            # 안 그러면 설정을 읽을 때 주석 시작점을 잘못 잡아 비밀번호가 잘린다.
            if m and ";" not in v: tail = m.group(0)
            lines[i] = f"{k:<15} = {v}{tail}\n"
    if left:
        lines.append(f"\n[{section}]\n" if not lines else "")
        for k, v in left.items():
            lines.append(f"{k:<15} = {v}\n")
    open(path, "w", encoding="utf-8").write("".join(lines))
    return path


def sync_sqlnet(wdir):
    """복사해 온 지갑의 sqlnet.ora 에는 남의 PC 절대경로가 박혀 있다.
    이걸 이 PC 의 실제 경로로 고쳐 두지 않으면 ORA-12154/28759/29024 가 난다."""
    p = os.path.join(wdir or "", "sqlnet.ora")
    if not (wdir and os.path.isfile(p)):
        return
    try:
        import re
        s = open(p, encoding="utf-8").read()
        new = re.sub(r'DIRECTORY\s*=\s*"[^"]*"', 'DIRECTORY="%s"' % wdir.replace("\\", "\\\\"), s)
        if new != s:
            open(p, "w", encoding="utf-8").write(new)
    except Exception:
        pass


def choose_backend(cfg=None):
    """(backend, 사람이 읽는 이유) 반환."""
    cfg = cfg or load_cfg()
    forced = (cfg.get("db", "backend", fallback="") or "auto").strip().lower()
    user = cfg.get("db", "user", fallback="").strip()
    pw   = cfg.get("db", "password", fallback="").strip()
    if forced == "sqlcl":
        return "sqlcl", "config.ini 에서 sqlcl 로 고정"
    if forced == "oracledb":
        return "oracledb", "config.ini 에서 oracledb 로 고정"
    if user and pw:
        try:
            import oracledb                      # noqa: F401
            return "oracledb", f"config.ini 에 DB 계정이 있어 드라이버로 직접 접속 (user={user}, SQLcl 불필요)"
        except ImportError:
            return "sqlcl", "DB 계정은 있으나 oracledb 가 설치되지 않아 SQLcl 로 진행"
    return "sqlcl", "config.ini 에 DB 계정이 비어 있어 SQLcl 저장 연결 사용"


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v.strftime("%Y-%m-%d")
    return str(v)


def _write_rows(cols, rows, out_csv):
    """SQLcl 출력과 같은 형태(헤더 따옴표 + 값 따옴표)로 저장한다.
    빌더들은 csv.DictReader 로 읽으므로 따옴표 유무는 무해하지만, 형식을 맞춰 둔다."""
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow([c.upper() for c in cols])
        for r in rows:
            w.writerow([_fmt(v) for v in r])
    return len(rows)


# ----------------------------------------------------------------- oracledb 경로
def _ora_connect(cfg):
    import oracledb
    wdir = wallet_dir(cfg)
    sync_sqlnet(wdir)
    user = cfg.get("db", "user", fallback="").strip()
    pw   = cfg.get("db", "password", fallback="").strip()
    dsn  = cfg.get("db", "dsn", fallback="changshinincaipoc_medium").strip()
    wpw  = cfg.get("db", "wallet_password", fallback="").strip()
    lib  = cfg.get("db", "oracle_client_lib", fallback="").strip() or None
    mode = (cfg.get("db", "mode", fallback="auto") or "auto").strip().lower()
    base = dict(user=user, password=pw, dsn=dsn, tcp_connect_timeout=8.0)
    if wdir:
        base["config_dir"] = wdir

    # 사내망이 HTTP 프록시를 통해서만 나가는 곳이 있다. 그때는 직접 TCP 가 막힌 것이
    # 정상이므로 프록시를 넘겨 주고 사전점검은 건너뛴다.
    prx  = cfg.get("db", "https_proxy", fallback="").strip()
    prxp = cfg.get("db", "https_proxy_port", fallback="").strip()
    if prx:
        base["https_proxy"] = prx
        if prxp.isdigit():
            base["https_proxy_port"] = int(prxp)

    # 포트가 막혀 있으면 여기서 끝낸다. tnsnames.ora 의 retry_count=20·retry_delay=3 때문에
    # 그냥 두면 1분 넘게 매달린 뒤에야 실패한다 — 현장에서 '멈췄다' 로 보인다.
    _pf = (cfg.get("db", "preflight", fallback="") or "auto").strip().lower()
    _h, _p = dsn_endpoint(wdir, dsn)
    if _h and _pf != "off" and not prx:
        _ok, _why = preflight(_h, _p, timeout=6.0)
        if _ok is False:
            raise RuntimeError(
                f"DB 포트에 닿지 못했습니다 — {_why}\n"
                f"[원인] 사내 방화벽/프록시에서 '{_h} {_p} 아웃바운드' 를 열어야 합니다.\n"
                f"       (계정·지갑 문제가 아닙니다. 네트워크를 먼저 푸세요.)\n"
                f"       프록시를 거쳐야만 나가는 망이면 config.ini [db] 에\n"
                f"       https_proxy / https_proxy_port 를 적으면 그쪽으로 붙습니다.")

    def _thick():
        try:
            oracledb.init_oracle_client(lib_dir=lib)
        except Exception as e:
            if "already" not in str(e).lower():
                raise RuntimeError(f"Instant Client 없음(thick): {e}")
        return oracledb.connect(**base)

    def _thin():
        kw = dict(base)
        if wdir:
            kw["wallet_location"] = wdir
            if wpw:
                kw["wallet_password"] = wpw
            elif os.path.exists(os.path.join(wdir, "ewallet.pem")):
                raise RuntimeError(
                    "지갑 비밀번호가 필요합니다. config.ini [db] wallet_password 에 넣어 주세요.\n"
                    "  (지갑의 ewallet.pem 이 암호화되어 있어 드라이버가 열 수 없습니다)")
        return oracledb.connect(**kw)

    # auto 는 thin 우선. 현장 PC 에 Instant Client 가 없는 것이 기본값이고,
    # thick 을 먼저 때리면 실패를 기다리는 시간만 늘어난다.
    order = {"thick": [_thick], "thin": [_thin]}.get(mode, [_thin, _thick])
    errs = []
    for fn in order:
        try:
            return fn()
        except Exception as e:
            errs.append(f"{fn.__name__.strip('_')}: {str(e)[:200]}")
    blob = " ".join(errs)
    host, port = dsn_endpoint(wdir, dsn)
    hint = classify(blob, wdir, host, port)
    raise RuntimeError("DB 접속 실패\n  · " + "\n  · ".join(errs) +
                       f"\n  · 지갑 폴더: {wdir or '(없음)'}\n\n[원인] " + hint)


def classify(blob, wdir="", host="", port=0):
    """오류 문자열을 보고 네트워크/지갑/비밀번호/계정 중 무엇인지 한 줄로 말해 준다."""
    b = (blob or "").upper()
    if "ORA-01017" in b or "INVALID USERNAME" in b:
        return "DB 계정 또는 비밀번호가 틀렸습니다 → setup.bat 을 다시 돌려 입력하세요."
    if "DPY-4027" in b or "WALLET_PASSWORD" in b or "지갑 비밀번호" in (blob or ""):
        return "지갑 비밀번호가 없거나 틀렸습니다 → setup.bat 을 다시 돌려 입력하세요."
    if "ORA-12154" in b or "DPY-4000" in b or "CANNOT CONNECT" in b:
        return f"접속 이름을 못 찾습니다. 지갑 폴더에 tnsnames.ora 가 있는지 보세요 → {wdir or '(지갑 없음)'}"
    if "ORA-28759" in b or "ORA-29024" in b or "SSL" in b or "CERT" in b:
        return f"지갑 파일을 읽지 못했습니다. wallet 폴더에 8개 파일이 다 있는지 확인하세요 → {wdir or '(없음)'}"
    if "ORA-17956" in b:
        return "폴더 경로에 한글·공백이 있습니다 → C:\\CKP-Report 처럼 영문 경로로 옮기세요."
    if "TIMEOUT" in b or "TIMED OUT" in b or "REFUSED" in b or "DPY-6005" in b or "ORA-12170" in b:
        ok, why = preflight(host, port)
        return ("사내 방화벽에서 DB 포트가 막혀 있습니다 — " + why) if ok is False else \
               "DB 서버 응답이 없습니다. 잠시 후 다시 시도하거나 네트워크를 확인하세요."
    return "위 메시지를 그대로 담당자에게 보내 주세요."


def _ora_batch(items, cfg):
    con = _ora_connect(cfg)
    try:
        cur = con.cursor()
        for path, sql in items:
            cur.execute(sql.rstrip().rstrip(";"))
            cols = [d[0] for d in cur.description]
            _write_rows(cols, cur.fetchall(), path)
        cur.close()
    finally:
        try: con.close()
        except Exception: pass


# ----------------------------------------------------------------- SQLcl 경로
def _env():
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    # TNS_ADMIN 이 없으면 지갑 폴더를 자동으로 넣는다.
    # 이게 없으면 SQLcl 이 지갑을 못 찾아 "파싱 실패(헤더 없음)" 로만 보인다 —
    # 원인을 알 수 없는 형태라 2026-07-28 에 한참 헤맸다.
    tns = TNS_ADMIN or wallet_dir()
    if tns:
        env["TNS_ADMIN"] = tns
    if JAVA_HOME:
        env["JAVA_HOME"] = JAVA_HOME
        env["PATH"] = os.path.join(JAVA_HOME, "bin") + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    return env


def _run_sqlcl(script):
    try:
        return subprocess.run([SQLCL, "-S", "/nolog"], input=script, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=_env())
    except FileNotFoundError:
        raise RuntimeError(
            f"SQLcl 을 찾을 수 없습니다 (시도: {SQLCL}).\n"
            "  · SQLcl 을 설치하고 bin 폴더를 PATH 에 넣거나 환경변수 SQLCL 에 전체 경로를 지정하세요.\n"
            "  · 또는 config.ini [db] 에 user/password 를 채우면 SQLcl 없이 드라이버로 접속합니다.")


def _parse_segment(lines, out_csv):
    rows = []; started = False
    for l in lines:
        if "ORA-" in l or l.strip().startswith("Error"):
            raise RuntimeError(f"[{os.path.basename(out_csv)}] SQL 오류: {l.strip()}")
        if not started:
            if l.lstrip().startswith('"'): started = True
            else: continue
        if l.strip() == "" or "rows selected" in l: continue
        rows.append(l)
    return rows


def _conn_hint(name, what, stderr):
    """SQLcl 이 조용히 실패하면 출력이 비어 '파싱 실패' 로만 보인다. 실제 원인을 짚어 준다."""
    tns = TNS_ADMIN or wallet_dir()
    return (f"[{name}] SQLcl 이 결과를 내지 못했습니다 ({what}).\n"
            f"  거의 대부분 접속이 안 된 경우입니다. 아래를 확인하세요.\n"
            f"  · 지갑(TNS_ADMIN) : {tns or '(없음) ← 지갑 폴더를 못 찾았습니다'}\n"
            f"  · SQLcl          : {SQLCL}\n"
            f"  · 저장된 연결 이름이 맞는지 (기본 changshinincaipoc)\n"
            f"  · 직접 확인:  printf 'connect -name changshinincaipoc\\nselect 1 from dual;\\nexit\\n' | "
            f"TNS_ADMIN=\"{tns}\" \"{SQLCL}\" -S /nolog\n"
            f"  · 또는 config.ini [db] 에 user/password 를 채우면 SQLcl 없이 접속합니다.\n"
            f"  stderr={(stderr or '')[:200]}")


def _sqlcl_batch(items, conn):
    lines = [f"connect -name {conn}", "set sqlformat csv", "set feedback off",
             "set pagesize 0", "set echo off"]
    for i, (path, sql) in enumerate(items):
        lines.append(f"prompt SEGMARK_B_{i}")
        lines.append(sql.rstrip().rstrip(";") + ";")
        lines.append(f"prompt SEGMARK_E_{i}")
    lines.append("exit")
    p = _run_sqlcl("\n".join(lines) + "\n")
    out_lines = p.stdout.splitlines()
    for i, (path, sql) in enumerate(items):
        b, e = f"SEGMARK_B_{i}", f"SEGMARK_E_{i}"
        try:
            si = next(k for k, l in enumerate(out_lines) if b in l)
            ei = next(k for k, l in enumerate(out_lines) if e in l)
        except StopIteration:
            raise RuntimeError(_conn_hint(os.path.basename(path), "세그먼트 마커 없음", p.stderr))
        rows = _parse_segment(out_lines[si + 1:ei], path)
        if not rows:
            raise RuntimeError(_conn_hint(os.path.basename(path), "헤더 없음", p.stderr))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")


# ----------------------------------------------------------------- 바깥 API
def sqlcl_csv(sql, out_csv, conn):
    """단일 쿼리 실행 → CSV 저장. 반환: 데이터 행수. (이름은 호환을 위해 유지)"""
    cfg = load_cfg()
    backend, _ = choose_backend(cfg)
    if backend == "oracledb":
        con = _ora_connect(cfg)
        try:
            cur = con.cursor(); cur.execute(sql.rstrip().rstrip(";"))
            n = _write_rows([d[0] for d in cur.description], cur.fetchall(), out_csv)
            cur.close(); return n
        finally:
            try: con.close()
            except Exception: pass
    script = (f"connect -name {conn}\nset sqlformat csv\nset feedback off\nset pagesize 0\nset echo off\n"
              + sql.rstrip().rstrip(";") + ";\nexit\n")
    p = _run_sqlcl(script)
    rows = _parse_segment(p.stdout.splitlines(), out_csv)
    if not rows:
        raise RuntimeError(f"[{os.path.basename(out_csv)}] 파싱 실패. stderr={p.stderr[:200]}")
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    return len(rows) - 1


# 한 번 끊겼다고 실패로 끝내지 않는다. OCI Autonomous 는 유휴 상태에서 첫 접속이
# 끊기거나 느린 일이 흔하고(resume), 사내망도 순간적으로 튄다. 아래 신호는
# '설정이 틀렸다' 가 아니라 '지금 순간이 안 좋다' 는 뜻이라 다시 시도할 값이 있다.
_TRANSIENT = ("ORA-03113", "ORA-03114", "ORA-12170", "ORA-12537", "ORA-12547",
              "DPY-4011", "DPY-6005", "connection not established", "connection reset",
              "timed out", "timeout", "broken pipe", "eof on communication channel")


def _is_transient(err):
    e = str(err).lower()
    return any(t.lower() in e for t in _TRANSIENT)


def run_batch(items, conn, _tries=3):
    """여러 쿼리를 접속 1회로 실행 → 각 CSV 저장. 경로는 자동 선택.
    일시적인 끊김이면 잠깐 쉬었다 스스로 다시 붙는다(최대 3회)."""
    if not items:
        return
    cfg = load_cfg()
    backend, why = choose_backend(cfg)
    print(f"[db] 접속 경로: {backend} — {why}")
    last = None
    for attempt in range(1, _tries + 1):
        try:
            if backend == "oracledb":
                _ora_batch(items, cfg)
            else:
                _sqlcl_batch(items, conn)
            if attempt > 1:
                print(f"[db] {attempt}번째 시도에서 성공했습니다.")
            return
        except Exception as e:
            last = e
            if attempt >= _tries or not _is_transient(e):
                raise
            wait = 5 * attempt          # 5초 → 10초. DB 가 깨어날 시간을 준다.
            print(f"[db] 연결이 끊겼습니다({str(e)[:120]}). {wait}초 뒤 다시 시도합니다 "
                  f"({attempt}/{_tries - 1}회차)")
            time.sleep(wait)
    raise last


def run_builder(script, *args):
    """core/ 안의 빌더 스크립트를 서브프로세스로 실행(엑셀 생성)."""
    env = dict(os.environ); env.setdefault("PYTHONUTF8", "1"); env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run([sys.executable, os.path.join(CORE_DIR, script), *args], check=True, env=env)
