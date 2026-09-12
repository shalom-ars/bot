import sqlite3

def migrate():
    conn = sqlite3.connect('data/bot.db')
    cursor = conn.cursor()
    
    new_columns = {
        'strategy': 'VARCHAR',
        'fair_probability': 'FLOAT',
        'calibrated_probability': 'FLOAT',
        'entry_price': 'FLOAT',
        'spread_cost': 'FLOAT',
        'slippage_cost': 'FLOAT',
        'liquidity_cost': 'FLOAT',
        'fees': 'FLOAT',
        'net_edge': 'FLOAT',
        'threshold': 'FLOAT',
        'uncertainty': 'FLOAT',
        'correlation_status': 'VARCHAR',
        'market_quality_status': 'VARCHAR',
        'model_version': 'VARCHAR'
    }
    
    for col, dtype in new_columns.items():
        try:
            cursor.execute(f"ALTER TABLE signals ADD COLUMN {col} {dtype}")
            print(f"Added column {col}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"Column {col} already exists")
            else:
                print(f"Error adding {col}: {e}")
                
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
