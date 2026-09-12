import sqlite3
c = sqlite3.connect('data/bot.db')
print("Recent snapshots:", c.execute("SELECT COUNT(*) FROM market_snapshots WHERE received_timestamp >= datetime('now', '-1 hour')").fetchone()[0])
