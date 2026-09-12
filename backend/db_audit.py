import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('../data/bot.db')
    print('--- TABLES ---')
    print(pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn))
    
    print('\n--- MARKETS COUNT ---')
    print(pd.read_sql_query('SELECT COUNT(*) as total_markets, COUNT(DISTINCT market_id) as unique_market_ids, COUNT(DISTINCT token_id) as unique_tokens FROM markets;', conn))
    
    print('\n--- SNAPSHOTS COUNT ---')
    print(pd.read_sql_query('SELECT COUNT(*) as total_snapshots, COUNT(DISTINCT market_id) as unique_market_ids, COUNT(DISTINCT token_id) as unique_tokens, SUM(CASE WHEN trade_eligible=1 THEN 1 ELSE 0 END) as trade_eligible_snapshots, SUM(CASE WHEN price=0 THEN 1 ELSE 0 END) as zero_prices FROM market_snapshots;', conn))
    
    print('\n--- SNAPSHOTS PREVIEW (Top 5) ---')
    print(pd.read_sql_query('SELECT source, symbol, market_id, token_id, price, bid, ask, spread, trade_eligible, ineligibility_reason FROM market_snapshots LIMIT 5;', conn))

    print('\n--- SIGNALS COUNT ---')
    print(pd.read_sql_query('SELECT COUNT(*) FROM signals;', conn))
    
    print('\n--- DATA COLLECTION STATS ---')
    print(pd.read_sql_query('SELECT * FROM data_collection_stats LIMIT 5;', conn))

    conn.close()
except Exception as e:
    print('Error:', e)
