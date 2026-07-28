#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CKP Manual Report — 11개 리포트를 메일 첨부(ZIP)로 발송
========================================================
report/CKP_official/*.xlsx 를 ZIP으로 묶어 [smtp] 설정으로 발송한다(첨부).
사용:  python mail_reports.py [YYYY-MM-DD]
전제:  balance_outgoing_mailer/config.ini 의 [smtp](Gmail 앱비번)·[report] recipients 설정.
       사내망/현지 PC 에서 실행 — SMTP 접속이 되는 곳이어야 한다.
"""
import os, sys, ssl, smtplib, zipfile, glob, configparser, datetime
from email.message import EmailMessage

# Windows 에서 stdout 이 파일/파이프면 ANSI 코드페이지로 인코딩되어 한글·기호 출력이
# UnicodeEncodeError 로 죽는다. 진입점에서 한 번 UTF-8 로 고정한다.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "balance_outgoing_mailer", "config.ini")
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))

def _today_iso():
    """현장 기준 오늘 (정의는 balance_outgoing_mailer.site_today() 한 곳)."""
    try:
        sys.path.insert(0, os.path.join(HERE, "..", "balance_outgoing_mailer"))
        import balance_outgoing_mailer as _BO
        return _BO.site_today().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else _today_iso()
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    cp.read(CFG, encoding="utf-8")
    files = sorted(glob.glob(os.path.join(OUTDIR, "*.xlsx")),
                   key=lambda p: int(os.path.basename(p).split(")")[0]) if os.path.basename(p).split(")")[0].isdigit() else 99)
    if not files:
        sys.exit(f"리포트가 없습니다: {OUTDIR}")
    zpath = os.path.join(OUTDIR, f"CKP_Manual_Report_{date}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files: z.write(f, os.path.basename(f))

    host = cp.get("smtp", "host"); port = cp.getint("smtp", "port", fallback=587)
    user = cp.get("smtp", "user", fallback="").strip(); pw = cp.get("smtp", "password", fallback="").strip()
    use_tls = cp.getboolean("smtp", "use_tls", fallback=True); sender = cp.get("smtp", "from")
    recips = [x.strip() for x in cp.get("report", "recipients").split(",") if x.strip()]

    msg = EmailMessage()
    msg["Subject"] = f"[CKP Manual Report] 공식 11개 리포트 (첨부) {date}"
    msg["From"] = sender; msg["To"] = ", ".join(recips)
    lines = "\n".join(os.path.basename(f).replace(".xlsx", "") for f in files)
    msg.set_content(f"안녕하십니까.\n\nCKP Manual Report 공식 11개 리포트를 첨부(ZIP)로 보내드립니다. ({date} 기준, 라이브 DB)\n\n[포함 리포트]\n{lines}\n\n자동 발송 메일입니다.")
    with open(zpath, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="zip", filename=os.path.basename(zpath))

    print(f"발송: {host}:{port} → {recips} (첨부 {os.path.basename(zpath)}, {len(files)}개)")
    with smtplib.SMTP(host, port, timeout=60) as s:
        if use_tls: s.starttls(context=ssl.create_default_context())
        if user: s.login(user, pw)
        s.send_message(msg)
    print("발송 완료.")

if __name__ == "__main__":
    main()
