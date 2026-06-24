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
import os, sys, ssl, re, smtplib, argparse, configparser, logging, datetime, getpass
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))

def load_config(path):
    cp = configparser.ConfigParser()
    if not cp.read(path, encoding="utf-8"): sys.exit(f"[설정오류] config 없음: {path}")
    return cp

def save_password(path, section, value):
    """config.ini의 [section] password 에 값을 저장하고 파일권한 600."""
    cp=configparser.ConfigParser(); cp.read(path,encoding="utf-8")
    if section not in cp: cp[section]={}
    cp[section]["password"]=value
    with open(path,"w",encoding="utf-8") as f: cp.write(f)
    try: os.chmod(path,0o600)
    except Exception: pass

def ensure_password(cfg, path, section, label):
    """비밀번호가 config에 있으면 그대로, 없으면 1회 숨김 입력받아 저장 후 반환."""
    v=cfg.get(section,"password",fallback="").strip()
    if v: return v
    if not sys.stdin.isatty():
        sys.exit(f"[설정] [{section}] password 가 비어 있습니다. 먼저 대화형으로 1회 실행해 저장하세요"
                 f" (예: python3 {os.path.basename(__file__)} --setup).")
    v=getpass.getpass(f"Enter {label} (saved once, hidden): ").strip()
    if not v: sys.exit("[설정] 비밀번호가 비어 있어 중단합니다.")
    if section not in cfg: cfg[section]={}
    cfg[section]["password"]=v
    save_password(path, section, v)
    LOG.info(f"[{section}] 비밀번호를 {path} 에 저장했습니다 (다음부터 묻지 않음).")
    return v

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

# ---------- Excel: 원본을 '스타일 템플릿'으로 사용해 100% 동일 양식 복제 ----------
# 원본(2.3 BALANCE OUTGOING)의 IP0306 시트를 report_template.xlsx(스타일 도너)로 보관하고,
# 각 셀의 폰트·채움·테두리·정렬·표시형식을 그대로 복사한다. 날짜의존 값(날짜/월/일/D오프셋)과
# 본문 데이터만 새로 써넣는다. 색상범례는 원본 이미지를 그대로 잘라낸 legend.png 를 삽입한다.
import os
from copy import copy as _copy
_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_XLSX = os.path.join(_HERE, "report_template.xlsx")
LEGEND_PNG    = os.path.join(_HERE, "legend.png")

# 템플릿 기준 행: 헤더 1~5, 대표 데이터행 6, 마지막 데이터행 70, GRAND TOTAL 71
T_HDR=range(1,6); T_DATA=6; T_LASTDATA=70; T_GTOT=71; T_NCOL=27

def _copy_style(src, dst):
    if src.has_style:
        dst.font=_copy(src.font); dst.fill=_copy(src.fill)
        dst.border=_copy(src.border); dst.alignment=_copy(src.alignment)
        dst.number_format=src.number_format; dst.protection=_copy(src.protection)

def build_workbook(data_by_sheet, buckets, today, today_str):
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter
    NOFILL=PatternFill(fill_type=None)   # 데이터행은 흰색(원본의 수작업 강조색 제거)
    if not os.path.exists(TEMPLATE_XLSX):
        raise FileNotFoundError(f"양식 템플릿이 없습니다: {TEMPLATE_XLSX} (legend.png 와 함께 스크립트 폴더에 두세요)")
    tplwb=openpyxl.load_workbook(TEMPLATE_XLSX)
    tpl=tplwb[tplwb.sheetnames[0]]
    nb=len(buckets); C_J=10; C_T=9+nb; GAP=(C_T+1,C_T+2,C_T+3)
    C_TOT=C_T+4; C_ISS=C_TOT+1; C_ZBEM=C_TOT+2; C_ADI=C_TOT+3; NCOL=C_ADI
    # 월 라벨(원본 형식: 'MARCH'26')
    MONTHS=["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST",
            "SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]
    month_lbl=f"{MONTHS[today.month-1]}'{today.strftime('%y')}"

    def hdr_merges():
        # 헤더(1~5행) 병합을 템플릿에서 그대로 가져옴
        return [str(m) for m in tpl.merged_cells.ranges if m.min_row<=5]

    wb=Workbook(); first=True
    for sheet_name,_fam in SHEETS:
        rows=data_by_sheet.get(sheet_name,[])
        ws=wb.active if first else wb.create_sheet(); first=False
        ws.title=sheet_name+"".join(today_str.split("-")[1:3])
        # 열너비/숨김 복사
        for c in range(1,NCOL+1):
            cl=get_column_letter(c)
            if cl in tpl.column_dimensions:
                ws.column_dimensions[cl].width=tpl.column_dimensions[cl].width
        # 행높이(헤더) 복사
        for r in T_HDR:
            if r in tpl.row_dimensions: ws.row_dimensions[r].height=tpl.row_dimensions[r].height

        # ---- 헤더 1~5행: 스타일+값 그대로 복사 ----
        for r in T_HDR:
            for c in range(1,NCOL+1):
                s=tpl.cell(r,c); d=ws.cell(r,c)
                _copy_style(s,d)
                if s.value is not None: d.value=s.value
        # 병합 복사
        for mr in hdr_merges():
            try: ws.merge_cells(mr)
            except Exception: pass
        # 날짜 의존 값 덮어쓰기 (스타일은 유지)
        ws.cell(1,C_TOT).value=today                 # X1: 날짜(표시형식은 템플릿=인니 long date)
        ws.cell(3,C_J).value=month_lbl               # J3: 월 라벨
        for j,(label,_d,daynum,k) in enumerate(buckets):
            ws.cell(4,C_J+j).value=daynum            # 4행: 일
            ws.cell(5,C_J+j).value=label             # 5행: D오프셋(색은 템플릿 그대로)

        # ---- 색상 범례 이미지 ----
        try:
            from openpyxl.drawing.image import Image as XLImage
            if os.path.exists(LEGEND_PNG):
                im=XLImage(LEGEND_PNG); im.width=130; im.height=30; ws.add_image(im,"E1")
        except Exception:
            pass

        # ---- 데이터 ----
        rr=6; grand=[0]*nb; gtot=0; run_start=rr; run_dong=None; pmerges=[]
        for row in rows:
            donor = T_DATA  # 대표 데이터행 스타일(테두리·폰트·정렬·표시형식)
            for c in range(1,NCOL+1):
                _copy_style(tpl.cell(donor,c), ws.cell(rr,c)); ws.cell(rr,c).fill=NOFILL
            ws.cell(rr,1,row["dong"]); ws.cell(rr,2,row["ic"]); ws.cell(rr,3,row["line"])
            ws.cell(rr,4,row["model"]); ws.cell(rr,5,row["style"])
            ws.cell(rr,6,row["color"] or None); ws.cell(rr,7,row["spray"] or None); ws.cell(rr,8,row["pad"] or None)
            ws.cell(rr,9,row["gen"])
            for j,(_l,_d,_n,k) in enumerate(buckets):
                v=row["cells"][j]; ws.cell(rr,C_J+j, v if v else None); grand[j]+=v
            ws.cell(rr,C_TOT,row["total"])   # 수식 대신 계산값(모든 뷰어에서 숫자 표시)
            ws.cell(rr,C_ISS,row["issue"] or None)
            ws.cell(rr,C_ZBEM,row["scan_bem"] or None); ws.cell(rr,C_ADI,row["scan_di"] or None)
            gtot+=row["total"]
            if row["dong"]!=run_dong:
                if run_dong is not None and rr-1>=run_start: pmerges.append((run_start,rr-1))
                run_dong=row["dong"]; run_start=rr
            rr+=1
        if run_dong is not None and rr-1>=run_start: pmerges.append((run_start,rr-1))
        # 마지막 데이터행은 하단 medium(표 박스 닫힘) 위해 row70 스타일로 덮기
        if rr>6:
            for c in range(1,NCOL+1):
                _copy_style(tpl.cell(T_LASTDATA,c), ws.cell(rr-1,c)); ws.cell(rr-1,c).fill=NOFILL
        # PLANT(동) 세로 병합
        for s,e in pmerges:
            if e>s:
                ws.merge_cells(start_row=s,start_column=1,end_row=e,end_column=1)

        # ---- GRAND TOTAL (템플릿 71행 스타일) ----
        for c in range(1,NCOL+1):
            _copy_style(tpl.cell(T_GTOT,c), ws.cell(rr,c))
        ws.merge_cells(start_row=rr,start_column=1,end_row=rr,end_column=9)
        ws.cell(rr,1,"GRAND TOTAL")
        for j,g in enumerate(grand): ws.cell(rr,C_J+j, g or None)
        ws.cell(rr,C_TOT,gtot)

        ws.sheet_view.showGridLines=False
        ws.freeze_panes=ws.cell(6,C_J)
        # ---- 페이지 설정(원본과 동일: landscape·A4·한 페이지 맞춤) ----
        ws.page_setup.orientation="landscape"; ws.page_setup.paperSize=9
        ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=1
        ws.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
        ws.page_margins.left=ws.page_margins.right=ws.page_margins.top=ws.page_margins.bottom=1.0
        ws.print_area=f"A1:{get_column_letter(NCOL)}{rr}"
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

def _smtp_send(cfg, msg):
    """[smtp] 설정으로 EmailMessage 발송 (공통)."""
    host=cfg.get("smtp","host"); port=cfg.getint("smtp","port",fallback=587)
    user=cfg.get("smtp","user",fallback="").strip(); pw=cfg.get("smtp","password",fallback="").strip()
    use_tls=cfg.getboolean("smtp","use_tls",fallback=True)
    LOG.info(f"SMTP 접속: {host}:{port} tls={use_tls} auth={'Y' if user else 'N'}")
    with smtplib.SMTP(host,port,timeout=60) as s:
        if use_tls: s.starttls(context=ssl.create_default_context())
        if user: s.login(user,pw)
        s.send_message(msg)

def send_test_mail(cfg):
    """DB 없이 SMTP 전송만 검증. 샘플 xlsx가 있으면 첨부."""
    sender=cfg.get("smtp","from")
    recips=[x.strip() for x in cfg.get("report","recipients").split(",") if x.strip()]
    if not recips: sys.exit("[설정오류] [report] recipients 비어 있음")
    now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg=EmailMessage()
    msg["Subject"]=f"[TEST] BALANCE OUTGOING mailer SMTP 점검 {now}"
    msg["From"]=sender; msg["To"]=", ".join(recips)
    msg.set_content(f"SMTP 전송 테스트 메일입니다. (생성시각 {now})\n\n"
                    "이 메일이 도착했다면 메일 전송기 설정이 정상입니다.\n"
                    "— balance_outgoing_mailer.py --test-mail")
    # 같은 폴더에 샘플이 있으면 첨부(첨부 동작까지 확인)
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("SAMPLE_BALANCE_OUTGOING") and fn.endswith(".xlsx"):
            with open(os.path.join(HERE,fn),"rb") as f:
                msg.add_attachment(f.read(),maintype="application",
                    subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",filename=fn)
            LOG.info(f"테스트 첨부: {fn}"); break
    LOG.info(f"테스트 메일 발송 → {recips}")
    _smtp_send(cfg,msg)
    LOG.info("테스트 메일 발송 완료")
    print(f"OK: 테스트 메일을 {', '.join(recips)} 로 보냈습니다. 받은편지함을 확인하세요.")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",default=os.path.join(HERE,"config.ini"))
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--test-db",action="store_true")
    ap.add_argument("--test-mail",action="store_true",help="DB 없이 SMTP 전송만 점검")
    ap.add_argument("--setup",action="store_true",help="비밀번호 1회 입력·저장(이후 무인 실행)")
    a=ap.parse_args(); cfg=load_config(a.config)
    if a.setup:
        ensure_password(cfg,a.config,"smtp","SMTP(메일) password")
        if cfg.get("db","dsn",fallback="").strip():
            ensure_password(cfg,a.config,"db","Oracle DB password")
        print("설정 저장 완료. 이제 'python3 balance_outgoing_mailer.py' 한 줄로 실행됩니다.")
        return
    if a.test_mail:
        ensure_password(cfg,a.config,"smtp","SMTP(메일) password")
        try: send_test_mail(cfg)
        except Exception as e: LOG.error(f"테스트 메일 실패: {e}"); sys.exit(4)
        return
    today=datetime.date.today(); today_str=today.strftime("%Y-%m-%d")
    before=cfg.getint("report","window_before",fallback=3); after=cfg.getint("report","window_after",fallback=7)
    plants=[x.strip() for x in cfg.get("report","plants").split(",") if x.strip()]
    buckets=build_buckets(today,before,after)
    d_from=min(b[1] for b in buckets); d_to=max(b[1] for b in buckets)
    LOG.info(f"=== 시작 {today_str} 창 {d_from}~{d_to} plants={plants} ===")
    ensure_password(cfg,a.config,"db","Oracle DB password")
    if not a.dry_run: ensure_password(cfg,a.config,"smtp","SMTP(메일) password")  # 발송 전 미리 확보
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
