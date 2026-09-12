import sqlite3
import json

c = sqlite3.connect('data/bot.db')
c.row_factory = sqlite3.Row

# Get 10 distinct active markets that have recent snapshots
markets = c.execute('''
    SELECT m.market_id, m.condition_id, m.question, 
           s.bid, s.ask, s.spread, s.token_id, s.received_timestamp
    FROM markets m 
    JOIN (
        SELECT market_id, bid, ask, spread, token_id, received_timestamp
        FROM market_snapshots
        WHERE received_timestamp > datetime('now', '-30 minutes')
    ) s ON m.market_id = s.market_id 
    WHERE m.active = 1 
    GROUP BY m.market_id
    ORDER BY s.received_timestamp DESC 
    LIMIT 10
''').fetchall()

for m in markets:
    print(f"MarketID: {m['market_id']}")
    print(f"ConditionID: {m['condition_id']}")
    print(f"Question: {m['question']}")
    print(f"DB_TokenID: {m['token_id']}")
    print(f"DB Bid: {m['bid']}, DB Ask: {m['ask']}, DB Spread: {m['spread']}")
    print("---")
