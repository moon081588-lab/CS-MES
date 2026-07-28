# No.3 IP Prod by size
from core import sql as BS, db
ID = "3"; NAME = "3-2. Balance IP Prod. by size"; SHEET = "IP Prod by size"

def plan(ctx):
    return [("no3.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    db.run_builder("build_bysize.py", "ip", ctx.out(ID, NAME), SHEET, ctx.csv("no3.csv"))
