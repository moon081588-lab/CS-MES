# No.7 Balance CMP (by date)
from core import sql as BS, db
ID = "7"; NAME = "3-1. Balance CMP"
SHEET = "CMP"; BEFORE = 6; AFTER = 7; TITLE = "BALANCE CMP"; KET = False

def plan(ctx):
    return [("no7.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    args = ["build_bydate.py", ctx.out(ID, NAME), f"{SHEET}={ctx.csv('no7.csv')}",
            "--date", ctx.date, "--before", str(BEFORE), "--after", str(AFTER), "--title", TITLE]
    if KET:
        args.append("--ket")
    db.run_builder(*args)
