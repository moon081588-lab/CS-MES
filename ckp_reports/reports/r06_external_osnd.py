# No.6 External OS&D Balance by size
from core import sql as BS, db
ID = "6"; NAME = "3-4. Balance External OS&D IPPH"

def plan(ctx):
    return [("no6.csv", BS.osnd_balance_sql(ctx.osnd_from, ctx.osnd_to))]

def build(ctx):
    db.run_builder("build_osnd.py", ctx.out(ID, NAME), "External OS&D", ctx.csv("no6.csv"))
