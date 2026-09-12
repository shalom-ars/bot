import sqlite3

def migrate():
    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()
    
    # Create PaperTestSession table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id VARCHAR UNIQUE,
            start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time DATETIME,
            status VARCHAR,
            initial_balance FLOAT,
            current_balance FLOAT,
            equity FLOAT,
            resolved_markets INTEGER DEFAULT 0,
            signals INTEGER DEFAULT 0,
            actionable_signals INTEGER DEFAULT 0,
            skipped_signals INTEGER DEFAULT 0,
            paper_trades INTEGER DEFAULT 0,
            closed_trades INTEGER DEFAULT 0,
            open_positions INTEGER DEFAULT 0,
            net_pnl FLOAT DEFAULT 0,
            drawdown FLOAT DEFAULT 0,
            win_rate FLOAT DEFAULT 0,
            profit_factor FLOAT DEFAULT 0,
            expectancy FLOAT DEFAULT 0,
            average_net_edge FLOAT DEFAULT 0
        )
        """)
        print("Created paper_test_sessions table")
    except Exception as e:
        print(f"Error creating paper_test_sessions: {e}")
        
    # Create PaperDailySnapshot table
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id VARCHAR,
            date DATE,
            starting_equity FLOAT,
            ending_equity FLOAT,
            daily_pnl FLOAT,
            daily_return FLOAT,
            trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            drawdown FLOAT,
            exposure FLOAT,
            fees FLOAT,
            slippage FLOAT,
            signals INTEGER,
            skips INTEGER,
            UNIQUE(session_id, date)
        )
        """)
        print("Created paper_daily_snapshots table")
    except Exception as e:
        print(f"Error creating paper_daily_snapshots: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
