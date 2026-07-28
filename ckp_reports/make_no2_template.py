#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""No.2 클린 템플릿 생성 (일회성 / 종합 양식 개정 시 재생성용).

종합(마스터)에서 '3-1. Balance IP Production' 시트만 남기고, 상속 쓰레기
 - 외부링크 8개(옛 Nike 네트워크/SharePoint 참조)
 - 정의된 이름 255개(IF(#REF!)·[N]Tables!#REF! 등)
를 제거해 깨끗한 no2_template.xlsx 를 만든다. → Excel '복구/손상' 경고 방지.
조건부서식은 양식 유지를 위해 보존(손상 원인 아님).

★ 종합의 No.2 양식이 바뀌면 이 스크립트를 다시 돌려 템플릿을 갱신할 것:
    python make_no2_template.py
사용: python make_no2_template.py [종합.xlsx] [out=no2_template.xlsx]
"""
import sys, os
import openpyxl

SHEET = "3-1. Balance IP Production"
HERE = os.path.dirname(os.path.abspath(__file__))

def find_src():
    for c in [os.path.join(HERE, "..", "CKP Manual Report (종합).xlsx"),
              os.path.join(HERE, "..", "report", "CKP Manual Report (종합).xlsx")]:
        if os.path.exists(c):
            return c
    return ""

def make(src, out):
    wb = openpyxl.load_workbook(src)
    for s in list(wb.sheetnames):
        if s != SHEET:
            wb.remove(wb[s])
    wb._external_links = []      # 외부링크 제거
    wb.defined_names.clear()     # 정의된 이름(쓰레기) 제거
    wb.save(out)
    print(f"clean template saved: {out}  (from {os.path.basename(src)})")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else find_src()
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "no2_template.xlsx")
    if not src:
        sys.exit("종합.xlsx 를 찾을 수 없습니다. 경로를 인자로 주세요.")
    make(src, out)
