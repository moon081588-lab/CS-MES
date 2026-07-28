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
import os, sys, csv, datetime, subprocess, configparser

CORE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../ckp_reports/core
PKG_DIR  = os.path.dirname(CORE_DIR)                           # .../ckp_reports
ROOT_DIR = os.path.dirname(PKG_DIR)                            # 번들 루트

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
    for c in (os.path.join(ROOT_DIR, "wallet"),
              os.path.join(ROOT_DIR, "balance_outgoing_mailer", "wallet"),   # 저장소 배치
              os.path.join(PKG_DIR, "wallet")):
        if os.path.isfile(os.path.join(c, "tnsnames.ora")):
            return os.path.abspath(c)
    return TNS_ADMIN or ""


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
    base = dict(user=user, password=pw, dsn=dsn)
    if wdir:
        base["config_dir"] = wdir

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

    order = {"thick": [_thick], "thin": [_thin]}.get(mode, [_thick, _thin])
    errs = []
    for fn in order:
        try:
            return fn()
        except Exception as e:
            errs.append(f"{fn.__name__.strip('_')}: {str(e)[:200]}")
    raise RuntimeError("DB 접속 실패\n  · " + "\n  · ".join(errs) +
                       f"\n  · 지갑 폴더: {wdir or '(없음)'}")


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


def run_batch(items, conn):
    """여러 쿼리를 접속 1회로 실행 → 각 CSV 저장. 경로는 자동 선택."""
    if not items:
        return
    cfg = load_cfg()
    backend, why = choose_backend(cfg)
    print(f"[db] 접속 경로: {backend} — {why}")
    if backend == "oracledb":
        _ora_batch(items, cfg)
    else:
        _sqlcl_batch(items, conn)


def run_builder(script, *args):
    """core/ 안의 빌더 스크립트를 서브프로세스로 실행(엑셀 생성)."""
    env = dict(os.environ); env.setdefault("PYTHONUTF8", "1"); env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run([sys.executable, os.path.join(CORE_DIR, script), *args], check=True, env=env)
