# No.11 PH in Market by size (ph 모드)
from core import sql as BS, db
ID = "11"; NAME = "3-2. Balance PH in Market PH by"; SHEET = "PH in Market by size"

def plan(ctx):
    return [("no11.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    db.run_builder("build_bysize.py", "ph", ctx.out(ID, NAME), SHEET, ctx.csv("no11.csv"), "BALANCE IN MARKET")
