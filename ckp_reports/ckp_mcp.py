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
"""
import os, sys, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "report", "CKP_official"))

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("ckp-reports")

def _run(script, date):
    args = [sys.executable, os.path.join(HERE, script)]
    if date: args.append(date)
    p = subprocess.run(args, capture_output=True, text=True, cwd=HERE)
    out = p.stdout or ""
    if p.returncode != 0:
        out += "\n[오류]\n" + (p.stderr or "")[-1500:]
    return out.strip()

@mcp.tool()
def ckp_make_all(date: str = "") -> str:
    """CKP Manual Report 공식 11개 리포트를 생성한다.
    date: 'YYYY-MM-DD' (생략 시 오늘). 저장된 SQLcl 연결로 DB 조회 → report/CKP_official/ 에 'NO) 리포트명.xlsx' 11개 생성.
    양식(사이즈·날짜 D-offset 컬럼)은 원본 고정 구조라 데이터가 0행이어도 열이 유지된다."""
    d = date or datetime.date.today().isoformat()
    res = _run("make_all.py", d)
    return f"[CKP 11개 생성] {d}\n{res}\n\n저장 위치: {OUTDIR}"

@mcp.tool()
def ckp_mail(date: str = "") -> str:
    """생성된 11개 리포트를 ZIP으로 묶어 메일 첨부 발송한다(config.ini [smtp]/[report] 수신자).
    ckp_make_all 로 먼저 생성한 뒤 호출."""
    d = date or datetime.date.today().isoformat()
    return f"[CKP 메일 발송] {d}\n{_run('mail_reports.py', d)}"

@mcp.tool()
def ckp_make_and_mail(date: str = "") -> str:
    """CKP 11개 생성 후 곧바로 메일 첨부 발송까지 한 번에."""
    d = date or datetime.date.today().isoformat()
    gen = _run("make_all.py", d)
    mail = _run("mail_reports.py", d)
    return f"[CKP 생성+발송] {d}\n\n== 생성 ==\n{gen}\n\n== 발송 ==\n{mail}"

if __name__ == "__main__":
    mcp.run()
