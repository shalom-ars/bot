import sqlite3
c = sqlite3.connect('data/bot.db')
c.row_factory = sqlite3.Row
market = c.execute("SELECT question, end_time, active FROM markets WHERE market_id='9195312844128905514645503106857912558078141569888031031723687687489317147622'").fetchone()
print(dict(market))
