import sqlite3
import os
import json

db_path = os.path.join("data", "bot.db")
if not os.path.exists(db_path):
    print(json.dumps({"error": f"DB not found at {db_path}"}))
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def get_count(table):
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    except Exception as e:
        return f"Error: {e}"

counts = {
    "snapshots": get_count("market_snapshots"),
    "signals": get_count("signals"),
    "positions": get_count("positions"),
    "trades": get_count("trades"),
    "paper_sessions": get_count("paper_test_sessions")
}

print(json.dumps(counts, indent=2))
conn.close()
