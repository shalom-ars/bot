import sqlite3
import os
import json
from datetime import datetime, timedelta

db_path = os.path.join("data", "bot.db")
if not os.path.exists(db_path):
    print(json.dumps({"error": f"DB not found at {db_path}"}))
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def fetch_one(query, params=()):
    try:
        cursor.execute(query, params)
        res = cursor.fetchone()
        return res[0] if res else None
    except Exception as e:
        return f"Error: {e}"

def fetch_all(query, params=()):
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    except Exception as e:
        return []

now = datetime.utcnow()
m1 = (now - timedelta(minutes=1)).isoformat()
m5 = (now - timedelta(minutes=5)).isoformat()
m15 = (now - timedelta(minutes=15)).isoformat()

stats = {
    "snapshots_total": fetch_one("SELECT COUNT(*) FROM market_snapshots"),
    "snapshots_1m": fetch_one("SELECT COUNT(*) FROM market_snapshots WHERE timestamp >= ?", (m1,)),
    "snapshots_5m": fetch_one("SELECT COUNT(*) FROM market_snapshots WHERE timestamp >= ?", (m5,)),
    "snapshots_15m": fetch_one("SELECT COUNT(*) FROM market_snapshots WHERE timestamp >= ?", (m15,)),
    "unique_markets": fetch_one("SELECT COUNT(DISTINCT market_id) FROM market_snapshots"),
    "unique_conditions": fetch_one("SELECT COUNT(DISTINCT condition_id) FROM market_snapshots"),
    "unique_tokens": fetch_one("SELECT COUNT(DISTINCT token_id) FROM market_snapshots"),
    
    "signals_total": fetch_one("SELECT COUNT(*) FROM signals"),
    "signals_buy_yes": fetch_one("SELECT COUNT(*) FROM signals WHERE signal_type = 'BUY' AND side = 'YES'"),
    "signals_buy_no": fetch_one("SELECT COUNT(*) FROM signals WHERE signal_type = 'BUY' AND side = 'NO'"),
    "signals_sell_yes": fetch_one("SELECT COUNT(*) FROM signals WHERE signal_type = 'SELL' AND side = 'YES'"),
    "signals_sell_no": fetch_one("SELECT COUNT(*) FROM signals WHERE signal_type = 'SELL' AND side = 'NO'"),
    "signals_skip": fetch_one("SELECT COUNT(*) FROM signals WHERE signal_type = 'SKIP'"),
    
    "skip_reasons": dict(fetch_all("SELECT reason, COUNT(*) FROM signals WHERE signal_type = 'SKIP' GROUP BY reason")),
    
    "paper_trades": fetch_one("SELECT COUNT(*) FROM trades"),
    "open_positions": fetch_one("SELECT COUNT(*) FROM positions WHERE quantity > 0"),
    "closed_positions": fetch_one("SELECT COUNT(*) FROM positions WHERE quantity = 0"),
    "realized_pnl": fetch_one("SELECT SUM(pnl) FROM trades WHERE pnl IS NOT NULL") or 0.0,
    
    "user_portfolios": fetch_one("SELECT COUNT(*) FROM user_portfolios"),
    "user_trades": fetch_one("SELECT COUNT(*) FROM user_trades"),
    "user_positions": fetch_one("SELECT COUNT(*) FROM user_positions"),
    
    "resolved_markets": fetch_one("SELECT COUNT(*) FROM markets WHERE resolved = 1"),
    "unresolved_markets": fetch_one("SELECT COUNT(*) FROM markets WHERE resolved = 0")
}

print(json.dumps(stats, indent=2))
conn.close()
