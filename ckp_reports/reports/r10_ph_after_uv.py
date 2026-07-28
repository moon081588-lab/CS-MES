# No.10 Balance PH after UV (by date)
from core import sql as BS, db
ID = "10"; NAME = "3-1. Balance PH after UV"
SHEET = "PH after UV"; BEFORE = 10; AFTER = 7; TITLE = "BALANCE IN MARKET"; KET = True

def plan(ctx):
    return [("no10.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    args = ["build_bydate.py", ctx.out(ID, NAME), f"{SHEET}={ctx.csv('no10.csv')}",
            "--date", ctx.date, "--before", str(BEFORE), "--after", str(AFTER), "--title", TITLE]
    if KET:
        args.append("--ket")
    db.run_builder(*args)
