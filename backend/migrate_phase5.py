import sqlite3

def migrate():
    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()
    
    # Create BacktestRun table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id VARCHAR UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            dataset_version VARCHAR,
            model_version VARCHAR,
            strategy_version VARCHAR,
            train_start DATETIME,
            train_end DATETIME,
            validation_start DATETIME,
            validation_end DATETIME,
            test_start DATETIME,
            test_end DATETIME,
            resolved_markets INTEGER,
            valid_samples INTEGER,
            trades INTEGER,
            win_rate FLOAT,
            brier_score FLOAT,
            net_pnl FLOAT,
            max_drawdown FLOAT,
            profit_factor FLOAT,
            status VARCHAR
        )
        """)
        print("Created backtest_runs table")
    except Exception as e:
        print(f"Error creating backtest_runs: {e}")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
