import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('../data/bot.db')
    
    print('==================================================')
    print('PHASE 2 - FORENSIC DATA VERIFICATION REPORT')
    print('==================================================')

    total_mkts = pd.read_sql_query('SELECT COUNT(*) as c FROM markets WHERE condition_id IS NOT NULL', conn).iloc[0]['c']
    unique_conds = pd.read_sql_query('SELECT COUNT(DISTINCT condition_id) as c FROM markets WHERE condition_id IS NOT NULL', conn).iloc[0]['c']
    unique_tokens = pd.read_sql_query('SELECT COUNT(DISTINCT token_id) as c FROM markets WHERE condition_id IS NOT NULL', conn).iloc[0]['c']
    yes_tokens = pd.read_sql_query('SELECT COUNT(*) as c FROM markets WHERE condition_id IS NOT NULL AND token=\"Yes\"', conn).iloc[0]['c']
    no_tokens = pd.read_sql_query('SELECT COUNT(*) as c FROM markets WHERE condition_id IS NOT NULL AND token=\"No\"', conn).iloc[0]['c']
    
    print(f"Total Markets Discovered (Records): {total_mkts}")
    print(f"Unique Market IDs (Condition IDs): {unique_conds}")
    print(f"Unique Token IDs (Instruments): {unique_tokens}")
    print(f"YES Tokens: {yes_tokens}")
    print(f"NO Tokens: {no_tokens}")
    
    # Orderbook metrics
    # A market has a valid orderbook if we have a snapshot where bid_depth > 0 or ask_depth > 0
    valid_ob = pd.read_sql_query("SELECT COUNT(DISTINCT market_id) as c FROM market_snapshots WHERE (bid_depth > 0 OR ask_depth > 0)", conn).iloc[0]['c']
    no_ob = pd.read_sql_query("SELECT COUNT(DISTINCT market_id) as c FROM market_snapshots WHERE bid_depth = 0 AND ask_depth = 0", conn).iloc[0]['c']
    
    print(f"Tokens with Valid Orderbooks: {valid_ob}")
    print(f"Tokens without Orderbooks: {no_ob}")
    
    valid_snaps = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE ineligibility_reason NOT LIKE '%EMPTY_BOOK%'", conn).iloc[0]['c']
    invalid_snaps = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE ineligibility_reason LIKE '%EMPTY_BOOK%'", conn).iloc[0]['c']
    eligible_snaps = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE trade_eligible = 1", conn).iloc[0]['c']
    skipped_snaps = pd.read_sql_query("SELECT COUNT(*) as c FROM market_snapshots WHERE trade_eligible = 0 AND ineligibility_reason NOT LIKE '%EMPTY_BOOK%'", conn).iloc[0]['c']

    print(f"Valid Snapshots (Research Quality): {valid_snaps}")
    print(f"Invalid Snapshots (Empty/Malformed): {invalid_snaps}")
    print(f"Trade-Eligible Snapshots: {eligible_snaps}")
    print(f"Skipped Snapshots (Valid but Trade-Ineligible): {skipped_snaps}")
    
    print('\n==================================================')
    print('10 REAL MARKET EXAMPLES')
    print('==================================================')
    
    examples = pd.read_sql_query('''
        SELECT 
            m.condition_id as market_id,
            m.question,
            s.symbol as token_id,
            m.token as outcome,
            s.bid,
            s.ask,
            s.price as mid,
            s.spread,
            s.event_timestamp as timestamp,
            s.trade_eligible,
            s.ineligibility_reason as reason
        FROM market_snapshots s
        JOIN markets m ON s.symbol = m.token_id
        WHERE m.condition_id IS NOT NULL 
        AND s.bid > 0
        GROUP BY m.condition_id
        LIMIT 10
    ''', conn)
    
    for _, row in examples.iterrows():
        print(f"Market ID: {row['market_id']}")
        print(f"Question:  {row['question']}")
        print(f"Token ID:  {row['token_id']} ({row['outcome']})")
        print(f"Prices:    Bid {row['bid']} | Ask {row['ask']} | Mid {row['mid']} | Spread {row['spread']}")
        print(f"Status:    Eligible={row['trade_eligible']} | Reason: {row['reason']}")
        print(f"Time:      {row['timestamp']}")
        print("-" * 50)
        
    conn.close()
except Exception as e:
    print('Error:', e)
