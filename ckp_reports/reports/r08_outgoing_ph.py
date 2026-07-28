# No.8 Balance Outgoing PH (by date)
from core import sql as BS, db
ID = "8"; NAME = "3-1. Balance Outgoing PH"
SHEET = "Outgoing PH"; BEFORE = 10; AFTER = 7; TITLE = "BALANCE OUTGOING PH"; KET = True

def plan(ctx):
    return [("no8.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    args = ["build_bydate.py", ctx.out(ID, NAME), f"{SHEET}={ctx.csv('no8.csv')}",
            "--date", ctx.date, "--before", str(BEFORE), "--after", str(AFTER), "--title", TITLE]
    if KET:
        args.append("--ket")
    db.run_builder(*args)
