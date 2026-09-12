import sqlite3
c = sqlite3.connect('data/bot.db')
c.row_factory = sqlite3.Row
res = c.execute("SELECT symbol, spread FROM market_snapshots WHERE received_timestamp > datetime('now', '-10 minutes') ORDER BY spread ASC LIMIT 5").fetchall()
for r in res: print(dict(r))
