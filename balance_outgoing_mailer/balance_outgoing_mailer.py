#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Changshin GMES — BALANCE OUTGOING 일일 자동발송 (독립 실행형)
================================================================
밑창(底部)의 미드솔(IP·PH) + 아웃솔(OS) '출고 부족분'을 라이브 DB에서 조회하여
원본 BALANCE OUTGOING 리포트 레이아웃(동(棟)·라인·스타일 / 일자버킷 D+3~D-7 색상강조 / TOTAL)의
Excel(.xlsx)로 만들고, 사내 SMTP로 지정 수신자에게 메일 발송한다.

특징
- Claude / 특정 계정과 무관한 순수 Python. 어느 PC/서버든 OS 스케줄러로 매일 08:00 실행.
- 접속정보·수신자는 config.ini 에서 관리.

[데이터 한계 — 추후 연결 대비]
원본의 COLOR / IP SPRAY(BEM) / PAD PRINTING(BEP) / SCAN DI CKP 컬럼은
현재 보유한 Oracle DB(OCI)에 데이터가 비어 있다. 컬럼 자리는 그대로 두고(빈칸),
나중에 소스가 확보되면 아래 `color_specs()` / `scan_di_ckp()` 한 곳만 채우면 된다.

필요 패키지:  pip install oracledb openpyxl
사용:  python balance_outgoing_mailer.py [--dry-run | --test-db | --config 경로.ini]
"""
import os, sys, ssl, re, smtplib, argparse, configparser, logging, datetime
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))

def load_config(path):
    cp = configparser.ConfigParser()
    if not cp.read(path, encoding="utf-8"):
        sys.exit(f"[설정오류] config 파일을 찾을 수 없습니다: {path}")
    return cp

def setup_log():
    log = logging.getLogger("bo"); log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(); sh.setFormatter(fmt); log.addHandler(sh)
    try:
        fh = logging.FileHandler(os.path.join(HERE, "balance_outgoing.log"), encoding="utf-8")
        fh.setFormatter(fmt); log.addHandler(fh)
    except Exception: pass
    return log
LOG = setup_log()

# 시트(반제품 등급)
SHEETS = [("IP", ["II", "IP"]), ("PH", ["PH", "PP", "CP"]), ("OS", ["OS"])]

# ============================================================== 추후 연결 지점 (현재 DB에 데이터 없음)
def color_specs(plant_cd, style_cd, item_class):
    """원본의 COLOR / IP SPRAY(BEM) / PAD PRINTING(BEP).
    [TODO] 색상 스펙 소스가 확보되면 여기서 조회해 (color, ip_spray, pad_print) 반환.
    현재 OCI DB에는 해당 데이터가 없어 빈 값 반환."""
    return ("", "", "")

def scan_di_ckp(plant_cd, fa_wc_cd, style_cd):
    """원본의 SCAN DI CKP. [TODO] DI 체크포인트 정의/소스 확보 시 연결.
    현재 스캔 데이터에 DI 체크포인트 식별자가 없어 빈 값 반환."""
    return ""
# ==============================================================

def build_buckets(today, before, after):
    out = []
    for k in range(before, -after - 1, -1):
        d = today - datetime.timedelta(days=k)
        label = "DD" if k == 0 else (f"D+{k}" if k > 0 else f"D{k}")
        out.append((label, d.strftime("%Y%m%d"), d.strftime("%m/%d"), k))
    return out

def dong(wc_group_cd):
    """WC_GROUP_CD(A1, C1, F1, JJ2 …) → 동(棟) 글자 (앞 알파벳)."""
    m = re.match(r"[A-Za-z]+", (wc_group_cd or "").strip())
    return m.group(0) if m else (wc_group_cd or "").strip()

def db_connect(cfg):
    import oracledb
    kw = {"user": cfg.get("db","user"), "password": cfg.get("db","password"), "dsn": cfg.get("db","dsn")}
    wdir = cfg.get("db","wallet_dir", fallback="").strip()
    wpw  = cfg.get("db","wallet_password", fallback="").strip()
    if wdir:
        kw["config_dir"]=wdir; kw["wallet_location"]=wdir
        if wpw: kw["wallet_password"]=wpw
    LOG.info(f"DB 접속: dsn={kw['dsn']} wallet={'Y' if wdir else 'N'}")
    return oracledb.connect(**kw)

def fetch_sheet(conn, families, plants, d_from, d_to):
    fam = ",".join(f":f{i}" for i in range(len(families)))
    pl  = ",".join(f":p{i}" for i in range(len(plants)))
    sql = f"""
      SELECT NVL(w.wc_group_cd,' ') wcg, r.plant_cd, r.item_class, r.fa_wc_cd,
             NVL(i.model_name,' ') model, NVL(i.gender,' ') gen, r.style_cd,
             r.fa_date, SUM(r.pcard_qty) qty
      FROM   OCI.MSPD_PCARD_RESULT r
      LEFT JOIN OCI.MSBS_ITEM_STYLE  i ON i.style_cd = r.style_cd
      LEFT JOIN OCI.MSBS_WORK_CENTER w ON w.plant_cd = r.plant_cd AND w.wc_cd = r.fa_wc_cd
      WHERE r.prod_move_type='PROD' AND r.end_routing_yn='Y' AND r.out_date='19991231'
        AND r.item_class_type IN ({fam}) AND r.plant_cd IN ({pl})
        AND r.fa_date BETWEEN :d_from AND :d_to
        AND NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g
                         WHERE g.prod_group_no=r.prod_group_no AND g.plant_cd=r.plant_cd AND g.closing_yn='Y')
      GROUP BY w.wc_group_cd, r.plant_cd, r.item_class, r.fa_wc_cd, i.model_name, i.gender, r.style_cd, r.fa_date
    """
    b = {f"f{i}":v for i,v in enumerate(families)}; b.update({f"p{i}":v for i,v in enumerate(plants)})
    b.update({"d_from":d_from, "d_to":d_to})
    cur = conn.cursor(); cur.execute(sql, b); rows = cur.fetchall(); cur.close()
    return rows

def fetch_scan_bembep(conn, plants, d_from, d_to):
    """SCAN BEM/BEP = 기간 내 BEM·BEP 공정 스캔 수량 합 (line+style 기준)."""
    pl = ",".join(f":p{i}" for i in range(len(plants)))
    sql = f"""
      SELECT plant_cd, fa_wc_cd, style_cd, SUM(prod_qty) q
      FROM OCI.POP_PCARD_SCAN
      WHERE op_cd IN ('BEM','BEP') AND NVL(cancel_flag,'N')<>'Y'
        AND plant_cd IN ({pl})
        AND scan_ymd BETWEEN :d_from AND :d_to
      GROUP BY plant_cd, fa_wc_cd, style_cd
    """
    b = {f"p{i}":v for i,v in enumerate(plants)}; b.update({"d_from":d_from,"d_to":d_to})
    cur = conn.cursor(); cur.execute(sql, b)
    d = {(p, w, s): (q or 0) for p, w, s, q in cur.fetchall()}
    cur.close(); return d

def pivot(rows, buckets, scan_map):
    bdates = [b[1] for b in buckets]
    table = {}
    for wcg, plant, ic, line, model, gen, style, fa, qty in rows:
        dng = dong(wcg) or plant                                 # 동 없으면(예: 3120) plant로 대체
        key = (dng, plant, ic, line, (model or " ").strip(), (gen or " ").strip(), style)
        table.setdefault(key, {})[fa] = table.setdefault(key, {}).get(fa, 0) + (qty or 0)
    out = []
    for key, dd in table.items():
        cells = [dd.get(bd, 0) for bd in bdates]; total = sum(cells)
        if total <= 0: continue
        dng, plant, ic, line, model, gen, style = key
        color, spray, pad = color_specs(plant, style, ic)       # 추후 연결(현재 빈칸)
        sbem = scan_map.get((plant, line, style), 0)
        sdi  = scan_di_ckp(plant, line, style)                   # 추후 연결(현재 빈칸)
        out.append({"dong":dng,"ic":ic,"line":line,"model":model,"style":style,
                    "color":color,"spray":spray,"pad":pad,"gen":gen,
                    "cells":cells,"total":total,"issue":"","scan_bem":sbem,"scan_di":sdi})
    out.sort(key=lambda r:(r["dong"], r["line"], r["style"]))   # 동→라인→스타일 (원본 정렬)
    return out

# ---------- Excel (원본 레이아웃 풀 리플리카) ----------
ID_COLS = ["PLANT","ITEM CLASS","LINE","MODEL","STYLE","COLOR","IP SPRAY (BEM)","PAD PRINTING (BEP)","GEN"]
TAIL_COLS = ["TOTAL","ISSUE","SCAN BEM/BEP","SCAN DI CKP"]

def build_workbook(data_by_sheet, buckets, today_str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    thin = Side(style="thin", color="C7CED6"); bd = Border(thin,thin,thin,thin)
    HFILL = PatternFill("solid", fgColor="1F3A5F"); HF = Font(bold=True, color="FFFFFF", size=9)
    SUB   = PatternFill("solid", fgColor="E8EEF5")
    TOTF  = PatternFill("solid", fgColor="FBEEDD")
    RED   = PatternFill("solid", fgColor="F4B6AE")   # D+ 납기경과
    AMB   = PatternFill("solid", fgColor="FCE3B4")   # DD
    GRN   = PatternFill("solid", fgColor="CDEBD6")   # D- 선행
    cen = Alignment(horizontal="center", vertical="center", wrap_text=True)
    lft = Alignment(horizontal="left", vertical="center")
    first = True
    for sheet_name, _fam in SHEETS:
        rows = data_by_sheet.get(sheet_name, [])
        ws = wb.active if first else wb.create_sheet(); first = False
        ws.title = sheet_name + "".join(today_str.split("-")[1:3])
        nbuck = len(buckets); ncol = len(ID_COLS) + nbuck + len(TAIL_COLS)
        # 제목
        ws.cell(1,1, f"BALANCE OUTGOING MARKET — {sheet_name}").font = Font(bold=True,size=13,color="1F3A5F")
        ws.cell(1, ncol, today_str).alignment = Alignment(horizontal="right")
        # 헤더 2줄 (r3 라벨, r4 이름/날짜)
        r1, r2 = 3, 4
        for c,name in enumerate(ID_COLS, start=1): ws.cell(r2,c,name)
        for j,(label,_d,datehdr,_k) in enumerate(buckets):
            c = len(ID_COLS)+1+j; ws.cell(r1,c,label); ws.cell(r2,c,datehdr)
        for j,name in enumerate(TAIL_COLS):
            c = len(ID_COLS)+nbuck+1+j; ws.cell(r2,c,name)
        for c in range(1, ncol+1):
            for rr in (r1,r2):
                cc = ws.cell(rr,c); cc.fill=HFILL; cc.font=HF; cc.border=bd; cc.alignment=cen
        # 데이터
        rr = r2+1; grand=[0]*nbuck; gtot=0; merge_runs=[]; run_start=rr; run_dong=None
        for row in rows:
            vals = [row["dong"],row["ic"],row["line"],row["model"],row["style"],
                    row["color"],row["spray"],row["pad"],row["gen"]] + row["cells"] + \
                   [row["total"],row["issue"],row["scan_bem"],row["scan_di"]]
            for c,v in enumerate(vals, start=1):
                cell = ws.cell(rr,c, (v if v not in (0,"") else None)); cell.border=bd
                if c <= len(ID_COLS): cell.alignment = cen if c==1 else lft; cell.font=Font(size=9)
                else: cell.alignment = Alignment(horizontal="center"); cell.font=Font(size=9)
            # 일자버킷 색상강조
            for j,(_l,_d,_h,k) in enumerate(buckets):
                c = len(ID_COLS)+1+j; cell = ws.cell(rr,c)
                if cell.value:
                    cell.fill = RED if k>=1 else (AMB if k==0 else GRN)
            ws.cell(rr, len(ID_COLS)+nbuck+1).fill = TOTF
            ws.cell(rr, len(ID_COLS)+nbuck+1).font = Font(bold=True, size=9)
            for j in range(nbuck): grand[j]+=row["cells"][j]
            gtot += row["total"]
            # 동 merge run 추적
            if row["dong"] != run_dong:
                if run_dong is not None and rr-1 >= run_start: merge_runs.append((run_start, rr-1))
                run_dong = row["dong"]; run_start = rr
            rr += 1
        if run_dong is not None and rr-1 >= run_start: merge_runs.append((run_start, rr-1))
        # 동(PLANT) 세로 병합
        for s,e in merge_runs:
            if e>s:
                ws.merge_cells(start_row=s,start_column=1,end_row=e,end_column=1)
                ws.cell(s,1).alignment = Alignment(horizontal="center", vertical="center")
        # GRAND TOTAL
        ws.cell(rr,1,"GRAND TOTAL").font=Font(bold=True,size=9)
        for j,g in enumerate(grand):
            cc=ws.cell(rr,len(ID_COLS)+1+j, g or None); cc.font=Font(bold=True,size=9); cc.fill=SUB; cc.alignment=Alignment(horizontal="center")
        gc=ws.cell(rr,len(ID_COLS)+nbuck+1, gtot); gc.font=Font(bold=True,size=9); gc.fill=TOTF; gc.alignment=Alignment(horizontal="center")
        # 너비
        widths=[7,10,8,22,13,13,14,16,6]+[6]*nbuck+[9,16,12,12]
        for c,w in enumerate(widths, start=1): ws.column_dimensions[get_column_letter(c)].width=w
        ws.freeze_panes = ws.cell(r2+1, len(ID_COLS)+1)
    return wb

def send_mail(cfg, xlsx_path, summary, today_str):
    host=cfg.get("smtp","host"); port=cfg.getint("smtp","port",fallback=587)
    user=cfg.get("smtp","user",fallback="").strip(); pw=cfg.get("smtp","password",fallback="").strip()
    use_tls=cfg.getboolean("smtp","use_tls",fallback=True); sender=cfg.get("smtp","from")
    recips=[x.strip() for x in cfg.get("report","recipients").split(",") if x.strip()]
    if not recips: sys.exit("[설정오류] report.recipients 비어 있음")
    msg=EmailMessage()
    msg["Subject"]=f"[BALANCE OUTGOING] {today_str} 밑창 출고 부족분 (미드솔·아웃솔)"
    msg["From"]=sender; msg["To"]=", ".join(recips)
    msg.set_content("안녕하십니까.\n\n"
        f"{today_str} 기준 밑창 출고 부족분(BALANCE OUTGOING)을 첨부드립니다. (라이브 DB 자동생성)\n\n"
        f"{summary}\n"
        "· 시트: IP(미드솔 IP사출) / PH(미드솔 파일론) / OS(아웃솔)\n"
        "· COLOR / IP SPRAY / PAD PRINTING / SCAN DI CKP 컬럼은 현재 DB에 데이터가 없어 빈칸입니다.\n\n"
        "본 메일은 자동 발송되었습니다.\n")
    with open(xlsx_path,"rb") as f:
        msg.add_attachment(f.read(), maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=os.path.basename(xlsx_path))
    LOG.info(f"메일 발송: {host}:{port} → {recips}")
    if use_tls:
        with smtplib.SMTP(host,port,timeout=60) as s:
            s.starttls(context=ssl.create_default_context())
            if user: s.login(user,pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=60) as s:
            if user: s.login(user,pw)
            s.send_message(msg)
    LOG.info("메일 발송 완료")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE,"config.ini"))
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--test-db", action="store_true")
    args=ap.parse_args(); cfg=load_config(args.config)
    today=datetime.date.today(); today_str=today.strftime("%Y-%m-%d")
    before=cfg.getint("report","window_before",fallback=3); after=cfg.getint("report","window_after",fallback=7)
    plants=[x.strip() for x in cfg.get("report","plants").split(",") if x.strip()]
    buckets=build_buckets(today,before,after)
    d_from=(today-datetime.timedelta(days=before)).strftime("%Y%m%d")
    d_to=(today+datetime.timedelta(days=after)).strftime("%Y%m%d")
    LOG.info(f"=== 시작 (기준일 {today_str}, 창 {d_from}~{d_to}, plants={plants}) ===")
    try: conn=db_connect(cfg)
    except Exception as e: LOG.error(f"DB 접속 실패: {e}"); sys.exit(2)
    if args.test_db:
        cur=conn.cursor(); cur.execute("SELECT 1 FROM DUAL"); print("DB OK:",cur.fetchone()); conn.close(); return
    data={}; summ=[]
    try:
        scan_map=fetch_scan_bembep(conn, plants, d_from, d_to)
        for name,fams in SHEETS:
            pv=pivot(fetch_sheet(conn,fams,plants,d_from,d_to), buckets, scan_map)
            data[name]=pv; tot=sum(r["total"] for r in pv)
            summ.append(f"· {name}: {len(pv)}개 스타일 / 잔량 {tot:,}족"); LOG.info(f"{name}: {len(pv)}행, 잔량 {tot:,}")
    finally: conn.close()
    summary="\n".join(summ)
    wb=build_workbook(data, buckets, today_str)
    out_path=os.path.join(HERE, f"BALANCE_OUTGOING_{today.strftime('%Y%m%d')}.xlsx")
    wb.save(out_path); LOG.info(f"Excel 생성: {out_path}"); print(summary)
    if args.dry_run: LOG.info("--dry-run: 발송 생략"); return
    try: send_mail(cfg, out_path, summary, today_str)
    except Exception as e: LOG.error(f"메일 발송 실패: {e}"); sys.exit(3)
    LOG.info("=== 완료 ===")

if __name__=="__main__": main()
