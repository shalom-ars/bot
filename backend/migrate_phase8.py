import sqlite3

def migrate():
    conn = sqlite3.connect('../data/bot.db')
    cursor = conn.cursor()
    
    # Create SaaS Tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR UNIQUE,
            hashed_password VARCHAR,
            role VARCHAR DEFAULT 'USER',
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            plan VARCHAR DEFAULT 'FREE',
            status VARCHAR DEFAULT 'ACTIVE',
            provider_subscription_id VARCHAR,
            current_period_end DATETIME,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            initial_balance FLOAT DEFAULT 500.0,
            current_balance FLOAT DEFAULT 500.0,
            equity FLOAT DEFAULT 500.0,
            exposure FLOAT DEFAULT 0.0,
            realized_pnl FLOAT DEFAULT 0.0,
            unrealized_pnl FLOAT DEFAULT 0.0,
            drawdown FLOAT DEFAULT 0.0,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            market_id VARCHAR,
            condition_id VARCHAR,
            token_id VARCHAR,
            side VARCHAR,
            entry_price FLOAT,
            exit_price FLOAT,
            quantity FLOAT,
            pnl FLOAT,
            status VARCHAR,
            entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            exit_time DATETIME,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            market_id VARCHAR,
            condition_id VARCHAR,
            token_id VARCHAR,
            side VARCHAR,
            entry_price FLOAT,
            quantity FLOAT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            max_position_risk FLOAT DEFAULT 0.02,
            max_drawdown FLOAT DEFAULT 0.15,
            notifications_enabled BOOLEAN DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            endpoint VARCHAR,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    ]
    
    for query in tables:
        try:
            cursor.execute(query)
            print("Successfully executed SaaS table creation.")
        except Exception as e:
            print(f"Error creating SaaS tables: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
