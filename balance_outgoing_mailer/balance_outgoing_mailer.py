#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Changshin GMES — BALANCE OUTGOING 일일 자동발송 (독립 실행형)
================================================================
밑창(底部)의 미드솔(IP·PH) + 아웃솔(OS) '출고 부족분'을 라이브 DB에서 조회하여
원본 BALANCE OUTGOING 구조(라인×스타일 행 / FA_DATE 일자버킷 D+3~D-7 / TOTAL)의
Excel(.xlsx)로 만들고, 사내 SMTP로 지정 수신자에게 메일 발송한다.

특징
- Claude / 특정 계정과 무관한 순수 Python 스크립트. 어느 PC/서버든 실행 가능.
- OS 스케줄러(cron / launchd / 작업 스케줄러)로 매일 08:00 실행하면 됨.
- 모든 접속정보·수신자는 config.ini 에서 관리 (코드 수정 불필요).

필요 패키지:  pip install oracledb openpyxl
사용법:
    python balance_outgoing_mailer.py                 # 조회 → Excel → 메일 발송
    python balance_outgoing_mailer.py --dry-run       # Excel만 생성(발송 안 함)
    python balance_outgoing_mailer.py --test-db       # DB 접속만 점검
    python balance_outgoing_mailer.py --config 다른경로.ini
"""
import os, sys, ssl, smtplib, argparse, configparser, logging, datetime
from email.message import EmailMessage

# ----------------------------------------------------------------------------- config / logging
HERE = os.path.dirname(os.path.abspath(__file__))

def load_config(path):
    cp = configparser.ConfigParser()
    if not cp.read(path, encoding="utf-8"):
        sys.exit(f"[설정오류] config 파일을 찾을 수 없습니다: {path}")
    return cp

def setup_log():
    log = logging.getLogger("bo")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(); sh.setFormatter(fmt); log.addHandler(sh)
    try:
        fh = logging.FileHandler(os.path.join(HERE, "balance_outgoing.log"), encoding="utf-8")
        fh.setFormatter(fmt); log.addHandler(fh)
    except Exception:
        pass
    return log

LOG = setup_log()

# ----------------------------------------------------------------------------- 시트 정의 (반제품 등급 → 시트)
SHEETS = [
    ("IP", ["II", "IP"]),            # IP 사출 계열 미드솔
    ("PH", ["PH", "PP", "CP"]),      # 파일론 계열 미드솔
    ("OS", ["OS"]),                  # 아웃솔
]

# ----------------------------------------------------------------------------- 일자 버킷 (D+3 ~ D-7)
def build_buckets(today, before, after):
    """offset k: D+k = today-k(납기경과), DD=today, D-k = today+k(선행).
    반환: [(label, yyyymmdd, datehdr)] 좌→우 = D+before ... DD ... D-after"""
    out = []
    for k in range(before, -after - 1, -1):           # before, ..., 1, 0, -1, ..., -after
        d = today - datetime.timedelta(days=k)
        label = "DD" if k == 0 else (f"D+{k}" if k > 0 else f"D{k}")
        out.append((label, d.strftime("%Y%m%d"), d.strftime("%m/%d")))
    return out

# ----------------------------------------------------------------------------- DB
def db_connect(cfg):
    import oracledb
    user = cfg.get("db", "user")
    pw   = cfg.get("db", "password")
    dsn  = cfg.get("db", "dsn")
    wdir = cfg.get("db", "wallet_dir", fallback="").strip()
    wpw  = cfg.get("db", "wallet_password", fallback="").strip()
    kw = {"user": user, "password": pw, "dsn": dsn}
    if wdir:                                   # OCI Autonomous DB (wallet, thin mode)
        kw["config_dir"] = wdir
        kw["wallet_location"] = wdir
        if wpw:
            kw["wallet_password"] = wpw
    LOG.info(f"DB 접속 시도: dsn={dsn} wallet={'Y' if wdir else 'N'}")
    return oracledb.connect(**kw)

def fetch_sheet(conn, families, plants, d_from, d_to):
    """한 시트(반제품 계열)의 부족분을 (plant,item_class,line,model,style,fa_date,qty) 행으로 반환"""
    fam_ph = ",".join(f":f{i}" for i in range(len(families)))
    pl_ph  = ",".join(f":p{i}" for i in range(len(plants)))
    sql = f"""
        SELECT r.plant_cd, r.item_class, r.fa_wc_cd, NVL(i.model_name,' ') model, r.style_cd,
               r.fa_date, SUM(r.pcard_qty) qty
        FROM   OCI.MSPD_PCARD_RESULT r
        LEFT JOIN OCI.MSBS_ITEM_STYLE i ON i.style_cd = r.style_cd
        WHERE  r.prod_move_type = 'PROD'
          AND  r.end_routing_yn = 'Y'
          AND  r.out_date       = '19991231'           -- 미출고(부족분) 판정
          AND  r.item_class_type IN ({fam_ph})
          AND  r.plant_cd        IN ({pl_ph})
          AND  r.fa_date BETWEEN :d_from AND :d_to
          AND  NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g
                            WHERE g.prod_group_no = r.prod_group_no
                              AND g.plant_cd      = r.plant_cd
                              AND g.closing_yn    = 'Y')   -- 명시적 마감 그룹만 제외
        GROUP BY r.plant_cd, r.item_class, r.fa_wc_cd, i.model_name, r.style_cd, r.fa_date
    """
    binds = {f"f{i}": v for i, v in enumerate(families)}
    binds.update({f"p{i}": v for i, v in enumerate(plants)})
    binds.update({"d_from": d_from, "d_to": d_to})
    cur = conn.cursor()
    cur.execute(sql, binds)
    rows = cur.fetchall()
    cur.close()
    return rows

# ----------------------------------------------------------------------------- 피벗
def pivot(rows, buckets):
    """rows → {(plant,ic,line,model,style): {yyyymmdd: qty}} + 합계"""
    bucket_dates = [b[1] for b in buckets]
    table = {}
    for plant, ic, line, model, style, fa, qty in rows:
        key = (plant, ic, line, (model or " ").strip(), style)
        d = table.setdefault(key, {})
        d[fa] = d.get(fa, 0) + (qty or 0)
    out = []
    for key, dd in table.items():
        cells = [dd.get(bd, 0) for bd in bucket_dates]   # 윈도우 내 일자별
        total = sum(cells)
        if total > 0:
            out.append((key, cells, total))
    out.sort(key=lambda x: x[2], reverse=True)            # 잔량 큰 순
    return out

# ----------------------------------------------------------------------------- Excel
def build_workbook(data_by_sheet, buckets, today_str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    thin = Side(style="thin", color="C7CED6")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor="1F3A5F")
    sub_fill = PatternFill("solid", fgColor="E8EEF5")
    tot_fill = PatternFill("solid", fgColor="FBEEDD")
    hdr_font = Font(bold=True, color="FFFFFF")
    idcols = ["PLANT", "ITEM CLASS", "LINE", "MODEL", "STYLE"]
    first = True
    for sheet_name, _families in SHEETS:
        rows = data_by_sheet.get(sheet_name, [])
        ws = wb.active if first else wb.create_sheet()
        _mmdd = "".join(today_str.split("-")[1:3])                  # "2026-06-24" → "0624"
        ws.title = sheet_name + _mmdd                                # 예: IP0624
        first = False
        # 제목
        ws.cell(1, 1, f"BALANCE OUTGOING — {sheet_name}  (출고 부족분, 기준일 {today_str})")
        ws.cell(1, 1).font = Font(bold=True, size=13, color="1F3A5F")
        # 헤더 2줄
        ncol = len(idcols) + len(buckets) + 1
        r1, r2 = 3, 4
        for c, name in enumerate(idcols, start=1):
            ws.cell(r2, c, name)
        for j, (label, _d, datehdr) in enumerate(buckets):
            c = len(idcols) + 1 + j
            ws.cell(r1, c, label); ws.cell(r2, c, datehdr)
        tcol = len(idcols) + 1 + len(buckets)
        ws.cell(r1, tcol, "TOTAL"); ws.cell(r2, tcol, "잔량")
        for c in range(1, ncol + 1):
            for rr in (r1, r2):
                cell = ws.cell(rr, c)
                cell.fill = hdr_fill if rr == r2 or c >= len(idcols)+1 else sub_fill
                cell.font = hdr_font if (rr == r2 or c >= len(idcols)+1) else Font(bold=True)
                cell.border = border
                cell.alignment = Alignment(horizontal="center", vertical="center")
        # 데이터
        rr = r2 + 1
        grand = [0]*len(buckets); gtot = 0
        for (plant, ic, line, model, style), cells, total in rows:
            vals = [plant, ic, line, model, style] + cells + [total]
            for c, v in enumerate(vals, start=1):
                cell = ws.cell(rr, c, v if v != 0 else None)
                cell.border = border
                if c > len(idcols):
                    cell.alignment = Alignment(horizontal="center")
                if c == tcol:
                    cell.fill = tot_fill; cell.font = Font(bold=True)
            for j in range(len(buckets)):
                grand[j] += cells[j]
            gtot += total
            rr += 1
        # GRAND TOTAL
        ws.cell(rr, 1, "GRAND TOTAL").font = Font(bold=True)
        for j, g in enumerate(grand):
            cell = ws.cell(rr, len(idcols)+1+j, g if g else None); cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center"); cell.fill = sub_fill
        gc = ws.cell(rr, tcol, gtot); gc.font = Font(bold=True); gc.fill = tot_fill
        gc.alignment = Alignment(horizontal="center")
        # 열 너비
        widths = [8, 11, 9, 26, 14] + [7]*len(buckets) + [10]
        for c, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.freeze_panes = ws.cell(r2+1, len(idcols)+1)
    return wb

# ----------------------------------------------------------------------------- 메일
def send_mail(cfg, xlsx_path, summary, today_str):
    host = cfg.get("smtp", "host"); port = cfg.getint("smtp", "port", fallback=587)
    user = cfg.get("smtp", "user", fallback="").strip()
    pw   = cfg.get("smtp", "password", fallback="").strip()
    use_tls = cfg.getboolean("smtp", "use_tls", fallback=True)
    sender  = cfg.get("smtp", "from")
    recips  = [x.strip() for x in cfg.get("report", "recipients").split(",") if x.strip()]
    if not recips:
        sys.exit("[설정오류] report.recipients 가 비어 있습니다.")
    msg = EmailMessage()
    msg["Subject"] = f"[BALANCE OUTGOING] {today_str} 밑창 출고 부족분 (미드솔·아웃솔)"
    msg["From"] = sender
    msg["To"] = ", ".join(recips)
    msg.set_content(
        "안녕하십니까.\n\n"
        f"{today_str} 기준 밑창 출고 부족분(BALANCE OUTGOING)을 첨부드립니다.\n"
        "라이브 DB에서 자동 생성된 자료입니다.\n\n"
        f"{summary}\n"
        "· 시트: IP(미드솔 IP사출) / PH(미드솔 파일론) / OS(아웃솔)\n"
        "· 각 칸 = 미출고 수량(PCARD_QTY), 열 = 납기일(FA_DATE) D+3~D-7, TOTAL = 행 잔량\n\n"
        "본 메일은 자동 발송되었습니다.\n"
    )
    with open(xlsx_path, "rb") as f:
        msg.add_attachment(f.read(),
                           maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=os.path.basename(xlsx_path))
    LOG.info(f"메일 발송: {host}:{port} → {recips}")
    if use_tls:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            if user: s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            if user: s.login(user, pw)
            s.send_message(msg)
    LOG.info("메일 발송 완료")

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    ap.add_argument("--dry-run", action="store_true", help="Excel만 생성, 발송 안 함")
    ap.add_argument("--test-db", action="store_true", help="DB 접속만 점검")
    args = ap.parse_args()
    cfg = load_config(args.config)

    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    before = cfg.getint("report", "window_before", fallback=3)
    after  = cfg.getint("report", "window_after",  fallback=7)
    plants = [x.strip() for x in cfg.get("report", "plants").split(",") if x.strip()]
    buckets = build_buckets(today, before, after)
    d_from = (today - datetime.timedelta(days=before)).strftime("%Y%m%d")
    d_to   = (today + datetime.timedelta(days=after)).strftime("%Y%m%d")

    LOG.info(f"=== BALANCE OUTGOING 자동발송 시작 (기준일 {today_str}, 창 {d_from}~{d_to}, plants={plants}) ===")
    try:
        conn = db_connect(cfg)
    except Exception as e:
        LOG.error(f"DB 접속 실패: {e}"); sys.exit(2)

    if args.test_db:
        cur = conn.cursor(); cur.execute("SELECT 1 FROM DUAL"); print("DB OK:", cur.fetchone()); conn.close(); return

    data_by_sheet = {}; summary_lines = []
    try:
        for sheet_name, families in SHEETS:
            rows = fetch_sheet(conn, families, plants, d_from, d_to)
            pv = pivot(rows, buckets)
            data_by_sheet[sheet_name] = pv
            tot = sum(t for _, _, t in pv)
            summary_lines.append(f"· {sheet_name}: {len(pv)}개 스타일 / 잔량 {tot:,}족")
            LOG.info(f"{sheet_name} 시트: {len(pv)}행, 잔량 {tot:,}")
    finally:
        conn.close()

    summary = "\n".join(summary_lines)
    wb = build_workbook(data_by_sheet, buckets, today_str)
    out_name = f"BALANCE_OUTGOING_{today.strftime('%Y%m%d')}.xlsx"
    out_path = os.path.join(HERE, out_name)
    wb.save(out_path)
    LOG.info(f"Excel 생성: {out_path}")
    print(summary)

    if args.dry_run:
        LOG.info("--dry-run: 메일 발송 생략"); return
    try:
        send_mail(cfg, out_path, summary, today_str)
    except Exception as e:
        LOG.error(f"메일 발송 실패: {e}"); sys.exit(3)
    LOG.info("=== 완료 ===")

if __name__ == "__main__":
    main()
