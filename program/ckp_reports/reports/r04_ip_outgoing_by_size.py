# No.4 IP Outgoing by size
from core import sql as BS, db
ID = "4"; NAME = "3-2. Balance IP Outgoing by size"; SHEET = "IP Outgoing by size"

def plan(ctx):
    return [("no4.csv", BS.build(ID, ctx.d_from, ctx.d_to)[1])]

def build(ctx):
    db.run_builder("build_bysize.py", "ip", ctx.out(ID, NAME), SHEET, ctx.csv("no4.csv"))
