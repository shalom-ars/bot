import sqlite3
c = sqlite3.connect('data/bot.db')
c.row_factory = sqlite3.Row
snaps = c.execute("SELECT symbol, bid, ask, spread, liquidity, ineligibility_reason FROM market_snapshots WHERE received_timestamp > datetime('now', '-10 minutes') ORDER BY liquidity DESC LIMIT 5").fetchall()
for s in snaps:
    print(dict(s))
