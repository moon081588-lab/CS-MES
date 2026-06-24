#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Changshin GMES — BALANCE OUTGOING 일일 자동발송 (독립 실행형)
================================================================
밑창 미드솔(IP·PH)+아웃솔(OS) '출고 부족분'을 라이브 DB에서 조회하여
원본 'BALANCE OUTGOING MARKET' 엑셀 양식 **그대로**(컬럼 A~I / 일자열 J~T 작업일 / 공백 U~W /
X=TOTAL · Y=ISSUE · Z=SCAN BEM/BEP · AA=SCAN DI CKP, 동(棟) 세로병합, GRAND TOTAL) 생성하여
사내 SMTP로 발송한다. Claude/계정 무관 순수 Python. OS 스케줄러로 매일 08:00 실행.

[데이터 한계] COLOR / IP SPRAY(BEM) / PAD PRINTING(BEP) / SCAN DI CKP 는 현재 Oracle DB(OCI)에
데이터가 없어 빈칸으로 출력된다. 소스 확보 시 color_specs()/scan_di_ckp() 한 곳만 채우면 자동 반영.

필요 패키지:  pip install oracledb openpyxl
사용:  python balance_outgoing_mailer.py [--dry-run | --test-db | --config 경로.ini]
"""
import os, sys, ssl, re, smtplib, argparse, configparser, logging, datetime
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))

def load_config(path):
    cp = configparser.ConfigParser()
    if not cp.read(path, encoding="utf-8"): sys.exit(f"[설정오류] config 없음: {path}")
    return cp

def setup_log():
    log=logging.getLogger("bo"); log.setLevel(logging.INFO)
    fmt=logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh=logging.StreamHandler(); sh.setFormatter(fmt); log.addHandler(sh)
    try:
        fh=logging.FileHandler(os.path.join(HERE,"balance_outgoing.log"),encoding="utf-8"); fh.setFormatter(fmt); log.addHandler(fh)
    except Exception: pass
    return log
LOG=setup_log()

SHEETS=[("IP",["II","IP"]),("PH",["PH","PP","CP"]),("OS",["OS"])]

# ============================================ 추후 연결 지점 (현재 DB에 데이터 없음 → 빈칸)
def color_specs(plant_cd, style_cd, item_class):
    """COLOR / IP SPRAY(BEM) / PAD PRINTING(BEP). [TODO] 색상 스펙 소스 확보 시 연결."""
    return ("", "", "")
def scan_di_ckp(plant_cd, fa_wc_cd, style_cd):
    """SCAN DI CKP. [TODO] DI 체크포인트 소스 확보 시 연결."""
    return ""
# ============================================

def build_buckets(today, before, after):
    """원본과 동일: 작업일(일요일 제외) 기준 D+before … DD … D-after.  반환 (label, yyyymmdd, 일, k)."""
    def walk(n, direction):
        days=[]; d=today
        while len(days)<n:
            d=d+datetime.timedelta(days=direction)
            if d.weekday()!=6: days.append(d)        # 일요일 제외(토요일은 작업일)
        return days
    seq=list(reversed(walk(before,-1)))+[today]+walk(after,+1)
    labels=[f"D+{k}" for k in range(before,0,-1)]+["DD"]+[f"D-{k}" for k in range(1,after+1)]
    ks=list(range(before,0,-1))+[0]+[-k for k in range(1,after+1)]
    return [(labels[i],seq[i].strftime("%Y%m%d"),seq[i].day,ks[i]) for i in range(len(seq))]

def dong(wcg):
    m=re.match(r"[A-Za-z]+",(wcg or "").strip())
    return m.group(0) if m else (wcg or "").strip()

def db_connect(cfg):
    import oracledb
    kw={"user":cfg.get("db","user"),"password":cfg.get("db","password"),"dsn":cfg.get("db","dsn")}
    wdir=cfg.get("db","wallet_dir",fallback="").strip(); wpw=cfg.get("db","wallet_password",fallback="").strip()
    if wdir:
        kw["config_dir"]=wdir; kw["wallet_location"]=wdir
        if wpw: kw["wallet_password"]=wpw
    LOG.info(f"DB 접속: dsn={kw['dsn']} wallet={'Y' if wdir else 'N'}")
    return oracledb.connect(**kw)

def fetch_sheet(conn, families, plants, d_from, d_to):
    fam=",".join(f":f{i}" for i in range(len(families))); pl=",".join(f":p{i}" for i in range(len(plants)))
    sql=f"""
      SELECT NVL(w.wc_group_cd,' ') wcg, r.plant_cd, r.item_class, r.fa_wc_cd,
             NVL(i.model_name,' ') model, NVL(i.gender,' ') gen, r.style_cd, r.fa_date, SUM(r.pcard_qty) qty
      FROM OCI.MSPD_PCARD_RESULT r
      LEFT JOIN OCI.MSBS_ITEM_STYLE  i ON i.style_cd=r.style_cd
      LEFT JOIN OCI.MSBS_WORK_CENTER w ON w.plant_cd=r.plant_cd AND w.wc_cd=r.fa_wc_cd
      WHERE r.prod_move_type='PROD' AND r.end_routing_yn='Y' AND r.out_date='19991231'
        AND r.item_class_type IN ({fam}) AND r.plant_cd IN ({pl})
        AND r.fa_date BETWEEN :d_from AND :d_to
        AND NOT EXISTS (SELECT 1 FROM OCI.MSPD_PROD_GROUP g
                         WHERE g.prod_group_no=r.prod_group_no AND g.plant_cd=r.plant_cd AND g.closing_yn='Y')
      GROUP BY w.wc_group_cd, r.plant_cd, r.item_class, r.fa_wc_cd, i.model_name, i.gender, r.style_cd, r.fa_date
    """
    b={f"f{i}":v for i,v in enumerate(families)}; b.update({f"p{i}":v for i,v in enumerate(plants)})
    b.update({"d_from":d_from,"d_to":d_to})
    cur=conn.cursor(); cur.execute(sql,b); rows=cur.fetchall(); cur.close(); return rows

def fetch_scan_bembep(conn, plants, d_from, d_to):
    pl=",".join(f":p{i}" for i in range(len(plants)))
    sql=f"""SELECT plant_cd, fa_wc_cd, style_cd, SUM(prod_qty) q FROM OCI.POP_PCARD_SCAN
            WHERE op_cd IN ('BEM','BEP') AND NVL(cancel_flag,'N')<>'Y' AND plant_cd IN ({pl})
              AND scan_ymd BETWEEN :d_from AND :d_to
            GROUP BY plant_cd, fa_wc_cd, style_cd"""
    b={f"p{i}":v for i,v in enumerate(plants)}; b.update({"d_from":d_from,"d_to":d_to})
    cur=conn.cursor(); cur.execute(sql,b); d={(p,w,s):(q or 0) for p,w,s,q in cur.fetchall()}; cur.close(); return d

def pivot(rows, buckets, scan_map):
    bdates=[b[1] for b in buckets]; table={}
    for wcg,plant,ic,line,model,gen,style,fa,qty in rows:
        dng=dong(wcg) or plant
        key=(dng,plant,ic,line,(model or " ").strip(),(gen or " ").strip(),style)
        table.setdefault(key,{})[fa]=table.setdefault(key,{}).get(fa,0)+(qty or 0)
    out=[]
    for key,dd in table.items():
        cells=[dd.get(bd,0) for bd in bdates]; total=sum(cells)
        if total<=0: continue
        dng,plant,ic,line,model,gen,style=key
        color,spray,pad=color_specs(plant,style,ic)
        out.append({"dong":dng,"ic":ic,"line":line,"model":model,"style":style,"color":color,
                    "spray":spray,"pad":pad,"gen":gen,"cells":cells,"total":total,"issue":"",
                    "scan_bem":scan_map.get((plant,line,style),0),"scan_di":scan_di_ckp(plant,line,style)})
    out.sort(key=lambda r:(r["dong"],r["line"],r["style"]))
    return out

# ---------- Excel: 원본 'BALANCE OUTGOING MARKET' 양식 그대로 ----------
def build_workbook(data_by_sheet, buckets, today, today_str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb=Workbook()
    thin=Side(style="thin",color="B7BFC9"); BD=Border(thin,thin,thin,thin)
    HFILL=PatternFill("solid",fgColor="1F3A5F"); HF=Font(bold=True,color="FFFFFF",size=9)
    SUB=PatternFill("solid",fgColor="E8EEF5"); TOTF=PatternFill("solid",fgColor="FCE9CF")
    RED=PatternFill("solid",fgColor="F4B6AE"); AMB=PatternFill("solid",fgColor="FCE3B4"); GRN=PatternFill("solid",fgColor="CDEBD6")
    cv=Alignment(horizontal="center",vertical="center"); cen=Alignment(horizontal="center",vertical="center",wrap_text=True)
    lf=Alignment(horizontal="left",vertical="center"); F9=Font(size=9); F9B=Font(size=9,bold=True)
    nb=len(buckets); C_J=10; C_T=9+nb; C_TOT=C_T+3+1; C_ISS=C_TOT+1; C_ZBEM=C_TOT+2; C_ADI=C_TOT+3; NCOL=C_ADI
    months=["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
    month_lbl=f"{months[today.month-1]}'{today.strftime('%y')}"
    first=True
    for sheet_name,_fam in SHEETS:
        rows=data_by_sheet.get(sheet_name,[])
        ws=wb.active if first else wb.create_sheet(); first=False
        ws.title=sheet_name+"".join(today_str.split("-")[1:3])
        # 제목줄 (A1:D2, X1:AA2)
        ws.merge_cells(start_row=1,start_column=1,end_row=2,end_column=4)
        t=ws.cell(1,1,"BALANCE OUTGOING MARKET"); t.font=Font(bold=True,size=12); t.alignment=lf
        ws.merge_cells(start_row=1,start_column=C_TOT,end_row=2,end_column=C_ADI)
        dc=ws.cell(1,C_TOT,today_str); dc.alignment=Alignment(horizontal="right",vertical="center"); dc.font=F9B
        # 식별 헤더 A3:I5
        for c,name in enumerate(["PLANT","ITEM CLASS","LINE","MODEL","STYLE","COLOR","IP SPRAY (BEM)","PAD PRINTING (BEP)","GEN"],start=1):
            ws.merge_cells(start_row=3,start_column=c,end_row=5,end_column=c)
            cc=ws.cell(3,c,name); cc.fill=HFILL; cc.font=HF; cc.alignment=cen; cc.border=BD
        # 월 라벨 J3:T3
        ws.merge_cells(start_row=3,start_column=C_J,end_row=3,end_column=C_T)
        mc=ws.cell(3,C_J,month_lbl); mc.fill=HFILL; mc.font=HF; mc.alignment=cv; mc.border=BD
        # 일자열 (4행=일, 5행=D offset)
        for j,(label,_d,daynum,k) in enumerate(buckets):
            c=C_J+j
            for cc in (ws.cell(4,c,daynum), ws.cell(5,c,label)): cc.fill=HFILL; cc.font=HF; cc.alignment=cv; cc.border=BD
        # 꼬리 헤더 (X/Y/Z/AA)
        for c,name in [(C_TOT,"TOTAL"),(C_ISS,"ISSUE"),(C_ZBEM,"SCAN BEM/BEP"),(C_ADI,"SCAN DI CKP")]:
            ws.merge_cells(start_row=3,start_column=c,end_row=5,end_column=c)
            cc=ws.cell(3,c,name); cc.fill=HFILL; cc.font=HF; cc.alignment=cen; cc.border=BD
        # 데이터
        rr=6; grand=[0]*nb; gtot=0; run_start=rr; run_dong=None; merges=[]
        for row in rows:
            ws.cell(rr,1,row["dong"]); ws.cell(rr,2,row["ic"]); ws.cell(rr,3,row["line"])
            ws.cell(rr,4,row["model"]); ws.cell(rr,5,row["style"])
            ws.cell(rr,6,row["color"] or None); ws.cell(rr,7,row["spray"] or None); ws.cell(rr,8,row["pad"] or None)
            ws.cell(rr,9,row["gen"])
            for j,(_l,_d,_n,k) in enumerate(buckets):
                v=row["cells"][j]; c=C_J+j; cell=ws.cell(rr,c, v if v else None)
                if v: cell.fill = RED if k>=1 else (AMB if k==0 else GRN)
                grand[j]+=v
            ws.cell(rr,C_TOT,row["total"]).fill=TOTF
            ws.cell(rr,C_ISS,row["issue"] or None)
            ws.cell(rr,C_ZBEM,row["scan_bem"] or None); ws.cell(rr,C_ADI,row["scan_di"] or None)
            gtot+=row["total"]
            for c in range(1,NCOL+1):
                cell=ws.cell(rr,c); cell.border=BD; cell.font=(F9B if c==C_TOT else F9)
                cell.alignment = lf if c in (4,5,6,7,8) else cv
            if row["dong"]!=run_dong:
                if run_dong is not None and rr-1>=run_start: merges.append((run_start,rr-1))
                run_dong=row["dong"]; run_start=rr
            rr+=1
        if run_dong is not None and rr-1>=run_start: merges.append((run_start,rr-1))
        for s,e in merges:
            if e>s: ws.merge_cells(start_row=s,start_column=1,end_row=e,end_column=1); ws.cell(s,1).alignment=cv
        # GRAND TOTAL (A:I 병합)
        ws.merge_cells(start_row=rr,start_column=1,end_row=rr,end_column=9)
        gcell=ws.cell(rr,1,"GRAND TOTAL"); gcell.font=F9B; gcell.alignment=cv; gcell.fill=SUB
        for j,g in enumerate(grand):
            cc=ws.cell(rr,C_J+j, g or None); cc.font=F9B; cc.fill=SUB; cc.alignment=cv; cc.border=BD
        gt=ws.cell(rr,C_TOT,gtot); gt.font=F9B; gt.fill=TOTF; gt.alignment=cv
        for c in range(1,NCOL+1): ws.cell(rr,c).border=BD
        # 열 너비 (원본 근사)
        W={1:6.7,2:7,3:7.5,4:38,5:13,6:17,7:17.5,8:19,9:5}
        for c in range(1,NCOL+1):
            L=get_column_letter(c)
            if c in W: ws.column_dimensions[L].width=W[c]
            elif C_J<=c<=C_T: ws.column_dimensions[L].width=8
            elif c in (C_T+1,C_T+2,C_T+3): ws.column_dimensions[L].width=3      # U,V,W 공백
            elif c==C_TOT: ws.column_dimensions[L].width=10
            elif c==C_ISS: ws.column_dimensions[L].width=22
            else: ws.column_dimensions[L].width=12
        ws.freeze_panes=ws.cell(6,C_J)
    return wb

def send_mail(cfg, xlsx_path, summary, today_str):
    host=cfg.get("smtp","host"); port=cfg.getint("smtp","port",fallback=587)
    user=cfg.get("smtp","user",fallback="").strip(); pw=cfg.get("smtp","password",fallback="").strip()
    use_tls=cfg.getboolean("smtp","use_tls",fallback=True); sender=cfg.get("smtp","from")
    recips=[x.strip() for x in cfg.get("report","recipients").split(",") if x.strip()]
    if not recips: sys.exit("[설정오류] recipients 비어 있음")
    msg=EmailMessage(); msg["Subject"]=f"[BALANCE OUTGOING] {today_str} 밑창 출고 부족분 (미드솔·아웃솔)"
    msg["From"]=sender; msg["To"]=", ".join(recips)
    msg.set_content("안녕하십니까.\n\n"
        f"{today_str} 기준 밑창 출고 부족분(BALANCE OUTGOING)을 첨부드립니다. (라이브 DB 자동생성)\n\n{summary}\n"
        "· 시트: IP(미드솔 IP사출) / PH(미드솔 파일론) / OS(아웃솔)\n"
        "· COLOR / IP SPRAY / PAD PRINTING / SCAN DI CKP 는 현재 DB에 데이터가 없어 빈칸입니다.\n\n자동 발송 메일입니다.\n")
    with open(xlsx_path,"rb") as f:
        msg.add_attachment(f.read(),maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",filename=os.path.basename(xlsx_path))
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
    ap=argparse.ArgumentParser(); ap.add_argument("--config",default=os.path.join(HERE,"config.ini"))
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--test-db",action="store_true")
    a=ap.parse_args(); cfg=load_config(a.config)
    today=datetime.date.today(); today_str=today.strftime("%Y-%m-%d")
    before=cfg.getint("report","window_before",fallback=3); after=cfg.getint("report","window_after",fallback=7)
    plants=[x.strip() for x in cfg.get("report","plants").split(",") if x.strip()]
    buckets=build_buckets(today,before,after)
    d_from=min(b[1] for b in buckets); d_to=max(b[1] for b in buckets)
    LOG.info(f"=== 시작 {today_str} 창 {d_from}~{d_to} plants={plants} ===")
    try: conn=db_connect(cfg)
    except Exception as e: LOG.error(f"DB 접속 실패: {e}"); sys.exit(2)
    if a.test_db:
        cur=conn.cursor(); cur.execute("SELECT 1 FROM DUAL"); print("DB OK:",cur.fetchone()); conn.close(); return
    data={}; summ=[]
    try:
        sm=fetch_scan_bembep(conn,plants,d_from,d_to)
        for name,fams in SHEETS:
            pv=pivot(fetch_sheet(conn,fams,plants,d_from,d_to),buckets,sm); data[name]=pv
            tot=sum(r["total"] for r in pv); summ.append(f"· {name}: {len(pv)}개 스타일 / 잔량 {tot:,}족"); LOG.info(f"{name}: {len(pv)}행 잔량 {tot:,}")
    finally: conn.close()
    summary="\n".join(summ)
    wb=build_workbook(data,buckets,today,today_str)
    out=os.path.join(HERE,f"BALANCE_OUTGOING_{today.strftime('%Y%m%d')}.xlsx"); wb.save(out)
    LOG.info(f"Excel 생성: {out}"); print(summary)
    if a.dry_run: LOG.info("--dry-run: 발송 생략"); return
    try: send_mail(cfg,out,summary,today_str)
    except Exception as e: LOG.error(f"메일 발송 실패: {e}"); sys.exit(3)
    LOG.info("=== 완료 ===")

if __name__=="__main__": main()
