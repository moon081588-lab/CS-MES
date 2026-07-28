# No.9 Balance PH before UV (by date)
from core import sql as BS, db
ID = "9"; NAME = "3-1. Balance PH before UV"
SHEET = "PH before UV"; BEFORE = 7; AFTER = 7; TITLE = "BALANCE PHYLON PRESS"; KET = True

def plan(ctx):
    return [("no9.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    args = ["build_bydate.py", ctx.out(ID, NAME), f"{SHEET}={ctx.csv('no9.csv')}",
            "--date", ctx.date, "--before", str(BEFORE), "--after", str(AFTER), "--title", TITLE]
    if KET:
        args.append("--ket")
    db.run_builder(*args)
