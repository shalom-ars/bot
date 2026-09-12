import sqlite3
c = sqlite3.connect('data/bot.db')
c.row_factory = sqlite3.Row
eligible = c.execute('SELECT COUNT(*) FROM market_snapshots WHERE trade_eligible=1').fetchone()[0]
total = c.execute('SELECT COUNT(*) FROM market_snapshots').fetchone()[0]
print(f'Total snapshots: {total}, Eligible: {eligible}')
recent_reasons = c.execute('SELECT ineligibility_reason, COUNT(*) as c FROM market_snapshots WHERE trade_eligible=0 GROUP BY ineligibility_reason ORDER BY c DESC LIMIT 5').fetchall()
print('Rejection reasons (all time):')
for r in recent_reasons:
    print(f"- {r['ineligibility_reason']}: {r['c']}")
    
recent_eligible = c.execute("SELECT COUNT(*) FROM market_snapshots WHERE trade_eligible=1 AND received_timestamp > datetime('now', '-10 minutes')").fetchone()[0]
print(f"Eligible in last 10 minutes: {recent_eligible}")

signals = c.execute("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now', '-10 minutes')").fetchone()[0]
print(f"Signals in last 10 minutes: {signals}")

trades = c.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
print(f"Total paper trades: {trades}")
