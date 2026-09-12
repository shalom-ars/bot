import sqlite3

def migrate():
    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()
    
    # 1. Add fields to positions
    pos_columns = {
        'condition_id': 'VARCHAR',
        'token_id': 'VARCHAR',
        'strategy': 'VARCHAR',
        'timestamp': 'DATETIME'
    }
    for col, dtype in pos_columns.items():
        try:
            cursor.execute(f"ALTER TABLE positions ADD COLUMN {col} {dtype}")
            print(f"Added column {col} to positions")
        except sqlite3.OperationalError as e:
            pass

    # 2. Add fields to trades
    trade_columns = {
        'condition_id': 'VARCHAR',
        'token_id': 'VARCHAR',
        'strategy': 'VARCHAR',
        'requested_size': 'FLOAT',
        'approved_size': 'FLOAT',
        'entry_timestamp': 'DATETIME',
        'exit_timestamp': 'DATETIME'
    }
    for col, dtype in trade_columns.items():
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {dtype}")
            print(f"Added column {col} to trades")
        except sqlite3.OperationalError as e:
            pass
            
    # 3. Create RiskDecisionLog table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            signal_id VARCHAR,
            market_id VARCHAR,
            condition_id VARCHAR,
            decision VARCHAR,
            requested_size FLOAT,
            approved_size FLOAT,
            current_exposure FLOAT,
            new_exposure FLOAT,
            daily_pnl FLOAT,
            drawdown FLOAT,
            consecutive_losses INTEGER,
            reason VARCHAR
        )
        """)
        print("Created risk_decisions table")
    except Exception as e:
        print(f"Error creating risk_decisions: {e}")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
