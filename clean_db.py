import sqlite3
c = sqlite3.connect('data/bot.db')
c.execute("UPDATE markets SET active=0 WHERE end_time < datetime('now') AND active=1")
c.commit()
print("Deactivated via SQL")
